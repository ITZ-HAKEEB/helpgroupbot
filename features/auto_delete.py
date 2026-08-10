import logging
import re
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters
from managers.settings_manager_mongo import get_chat_settings, update_chat_setting
from managers.user_manager_mongo import is_user_admin

def parse_duration(duration_str):
    """
    Parse a duration string like '1h 30m 10s' into total seconds.
    Supported units: h (hours), m (minutes), s (seconds).
    """
    if not duration_str:
        return None
        
    total_seconds = 0
    # Match patterns like '10h', '5m', '30s'
    matches = re.findall(r'(\d+)\s*([hms])', duration_str.lower())
    
    if not matches:
        # Try if it's just a number (default to seconds)
        try:
            return int(duration_str)
        except ValueError:
            return None
            
    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
            
    return total_seconds

def format_duration(seconds):
    """Format seconds into a human-readable duration string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
        
    return " ".join(parts)

async def delete_msg_job(context: ContextTypes.DEFAULT_TYPE):
    """Job that deletes a message after a delay."""
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)
    except Exception as e:
        # Ignore if message is already deleted or bot has no permission
        pass

async def auto_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically schedules deletion for every message in the group based on settings."""
    if not update.message:
        return
        
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    
    if not settings.get("auto_delete_enabled", False):
        return

    # Check if message type should be deleted
    is_sticker = bool(update.message.sticker)
    is_media = bool(update.message.photo or update.message.video or update.message.document or 
                   update.message.audio or update.message.voice or update.message.video_note or 
                   update.message.animation)
    is_text = bool(update.message.text and not update.message.caption)

    should_delete = False
    if is_sticker and settings.get("auto_delete_stickers", True):
        should_delete = True
    elif is_media and settings.get("auto_delete_media", True):
        should_delete = True
    elif is_text and settings.get("auto_delete_text", True):
        should_delete = True
    # If it's a media with caption, it counts as media
    elif update.message.caption and settings.get("auto_delete_media", True):
        should_delete = True

    if not should_delete:
        return

    delay = settings.get("auto_delete_time", 60) # seconds
    
    # Schedule deletion job
    logging.info(f"Scheduling deletion for message {update.message.message_id} in {chat_id} in {delay}s")
    context.job_queue.run_once(
        delete_msg_job, 
        when=delay, 
        chat_id=chat_id, 
        data=update.message.message_id,
        name=f"delete_{chat_id}_{update.message.message_id}"
    )

async def self_destruct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to toggle self-destruction settings."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ You must be an admin to use this command.")
        return

    if not context.args:
        settings = get_chat_settings(chat_id)
        status = "Enabled ✅" if settings.get("auto_delete_enabled") else "Disabled ❌"
        text_status = "Enabled ✅" if settings.get("auto_delete_text") else "Disabled ❌"
        sticker_status = "Enabled ✅" if settings.get("auto_delete_stickers") else "Disabled ❌"
        media_status = "Enabled ✅" if settings.get("auto_delete_media") else "Disabled ❌"
        time_str = format_duration(settings.get("auto_delete_time", 60))
        
        help_text = (
            f"🚀 <b>Message Self-Destruction</b>\n\n"
            f"• <b>Overall:</b> {status}\n"
            f"• <b>Timer:</b> {time_str}\n"
            f"• <b>Text Messages:</b> {text_status}\n"
            f"• <b>Stickers:</b> {sticker_status}\n"
            f"• <b>Media:</b> {media_status}\n\n"
            f"<b>Commands:</b>\n"
            f"» /selfdestruct <code>on|off</code> - Toggle feature\n"
            f"» /selfdestruct <code>text|sticker|media</code> <code>on|off</code> - Toggle types\n"
            f"» /selfdestructtime <code>1h 30m 10s</code> - Set timer"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
        return

    action = context.args[0].lower()
    
    if action in ['on', 'enable', 'yes', 'true']:
        update_chat_setting(chat_id, "auto_delete_enabled", True)
        await update.message.reply_text("✅ Message self-destruction has been <b>enabled</b>.", parse_mode='HTML')
    elif action in ['off', 'disable', 'no', 'false']:
        update_chat_setting(chat_id, "auto_delete_enabled", False)
        await update.message.reply_text("❌ Message self-destruction has been <b>disabled</b>.", parse_mode='HTML')
    elif action in ['text', 'sticker', 'media']:
        if len(context.args) < 2:
            await update.message.reply_text(f"Usage: /selfdestruct {action} on/off")
            return
        
        state = context.args[1].lower()
        enabled = state in ['on', 'enable', 'yes', 'true']
        
        setting_key = f"auto_delete_{action if action != 'sticker' else 'stickers'}"
        if action == 'text': setting_key = "auto_delete_text"
        elif action == 'sticker': setting_key = "auto_delete_stickers"
        elif action == 'media': setting_key = "auto_delete_media"
        
        update_chat_setting(chat_id, setting_key, enabled)
        status_text = "enabled" if enabled else "disabled"
        await update.message.reply_text(f"✅ Self-destruction for <b>{action}</b> has been <b>{status_text}</b>.", parse_mode='HTML')
    else:
        await update.message.reply_text("Invalid argument. Use on/off or text/sticker/media on/off.")

async def self_destruct_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to set self-destruction time."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ You must be an admin to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /selfdestructtime 1h 30m 10s")
        return

    time_str = " ".join(context.args)
    seconds = parse_duration(time_str)
    
    if seconds is None or seconds <= 0:
        await update.message.reply_text("❌ Invalid time format. Please use something like <code>1h 30m 10s</code> or <code>60s</code>.", parse_mode='HTML')
        return

    # Limit to reasonable time (e.g., 1 week)
    if seconds > 604800:
        await update.message.reply_text("❌ Timer cannot be longer than 1 week.")
        return

    update_chat_setting(chat_id, "auto_delete_time", seconds)
    await update.message.reply_text(f"✅ Message self-destruction timer set to: <b>{format_duration(seconds)}</b>", parse_mode='HTML')

def get_auto_delete_handlers():
    """Return handlers for auto-deletion."""
    return [
        CommandHandler("selfdestruct", self_destruct_command),
        CommandHandler("selfdestructtime", self_destruct_time_command),
        MessageHandler((filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP) & ~filters.COMMAND & filters.ALL, auto_delete_handler)
    ]
