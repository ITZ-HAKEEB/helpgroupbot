import logging
import logging
import datetime
from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from managers.moderation_manager_mongo import get_user_warns, add_warn, reset_warns
from managers.user_manager_mongo import is_user_admin
from moderation.moderation import ban_user, mute_user, kick_user
from telegram.error import BadRequest
from core.config import delete_message_job

async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edited messages."""
    if not update.edited_message or not update.edited_message.from_user:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    settings = get_chat_settings(chat_id)

    # Check if feature is enabled
    if not settings.get("edit_checks_enabled", False):
        return

    # Check age of message (1 month = 30 days)
    # Only ignore if the message is older than 30 days
    message_date = update.edited_message.date
    if message_date:
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - message_date).days > 30:
            logging.info(f"[EDIT] Ignoring old message edit (ID: {update.edited_message.message_id}, Date: {message_date})")
            return

    # Check target (members or everyone)
    target = settings.get("edit_checks_target", "members")
    is_admin = await is_user_admin(chat_id, user_id, context)
    
    if target == "members" and is_admin:
        return

    # Delete the edited message
    try:
        await update.edited_message.delete()
    except BadRequest as e:
        if "Message to delete not found" not in str(e):
            logging.error(f"Failed to delete edited message: {e}")
            return
    except Exception as e:
        logging.error(f"Error deleting edited message: {e}")
        return

    # Apply penalty
    penalty = settings.get("edit_checks_penalty", "off").lower()
    if penalty == "off":
        return

    # Show only user ID as requested
    user_id_str = f"<code>{user_id}</code>"
    limit = settings.get("edit_checks_warn_limit", 3)
    
    # Always increment warn count for any penalty that isn't 'off'
    current_warns = add_warn(chat_id, user_id)
    
    keyboard = [
        [
            InlineKeyboardButton(colored_button("➕ Add Warn", "red"), callback_data=f"edit_warn_add_{user_id}"),
            InlineKeyboardButton(colored_button("🔄 Reset Warns", "green"), callback_data=f"edit_warn_reset_{user_id}")
        ]
    ]
    
    if current_warns >= limit:
        # Reset warns after penalty
        reset_warns(chat_id, user_id)
        
        if penalty == "mute" or penalty == "warn": # 'warn' defaults to mute in original code
            await mute_user(update, context, user_id, reason="Reached warn limit for editing messages")
            keyboard.insert(0, [InlineKeyboardButton(colored_button("🔊 Unmute", "green"), callback_data=f"edit_unmute_{user_id}")])
            msg_text = f"🚫 User {user_id_str} has been muted for reaching the warn limit (editing messages)."
        elif penalty == "kick":
            await kick_user(update, context, user_id, reason="Reached warn limit for editing messages")
            msg_text = f"👢 User {user_id_str} has been kicked for reaching the warn limit (editing messages)."
        elif penalty == "ban":
            await ban_user(update, context, user_id, reason="Reached warn limit for editing messages")
            msg_text = f"🔨 User {user_id_str} has been banned for reaching the warn limit (editing messages)."
        else:
            msg_text = f"⚠️ User {user_id_str}, edited messages are not allowed! ({current_warns}/{limit})"
    else:
        msg_text = f"⚠️ User {user_id_str}, edited messages are not allowed here! ({current_warns}/{limit})"

    try:
        sent_msg = await context.bot.send_message(
            chat_id, 
            msg_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Auto delete warning message after custom time (default 5 minutes)
        warn_delete_time = settings.get("warning_delete_time", 300)
        if context.job_queue:
            context.job_queue.run_once(
                delete_message_job,
                warn_delete_time,
                data={"chat_id": chat_id, "message_id": sent_msg.message_id}
            )
    except Exception as e:
        logging.error(f"Error sending edit protection warning: {e}")

def get_edit_handlers():
    """Return edit handlers."""
    return [
        MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS, edited_message_handler)
    ]
