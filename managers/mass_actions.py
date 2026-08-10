"""
Manager Mass Actions - kickall, banall, unbanall, muteall, unmuteall, unpinall
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ChatMemberStatus
import re
from managers.settings_manager_mongo import get_chat_settings
from managers.actions import check_admin_permission, check_bot_permission

MASS_CMDS = ["kickall", "banall", "unbanall", "muteall", "unmuteall", "unpinall"]

def confirmation_keyboard(cmd):
    """Create confirmation keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes", callback_data=f"{cmd}_yes"),
         InlineKeyboardButton("No", callback_data=f"{cmd}_no")]
    ])

async def ask_mass_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for confirmation before mass action."""
    cmd = update.message.command[0] if update.message.command else context.args[0] if context.args else None
    if not cmd or cmd not in MASS_CMDS:
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if mass actions are enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_mass_actions_enabled", True):
        return await update.message.reply_text(f"❌ Mass action commands are currently disabled.")
    
    # Permission check
    if cmd == 'unpinall':
        permission = 'can_pin_messages'
    elif cmd in ['kickall', 'banall', 'unbanall']:
        permission = 'can_ban_users'
    else: # muteall, unmuteall
        permission = 'can_restrict_members'
        
    has_perm, error_msg = await check_admin_permission(update, context, permission)
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, permission)
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    await update.message.reply_text(
        f"⚠️ {user.mention_html()}, confirm `{cmd}` for this group?",
        reply_markup=confirmation_keyboard(cmd),
        parse_mode='HTML'
    )

async def handle_mass_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mass action confirmation."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    match = re.match(r'^(kickall|banall|unbanall|muteall|unmuteall|unpinall)_(yes|no)$', data)
    if not match:
        return
    
    cmd, answer = match.groups()
    chat_id = query.message.chat_id
    
    # Permission check
    if cmd == 'unpinall':
        permission = 'can_pin_messages'
    elif cmd in ['kickall', 'banall', 'unbanall']:
        permission = 'can_ban_users'
    else: # muteall, unmuteall
        permission = 'can_restrict_members'
        
    has_perm, error_msg = await check_admin_permission(update, context, permission)
    if not has_perm:
        return await query.answer(error_msg, show_alert=True)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, permission)
    if not has_bot_perm:
        return await query.answer(bot_error_msg, show_alert=True)
    
    if answer == "no":
        return await query.message.edit_text(f"❌ `{cmd}` canceled.", parse_mode='HTML')
    
    await query.message.edit_text(f"⏳ `{cmd}` in progress…", parse_mode='HTML')
    
    try:
        if cmd == "kickall":
            await do_kickall(context.bot, chat_id)
        elif cmd == "banall":
            await do_banall(context.bot, chat_id)
        elif cmd == "unbanall":
            await do_unbanall(context.bot, chat_id)
        elif cmd == "muteall":
            await do_muteall(context.bot, chat_id)
        elif cmd == "unmuteall":
            await do_unmuteall(context.bot, chat_id)
        elif cmd == "unpinall":
            await do_unpinall(context.bot, chat_id)
        
        await query.message.edit_text(f"✅ `{cmd}` completed.", parse_mode='HTML')
    except Exception as e:
        await query.message.edit_text(f"❌ Error during `{cmd}`:\n{str(e)}", parse_mode='HTML')

async def do_kickall(bot, chat_id):
    """Kick all non-admin members."""
    kicked, errors = 0, 0
    async for member in bot.get_chat_members(chat_id):
        if member.user.is_bot or member.status == 'creator':
            continue
        try:
            await bot.ban_chat_member(chat_id, member.user.id)
            await asyncio.sleep(0.1)
            await bot.unban_chat_member(chat_id, member.user.id)
            kicked += 1
        except:
            errors += 1
        await asyncio.sleep(0.05)
    await bot.send_message(chat_id, f"Kicked: {kicked}\nFailures: {errors}")

async def do_banall(bot, chat_id):
    """Ban all non-admin members."""
    banned, errors = 0, 0
    async for member in bot.get_chat_members(chat_id):
        if member.user.is_bot or member.status == 'creator':
            continue
        try:
            await bot.ban_chat_member(chat_id, member.user.id)
            banned += 1
        except:
            errors += 1
        await asyncio.sleep(0.05)
    await bot.send_message(chat_id, f"Banned: {banned}\nFailures: {errors}")

async def do_unbanall(bot, chat_id):
    """Unban all banned members."""
    unbanned, errors = 0, 0
    # Note: Getting banned members requires admin privileges
    try:
        async for member in bot.get_chat_members(chat_id):
            if member.status == 'kicked':
                try:
                    await bot.unban_chat_member(chat_id, member.user.id)
                    unbanned += 1
                except:
                    errors += 1
                await asyncio.sleep(0.05)
    except:
        pass
    await bot.send_message(chat_id, f"Unbanned: {unbanned}\nFailures: {errors}")

async def do_muteall(bot, chat_id):
    """Mute all non-admin members."""
    muted, errors = 0, 0
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_invite_users=False,
    )
    async for member in bot.get_chat_members(chat_id):
        if member.user.is_bot or member.status in ['administrator', 'creator']:
            continue
        try:
            await bot.restrict_chat_member(chat_id, member.user.id, permissions)
            muted += 1
        except:
            errors += 1
        await asyncio.sleep(0.05)
    await bot.send_message(chat_id, f"Muted: {muted}\nFailures: {errors}")

async def do_unmuteall(bot, chat_id):
    """Unmute all muted members."""
    unmuted, errors = 0, 0
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
    )
    async for member in bot.get_chat_members(chat_id):
        if member.user.is_bot or member.status in ['administrator', 'creator']:
            continue
        try:
            await bot.restrict_chat_member(chat_id, member.user.id, permissions)
            unmuted += 1
        except:
            errors += 1
        await asyncio.sleep(0.05)
    await bot.send_message(chat_id, f"Unmuted: {unmuted}\nFailures: {errors}")

async def do_unpinall(bot, chat_id):
    """Unpin all messages."""
    try:
        await bot.unpin_all_chat_messages(chat_id)
        await bot.send_message(chat_id, "Unpinned all messages.")
    except Exception as e:
        await bot.send_message(chat_id, f"Failed to unpin messages:\n{str(e)}")

def get_mass_actions_handlers():
    """Return mass actions handlers."""
    handlers = []
    for cmd in MASS_CMDS:
        handlers.append(CommandHandler(cmd, ask_mass_confirm))
    
    handlers.append(CallbackQueryHandler(handle_mass_confirm, pattern=r'^(kickall|banall|unbanall|muteall|unmuteall|unpinall)_(yes|no)$'))
    return handlers
