"""
Manager ID Command - Show IDs of user, chat, message
Ported from AnnieXMusic to python-telegram-bot
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from managers.settings_manager_mongo import get_chat_settings

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get ID information."""
    chat = update.effective_chat
    user = update.effective_user
    reply = update.message.reply_to_message
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_id_enabled", True):
        return await update.message.reply_text("❌ The /id command is currently disabled.")
    
    out = []
    
    if update.message.link:
        out.append(f"**[Message ID:]({update.message.link})** `{update.message.id}`")
    else:
        out.append(f"**Message ID:** `{update.message.id}`")
    
    out.append(f"**[Your ID:](tg://user?id={user.id})** `{user.id}`")
    
    if context.args:
        try:
            target = " ".join(context.args)
            # Try to get user from username
            if target.startswith('@'):
                target_user = await context.bot.get_chat(target)
                out.append(f"**[User ID:](tg://user?id={target_user.id})** `{target_user.id}`")
            elif target.isdigit():
                out.append(f"**User ID:** `{target}`")
        except Exception:
            return await update.message.reply_text("**This user doesn't exist.**", quote=True)
    
    if chat.username and chat.type in ['group', 'supergroup']:
        out.append(f"**[Chat ID:](https://t.me/{chat.username})** `{chat.id}`")
    else:
        out.append(f"**Chat ID:** `{chat.id}`")
    
    if reply:
        if reply.link:
            out.append(f"**[Replied Message ID:]({reply.link})** `{reply.id}`")
        else:
            out.append(f"**Replied Message ID:** `{reply.id}`")
        
        if reply.from_user:
            out.append(
                f"**[Replied User ID:](tg://user?id={reply.from_user.id})** "
                f"`{reply.from_user.id}`"
            )
        
        if reply.forward_from_chat:
            out.append(
                f"The forwarded channel **{reply.forward_from_chat.title}** "
                f"has ID `{reply.forward_from_chat.id}`"
            )
        
        if reply.sender_chat:
            out.append(f"ID of the replied chat/channel: `{reply.sender_chat.id}`")
    
    await update.message.reply_text(
        "\n".join(out),
        disable_web_page_preview=True,
        parse_mode='Markdown'
    )

def get_id_handlers():
    """Return ID command handler."""
    return [CommandHandler("id", get_id)]
