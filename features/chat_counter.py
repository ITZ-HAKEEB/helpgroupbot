import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ChatType

from managers.chat_counter_mongo import increment_user_count, get_top_chatters, reset_group_count
from features.leaderboard_image import generate_leaderboard_image

logger = logging.getLogger(__name__)

async def chat_counter_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Message handler to increment user chat count per group.
    Group isolated: chat.id is tracked independently.
    """
    if not update.effective_chat or update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    chat_id = update.effective_chat.id
    user_id = user.id
    user_name = user.first_name or f"User {user_id}"

    # Determine points based on message type
    msg = update.effective_message
    points = 1
    if msg:
        if msg.photo or msg.video or msg.document or msg.animation:
            points = 2
        elif msg.voice or msg.audio or msg.video_note:
            points = 3

    increment_user_count(chat_id, user_id, user_name, points=points)

def _build_keyboard(chat_id: int, current_timeframe: str):
    """Build interactive inline keyboard for leaderboard timeframes."""
    daily_btn = f"{'✅ ' if current_timeframe == 'daily' else ''}📅 Daily"
    weekly_btn = f"{'✅ ' if current_timeframe == 'weekly' else ''}🗓 Weekly"
    overall_btn = f"{'✅ ' if current_timeframe == 'overall' else ''}🏆 Overall"

    buttons = [
        [
            InlineKeyboardButton(daily_btn, callback_data=f"lb_tf:{chat_id}:daily"),
            InlineKeyboardButton(weekly_btn, callback_data=f"lb_tf:{chat_id}:weekly"),
            InlineKeyboardButton(overall_btn, callback_data=f"lb_tf:{chat_id}:overall"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"lb_tf:{chat_id}:{current_timeframe}")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /leaderboard, /top, and /chatcount commands.
    Generates and posts the graphical PNG leaderboard image.
    """
    if not update.effective_chat or update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.effective_message.reply_text("❌ Leaderboard command can only be used inside group chats.")
        return

    chat_id = update.effective_chat.id
    group_title = update.effective_chat.title or "Our Group"
    timeframe = "daily"

    # Allow passing timeframe as argument: /top weekly
    if context.args:
        arg = context.args[0].lower()
        if arg in ["daily", "day", "d"]:
            timeframe = "daily"
        elif arg in ["weekly", "week", "w"]:
            timeframe = "weekly"
        elif arg in ["overall", "all", "o"]:
            timeframe = "overall"

    top_users = get_top_chatters(chat_id, timeframe=timeframe, limit=10)
    img_path = generate_leaderboard_image(group_title, top_users, timeframe=timeframe)

    keyboard = _build_keyboard(chat_id, timeframe)

    try:
        with open(img_path, "rb") as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=f"🏆 **Leaderboard - {group_title}** ({timeframe.capitalize()})\n\nShowing Top 10 Chatters!",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error sending leaderboard photo: {e}")
        await update.effective_message.reply_text("❌ Failed to generate leaderboard image.")
    finally:
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception:
                pass

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback query handler to switch timeframes on the leaderboard image."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("lb_tf:"):
        return

    parts = data.split(":")
    if len(parts) < 3:
        return

    target_chat_id = int(parts[1])
    timeframe = parts[2]
    group_title = query.message.chat.title or "Our Group"

    top_users = get_top_chatters(target_chat_id, timeframe=timeframe, limit=10)
    img_path = generate_leaderboard_image(group_title, top_users, timeframe=timeframe)

    keyboard = _build_keyboard(target_chat_id, timeframe)

    try:
        with open(img_path, "rb") as photo:
            await query.edit_message_media(
                media=update.effective_message.photo[0].__class__(media=photo, caption=f"🏆 **Leaderboard - {group_title}** ({timeframe.capitalize()})\n\nShowing Top 10 Chatters!"),
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error editing leaderboard photo callback: {e}")
    finally:
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception:
                pass

async def resetcount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to reset chat counters for the group."""
    if not update.effective_chat or update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.effective_message.reply_text("❌ Reset count command can only be used in group chats.")
        return

    user = update.effective_user
    member = await update.effective_chat.get_member(user.id)
    if member.status not in ["administrator", "creator"]:
        await update.effective_message.reply_text("⛔ Only Group Administrators can reset chat counters.")
        return

    chat_id = update.effective_chat.id
    reset_group_count(chat_id)
    await update.effective_message.reply_text("✅ Chat counter for this group has been reset successfully!")

def register_chat_counter_handlers(app):
    """Register message listeners, commands, and callback handlers."""
    # Message listener for group chat count increments
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, chat_counter_listener), group=10)

    # Leaderboard commands
    app.add_handler(CommandHandler(["leaderboard", "top", "chatcount"], leaderboard_command))
    app.add_handler(CommandHandler("resetcount", resetcount_command))

    # Callback Query Handler for inline timeframe switching
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^lb_tf:"))
