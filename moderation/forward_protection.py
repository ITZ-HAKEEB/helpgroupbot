import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import is_user_admin
from core.config import OWNER_ID

async def check_forwarded_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MessageHandler to check for forwarded messages and delete them if forward protection is enabled."""
    if not update.message or not update.effective_chat:
        return
        
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Skip private chats
    if update.effective_chat.type == "private":
        return
    
    # Get settings
    settings = get_chat_settings(chat_id)
    
    # Check if forward protection is enabled
    if not settings.get("forward_protection_enabled", False):
        return

    # Check "Apply On" setting
    apply_on = settings.get("forward_protection_apply_on", "members")
    is_admin = user_id == OWNER_ID or await is_user_admin(chat_id, user_id, context)
    
    # Logic for "Apply On"
    if apply_on == "members":
        if is_admin:
            return # Skip admins and owner
    elif apply_on == "admins":
        if not is_admin:
            return # Skip regular members
        if user_id == OWNER_ID:
            return # Still skip owner
    elif apply_on == "everyone":
        if user_id == OWNER_ID:
            return # Still skip owner
    
    # Check if message is forwarded
    # In python-telegram-bot v21+, we need to check if the message has forward_origin attribute
    is_forwarded = False
    
    try:
        # Check for forward_origin (Telegram Bot API 5.0+)
        if hasattr(update.message, 'forward_origin') and update.message.forward_origin:
            is_forwarded = True
    except AttributeError:
        pass
    
    # Legacy checks for older API versions
    if not is_forwarded:
        if hasattr(update.message, 'forward_from') and update.message.forward_from:
            is_forwarded = True
        elif hasattr(update.message, 'forward_from_chat') and update.message.forward_from_chat:
            is_forwarded = True
    
    if is_forwarded:
        try:
            # Delete the forwarded message
            await update.message.delete()
            logging.info(f"Forward Protection: Deleted forwarded message from user {user_id} in chat {chat_id}")
            
            # Notify the user
            from core.config import send_bot_response
            await send_bot_response(
                update, context,
                f"⚠️ User <code>{update.effective_user.id}</code>, forwarded messages are not allowed in this group.",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"Forward Protection: Failed to delete forwarded message from user {user_id} in chat {chat_id}: {e}")

def get_forward_protection_handlers():
    """Returns the handlers for forward protection."""
    return [
        MessageHandler(
            filters.ALL & ~filters.COMMAND & filters.ChatType.GROUPS,
            check_forwarded_messages
        )
    ]
