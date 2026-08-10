"""
Anti-Flood Module - Detect and penalize message flooding
"""

import logging
import time
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import is_user_admin
from core.config import OWNER_ID

# In-memory storage for flood tracking: {chat_id: {user_id: {"times": [timestamps], "msg_ids": [message_ids]}}}
FLOOD_TRACKER = {}

async def handle_antiflood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles anti-flood detection and penalties."""
    if not update.effective_chat or not update.effective_user or not update.effective_message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_id = update.effective_message.message_id
    
    settings = get_chat_settings(chat_id)
    if not settings.get("antiflood_enabled", False):
        return

    # Check "Apply On" setting
    apply_on = settings.get("antiflood_apply_on", "members")
    if apply_on == "members":
        # Skip admins and owner if apply_on is members
        if user_id == OWNER_ID or await is_user_admin(chat_id, user_id, context):
            return
    # If apply_on is everyone, we don't skip (except for the bot itself)
    if user_id == context.bot.id:
        return

    limit = settings.get("antiflood_limit", 5)
    window = settings.get("antiflood_window", 3)
    penalty = settings.get("antiflood_penalty", "mute")
    
    now = time.time()
    
    # Initialize tracker for chat if not exists
    if chat_id not in FLOOD_TRACKER:
        FLOOD_TRACKER[chat_id] = {}
    
    # Initialize user data if not exists
    if user_id not in FLOOD_TRACKER[chat_id]:
        FLOOD_TRACKER[chat_id][user_id] = {"times": [], "msg_ids": []}
    
    user_data = FLOOD_TRACKER[chat_id][user_id]
    user_data["times"].append(now)
    user_data["msg_ids"].append(message_id)
    
    # Remove old data outside the window
    valid_indices = [i for i, t in enumerate(user_data["times"]) if now - t <= window]
    user_data["times"] = [user_data["times"][i] for i in valid_indices]
    user_data["msg_ids"] = [user_data["msg_ids"][i] for i in valid_indices]
    
    # Check if limit exceeded
    if len(user_data["times"]) >= limit:
        # Collect all messages to delete
        messages_to_delete = list(user_data["msg_ids"])
        
        # Clear tracker for this user to avoid repeat penalties for the same flood
        FLOOD_TRACKER[chat_id][user_id] = {"times": [], "msg_ids": []}
        
        mention = f"User <code>{user_id}</code>"
        
        try:
            # 1. Apply penalty
            if penalty == "warn":
                await context.bot.send_message(
                    chat_id,
                    f"⚠️ {mention}, please stop flooding! You are sending messages too fast.",
                    parse_mode='HTML'
                )
            elif penalty == "mute":
                await context.bot.restrict_chat_member(
                    chat_id, 
                    user_id, 
                    permissions=ChatPermissions(can_send_messages=False)
                )
                await context.bot.send_message(
                    chat_id,
                    f"🔇 {mention} has been muted for flooding.",
                    parse_mode='HTML'
                )
            elif penalty == "kick":
                await context.bot.ban_chat_member(chat_id, user_id)
                await context.bot.unban_chat_member(chat_id, user_id)
                await context.bot.send_message(
                    chat_id,
                    f"👞 {mention} has been kicked for flooding.",
                    parse_mode='HTML'
                )
            elif penalty == "ban":
                await context.bot.ban_chat_member(chat_id, user_id)
                await context.bot.send_message(
                    chat_id,
                    f"🚫 {mention} has been banned for flooding.",
                    parse_mode='HTML'
                )
            
            # 2. Delete ALL flooding messages
            for m_id in messages_to_delete:
                try:
                    await context.bot.delete_message(chat_id, m_id)
                except:
                    pass
            
        except Exception as e:
            logging.error(f"Error applying antiflood penalty: {e}")

def get_antiflood_handlers():
    """Returns antiflood message handler."""
    return [
        MessageHandler(filters.ALL & ~filters.COMMAND & filters.ChatType.GROUPS, handle_antiflood)
    ]
