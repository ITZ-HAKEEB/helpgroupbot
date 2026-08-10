import logging
import shlex
from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from managers.filters_manager_mongo import get_chat_filters, add_chat_filter, remove_chat_filter, remove_all_chat_filters
from managers.user_manager_mongo import can_user_configure_settings, is_user_admin
from moderation.moderation import can_user_ban
from core.config import OWNER_ID, send_bot_response, edit_bot_response

async def set_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a new filter for the chat."""
    if not update.message: return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check permissions (only admins with Ban permission)
    can_ban, error_msg = await can_user_ban(chat_id, user_id, context)
    if not can_ban:
        await update.message.reply_text(error_msg or "Only admins with 'Ban Users' permission can use the /filter command.")
        return

    # Check if it's a reply or has enough arguments
    args = context.args
    reply = update.message.reply_to_message
    
    if not args and not reply:
        await update.message.reply_text("Usage: `/filter <trigger> <reply>` or reply to a message with `/filter <trigger>`", parse_mode=ParseMode.MARKDOWN)
        return

    # Extract trigger and content
    text_content = update.message.text
    try:
        # Use shlex to handle quoted triggers correctly
        split_text = shlex.split(text_content)
        # split_text[0] is /filter, split_text[1] is trigger
        if len(split_text) < 2:
            await update.message.reply_text("Please provide a trigger name.")
            return
        
        trigger = split_text[1].lower()
        
        content_data = {}
        if reply:
            # Save media/content from the replied message
            if reply.text:
                content_data = {"type": "text", "content": reply.text_markdown_v2_urled, "is_markdown": True}
            elif reply.sticker:
                content_data = {"type": "sticker", "content": reply.sticker.file_id}
            elif reply.photo:
                content_data = {"type": "photo", "content": reply.photo[-1].file_id, "caption": reply.caption_markdown_v2_urled}
            elif reply.video:
                content_data = {"type": "video", "content": reply.video.file_id, "caption": reply.caption_markdown_v2_urled}
            elif reply.document:
                content_data = {"type": "document", "content": reply.document.file_id, "caption": reply.caption_markdown_v2_urled}
            elif reply.animation:
                content_data = {"type": "animation", "content": reply.animation.file_id, "caption": reply.caption_markdown_v2_urled}
            elif reply.voice:
                content_data = {"type": "voice", "content": reply.voice.file_id}
            else:
                await update.message.reply_text("This type of content is not supported for filters.")
                return
            # Save inline keyboard if present
            if reply.reply_markup:
                content_data["reply_markup"] = reply.reply_markup.to_dict()
        else:
            # Text only from command arguments
            if len(split_text) < 3:
                await update.message.reply_text("Please provide a reply message or reply to a message.")
                return
            content_data = {"type": "text", "content": " ".join(split_text[2:]), "is_markdown": False}

        add_chat_filter(chat_id, trigger, content_data)
        await update.message.reply_text(f"✅ Filter for `{trigger}` has been set!", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Error setting filter: {e}")
        await update.message.reply_text("Error parsing command. For multi-word triggers, use quotes: `/filter \"my trigger\" reply`")

async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all filters in the current chat."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check permissions (only admins with Ban permission)
    can_ban, _ = await can_user_ban(chat_id, user_id, context)
    if not can_ban:
        await update.message.reply_text("Only admins with 'Ban Users' permission can use this command.")
        return

    chat_filters = get_chat_filters(chat_id)
    
    if not chat_filters:
        await update.message.reply_text("No filters active in this chat.")
        return
    
    msg = "🔍 **Active Filters in this chat:**\n"
    for trigger in chat_filters.keys():
        msg += f"• `{trigger}`\n"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(colored_button("❌ Close", "default"), callback_data="close_filter")]])
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def close_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close the filters list."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_user_admin(chat_id, user_id, context):
        await query.answer("Only admins can close this list.", show_alert=True)
        return
        
    await query.message.delete()
    await query.answer()

async def stop_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop a specific filter."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check permissions (only admins with Ban permission)
    can_ban, _ = await can_user_ban(chat_id, user_id, context)
    if not can_ban:
        await update.message.reply_text("Only admins with 'Ban Users' permission can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/stop <trigger>`", parse_mode=ParseMode.MARKDOWN)
        return
    
    trigger = " ".join(context.args).lower()
    if remove_chat_filter(chat_id, trigger):
        await update.message.reply_text(f"🛑 Stopped filter for `{trigger}`.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"Could not find filter for `{trigger}`.")

async def stop_all_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all filters in the chat."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check permissions (only admins with Ban permission)
    can_ban, _ = await can_user_ban(chat_id, user_id, context)
    if not can_ban:
        await update.message.reply_text("Only admins with 'Ban Users' permission can use this command.")
        return

    if remove_all_chat_filters(chat_id):
        await update.message.reply_text("🗑 All filters have been deleted. This cannot be undone.")
    else:
        await update.message.reply_text("No filters found to delete.")

async def filter_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check every message for a filter trigger."""
    if not update.message or not update.message.text:
        return
    
    chat_id = update.effective_chat.id
    text = update.message.text.lower()
    chat_filters = get_chat_filters(chat_id)
    
    for trigger, data in chat_filters.items():
        # Match trigger as a whole word or exact string
        if trigger in text:
            # Found a match!
            msg_type = data.get("type", "text")
            content = data.get("content")
            caption = data.get("caption")
            
            try:
                reply_markup = None
                if data.get("reply_markup"):
                    reply_markup = InlineKeyboardMarkup.de_json(data["reply_markup"], context.bot)
                    
                if msg_type == "text":
                    parse_mode = ParseMode.MARKDOWN_V2 if data.get("is_markdown") else None
                    await update.message.reply_text(content, parse_mode=parse_mode, reply_markup=reply_markup)
                elif msg_type == "sticker":
                    await update.message.reply_sticker(content, reply_markup=reply_markup)
                elif msg_type == "photo":
                    await update.message.reply_photo(content, caption=caption, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                elif msg_type == "video":
                    await update.message.reply_video(content, caption=caption, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                elif msg_type == "document":
                    await update.message.reply_document(content, caption=caption, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                elif msg_type == "animation":
                    await update.message.reply_animation(content, caption=caption, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                elif msg_type == "voice":
                    await update.message.reply_voice(content, reply_markup=reply_markup)
            except Exception as e:
                logging.error(f"Error sending filter reply: {e}")

def get_filter_handlers():
    return [
        CommandHandler("filter", set_filter),
        CommandHandler("filters", list_filters),
        CommandHandler("stop", stop_filter),
        CommandHandler("stopall", stop_all_filters),
        CallbackQueryHandler(close_filter, pattern="^close_filter$"),
        # This one handles the actual triggers, put it in a separate group in bot.py
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, filter_reply_handler)
    ]
