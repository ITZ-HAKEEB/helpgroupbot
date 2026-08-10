"""
Manager Psend Command - Send private message to a specific user
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from managers.settings_manager_mongo import check_command_access
from managers.user_manager_mongo import get_user_id
from core.config import send_bot_response

async def psend_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a private message to a specific user."""
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Delete command message immediately for privacy
    try:
        await update.message.delete()
    except:
        pass
        
    async def send_private_response(text):
        """Helper to send a temporary response and delete it quickly."""
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            import asyncio
            async def delete_msg():
                await asyncio.sleep(3)
                try: await msg.delete()
                except: pass
            asyncio.create_task(delete_msg())
        except:
            pass

    # Permission check removed as per user request (Everyone can use /psend)
    
    target_user_id, _ = await get_user_id(update, context)
    
    if not target_user_id:
        await send_private_response(
            "❌ <b>Usage:</b>\n"
            "• Reply to a user: <code>/psend [message]</code>\n"
            "• Use username/ID: <code>/psend [@username/ID] [message]</code>"
        )
        return

    # Extract message text
    if update.message.reply_to_message:
        message_text = " ".join(context.args) if context.args else ""
    else:
        # If it was an ID/Username in args[0], message is from args[1:]
        message_text = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    if not message_text:
        await send_private_response("❌ Please provide a message to send.")
        return

    try:
        # Send the message
        sender_mention = update.effective_user.mention_html()
        chat_title = update.effective_chat.title
        
        pm_text = (
            f"📩 <b>New Private Message</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"➣ <b>From:</b> {sender_mention}\n"
            f"➣ <b>Group:</b> {chat_title}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{message_text}"
        )
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text=pm_text,
            parse_mode='HTML'
        )
        
        await send_private_response(f"✅ Message sent to <code>{target_user_id}</code>.")
        
    except Exception as e:
        error_msg = str(e)
        if "bot was blocked" in error_msg.lower():
            await send_private_response("❌ Could not send message: The user has blocked the bot.")
        elif "chat not found" in error_msg.lower():
            await send_private_response("❌ Could not send message: The user has not started the bot.")
        else:
            await send_private_response(f"❌ Failed to send message: {error_msg}")

def get_psend_handlers():
    """Return psend command handlers."""
    return [CommandHandler("psend", psend_handler)]
