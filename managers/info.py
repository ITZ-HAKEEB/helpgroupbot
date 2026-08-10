"""
Manager Info Command - User information
Ported from AnnieXMusic to python-telegram-bot
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import get_user_id

async def whois_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user information."""
    # Check if command is enabled
    chat = update.effective_chat
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_info_enabled", True):
        return await update.message.reply_text("❌ The /info command is currently disabled.")
    
    try:
        user_id, name = await get_user_id(update, context)
        
        if not user_id:
            user = update.effective_user
        else:
            try:
                user = await context.bot.get_chat(user_id)
            except:
                return await update.message.reply_text("❌ Could not find this user.")
        
        loading = await update.message.reply_text("🔍 <b>Gathering user info...</b>", parse_mode='HTML')
        
        name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        username = f"@{user.username}" if user.username else "N/A"
        bio = getattr(user, 'description', "No bio") or "No bio"
        
        text = (
            f"👤 <b>User Info</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"➣ <b>User ID:</b> <code>{user.id}</code>\n"
            f"➣ <b>Name:</b> {name}\n"
            f"➣ <b>Username:</b> {username}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"➣ <b>Verified:</b> {'Yes ✅' if getattr(user, 'is_verified', False) else 'No 🥀'}\n"
            f"➣ <b>Premium:</b> {'Yes ☑️' if getattr(user, 'is_premium', False) else 'No 🥀'}\n"
            f"➣ <b>Bot:</b> {'Yes 🤖' if user.is_bot else 'No 👤'}\n"
            f"➣ <b>Profile Picture:</b> {'Yes 🌠' if getattr(user, 'photo', None) else 'No 🥀'}\n"
        )
        
        profile_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 View Profile", url=profile_url)],
            [InlineKeyboardButton("❌ Close", callback_data="info_close")]
        ])
        
        await loading.edit_text(
            text=text,
            parse_mode='HTML',
            reply_markup=buttons
        )
        
    except Exception as e:
        await update.message.reply_text(f"🥀 Error:\n<code>{str(e)}</code>", parse_mode='HTML')

def get_info_handlers():
    """Return info command handlers."""
    return [CommandHandler(["info", "whois"], whois_handler)]
