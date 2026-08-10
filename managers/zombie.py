"""
Manager Zombie - Clean deleted accounts
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
import html
import logging
from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ChatMemberStatus
from managers.settings_manager_mongo import get_chat_settings
from core.database import get_collection, COLLECTIONS
from managers.actions import check_admin_permission, check_bot_permission

chatQueue = set()
stopProcess = {}

async def get_total_zombies_count(bot):
    """Get total count of deleted accounts across all groups."""
    try:
        settings_col = get_collection(COLLECTIONS["settings"])
        if settings_col is None:
            return {"total_zombies": 0, "groups_checked": 0}
        
        # Get all group chat IDs
        groups = list(settings_col.find({}))
        total_zombies = 0
        groups_checked = 0
        
        for group in groups:
            chat_id = int(group["chat_id"])
            try:
                # PTB Bots cannot get all members easily. 
                # This function is not possible with PTB and should be removed or refactored to use MTProto.
                zombie_count = 0
                # async for member in bot.get_chat_members(chat_id):
                #     if member.user.is_deleted:
                #         zombie_count += 1
                
                total_zombies += zombie_count
                groups_checked += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.warning(f"Could not check group {chat_id}: {e}")
                continue
        
        return {"total_zombies": total_zombies, "groups_checked": groups_checked}
    except Exception as e:
        logging.error(f"Error counting zombies: {e}")
        return {"total_zombies": 0, "groups_checked": 0}

async def get_total_blocked_count(bot):
    """Get total count of banned/blocked members across all groups."""
    try:
        from core.database import COLLECTIONS
        
        # Get moderation collection
        moderation_col = get_collection(COLLECTIONS.get("moderation", "moderation"))
        if moderation_col is None:
            return {"total_blocked": 0, "groups_with_bans": 0}
        
        total_blocked = 0
        groups_with_bans = 0
        
        # Count all banned users across all groups
        all_moderation = list(moderation_col.find({}))
        for mod_doc in all_moderation:
            if "banned_users" in mod_doc and mod_doc["banned_users"]:
                banned_list = mod_doc["banned_users"]
                if isinstance(banned_list, list):
                    total_blocked += len(banned_list)
                    groups_with_bans += 1
        
        return {"total_blocked": total_blocked, "groups_with_bans": groups_with_bans}
    except Exception as e:
        logging.error(f"Error counting blocked members: {e}")
        return {"total_blocked": 0, "groups_with_bans": 0}

def mention_html(user):
    """Create HTML mention."""
    name = html.escape((user.first_name or "User").strip())
    return f'<a href="tg://user?id={user.id}">{name}</a>'

async def scan_deleted_members(bot, chat_id) -> List:
    """Scan for deleted accounts (Not possible for bots in PTB)."""
    return []
    # users = []
    # try:
    #     async for member in bot.get_chat_members(chat_id):
    #         if member.user.is_deleted:
    #             users.append(member.user)
    # except Exception:
    #     return []
    # return users

async def scan_bots(bot, chat_id) -> List:
    """Scan for bots."""
    bots = []
    try:
        async for member in bot.get_chat_members(chat_id):
            if member.user.is_bot:
                bots.append(member.user)
    except Exception:
        return []
    return bots

def generate_channel_keyboard(chat_id, user_id):
    """Generate keyboard for channel scan."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Remove Zombies", callback_data=f"clean_zombies:{chat_id}:{user_id}"),
            InlineKeyboardButton("Remove Bots", callback_data=f"clean_bots:{chat_id}:{user_id}")
        ],
        [
            InlineKeyboardButton("Close", callback_data=f"close_panel:{user_id}")
        ]
    ])

def generate_group_keyboard(chat_id):
    """Generate keyboard for group scan."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Clean Zombies", callback_data=f"confirm_zombies:{chat_id}")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_zombies")]
    ])

async def zombie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /zombies command."""
    user_id = update.effective_user.id
    args = update.message.text.split()
    target_id = None
    
    # Check if command is enabled
    chat = update.effective_chat
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_zombie_enabled", True):
        return await update.message.reply_text("❌ The /zombies command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_ban_users')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_restrict_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    if len(args) > 1:
        try:
            target_id = int(args[1])
        except ValueError:
            return await update.message.reply_text(
                "<i>Invalid ID. Use numeric format like <code>-1001234567890</code></i>",
                parse_mode='HTML'
            )
    
    if target_id:
        await zombie_channel_scan(update, context, target_id, user_id)
    else:
        chat = update.effective_chat
        if chat.type not in ['group', 'supergroup']:
            return await update.message.reply_text(
                "<i>Use this command in a group or with a channel ID.</i>\n\n"
                "<b>Example:</b> <code>/zombies -1002014937805</code>",
                parse_mode='HTML'
            )
        await zombie_group_scan(update, context)

async def zombie_channel_scan(update, context, channel_id, user_id):
    """Scan channel for zombies."""
    status_msg = await update.message.reply_text("<i>Checking access...</i>", parse_mode='HTML')
    
    try:
        chat = await context.bot.get_chat(channel_id)
        members_count = chat.members_count or 0
    except:
        return await status_msg.edit_text(
            "<i>Access Denied</i>\n\n"
            "<b>Add me first, give full rights, then try again.</b>",
            parse_mode='HTML'
        )
    
    # Check if bot is admin
    try:
        bot_member = await chat.get_member(context.bot.id)
        if bot_member.status != 'administrator':
            return await status_msg.edit_text(
                "<i>Access Denied</i>\n\n"
                "<b>I need admin rights with ban permission in the channel.</b>",
                parse_mode='HTML'
            )
    except:
        return await status_msg.edit_text(
            "<i>Access Denied</i>\n\n"
            "<b>I need admin rights with ban permission in the channel.</b>",
            parse_mode='HTML'
        )
    
    zombies = await scan_deleted_members(context.bot, channel_id)
    bots = await scan_bots(context.bot, channel_id)
    
    keyboard = generate_channel_keyboard(channel_id, user_id)
    
    await status_msg.edit_text(
        f"<b>Access</b>\n"
        f"<b>Channel:</b> {html.escape(chat.title)}\n"
        f"<b>Members:</b> <code>{members_count}</code>\n"
        f"<b>Bots:</b> <code>{len(bots)}</code>\n"
        f"<b>Zombies:</b> <code>{len(zombies)}</code>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def zombie_group_scan(update, context):
    """Scan group for zombies."""
    chat = update.effective_chat
    
    # Check if bot is admin
    try:
        bot_member = await chat.get_member(context.bot.id)
        if bot_member.status != 'administrator':
            return await update.message.reply_text("<i>I need admin rights to scan.</i>", parse_mode='HTML')
    except:
        return
    
    zombies = await scan_deleted_members(context.bot, chat.id)
    if not zombies:
        return await update.message.reply_text("<i>No zombies found.</i>", parse_mode='HTML')
    
    total = len(zombies)
    keyboard = generate_group_keyboard(chat.id)
    
    await update.message.reply_text(
        f"<i>Found <code>{total}</code> zombies.</i>\n\n"
        "Remove them?",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def clean_zombies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle zombie cleanup callback."""
    query = update.callback_query
    await query.answer()
    
    try:
        _, chat_id_str, user_id_str = query.data.split(":")
        chat_id = int(chat_id_str)
        user_id = int(user_id_str)
    except:
        return await query.answer("Invalid data.", show_alert=True)
    
    if query.from_user.id != user_id:
        return await query.answer("This panel is not for you.", show_alert=True)
    
    if chat_id in chatQueue:
        return await query.answer("Cleanup already in progress.", show_alert=True)
    
    chatQueue.add(chat_id)
    stopProcess[chat_id] = False
    
    zombies = await scan_deleted_members(context.bot, chat_id)
    total = len(zombies)
    
    if total == 0:
        chatQueue.discard(chat_id)
        return await query.answer("No zombies to remove.", show_alert=True)
    
    status = await query.edit_message_text(f"<i>Removing {total} zombies...</i>", parse_mode='HTML')
    
    removed = 0
    batch_size = 15
    for i in range(0, len(zombies), batch_size):
        if stopProcess.get(chat_id, False):
            break
        
        batch = zombies[i:i + batch_size]
        for zombie in batch:
            try:
                await context.bot.ban_chat_member(chat_id, zombie.id)
                removed += 1
            except:
                pass
            await asyncio.sleep(0.1)
        
        await status.edit_text(f"<i>Removed {removed}/{total} zombies...</i>", parse_mode='HTML')
    
    chatQueue.discard(chat_id)
    if chat_id in stopProcess:
        del stopProcess[chat_id]
    
    keyboard = generate_channel_keyboard(chat_id, user_id)
    await status.edit_text(
        f"<b>Zombies cleaned!</b>\n"
        f"<code>{removed}</code> out of <code>{total}</code> removed.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def cancel_zombie_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel zombie cleanup."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    stopProcess[chat_id] = True
    await query.edit_message_text("<i>Cancelled.</i>", parse_mode='HTML')

async def close_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close panel."""
    query = update.callback_query
    await query.answer()
    
    try:
        _, user_id_str = query.data.split(":")
        user_id = int(user_id_str)
    except:
        return await query.answer("Error.", show_alert=True)
    
    if query.from_user.id != user_id:
        return await query.answer("Not your panel.", show_alert=True)
    
    await query.message.delete()

def get_zombie_handlers():
    """Return zombie handlers."""
    return [
        CommandHandler("zombies", zombie_handler),
        CallbackQueryHandler(clean_zombies_callback, pattern=r'^clean_zombies:'),
        CallbackQueryHandler(cancel_zombie_cleanup, pattern=r'^cancel_zombies$'),
        CallbackQueryHandler(close_panel, pattern=r'^close_panel:'),
    ]
