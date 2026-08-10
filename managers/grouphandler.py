"""
Manager Group Handler - Pin, Unpin, Set Photo, Title, Description
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ChatMemberStatus
from managers.settings_manager_mongo import get_chat_settings
from core.config import delete_message_job
from managers.actions import check_admin_permission, check_bot_permission

async def is_group_admin(chat, user_id):
    """Check if user is admin with required permissions."""
    member = await chat.get_member(user_id)
    if hasattr(member, 'privileges'):
        return member.privileges
    return False

async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pin a message."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_pin_enabled", True):
        return await update.message.reply_text("❌ The /pin command is currently disabled.")
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to pin it!")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_pin_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_pin_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    try:
        await update.message.reply_to_message.pin()
        
        msg_link = update.message.reply_to_message.link if update.message.reply_to_message.link else None
        text = f"**Successfully pinned message!**\n\n"
        text += f"**Chat:** {chat.title}\n"
        text += f"**Admin:** {user.mention_html()}"
        
        keyboard = None
        if msg_link:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📝 View Message", url=msg_link)]])
        
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)
    except Exception as e:
        await update.message.reply_text(f"**Failed to pin message:**\n`{str(e)}`", parse_mode='HTML')

async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unpin a message."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a message to unpin it!")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_pin_messages')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_pin_messages')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    try:
        await update.message.reply_to_message.unpin()
        
        text = f"**Successfully unpinned message!**\n\n"
        text += f"**Chat:** {chat.title}\n"
        text += f"**Admin:** {user.mention_html()}"
        
        await update.message.reply_text(text, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"**Failed to unpin message:**\n`{str(e)}`", parse_mode='HTML')

async def set_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group photo."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to a photo or document.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_change_info')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_change_info')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    target = update.message.reply_to_message
    
    try:
        if target.photo:
            file_id = target.photo[-1].file_id
            await context.bot.set_chat_photo(chat.id, photo=file_id)
            await update.message.reply_text(f"**Group photo updated successfully!**\nBy {user.mention_html()}", parse_mode='HTML')
        elif target.document and target.document.mime_type.startswith('image/'):
            file_id = target.document.file_id
            await context.bot.set_chat_photo(chat.id, photo=file_id)
            await update.message.reply_text(f"**Group photo updated successfully!**\nBy {user.mention_html()}", parse_mode='HTML')
        else:
            await update.message.reply_text("**Please reply with an image (photo or image document).**", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"**Failed to set photo:**\n`{str(e)}`", parse_mode='HTML')

async def remove_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove group photo."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_change_info')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_change_info')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    try:
        await context.bot.delete_chat_photo(chat.id)
        await update.message.reply_text(f"**Group photo removed!**\nBy {user.mention_html()}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"**Failed to remove photo:**\n`{str(e)}`", parse_mode='HTML')

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group title."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_change_info')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_change_info')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    title = None
    if context.args:
        title = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        title = update.message.reply_to_message.text.strip()
    
    if not title:
        return await update.message.reply_text("**Please provide a new title.**", parse_mode='HTML')
    
    try:
        await context.bot.set_chat_title(chat.id, title)
        msg = await update.message.reply_text(f"**Group name changed to:** {title}\nBy {user.mention_html()}", parse_mode='HTML')
        
        # Schedule deletion for both messages in 15 seconds
        if context.job_queue:
            context.job_queue.run_once(
                delete_message_job,
                15,
                data={"chat_id": chat.id, "message_id": msg.message_id}
            )
            context.job_queue.run_once(
                delete_message_job,
                15,
                data={"chat_id": chat.id, "message_id": update.message.message_id}
            )
    except Exception as e:
        await update.message.reply_text(f"**Failed to set title:**\n`{str(e)}`", parse_mode='HTML')

async def set_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group description."""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("This command works only in groups!")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_change_info')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_change_info')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    description = None
    if context.args:
        description = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        description = update.message.reply_to_message.text.strip()
    
    if not description:
        return await update.message.reply_text("**Please provide a new description.**", parse_mode='HTML')
    
    try:
        await context.bot.set_chat_description(chat.id, description)
        await update.message.reply_text(f"**Group description updated!**\nBy {user.mention_html()}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"**Failed to set description:**\n`{str(e)}`", parse_mode='HTML')

def get_grouphandler_handlers():
    """Return all group handler commands."""
    return [
        CommandHandler("pin", pin_message),
        CommandHandler("unpin", unpin_message),
        CommandHandler("setphoto", set_photo),
        CommandHandler("removephoto", remove_photo),
        CommandHandler("settitle", set_title),
        CommandHandler("setdescription", set_description),
    ]
