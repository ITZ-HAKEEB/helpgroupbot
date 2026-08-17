import logging
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from core.config import OWNER_ID, log_to_channel, send_bot_response, colored_button
from managers.settings_manager_mongo import get_chat_settings
from managers.moderation_manager_mongo import (
    get_user_warns, add_warn, reset_warns, 
    is_muter as check_is_muter, add_muter, remove_muter, get_all_muters,
    is_voice_chat_manager as check_is_voice_chat_manager,
    add_voice_chat_manager, remove_voice_chat_manager, get_all_voice_chat_managers
)
from managers.user_manager_mongo import resolve_username, get_user_id, is_user_admin
import features.voice_chat
from moderation.anonymous_admin import is_anonymous_admin, check_anonymous_admin_ban_permission, check_anonymous_admin_mute_permission

from managers.staff_manager_mongo import increment_staff_stat

async def can_user_mute(chat_id, user_id, context):
    """Check if a user can mute/unmute (Admin or Muter)."""
    # dedicated Muter (role in MongoDB) can always mute
    if check_is_muter(chat_id, user_id):
        return True

    # Use the centralized check_admin_permission from Manager.actions
    from managers.actions import check_admin_permission
    
    class MockUpdate:
        def __init__(self, chat_id, user_id):
            from telegram import Chat, User
            self.effective_chat = Chat(chat_id, 'group')
            self.effective_user = User(user_id, 'User', False)
    
    mock_update = MockUpdate(chat_id, user_id)
    has_perm, _ = await check_admin_permission(mock_update, context, 'can_restrict_members')
    return has_perm

async def can_user_manage_voice_chat(chat_id, user_id, context):
    """Check if a user can manage voice chats (Admin, Muter, or Voice Chat Manager)."""
    # Admins can always manage voice chats
    if await is_user_admin(chat_id, user_id, context):
        return True
    # Muters can manage voice chats
    if check_is_muter(chat_id, user_id):
        return True
    # Voice chat managers can manage voice chats
    if check_is_voice_chat_manager(chat_id, user_id):
        return True
    return False

async def can_user_ban(chat_id, user_id, context):
    """Check if a user can ban/unban (Admin with custom ban permission)."""
    if user_id == OWNER_ID:
        return True, None

    # Use the centralized check_admin_permission from Manager.actions
    from managers.actions import check_admin_permission
    
    # We create a mock update for the check
    class MockUpdate:
        def __init__(self, chat_id, user_id):
            from telegram import Chat, User
            self.effective_chat = Chat(chat_id, 'group')
            self.effective_user = User(user_id, 'User', False)
    
    mock_update = MockUpdate(chat_id, user_id)
    return await check_admin_permission(mock_update, context, 'can_ban_users')

async def check_bot_admin_rights(chat_id, context, required_rights=None):
    """Checks if the bot has the required administrative rights."""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if bot_member.status == 'creator':
            return True, None
        if bot_member.status != 'administrator':
            return False, "❌ I am not an administrator in this group."
        
        if required_rights:
            missing = []
            for right in required_rights:
                if not getattr(bot_member, right, False):
                    missing.append(right)
            if missing:
                return False, f"❌ I am missing the following rights: {', '.join(missing)}"
        return True, None
    except Exception as e:
        return False, f"❌ Error checking bot rights: {str(e)}"

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str = None):
    """Helper to mute a user."""
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
        return True
    except Exception as e:
        logging.error(f"Error in mute_user: {e}")
        return False

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str = None):
    """Helper to kick a user."""
    chat_id = update.effective_chat.id
    try:
        # unban_chat_member kicks the user if they are in the group
        await context.bot.unban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logging.error(f"Error in kick_user: {e}")
        return False

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str = None):
    """Helper to ban a user."""
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logging.error(f"Error in ban_user: {e}")
        return False

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bans a user or channel from the chat or channel."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    chat_type = update.effective_chat.type
    
    # Check if user has ban permission (not just admin status)
    if chat_type != 'channel':
        can_ban, error_msg = await can_user_ban(chat_id, sender_id, context)
        if not can_ban:
            await send_bot_response(update, context, error_msg)
            return
    
    # Check bot rights
    has_rights, error_msg = await check_bot_admin_rights(chat_id, context, ['can_restrict_members'])
    if not has_rights:
        await send_bot_response(update, context, error_msg)
        return

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(update, context, "Please reply to a user/channel or provide an ID/username to ban.")
        return

    # Check if target is an admin
    if await is_user_admin(chat_id, target_id, context) and sender_id != OWNER_ID:
        await send_bot_response(update, context, "❌ I cannot ban another administrator.")
        return

    try:
        if str(target_id).startswith('-100'):
            # It's a channel/chat
            await context.bot.ban_chat_sender_chat(chat_id, target_id)
            await send_bot_response(update, context, f"✅ Banned channel {target_name}.")
        else:
            # It's a user
            await context.bot.ban_chat_member(chat_id, target_id)
            await send_bot_response(update, context, f"✅ Banned {target_name}.")
            
        admin_name = update.effective_user.first_name if update.effective_user else "Channel Admin"
        await log_to_channel(context, f"🔨 #BAN\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        
        # Record stats
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "ban")
    except BadRequest as e:
        if "user not found" in str(e).lower() or "invalid" in str(e).lower():
            await send_bot_response(update, context, f"Invalid user/ID. Make sure the user exists and the ID is correct.")
        else:
            await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unbans a user or channel from the chat or channel."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    chat_type = update.effective_chat.type
    
    # Check if user has ban permission
    if chat_type != 'channel':
        can_ban, error_msg = await can_user_ban(chat_id, sender_id, context)
        if not can_ban:
            await send_bot_response(update, context, error_msg)
            return

    # Check bot rights
    has_rights, error_msg = await check_bot_admin_rights(chat_id, context, ['can_restrict_members'])
    if not has_rights:
        await send_bot_response(update, context, error_msg)
        return

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(update, context, "Please reply to a user/channel or provide an ID/username to unban.")
        return

    try:
        if str(target_id).startswith('-100'):
            # It's a channel/chat
            await context.bot.unban_chat_sender_chat(chat_id, target_id)
            await send_bot_response(update, context, f"✅ Unbanned channel {target_name}.")
        else:
            # It's a user
            await context.bot.unban_chat_member(chat_id, target_id, only_if_banned=False)
            await send_bot_response(update, context, f"✅ Unbanned {target_name}.")
            
        admin_name = update.effective_user.first_name if update.effective_user else "Channel Admin"
        await log_to_channel(context, f"🔓 #UNBAN\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        
        # Record stats
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "unban")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def promote_muter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote a member to Muter (can only mute/unmute members)."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    # Only admins with promote permission can use this
    from managers.actions import check_admin_permission
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(update, context, "Please reply to a member's message or provide an ID/username to make them a Muter.")
        return

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        if member.status in ['administrator', 'creator']:
            await send_bot_response(update, context, "❌ This command only works on regular members, not admins.")
            return

        # Check bot rights
        has_rights, bot_error = await check_bot_admin_rights(chat_id, context, ['can_promote_members', 'can_restrict_members'])
        if not has_rights:
            await send_bot_response(update, context, bot_error)
            return

        # Promote to admin with NO native rights (bot-only muter)
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            can_restrict_members=False
        )
        
        # Set custom title
        try:
            await context.bot.set_chat_administrator_custom_title(chat_id, target_id, "мυтєя")
        except:
            pass

        # Update cache/database
        add_muter(chat_id, target_id)
        from managers.admin_manager_mongo import update_admin_cache
        update_admin_cache(chat_id, target_id, {"can_restrict_members": True})

        await send_bot_response(update, context, f"✅ <b>{target_name}</b> ʜᴀs ʙᴇᴇɴ ᴘʀᴏᴍᴏᴛᴇᴅ ᴛᴏ <b>мυтєя</b>.\nᴛʜᴇʏ ᴄᴀɴ ɴᴏᴡ ᴍᴜᴛᴇ/ᴜɴᴍᴜᴛᴇ ᴍᴇᴍʙᴇʀs.")
        await log_to_channel(context, f"🔇 #MUTER_PROMOTED\nTarget: {target_name} ({target_id})\nAdmin: {update.effective_user.first_name}")

    except Exception as e:
        await send_bot_response(update, context, f"❌ Failed to promote: {str(e)}")

async def demote_muter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demote a Muter back to regular member."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    # Only admins with promote permission can use this
    from managers.actions import check_admin_permission
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(update, context, "Please reply to a Muter's message or provide an ID/username to demote them.")
        return

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        
        # Safety check: if they are a real admin (not just a Muter), don't demote
        from managers.admin_manager_mongo import get_stored_admin_permissions
        admin_data = get_stored_admin_permissions(chat_id, target_id)
        
        # If they have permissions other than just restricting, they might be a full admin
        if admin_data:
            perms_count = sum(1 for v in admin_data.values() if v is True)
            if perms_count > 1 or (perms_count == 1 and not admin_data.get('can_restrict_members')):
                await send_bot_response(update, context, "❌ This user appears to be a full administrator. Use /demote instead.")
                return

        # Check bot rights
        has_rights, bot_error = await check_bot_admin_rights(chat_id, context, ['can_promote_members'])
        if not has_rights:
            await send_bot_response(update, context, bot_error)
            return

        # Demote to member
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            can_change_info=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_promote_members=False
        )
        
        # Remove from muter list and cache
        remove_muter(chat_id, target_id)
        from managers.admin_manager_mongo import remove_admin_cache
        remove_admin_cache(chat_id, target_id)

        await send_bot_response(update, context, f"✅ <b>{target_name}</b> ʜᴀs ʙᴇᴇɴ ᴅᴇᴍᴏᴛᴇᴅ ғʀᴏᴍ <b>мυтєя</b>.")
        await log_to_channel(context, f"🔊 #MUTER_DEMOTED\nTarget: {target_name} ({target_id})\nAdmin: {update.effective_user.first_name}")

    except Exception as e:
        await send_bot_response(update, context, f"❌ Failed to demote: {str(e)}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mutes a user by restricting their permissions."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    # Check if user is admin or muter
    if not await can_user_mute(chat_id, sender_id, context):
        await send_bot_response(update, context, "You must be an admin or have the 'Muter' role to mute users.")
        return

    # Check bot rights
    has_rights, error_msg = await check_bot_admin_rights(chat_id, context, ['can_restrict_members'])
    if not has_rights:
        await send_bot_response(update, context, error_msg)
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id: return

    # Check if target is an admin
    if await is_user_admin(chat_id, user_id, context) and sender_id != OWNER_ID:
        await send_bot_response(update, context, "❌ I cannot mute another administrator.")
        return

    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
        await send_bot_response(update, context, f"🔇 Muted {user_name}.")
        
        # Record stats
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "mute")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await can_user_mute(chat_id, sender_id, context):
        await send_bot_response(update, context, "You don't have permission to unmute users.")
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id: return

    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(
            can_send_messages=True, 
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True, 
            can_send_other_messages=True,
            can_add_web_page_previews=True
        ))
        await send_bot_response(update, context, f"🔊 Unmuted {user_name}.")
        
        # Record stats
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "unmute")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def muter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to list all muters or add/remove a muter."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context):
        await send_bot_response(update, context, "Admin only command.")
        return

    # If no arguments and not a reply, list all muters
    if not context.args and not update.message.reply_to_message:
        muter_ids = get_all_muters(chat_id)
        if not muter_ids:
            await send_bot_response(update, context, "No muters set in this group.")
            return
        
        muter_list = []
        for mid in muter_ids:
            try:
                member = await context.bot.get_chat_member(chat_id, mid)
                user_name = f"{member.user.first_name} (<code>{mid}</code>)"
            except:
                user_name = f"<code>{mid}</code>"
            muter_list.append(f"• {user_name}")
        
        await send_bot_response(
            update, context,
            "🛡️ <b>мυтєя List:</b>\n" + "\n".join(muter_list),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(colored_button("❌ Close", "default"), callback_data="close_moderation")]])
        )
        return

    # Otherwise, handle as /muter [promote]
    await promote_muter_command(update, context)

async def unmuter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to remove a muter specifically (/unmuter)."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context):
        await send_bot_response(update, context, "Admin only command.")
        return

    await demote_muter_command(update, context)

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Please reply to a user or provide a username/ID to set as muter.")
        return

    if check_is_muter(chat_id, user_id):
        remove_muter(chat_id, user_id)
        await send_bot_response(update, context, f"✅ Removed {user_name} from muters.")
    else:
        add_muter(chat_id, user_id)
        await send_bot_response(update, context, f"✅ {user_name} is now a muter. They can use /mute, /unmute, and manage voice chats.")

async def unmuter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to remove a muter specifically."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context):
        await send_bot_response(update, context, "Admin only command.")
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Please reply to a user or provide a username/ID to remove from muters.")
        return

    if check_is_muter(chat_id, user_id):
        remove_muter(chat_id, user_id)
        await send_bot_response(update, context, f"✅ Removed {user_name} from muters.")
    else:
        await send_bot_response(update, context, f"❌ {user_name} is not a muter.")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context): return

    user_id, user_name = await get_user_id(update, context)
    if not user_id: return

    # Check if target is an admin
    if await is_user_admin(chat_id, user_id, context) and sender_id != OWNER_ID:
        await send_bot_response(update, context, "❌ I cannot warn another administrator.")
        return

    settings = get_chat_settings(chat_id)
    limit = settings.get("warn_limit", 3)
    penalty = settings.get("warn_penalty", "ban")

    current_warns = add_warn(chat_id, user_id)
    
    if current_warns >= limit:
        reset_warns(chat_id, user_id)
        if penalty == "ban":
            await context.bot.ban_chat_member(chat_id, user_id)
            await send_bot_response(update, context, f"⛔ User <code>{user_id}</code> reached warn limit ({limit}/{limit}) and was banned.", parse_mode=ParseMode.HTML)
        elif penalty == "mute":
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            await send_bot_response(update, context, f"⛔ User <code>{user_id}</code> reached warn limit ({limit}/{limit}) and was muted.", parse_mode=ParseMode.HTML)
        elif penalty == "kick":
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id)
            await send_bot_response(update, context, f"⛔ User <code>{user_id}</code> reached warn limit ({limit}/{limit}) and was kicked.", parse_mode=ParseMode.HTML)
    else:
        await send_bot_response(update, context, f"⚠️ User <code>{user_id}</code> has been warned. ({current_warns}/{limit})", parse_mode=ParseMode.HTML)
    
    # Record stats
    if sender_id:
        increment_staff_stat(chat_id, sender_id, "warn")

async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context): return

    user_id, user_name = await get_user_id(update, context)
    if not user_id: return

    reset_warns(chat_id, user_id)
    await send_bot_response(update, context, f"✅ Reset warnings for {user_name}.")

async def voicechatmgr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to add or remove a voice chat manager."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context):
        await send_bot_response(update, context, "Admin only command.")
        return

    # Check if we should list all voice chat managers
    if not context.args and not update.message.reply_to_message:
        manager_ids = get_all_voice_chat_managers(chat_id)
        if not manager_ids:
            await send_bot_response(update, context, "No voice chat managers set in this group.")
            return
        
        manager_list = []
        users_data = load_users()
        for mid in manager_ids:
            user_name = f"<code>{mid}</code>"
            # Try to resolve username or use ID
            found = False
            for username, info in users_data.items():
                if str(info["id"]) == str(mid):
                    user_name = f"{info['name']} (@{username})"
                    found = True
                    break
            if not found:
                # If not in cache, just show ID
                user_name = f"<code>{mid}</code>"
            manager_list.append(f"• {user_name}")
        
        await send_bot_response(
            update, context,
            "🎙️ <b>Voice Chat Managers:</b>\n" + "\n".join(manager_list),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(colored_button("❌ Close", "default"), callback_data="close_moderation")]])
        )
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Please reply to a user or provide a username/ID to set as voice chat manager.")
        return

    if check_is_voice_chat_manager(chat_id, user_id):
        remove_voice_chat_manager(chat_id, user_id)
        await send_bot_response(update, context, f"✅ Removed {user_name} from voice chat managers.")
    else:
        add_voice_chat_manager(chat_id, user_id)
        await send_bot_response(update, context, f"✅ {user_name} is now a voice chat manager. They can manage voice/video chats.")

async def unvoicechatmgr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to remove a voice chat manager specifically."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, sender_id, context):
        await send_bot_response(update, context, "Admin only command.")
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Please reply to a user or provide a username/ID to remove from voice chat managers.")
        return

    if not check_is_voice_chat_manager(chat_id, user_id):
        await send_bot_response(update, context, f"❌ {user_name} is not a voice chat manager.")
        return

    remove_voice_chat_manager(chat_id, user_id)
    await send_bot_response(update, context, f"✅ Removed {user_name} from voice chat managers.")

async def close_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close the moderation list."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, user_id, context):
        await query.answer("Only admins can close this list.", show_alert=True)
        return
        
    await query.message.delete()
    await query.answer()

async def edit_protection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for edit protection warning buttons."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id
    data = query.data

    if not await is_user_admin(chat_id, admin_id, context):
        await query.answer("Only admins can use these buttons.", show_alert=True)
        return

    parts = data.split("_")
    action = parts[1]
    user_id = int(parts[-1])
    
    # Try to get user name for the response
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        user_name = member.user.mention_html()
    except:
        user_name = f"User {user_id}"

    if action == "unmute":
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(
                can_send_messages=True, 
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True, 
                can_send_other_messages=True,
                can_add_web_page_previews=True
            ))
            await query.answer(f"🔊 Unmuted {user_id}")
            # Update message text to reflect status
            await query.edit_message_text(f"🔊 {user_name} has been unmuted by an admin.", parse_mode='HTML')
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)

    elif action == "warn":
        if parts[2] == "add":
            new_warns = add_warn(chat_id, user_id)
            await query.answer(f"⚠️ Added warn to {user_id}. Total: {new_warns}")
            # Optional: edit message to show new warn count if we were showing it
        elif parts[2] == "reset":
            reset_warns(chat_id, user_id)
            await query.answer(f"🔄 Reset warns for {user_id}")
            await query.edit_message_text(f"🔄 Warnings for {user_name} have been reset by an admin.", parse_mode='HTML')

async def _resolve_telethon_target(update, context, logger):
    """Fallback: resolve a @username via Telethon when get_user_id fails."""
    if not context.args:
        return None, None
    raw = context.args[0].replace('@', '')
    if raw.isdigit():
        return None, None
    if not voice_chat.telethon_client or not voice_chat.telethon_client.is_connected():
        return None, None
    try:
        entity = await voice_chat.telethon_client.get_entity(raw)
        logger.info(f"_resolve_telethon_target: resolved {raw} -> {entity.id}")
        return entity.id, f"@{raw}"
    except Exception as e:
        logger.warning(f"_resolve_telethon_target: failed for {raw}: {e}")
        return None, None

async def forceban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban by user ID or @username even if user is not in the group."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    logger = logging.getLogger(__name__)

    # Permission check for admin
    if not await can_user_ban(chat_id, sender_id, context):
        return await send_bot_response(update, context, "You don't have permission to ban users.")

    if not await check_bot_admin_rights(chat_id, context, ['can_restrict_members']):
        return await send_bot_response(update, context, "Bot needs restrict members permission.")

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        target_id, target_name = await _resolve_telethon_target(update, context, logger)

    if not target_id:
        return await send_bot_response(update, context, "Provide a user ID or @username.")

    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        await send_bot_response(update, context, f"✅ Banned {target_name} (ID: <code>{target_id}</code>).", parse_mode=ParseMode.HTML)
        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔨 #FORCEBAN\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "ban")
    except BadRequest as e:
        if "user not found" in str(e).lower() or "invalid" in str(e).lower():
            await send_bot_response(update, context, f"Invalid user ID <code>{target_id}</code>. Check the ID and try again.", parse_mode=ParseMode.HTML)
        elif "not enough rights" in str(e).lower() or "need administrator" in str(e).lower():
            await send_bot_response(update, context, "Bot has no rights to ban members in this group.")
        else:
            await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def forceunban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban by user ID or @username even if user is not in the group."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    logger = logging.getLogger(__name__)

    # Permission check for admin
    if not await can_user_ban(chat_id, sender_id, context):
        return await send_bot_response(update, context, "You don't have permission to unban users.")

    if not await check_bot_admin_rights(chat_id, context, ['can_restrict_members']):
        return await send_bot_response(update, context, "Bot needs restrict members permission.")

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        target_id, target_name = await _resolve_telethon_target(update, context, logger)

    if not target_id:
        return await send_bot_response(update, context, "Provide a user ID or @username.")

    try:
        await context.bot.unban_chat_member(chat_id, target_id)
        await send_bot_response(update, context, f"✅ Unbanned {target_name} (ID: <code>{target_id}</code>).", parse_mode=ParseMode.HTML)
        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔓 #FORCEUNBAN\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "unban")
    except BadRequest as e:
        if "user not found" in str(e).lower() or "invalid" in str(e).lower():
            await send_bot_response(update, context, f"Invalid user ID <code>{target_id}</code>. Check the ID and try again.", parse_mode=ParseMode.HTML)
        else:
            await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def forcemute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute by user ID or @username even if user is not currently a member."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    logger = logging.getLogger(__name__)

    # Permission check for admin
    if not await can_user_mute(chat_id, sender_id, context):
        return await send_bot_response(update, context, "You don't have permission to mute users.")

    if not await check_bot_admin_rights(chat_id, context, ['can_restrict_members']):
        return await send_bot_response(update, context, "Bot needs restrict members permission.")

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        target_id, target_name = await _resolve_telethon_target(update, context, logger)

    if not target_id:
        return await send_bot_response(update, context, "Provide a user ID or @username.")

    try:
        await context.bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False))
        await send_bot_response(update, context, f"🔇 Muted {target_name} (ID: <code>{target_id}</code>).", parse_mode=ParseMode.HTML)
        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔇 #FORCEMUTE\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "mute")
    except BadRequest as e:
        if "user not found" in str(e).lower() or "invalid" in str(e).lower():
            await send_bot_response(update, context, f"Invalid user ID <code>{target_id}</code>. Check the ID and try again.", parse_mode=ParseMode.HTML)
        else:
            await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def forceunmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unmute by user ID or @username even if user is not currently a member."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None
    logger = logging.getLogger(__name__)

    # Permission check for admin
    if not await can_user_mute(chat_id, sender_id, context):
        return await send_bot_response(update, context, "You don't have permission to unmute users.")

    if not await check_bot_admin_rights(chat_id, context, ['can_restrict_members']):
        return await send_bot_response(update, context, "Bot needs restrict members permission.")

    target_id, target_name = await get_user_id(update, context)
    if not target_id:
        target_id, target_name = await _resolve_telethon_target(update, context, logger)

    if not target_id:
        return await send_bot_response(update, context, "Provide a user ID or @username.")

    try:
        await context.bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        ))
        await send_bot_response(update, context, f"🔊 Unmuted {target_name} (ID: <code>{target_id}</code>).", parse_mode=ParseMode.HTML)
        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔊 #FORCEUNMUTE\nTarget: {target_name} ({target_id})\nAdmin: {admin_name}")
        if sender_id:
            increment_staff_stat(chat_id, sender_id, "unmute")
    except BadRequest as e:
        if "user not found" in str(e).lower() or "invalid" in str(e).lower():
            await send_bot_response(update, context, f"Invalid user ID <code>{target_id}</code>. Check the ID and try again.", parse_mode=ParseMode.HTML)
        else:
            await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def _delete_user_messages(context, chat_id: int, user_id: int) -> bool:
    """Delete all messages from a user in a chat using Bot API deleteUserMessages (Bot API 7.2+)."""
    try:
        from core.config import BOT_TOKEN
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteUserMessages",
                json={"chat_id": chat_id, "user_id": user_id}
            )
            result = resp.json()
            if result.get("ok"):
                logging.info(f"[DMUTE/DBAN] Deleted all messages of user {user_id} in chat {chat_id}")
                return True
            else:
                logging.warning(f"[DMUTE/DBAN] deleteUserMessages failed: {result.get('description')}")
                return False
    except Exception as e:
        logging.error(f"[DMUTE/DBAN] Error calling deleteUserMessages: {e}")
        return False

async def dmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mutes a user AND deletes all their messages in the chat."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None

    if not await can_user_mute(chat_id, sender_id, context):
        await send_bot_response(update, context, "You must be an admin or have the 'Muter' role to use /dmute.")
        return

    has_rights, error_msg = await check_bot_admin_rights(chat_id, context, ['can_restrict_members', 'can_delete_messages'])
    if not has_rights:
        await send_bot_response(update, context, error_msg)
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Usage: Reply to a user's message or provide /dmute <user_id|@username>")
        return

    if await is_user_admin(chat_id, user_id, context) and sender_id != OWNER_ID:
        await send_bot_response(update, context, "❌ I cannot mute another administrator.")
        return

    try:
        # Step 1: Mute the user
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))

        # Step 2: Delete all their messages
        deleted = await _delete_user_messages(context, chat_id, user_id)
        del_status = "and all their messages were deleted 🗑️" if deleted else "(note: message deletion requires Bot API 7.2+)"

        await send_bot_response(update, context, f"🔇🗑️ <b>{user_name}</b> has been muted {del_status}.", parse_mode=ParseMode.HTML)

        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔇🗑️ #DMUTE\nTarget: {user_name} ({user_id})\nAdmin: {admin_name}")

        if sender_id:
            increment_staff_stat(chat_id, sender_id, "mute")
    except BadRequest as e:
        await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

async def dban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bans a user AND deletes all their messages in the chat."""
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id if update.effective_user else None

    can_ban, error_msg = await can_user_ban(chat_id, sender_id, context)
    if not can_ban:
        await send_bot_response(update, context, error_msg)
        return

    has_rights, error_msg = await check_bot_admin_rights(chat_id, context, ['can_restrict_members', 'can_delete_messages'])
    if not has_rights:
        await send_bot_response(update, context, error_msg)
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Usage: Reply to a user's message or provide /dban <user_id|@username>")
        return

    if await is_user_admin(chat_id, user_id, context) and sender_id != OWNER_ID:
        await send_bot_response(update, context, "❌ I cannot ban another administrator.")
        return

    try:
        # Step 1: Delete all their messages first (while still a member so the API resolves them)
        deleted = await _delete_user_messages(context, chat_id, user_id)

        # Step 2: Ban the user
        await context.bot.ban_chat_member(chat_id, user_id)

        del_status = "and all their messages were deleted 🗑️" if deleted else "(note: message deletion requires Bot API 7.2+)"
        await send_bot_response(update, context, f"🔨🗑️ <b>{user_name}</b> has been banned {del_status}.", parse_mode=ParseMode.HTML)

        admin_name = update.effective_user.first_name if update.effective_user else "Admin"
        await log_to_channel(context, f"🔨🗑️ #DBAN\nTarget: {user_name} ({user_id})\nAdmin: {admin_name}")

        if sender_id:
            increment_staff_stat(chat_id, sender_id, "ban")
    except BadRequest as e:
        await send_bot_response(update, context, f"Error: {e}")
    except Exception as e:
        await send_bot_response(update, context, f"Error: {e}")

def get_moderation_handlers():

    return [
        CommandHandler("ban", ban_command),
        CommandHandler("forceban", forceban_command),
        CommandHandler("forceunban", forceunban_command),
        CommandHandler("forcemute", forcemute_command),
        CommandHandler("forceunmute", forceunmute_command),
        CommandHandler("unban", unban_command),
        CommandHandler("mute", mute_command),
        CommandHandler("unmute", unmute_command),
        CommandHandler("dmute", dmute_command),
        CommandHandler("dban", dban_command),
        CommandHandler("muter", muter_command),
        CommandHandler("unmuter", unmuter_command),
        CommandHandler("warn", warn_command),
        CommandHandler("unwarn", unwarn_command),
        CommandHandler("voicechatmgr", voicechatmgr_command),
        CommandHandler("unvoicechatmgr", unvoicechatmgr_command),
        CallbackQueryHandler(close_moderation, pattern="^close_moderation$"),
        CallbackQueryHandler(edit_protection_callback, pattern="^edit_(warn|unmute)_")
    ]
