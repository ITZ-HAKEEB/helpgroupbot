"""
Manager Purge - Delete messages in bulk
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import Forbidden, BadRequest
from managers.settings_manager_mongo import get_chat_settings
from managers.actions import check_admin_permission, check_bot_permission
from managers.staff_manager_mongo import increment_staff_stat

def divide_chunks(l, n=100):
    """Divide list into chunks."""
    for i in range(0, len(l), n):
        yield l[i: i + n]

async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Purge messages from replied message to current."""
    chat = update.effective_chat
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_purge_enabled", True):
        return await update.message.reply_text("❌ The /purge command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("I can't purge messages in a basic group. Please convert it to a supergroup.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to start purge!")
    
    message_ids = list(range(update.message.reply_to_message.id, update.message.id))
    m_list = list(divide_chunks(message_ids))
    
    try:
        for plist in m_list:
            try:
                await context.bot.delete_messages(chat.id, plist)
                await asyncio.sleep(0.2)
            except Exception as e:
                if 'FloodWait' in str(type(e)):
                    await asyncio.sleep(int(str(e).split()[-1]))
        
        await update.message.delete()
        count = len(message_ids)
        confirm = await update.message.reply_text(f"✅ | **Deleted `{count}` messages.**", parse_mode='Markdown')
        
        # Record stats
        if update.effective_user:
            increment_staff_stat(chat.id, update.effective_user.id, "purge", count)
            
        await asyncio.sleep(3)
        await confirm.delete()
    except Forbidden:
        await update.message.reply_text("I can't delete messages in this chat. Maybe too old or no rights.")
    except Exception as e:
        await update.message.reply_text(f"**Error occurred:**\n<code>{str(e)}</code>", parse_mode='HTML')

async def spurge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent purge (delete command message too)."""
    chat = update.effective_chat
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("I can't purge messages in a basic group. Please convert it to a supergroup.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to start purge!")
    
    message_ids = list(range(update.message.reply_to_message.id, update.message.id))
    m_list = list(divide_chunks(message_ids))
    
    try:
        for plist in m_list:
            try:
                await context.bot.delete_messages(chat.id, plist)
                await asyncio.sleep(0.2)
            except Exception as e:
                if 'FloodWait' in str(type(e)):
                    await asyncio.sleep(int(str(e).split()[-1]))
        
        await update.message.delete()
        
        # Record stats
        if update.effective_user:
            count = len(message_ids)
            increment_staff_stat(chat.id, update.effective_user.id, "purge", count)
    except Forbidden:
        await update.message.reply_text("I can't delete messages in this chat.")
    except Exception as e:
        await update.message.reply_text(f"**Error occurred:**\n<code>{str(e)}</code>", parse_mode='HTML')

async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a single message."""
    chat = update.effective_chat
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("I can't delete messages in a basic group.")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("What do you want to delete?")
    
    try:
        await update.message.delete()
        await update.message.reply_to_message.delete()
    except Exception as e:
        await update.message.reply_text(f"**Failed to delete message:**\n<code>{str(e)}</code>", parse_mode='HTML')

async def purge_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete all messages in the group."""
    chat = update.effective_chat
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)

    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in supergroups.")

    # Confirmation logic if not already confirmed
    if not context.args or context.args[0] != "confirm":
        return await update.message.reply_text(
            "⚠️ **WARNING**\n\n"
            "This will attempt to delete ALL messages in this group. This action cannot be undone.\n\n"
            "Type `/purgeall confirm` to proceed.",
            parse_mode='Markdown'
        )

    status_msg = await update.message.reply_text("🚀 **Starting global purge...**", parse_mode='Markdown')
    
    current_id = update.message.id
    deleted_count = 0
    
    # We delete in batches of 100 backwards
    # This will cover all messages including every type of service message
    try:
        consecutive_errors = 0
        for i in range(current_id, 0, -100):
            batch = list(range(max(1, i - 100), i))
            try:
                await context.bot.delete_messages(chat.id, batch)
                deleted_count += len(batch)
                consecutive_errors = 0
                if deleted_count % 500 == 0:
                    await status_msg.edit_text(f"🚀 **Purging...**\nDeleted: `{deleted_count}` messages", parse_mode='Markdown')
                await asyncio.sleep(0.2) # Optimized for speed
            except BadRequest as e:
                err = str(e)
                if "Message to delete not found" in err or "Message can't be deleted" in err:
                    consecutive_errors += 1
                    # Stop if 5000 messages in a row are missing/undeletable
                    if consecutive_errors > 50:
                        break
                    continue
                elif "Flood control exceeded" in err:
                    # Handle flood wait
                    import re
                    seconds = re.search(r'wait (\d+)', err)
                    wait_time = int(seconds.group(1)) if seconds else 30
                    await asyncio.sleep(wait_time + 1)
                    continue
                else:
                    # Other errors like "Chat not found" or permissions
                    break
            except Exception:
                break
                
        await status_msg.edit_text(f"✅ **Global purge complete!**\nTotal deleted: `{deleted_count}` messages\nAll service messages, VC invites, and joins have been cleared.", parse_mode='Markdown')
        
        # Record stats
        if update.effective_user:
            increment_staff_stat(chat.id, update.effective_user.id, "purge", deleted_count)
            
        await asyncio.sleep(5)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ **Purge interrupted:**\n`{str(e)}`", parse_mode='Markdown')

async def purge_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete all messages of a specific user in the group."""
    chat = update.effective_chat
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
  
    from managers.user_manager_mongo import get_user_id
    target_user_id, target_user_name = await get_user_id(update, context)
    if not target_user_id:
        return await update.message.reply_text("Please reply to a user or provide a user ID/username to purge their messages.")

    status_msg = await update.message.reply_text(f"🔍 **Searching and deleting messages of {target_user_name}...**", parse_mode='Markdown')
    
    try:
        member = await context.bot.get_chat_member(chat.id, target_user_id)
        
        # If user is owner, we cannot demote them. Must scan manually or use other methods.
        if member.status == 'creator':
            await status_msg.edit_text(f"⚠️ **Cannot demote the owner.** Scanning manually is not supported yet for the owner. "
                                    f"I've cleared what I could from my cache.", parse_mode='Markdown')
            await asyncio.sleep(5)
            await status_msg.delete()
            return

        is_admin = member.status == 'administrator'
        
        if is_admin:
            # Check bot permissions to demote and re-promote
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if not (bot_member.status == 'creator' or (bot_member.status == 'administrator' and bot_member.can_promote_members)):
                await status_msg.edit_text("❌ I need 'Add New Admins' permission to purge an admin's messages.", parse_mode='Markdown')
                return

            # Store current admin rights to restore later
            rights = {
                'can_change_info': member.can_change_info,
                'can_delete_messages': member.can_delete_messages,
                'can_restrict_members': member.can_restrict_members,
                'can_invite_users': member.can_invite_users,
                'can_pin_messages': member.can_pin_messages,
                'can_post_stories': member.can_post_stories,
                'can_edit_stories': member.can_edit_stories,
                'can_delete_stories': member.can_delete_stories,
                'can_manage_video_chats': member.can_manage_video_chats,
                'can_promote_members': member.can_promote_members,
                'is_anonymous': member.is_anonymous,
                'custom_title': member.custom_title
            }
            
            await status_msg.edit_text(f"🛠 **Temporarily demoting admin {target_user_name} to purge messages...**", parse_mode='Markdown')
            
            # Demote
            await context.bot.promote_chat_member(chat.id, target_user_id, can_change_info=False)
            await asyncio.sleep(0.3)
            
            # Ban with revoke
            await context.bot.ban_chat_member(chat.id, target_user_id, revoke_messages=True)
            await asyncio.sleep(0.3)
            
            # Unban
            await context.bot.unban_chat_member(chat.id, target_user_id)
            await asyncio.sleep(0.3)
            
            # Re-promote
            await context.bot.promote_chat_member(chat.id, target_user_id, **rights)
            
            await status_msg.edit_text(f"✅ **Purged all messages of admin {target_user_name} and restored their rights.**", parse_mode='Markdown')
            
        else:
            # Regular member
            await context.bot.ban_chat_member(chat.id, target_user_id, revoke_messages=True)
            await context.bot.unban_chat_member(chat.id, target_user_id)
            await status_msg.edit_text(f"✅ **Purged all messages of {target_user_name}.**", parse_mode='Markdown')
            
        await asyncio.sleep(5)
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during purge:**\n`{str(e)}`", parse_mode='Markdown')

async def purge_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    """Delete all service/event messages in the group."""
    if chat_id is None:
        chat = update.effective_chat
        chat_id = chat.id
    else:
        chat = await context.bot.get_chat(chat_id)
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_delete_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_delete_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)

    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in supergroups.")

    status_msg = await update.message.reply_text("🚀 **Starting service messages purge...**", parse_mode='Markdown')
    
    current_id = update.message.id if update.message else 0
    deleted_count = 0
    
    try:
        # We delete in batches of 100 backwards
        # Service messages are typically lower message IDs
        consecutive_errors = 0
        for i in range(current_id, 0, -100):
            batch = list(range(max(1, i - 100), i))
            try:
                await context.bot.delete_messages(chat_id, batch)
                deleted_count += len(batch)
                consecutive_errors = 0
                if deleted_count % 500 == 0:
                    await status_msg.edit_text(f"🚀 **Purging service messages...**\nDeleted: `{deleted_count}` messages", parse_mode='Markdown')
                await asyncio.sleep(0.2)
            except BadRequest as e:
                err = str(e)
                if "Message to delete not found" in err or "Message can't be deleted" in err:
                    consecutive_errors += 1
                    # Stop if 5000 messages in a row are missing/undeletable
                    if consecutive_errors > 50:
                        break
                    continue
                elif "Flood control exceeded" in err:
                    # Handle flood wait
                    import re
                    seconds = re.search(r'wait (\d+)', err)
                    wait_time = int(seconds.group(1)) if seconds else 30
                    await asyncio.sleep(wait_time + 1)
                    continue
                else:
                    # Other errors like "Chat not found" or permissions
                    break
            except Exception:
                break
                
        await status_msg.edit_text(f"✅ **Service messages purge complete!**\nTotal deleted: `{deleted_count}` messages\nAll service messages, VC invites, and joins have been cleared.", parse_mode='Markdown')
        
        # Record stats
        if update.effective_user:
            increment_staff_stat(chat_id, update.effective_user.id, "purge", deleted_count)
            
        await asyncio.sleep(5)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ **Purge interrupted:**\n`{str(e)}`", parse_mode='Markdown')

def get_purge_handlers():
    """Return purge handlers."""
    return [
        CommandHandler("purge", purge),
        CommandHandler("spurge", spurge),
        CommandHandler("del", delete_msg),
        CommandHandler(["purgeall", "cleanall"], purge_all),
        CommandHandler(["purgeuser", "delalluser"], purge_user_messages),
        CommandHandler(["epurge", "cleanevent"], purge_service_messages),
    ]
