"""
Manager Actions - Ban, Unban, Mute, Unmute, Kick, etc.
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions, ChatMemberAdministrator, ChatMemberOwner, ChatMemberBanned, ChatMemberRestricted, ReplyParameters, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ChatMemberStatus, ParseMode
from managers.settings_manager_mongo import get_chat_settings
from moderation.anonymous_admin import (
    is_anonymous_admin, 
    check_anonymous_admin_ban_permission, 
    check_anonymous_admin_mute_permission,
    check_anonymous_admin_promote_permission,
    check_anonymous_admin_pin_permission,
    check_anonymous_admin_delete_permission,
    check_anonymous_admin_invite_permission,
    check_anonymous_admin_change_info_permission
)
from core.config import OWNER_ID
from managers.admin_manager_mongo import update_admin_cache, get_stored_admin_permissions

def parse_time(time_str):
    """Parse time string like '1h', '30m', '2d' into timedelta."""
    time_str = time_str.lower()
    if time_str.endswith('d'):
        return timedelta(days=int(time_str[:-1]))
    elif time_str.endswith('h'):
        return timedelta(hours=int(time_str[:-1]))
    elif time_str.endswith('m'):
        return timedelta(minutes=int(time_str[:-1]))
    elif time_str.endswith('s'):
        return timedelta(seconds=int(time_str[:-1]))
    return None

from managers.user_manager_mongo import get_user_id
from features.voice_chat import remove_user_from_vc
from core.database import get_collection, COLLECTIONS
from managers.staff_manager_mongo import increment_staff_stat
import uuid

async def is_admin(chat, user_id):
    """Check if user is admin."""
    try:
        member = await chat.get_member(user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except:
        return False

async def check_admin_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, permission: str = None):
    """
    Check if a user has administrative permissions.
    
    Args:
        update: The Telegram update
        context: The bot context
        permission: The permission key to check (e.g., 'can_restrict_members')
        
    Returns:
        tuple: (has_permission, error_message)
    """
    user = update.effective_user
    chat = update.effective_chat
    
    if not user or not chat:
        return False, "Error identifying user or chat."

    # Owner always has permission
    if user.id == OWNER_ID:
        return True, None

    # Check if it's an anonymous admin
    if is_anonymous_admin(user.id):
        if not permission:
            return True, None
        
        anon_checks = {
            'can_restrict_members': check_anonymous_admin_mute_permission,
            'can_ban_users': check_anonymous_admin_ban_permission,
            'can_promote_members': check_anonymous_admin_promote_permission,
            'can_pin_messages': check_anonymous_admin_pin_permission,
            'can_delete_messages': check_anonymous_admin_delete_permission,
            'can_invite_users': check_anonymous_admin_invite_permission,
            'can_change_info': check_anonymous_admin_change_info_permission,
        }
        
        if permission in anon_checks:
            return await anon_checks[permission](chat.id, context)
        return False, f"❌ Unsupported permission check: {permission}"
    
    # 1. Check database first for bot-only permissions
    if permission in ['can_restrict_members', 'can_ban_users']:
        stored_perms = get_stored_admin_permissions(chat.id, user.id)
        if stored_perms and stored_perms.get(permission):
            return True, None

    # 2. Try Telegram API for native permissions
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        status = member.status
        
        # Build permissions dict to update cache
        permissions = {
            "can_change_info": getattr(member, "can_change_info", False),
            "can_delete_messages": getattr(member, "can_delete_messages", False),
            "can_restrict_members": getattr(member, "can_restrict_members", False),
            "can_invite_users": getattr(member, "can_invite_users", False),
            "can_pin_messages": getattr(member, "can_pin_messages", False),
            "can_promote_members": getattr(member, "can_promote_members", False),
            "can_manage_chat": getattr(member, "can_manage_chat", False),
            "can_manage_video_chats": getattr(member, "can_manage_video_chats", False),
            "is_anonymous": getattr(member, "is_anonymous", False),
        }
        
        # Update cache in background
        asyncio.create_task(asyncio.to_thread(update_admin_cache, chat.id, user.id, permissions))

        if status == ChatMemberStatus.OWNER:
            return True, None
            
        if status != ChatMemberStatus.ADMINISTRATOR:
            # If they have a bot-only permission (already checked above), we would have returned True.
            # If they reach here and are not a Telegram admin, they are denied.
            return False, "❌ You need to be an administrator to use this command."
        
        if not permission:
            return True, None
        
        # Check specific right
        if permission in ['can_restrict_members', 'can_ban_users']:
            # Fallback: if they have Telegram restriction right, allow it
            if getattr(member, 'can_restrict_members', False):
                return True, None
            
            perm_name = "Ban Users" if permission == 'can_ban_users' else "Mute Users"
            return False, f"❌ You don't have the '{perm_name}' permission."

        has_right = getattr(member, permission, False)
        if has_right is True:
            return True, None
            
        perm_names = {
            'can_restrict_members': "Mute Users",
            'can_ban_users': "Ban Users",
            'can_promote_members': "Add New Admins",
            'can_pin_messages': "Pin Messages",
            'can_delete_messages': "Delete Messages",
            'can_invite_users': "Invite Users",
            'can_change_info': "Change Group Info",
        }
        perm_name = perm_names.get(permission, permission)
        return False, f"❌ You don't have the '{perm_name}' permission."

    except Exception as e:
        logging.warning(f"Telegram API check failed for admin {user.id}, falling back to DB: {e}")
        # Fallback to DB if API is down
        stored_perms = get_stored_admin_permissions(chat.id, user.id)
        if stored_perms:
            if not permission:
                return True, None
            if stored_perms.get(permission, False):
                return True, None
            
            perm_names = {
                'can_restrict_members': "Ban Users",
                'can_promote_members': "Add New Admins",
                'can_pin_messages': "Pin Messages",
                'can_delete_messages': "Delete Messages",
                'can_invite_users': "Invite Users",
                'can_change_info': "Change Group Info",
            }
            perm_name = perm_names.get(permission, permission)
            return False, f"❌ You don't have the '{perm_name}' permission."
            
        return False, "❌ Access denied. (Could not verify permissions)"

async def check_bot_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, permission: str):
    """
    Check if the bot itself has the required administrative permission.
    
    Args:
        update: The Telegram update
        context: The bot context
        permission: The permission key to check
        
    Returns:
        tuple: (has_permission, error_message)
    """
    chat = update.effective_chat
    try:
        bot_member = await chat.get_member(context.bot.id)
        if bot_member.status == 'creator':
            return True, None
            
        if bot_member.status != 'administrator':
            return False, "❌ I need to be an administrator to perform this action."
            
        if getattr(bot_member, permission, False):
            return True, None
            
        perm_names = {
            'can_restrict_members': "Ban Users",
            'can_promote_members': "Add New Admins",
            'can_pin_messages': "Pin Messages",
            'can_delete_messages': "Delete Messages",
            'can_invite_users': "Invite Users",
            'can_change_info': "Change Group Info",
        }
        perm_name = perm_names.get(permission, permission)
        return False, f"❌ I don't have the '{perm_name}' permission."
    except Exception as e:
        logging.error(f"Error checking bot permission: {e}")
        return False, "Error checking bot permissions."

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user from the group."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_ban_enabled", True):
        return await update.message.reply_text("❌ The /ban command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    
    # Extract reason
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else None
    else:
        # First arg was user ID/username, rest is reason
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    if not user_id:
        return await update.message.reply_text("Usage: /ban @username [reason] or reply to a user with /ban [reason]")
    
    try:
        try:
            member = await chat.get_member(user_id)
            if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
                return await update.message.reply_text("I cannot ban an admin or the group owner.")
            if isinstance(member, ChatMemberBanned):
                return await update.message.reply_text("User is already banned.")
        except BadRequest as e:
            if "user not found" not in str(e).lower():
                raise
            # User not in group — still allow ban by ID/username
        
        await chat.ban_member(user_id)
        
        admin_name = user.full_name
        text = f"» Ban a user in {chat.title}\n"
        text += f" User  : {name} (ID: <code>{user_id}</code>)\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        
        # Record stats
        increment_staff_stat(chat.id, user.id, "ban")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban user: {str(e)}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user from the group."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_unban_enabled", True):
        return await update.message.reply_text("❌ The /unban command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    
    # Extract reason
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else None
    else:
        # First arg was user ID/username, rest is reason
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    if not user_id:
        return await update.message.reply_text("Usage: /unban @username [reason] or reply to a user with /unban [reason]")
    
    try:
        if str(user_id).startswith('-100'):
            await context.bot.unban_chat_sender_chat(chat.id, user_id)
        else:
            await context.bot.unban_chat_member(chat.id, user_id, only_if_banned=False)
        
        admin_name = user.full_name
        text = f"» Unbanned user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
        
        # Record stats
        increment_staff_stat(chat.id, user.id, "unban")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban user: {str(e)}")

async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message, media, or sticker through the bot."""
    chat = update.effective_chat
    if not chat or chat.type == 'private':
        return

    # Permission check: Admin who has permission to ban (can_restrict_members)
    has_perm, error_msg = await check_admin_permission(update, context, 'can_restrict_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)

    is_protected = update.message.text.startswith('/psend')
    logging.info(f"Send command: chat_id={chat.id}, user_id={update.effective_user.id}, is_protected={is_protected}, args={context.args}")

    # Special logic for /psend (Hidden Message / Whisper)
    if is_protected:
        target_user_id = None
        target_name = None
        message_text = ""
        
        # Case 1: Targeted via mention/ID in arguments
        if context.args:
            first_arg = context.args[0]
            if first_arg.startswith('@') or first_arg.isdigit() or (update.message.entities and any(e.type == 'text_mention' for e in update.message.entities)):
                target_user_id, target_name = await get_user_id(update, context)
                if target_user_id:
                    message_text = " ".join(context.args[1:])
        
        # Case 2: Targeted via reply
        if not target_user_id and update.message.reply_to_message:
            reply = update.message.reply_to_message
            if not reply.from_user.is_bot:
                target_user_id = reply.from_user.id
                target_name = reply.from_user.first_name
                message_text = " ".join(context.args)
        
        # If we have a target and a message, send the hidden message
        if target_user_id and message_text:
            msg_id = str(uuid.uuid4())[:8]
            hidden_col = get_collection(COLLECTIONS["hidden_messages"])
            if hidden_col is not None:
                logging.info(f"Storing hidden message {msg_id}: target={target_user_id}, admin={update.effective_user.id}")
                hidden_col.insert_one({
                    "msg_id": msg_id,
                    "text": message_text,
                    "target_id": int(target_user_id),
                    "admin_id": int(update.effective_user.id),
                    "expires_at": datetime.utcnow() + timedelta(hours=24)
                })
                
                keyboard = [[InlineKeyboardButton("📩 Click to Read", callback_data=f"hidden_msg_{msg_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                target_mention = f"<a href='tg://user?id={target_user_id}'>{target_name}</a>"
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🔐 <b>Secret Message for {target_mention}</b>\n<i>Only they can read this.</i>",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
                # Delete admin command
                try: await update.message.delete()
                except: pass
                return
        elif is_protected and not target_user_id and not update.message.reply_to_message:
             return await update.message.reply_text("Usage: /psend @username message OR reply to someone with /psend message")

    # Helper to get text and entities after the command
    def get_text_and_entities_after_command(message):
        raw_text = message.text
        entities = message.entities
        if not entities:
            return raw_text, []
            
        command_entity = next((e for e in entities if e.type == 'bot_command'), None)
        if not command_entity:
            return raw_text, entities
            
        command_end = command_entity.offset + command_entity.length
        # Skip one space if it exists, but keep other formatting
        text_start = command_end
        if text_start < len(raw_text) and raw_text[text_start].isspace():
            text_start += 1
            
        new_text = raw_text[text_start:]
        new_entities = []
        for entity in entities:
            if entity.offset >= text_start:
                # Create a new entity with adjusted offset
                ent_dict = entity.to_dict()
                ent_dict['offset'] -= text_start
                from telegram import MessageEntity
                new_entities.append(MessageEntity(**ent_dict))
            elif entity.offset + entity.length > text_start:
                # Entity overlaps with the command removal
                ent_dict = entity.to_dict()
                ent_dict['length'] -= (text_start - entity.offset)
                ent_dict['offset'] = 0
                from telegram import MessageEntity
                new_entities.append(MessageEntity(**ent_dict))
        
        return new_text, new_entities

    # 1. Handle reply
    if update.message.reply_to_message:
        reply = update.message.reply_to_message
        
        # If the reply is to a user's message (not media/sticker) and no args,
        # enter interactive mode.
        if not context.args and not (reply.sticker or reply.photo or reply.video or reply.animation or reply.document or reply.audio or reply.voice or reply.video_note):
            # Save target in chat_data
            target_id = reply.message_id
            admin_id = update.effective_user.id
            
            if 'send_targets' not in context.chat_data:
                context.chat_data['send_targets'] = {}
            
            prompt_text = "🔐 <b>Protected Target Locked.</b>\n\n" if is_protected else "✅ <b>Target Locked.</b>\n\n"
            prompt_text += "Now <b>reply to this message</b> with the sticker, media, or text you want the bot to send."
            
            prompt = await update.message.reply_text(prompt_text, parse_mode='HTML')
            
            context.chat_data['send_targets'][prompt.message_id] = {
                'target_id': target_id,
                'admin_id': admin_id,
                'protected': is_protected
            }
            
            # Delete the /send command
            try: await update.message.delete()
            except: pass
            return

        # Double-reply logic: If the replied message is itself a reply to something else,
        # target that original message instead.
        target_message_id = reply.message_id
        if reply.reply_to_message:
            target_message_id = reply.reply_to_message.message_id
        elif hasattr(reply, 'reply_to_message_id') and reply.reply_to_message_id: # Some versions of PTB/Telegram provide this
            target_message_id = reply.reply_to_message_id
            
        try:
            # If command has text, send that text as a reply to the target message
            if context.args:
                new_text, new_entities = get_text_and_entities_after_command(update.message)
                
                await context.bot.send_message(
                    chat_id=chat.id, 
                    text=new_text,
                    entities=new_entities,
                    reply_to_message_id=target_message_id,
                    protect_content=is_protected
                )
            # If no text, send the replied media/sticker back as a reply to the target message
            else:
                if reply.sticker:
                    await context.bot.send_sticker(chat_id=chat.id, sticker=reply.sticker.file_id, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.photo:
                    await context.bot.send_photo(chat_id=chat.id, photo=reply.photo[-1].file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.video:
                    await context.bot.send_video(chat_id=chat.id, video=reply.video.file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.animation:
                    await context.bot.send_animation(chat_id=chat.id, animation=reply.animation.file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.document:
                    await context.bot.send_document(chat_id=chat.id, document=reply.document.file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.audio:
                    await context.bot.send_audio(chat_id=chat.id, audio=reply.audio.file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.voice:
                    await context.bot.send_voice(chat_id=chat.id, voice=reply.voice.file_id, caption=reply.caption, caption_entities=reply.caption_entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.video_note:
                    await context.bot.send_video_note(chat_id=chat.id, video_note=reply.video_note.file_id, reply_to_message_id=target_message_id, protect_content=is_protected)
                elif reply.text:
                    await context.bot.send_message(chat_id=chat.id, text=reply.text, entities=reply.entities, reply_to_message_id=target_message_id, protect_content=is_protected)
                else:
                    return await update.message.reply_text("❌ Unsupported media type in reply.")
            
            # Delete the /send command message and the intermediate reply if it was a double-reply
            try:
                await update.message.delete()
                if reply.reply_to_message: # Only delete the intermediate media if it was a double-reply
                    await reply.delete()
            except: pass
            return
        except Exception as e:
            logging.error(f"Error in send_command (reply): {e}")
            return await update.message.reply_text(f"❌ Failed to send: {str(e)}")


    # 2. Handle arguments (text message) without reply
    if context.args:
        new_text, new_entities = get_text_and_entities_after_command(update.message)
        try:
            await context.bot.send_message(chat_id=chat.id, text=new_text, entities=new_entities, protect_content=is_protected)
            # Delete the /send command message
            try:
                await update.message.delete()
            except: pass
        except Exception as e:
            logging.error(f"Error in send_command (text): {e}")
            return await update.message.reply_text(f"❌ Failed to send message: {str(e)}")
        return



    await update.message.reply_text("Usage: /send <message> or reply to media/sticker with /send")


async def hidden_msg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for the 'Click to Read' button on hidden messages."""
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    if not data.startswith("hidden_msg_"):
        return
        
    msg_id = data.replace("hidden_msg_", "")
    hidden_col = get_collection(COLLECTIONS["hidden_messages"])
    
    if hidden_col is None:
        return await query.answer("❌ Database connection error.", show_alert=True)
        
    hidden_msg = hidden_col.find_one({"msg_id": msg_id})
    
    if not hidden_msg:
        return await query.answer("❌ This message has expired or no longer exists.", show_alert=True)
        
    target_id = hidden_msg["target_id"]
    admin_id = hidden_msg["admin_id"]
    
    logging.info(f"Hidden message read attempt {msg_id}: clicker={user_id}, target={target_id}, admin={admin_id}")
    
    if int(user_id) == int(target_id) or int(user_id) == int(admin_id) or int(user_id) == int(OWNER_ID):
        # Show the message
        await query.answer(hidden_msg["text"], show_alert=True)
    else:
        # Not the target user
        await query.answer("❌ This message is not for you!", show_alert=True)


async def handle_interactive_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the media/sticker reply in interactive send mode."""
    if not update.message.reply_to_message:
        return
        
    # Security: Must be a reply to the bot's own prompt
    if update.message.reply_to_message.from_user.id != context.bot.id:
        return
        
    chat_id = update.effective_chat.id
    prompt_id = update.message.reply_to_message.message_id
    
    if 'send_targets' not in context.chat_data or prompt_id not in context.chat_data['send_targets']:
        return
        
    target_info = context.chat_data['send_targets'][prompt_id]
    
    # Security: Only the admin who initiated the /send can complete it
    if update.effective_user.id != target_info['admin_id']:
        return
        
    target_id = target_info['target_id']
    is_protected = target_info.get('protected', False)
    msg = update.message
    
    logging.info(f"Interactive Send: Sending {msg.type} to target_id={target_id}, protected={is_protected}")
    
    try:
        reply_params = ReplyParameters(message_id=target_id, allow_sending_without_reply=True)
        
        if msg.sticker:
            await context.bot.send_sticker(chat_id=chat_id, sticker=msg.sticker.file_id, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.photo:
            await context.bot.send_photo(chat_id=chat_id, photo=msg.photo[-1].file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.video:
            await context.bot.send_video(chat_id=chat_id, video=msg.video.file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.animation:
            await context.bot.send_animation(chat_id=chat_id, animation=msg.animation.file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.document:
            await context.bot.send_document(chat_id=chat_id, document=msg.document.file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.audio:
            await context.bot.send_audio(chat_id=chat_id, audio=msg.audio.file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.voice:
            await context.bot.send_voice(chat_id=chat_id, voice=msg.voice.file_id, caption=msg.caption, caption_entities=msg.caption_entities, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.video_note:
            await context.bot.send_video_note(chat_id=chat_id, video_note=msg.video_note.file_id, reply_parameters=reply_params, protect_content=is_protected)
        elif msg.text:
            await context.bot.send_message(chat_id=chat_id, text=msg.text, entities=msg.entities, reply_parameters=reply_params, protect_content=is_protected)
            
        # Cleanup
        try:
            await msg.delete() # Delete the admin's sticker/media
            await update.message.reply_to_message.delete() # Delete the bot's prompt
        except: pass
        
        # Remove from targets
        del context.chat_data['send_targets'][prompt_id]
        
    except Exception as e:
        logging.error(f"Error in handle_interactive_send: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute a user in the group."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_mute_enabled", True):
        return await update.message.reply_text("❌ The /mute command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_restrict_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    
    # Extract reason
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else None
    else:
        # First arg was user ID/username, rest is reason
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    if not user_id:
        return await update.message.reply_text("Usage: /mute @username [reason] or reply to a user with /mute [reason]")
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot mute an admin or the group owner.")
        
        if isinstance(member, ChatMemberRestricted) and not member.can_send_messages:
            return await update.message.reply_text("User is already muted.")
        
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        await chat.restrict_member(user_id, permissions)
        
        admin_name = user.full_name
        text = f"» Mute a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to mute user: {str(e)}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute a user in the group."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_restrict_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    
    # Extract reason
    if update.message.reply_to_message:
        reason = " ".join(context.args) if context.args else None
    else:
        # First arg was user ID/username, rest is reason
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    if not user_id:
        return await update.message.reply_text("Usage: /unmute @username [reason] or reply to a user with /unmute [reason]")
    
    try:
        member = await chat.get_member(user_id)
        if not isinstance(member, ChatMemberRestricted):
            return await update.message.reply_text("User is not muted.")
        
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True,
        )
        
        await chat.restrict_member(user_id, permissions)
        
        admin_name = user.full_name
        text = f"» Unmute a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute user: {str(e)}")

async def tmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporarily mute a user."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_restrict_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /tmute @username <time> [reason] or reply with /tmute <time> [reason]")

    # Extract time and reason
    if update.message.reply_to_message:
        if len(context.args) < 1:
            return await update.message.reply_text("Usage: /tmute @username <time> [reason] or reply with /tmute <time> [reason]")
        time_str = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    else:
        # First arg was user ID/username, second is time, rest is reason
        if len(context.args) < 2:
            return await update.message.reply_text("Usage: /tmute @username <time> [reason] or reply with /tmute <time> [reason]")
        time_str = context.args[1]
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot mute an admin or the group owner.")
        
        delta = parse_time(time_str)
        if not delta:
            return await update.message.reply_text("Invalid time format. Use s/m/h/d suffix (e.g., 1h, 30m, 2d).")
        
        until_date = datetime.utcnow() + delta
        
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        await chat.restrict_member(user_id, permissions, until_date=until_date)
        
        admin_name = user.full_name
        text = f"» Mute for {time_str} in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to temporarily mute user: {str(e)}")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kick a user from the group."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_kick_enabled", True):
        return await update.message.reply_text("❌ The /kick command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else " ".join(context.args) if context.args and not str(context.args[0]).startswith('@') and not str(context.args[0]).isdigit() else None
    
    if not user_id:
        return await update.message.reply_text("Usage: /kick @username or reply to a user with /kick [reason]")
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot kick an admin or the group owner.")
        
        await chat.ban_member(user_id)
        
        # Remove from VC if safety is enabled
        if settings.get("vc_safety_enabled", False):
            await remove_user_from_vc(chat.id, user_id)
            
        await asyncio.sleep(2)
        await chat.unban_member(user_id)
        
        admin_name = user.full_name
        text = f"» Kick a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to kick user: {str(e)}")

async def dban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete message and ban user."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Usage: Reply to a user's message with /dban [reason]")
    
    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    name = target_user.full_name
    reason = " ".join(context.args) if context.args else None
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot ban an admin or the group owner.")
        
        await chat.ban_member(user_id)
        
        # Remove from VC if safety is enabled
        settings = get_chat_settings(chat.id)
        if settings.get("vc_safety_enabled", False):
            await remove_user_from_vc(chat.id, user_id)
            
        await update.message.reply_to_message.delete()
        
        admin_name = user.full_name
        text = f"» Ban a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to delete and ban: {str(e)}")

async def sban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent ban (no notification)."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /sban @username or reply to a user with /sban")
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot ban an admin or the group owner.")
        
        await chat.ban_member(user_id)
        
        # Remove from VC if safety is enabled
        settings = get_chat_settings(chat.id)
        if settings.get("vc_safety_enabled", False):
            await remove_user_from_vc(chat.id, user_id)
            
        await update.message.delete()
    except Exception as e:
        await update.message.reply_text(f"Failed to silently ban: {str(e)}")

async def kickme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User self-kick."""
    chat = update.effective_chat
    user = update.effective_user
    
    try:
        member = await chat.get_member(user.id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("Nice try, boss 😅 I can't kick admins or the owner.")
        
        await chat.ban_member(user.id)
        await asyncio.sleep(3)
        await chat.unban_member(user.id)
        
        await update.message.reply_text("Kicked so hard, your ancestors felt it. 👟💥")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick you: {str(e)}")

async def tban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporarily ban a user."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    
    if update.message.reply_to_message:
        if len(context.args) < 1:
            return await update.message.reply_text("Usage: /tban @username <time> [reason] or reply with /tban <time> [reason]")
        time_str = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    else:
        if len(context.args) < 2:
            return await update.message.reply_text("Usage: /tban @username <time> [reason] or reply with /tban <time> [reason]")
        time_str = context.args[1]
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    if not user_id:
        return await update.message.reply_text("User not found.")
    
    try:
        member = await chat.get_member(user_id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return await update.message.reply_text("I cannot ban an admin or the group owner.")
        
        delta = parse_time(time_str)
        if not delta:
            return await update.message.reply_text("Invalid time format. Use s/m/h/d suffix (e.g., 1h, 30m, 2d).")
        
        until_date = datetime.utcnow() + delta
        
        await chat.ban_member(user_id, until_date=until_date)
        
        # Remove from VC if safety is enabled
        settings = get_chat_settings(chat.id)
        if settings.get("vc_safety_enabled", False):
            await remove_user_from_vc(chat.id, user_id)
        
        admin_name = user.full_name
        text = f"» Ban for {time_str} in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if reason:
            text += f"\nReason: {reason}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to temporarily ban user: {str(e)}")

def get_manager_actions_handlers():
    """Return all Manager action handlers."""
    return [
        CommandHandler("ban", ban_user),
        CommandHandler("unban", unban_user),
        CommandHandler("mute", mute_user),
        CommandHandler("unmute", unmute_user),
        CommandHandler("tmute", tmute_user),
        CommandHandler("kick", kick_user),
        CommandHandler("dban", dban_user),
        CommandHandler("sban", sban_user),
        CommandHandler("kickme", kickme),
        CommandHandler("tban", tban_user),
        CommandHandler(["send", "psend"], send_command),
        CallbackQueryHandler(hidden_msg_callback, pattern="^hidden_msg_"),
        MessageHandler(filters.REPLY & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP) & ~filters.COMMAND, handle_interactive_send),
    ]
