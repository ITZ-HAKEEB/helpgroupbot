import logging
from html import escape
import time
import httpx
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    filters
)
try:
    from telegram.ext import ChatBoostHandler
except ImportError:
    ChatBoostHandler = None

from core.config import OWNER_ID, BOT_TOKEN, colored_button, delete_message_job
from managers.settings_manager_mongo import get_chat_settings, update_chat_setting
from managers.user_manager_mongo import is_user_admin

logger = logging.getLogger(__name__)

# Default official boost link requested for the group
DEFAULT_BOOST_URL = "https://t.me/boost/Titanic_World_Chatting_Group"

# Cache of verified users who currently meet the boost requirement: (chat_id, user_id)
_VERIFIED_BOOST_USERS: set[tuple[int, int]] = set()

# Anti-spam cooldown for join/message notices: (chat_id, user_id) -> timestamp
_LAST_NOTICE_TIME: dict[tuple[int, int], float] = {}


def is_premium_user(user) -> bool:
    """Check if a telegram user is Telegram Premium."""
    if not user:
        return False
    return bool(getattr(user, "is_premium", False) or getattr(user, "has_custom_emoji_status", False))


def is_user_boost_verified(chat_id: int, user_id: int) -> bool:
    """Check if user has already been verified as having required boosts in memory."""
    return (chat_id, user_id) in _VERIFIED_BOOST_USERS


def get_chat_boost_url(chat=None) -> str:
    """Generate the official Telegram boost link for the chat.
    Defaults to https://t.me/boost/Titanic_World_Chatting_Group if not specified.
    """
    if chat:
        chat_id = getattr(chat, "id", None)
        if chat_id:
            try:
                settings = get_chat_settings(chat_id)
                if settings.get("boost_url"):
                    return settings["boost_url"]
            except Exception:
                pass
        username = getattr(chat, "username", None)
        if username:
            return f"https://t.me/boost/{username}"
    return DEFAULT_BOOST_URL


def build_boost_markup(boost_url: str, user_id: int) -> InlineKeyboardMarkup:
    """Build the inline keyboard with green boost button and blue verify captcha button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(colored_button("🚀 ʙᴏᴏsᴛ ᴛʜᴇ ɢʀᴏᴜᴘ (4 ʙᴏᴏsᴛs)", "green"), url=boost_url)],
        [InlineKeyboardButton(colored_button("🔄 ᴠᴇʀɪғʏ ᴄᴀᴘᴛᴄʜᴀ", "blue"), callback_data=f"verify_boost:{user_id}")]
    ])


def format_captcha_message(user, chat, current_boosts: int, required_boosts: int = 4) -> str:
    """Format the premium captcha challenge prompt."""
    user_mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>'
    remaining = max(0, required_boosts - current_boosts)
    return (
        f"<blockquote>🛡️ <b>#PremiumUser Captcha Verification!</b>\n\n"
        f"ⓘ <b>𝖴sᴇʀ -</b> {user_mention}\n"
        f"ⓘ <b>𝖴sᴇʀɪᴅ -</b> <code>{user.id}</code>\n"
        f"ⓘ <b>𝖲ᴛᴀᴛᴜs -</b> 🔒 𝖬𝗎𝗍𝖾𝖽 (Captcha Pending)\n\n"
        f"💡 <i>You are a Telegram Premium user! In this group, Premium members must give <b>{required_boosts} boosts</b> to the group using the button below to solve the captcha and chat.</i>\n\n"
        f"📊 <b>Current Boosts:</b> <code>{current_boosts}/{required_boosts}</code>\n"
        f"🚀 <b>Remaining:</b> <b>{remaining}</b> more boost(s) needed\n\n"
        f"<i>Click the button below to boost, then click Verify Captcha!</i></blockquote>"
    )


def format_captcha_success_message(user, current_boosts: int, required_boosts: int = 4) -> str:
    """Format the captcha completion notification."""
    user_mention = f'<a href="tg://user?id={user.id}">{escape(user.first_name)}</a>'
    return (
        f"<blockquote>🎉 <b>Captcha Passed! Boost Verified!</b>\n\n"
        f"ⓘ <b>𝖴sᴇʀ -</b> {user_mention}\n"
        f"ⓘ <b>𝖴sᴇʀɪᴅ -</b> <code>{user.id}</code>\n"
        f"ⓘ <b>𝖲ᴛᴀᴛᴜs -</b> 🔓 𝖴𝗇𝗆𝗎𝗍𝖾𝖽 & 𝖵𝖾𝗋𝗂𝖿𝗂𝖾𝖽\n\n"
        f"Thank you for giving <b>{current_boosts}/{required_boosts} boosts</b> to the group! ⭐\n"
        f"You can now send messages freely.</blockquote>"
    )


async def get_user_boost_count(bot, chat_id: int, user_id: int) -> int:
    """Fetch the number of active boosts a user has given to a chat."""
    # 1. Try python-telegram-bot's get_user_chat_boosts if available
    try:
        if hasattr(bot, "get_user_chat_boosts"):
            res = await bot.get_user_chat_boosts(chat_id=chat_id, user_id=user_id)
            if res and hasattr(res, "boosts"):
                return len(res.boosts)
    except Exception as e:
        logger.debug(f"[PREMIUM_BOOST] bot.get_user_chat_boosts failed: {e}")

    # 2. Direct HTTP fallback to Telegram Bot API
    try:
        token = getattr(bot, "token", None) or BOT_TOKEN
        if token:
            url = f"https://api.telegram.org/bot{token}/getUserChatBoosts"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, params={"chat_id": chat_id, "user_id": user_id})
                data = resp.json()
                if data.get("ok"):
                    boosts = data.get("result", {}).get("boosts", [])
                    return len(boosts)
                else:
                    logger.debug(f"[PREMIUM_BOOST] getUserChatBoosts API response: {data}")
    except Exception as e:
        logger.error(f"[PREMIUM_BOOST] HTTP getUserChatBoosts fallback failed: {e}")

    return 0


async def mute_user_in_chat(bot, chat_id: int, user_id: int) -> bool:
    """Restrict user from sending messages and media until captcha is solved."""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
        return True
    except Exception as e:
        logger.warning(f"[PREMIUM_BOOST] Could not mute user {user_id} in {chat_id}: {e}")
        return False


async def unmute_user_in_chat(bot, chat_id: int, user_id: int) -> bool:
    """Restore all chatting permissions to user."""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_invite_users=True
            )
        )
        _VERIFIED_BOOST_USERS.add((chat_id, user_id))
        return True
    except Exception as e:
        logger.warning(f"[PREMIUM_BOOST] Could not unmute user {user_id} in {chat_id}: {e}")
        return False


async def handle_premium_user_join(bot, chat, user, context: ContextTypes.DEFAULT_TYPE):
    """Core logic when a premium user joins: mute and send boost captcha."""
    chat_id = chat.id
    user_id = user.id

    if user.is_bot:
        return

    # Check anti-spam debounce (within 5 seconds)
    now = time.time()
    last = _LAST_NOTICE_TIME.get((chat_id, user_id), 0)
    if now - last < 5:
        return

    settings = get_chat_settings(chat_id)
    if not settings.get("premium_boost_enabled", True):
        return

    if not is_premium_user(user):
        return

    # Admins and Owner exempt
    if user_id == OWNER_ID or await is_user_admin(chat_id, user_id, context):
        return

    required_boosts = settings.get("premium_boost_count", 4)
    current_boosts = await get_user_boost_count(bot, chat_id, user_id)

    if current_boosts >= required_boosts:
        _VERIFIED_BOOST_USERS.add((chat_id, user_id))
        return

    # 1. Restrict user from sending messages
    await mute_user_in_chat(bot, chat_id, user_id)

    # 2. Build Captcha message & button with boost url
    boost_url = get_chat_boost_url(chat)
    markup = build_boost_markup(boost_url, user_id)
    text = format_captcha_message(user, chat, current_boosts, required_boosts)

    try:
        sent_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
        _LAST_NOTICE_TIME[(chat_id, user_id)] = now

        # Retain captcha notice for 300s (5 min) or delete job
        if context.job_queue and sent_msg:
            context.job_queue.run_once(
                delete_message_job,
                300,
                data={"chat_id": chat_id, "message_id": sent_msg.message_id}
            )
    except Exception as e:
        logger.error(f"[PREMIUM_BOOST] Failed to send captcha notice in {chat_id}: {e}")


async def on_premium_member_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat member status changes to detect joins/re-joins of premium users."""
    result = update.chat_member
    if not result:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    active_statuses = ["member", "administrator", "restricted"]
    inactive_statuses = ["left", "kicked", "none"]

    if not (new_status in active_statuses and old_status in inactive_statuses):
        return

    user = result.new_chat_member.user
    await handle_premium_user_join(context.bot, update.effective_chat, user, context)


async def on_new_chat_members_boost_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for service message new_chat_members."""
    if not update.message or not update.message.new_chat_members:
        return

    chat = update.effective_chat
    for user in update.message.new_chat_members:
        await handle_premium_user_join(context.bot, chat, user, context)


async def check_premium_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercept messages from premium users who haven't met the 4-boost requirement."""
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    if user.is_bot:
        return

    chat_id = chat.id
    user_id = user.id

    # If already verified in memory cache, allow message immediately
    if (chat_id, user_id) in _VERIFIED_BOOST_USERS:
        return

    # Check if user is Telegram Premium
    if not is_premium_user(user):
        return

    # Admins and Owner exempt
    if user_id == OWNER_ID or await is_user_admin(chat_id, user_id, context):
        return

    settings = get_chat_settings(chat_id)
    if not settings.get("premium_boost_enabled", True):
        return

    required_boosts = settings.get("premium_boost_count", 4)
    current_boosts = await get_user_boost_count(context.bot, chat_id, user_id)

    if current_boosts >= required_boosts:
        _VERIFIED_BOOST_USERS.add((chat_id, user_id))
        await unmute_user_in_chat(context.bot, chat_id, user_id)
        return

    # User does NOT have enough boosts: delete message and re-mute
    try:
        await update.message.delete()
    except Exception:
        pass

    await mute_user_in_chat(context.bot, chat_id, user_id)

    # Debounce notice so the chat isn't spammed with every blocked message
    now = time.time()
    last_notice = _LAST_NOTICE_TIME.get((chat_id, user_id), 0)
    if now - last_notice < 30:
        return
    _LAST_NOTICE_TIME[(chat_id, user_id)] = now

    boost_url = get_chat_boost_url(chat)
    markup = build_boost_markup(boost_url, user_id)
    text = format_captcha_message(user, chat, current_boosts, required_boosts)

    try:
        sent_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
        if context.job_queue and sent_msg:
            context.job_queue.run_once(
                delete_message_job,
                60,
                data={"chat_id": chat_id, "message_id": sent_msg.message_id}
            )
    except Exception as e:
        logger.error(f"[PREMIUM_BOOST] Failed to send message restriction notice: {e}")


async def verify_boost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'Verify Captcha' button callback."""
    query = update.callback_query
    if not query or not query.data:
        return

    parts = query.data.split(":")
    if len(parts) != 2:
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        return

    chat = update.effective_chat
    chat_id = chat.id
    clicker_id = query.from_user.id

    if clicker_id != target_user_id and clicker_id != OWNER_ID and not await is_user_admin(chat_id, clicker_id, context):
        await query.answer("❌ This captcha verification is only for the tagged user.", show_alert=True)
        return

    settings = get_chat_settings(chat_id)
    required_boosts = settings.get("premium_boost_count", 4)
    current_boosts = await get_user_boost_count(context.bot, chat_id, target_user_id)

    if current_boosts >= required_boosts:
        await unmute_user_in_chat(context.bot, chat_id, target_user_id)
        _VERIFIED_BOOST_USERS.add((chat_id, target_user_id))

        await query.answer("🎉 Verification successful! You gave enough boosts. Chatting unlocked!", show_alert=True)

        target_user = query.from_user if clicker_id == target_user_id else None
        if not target_user:
            try:
                chat_member = await context.bot.get_chat_member(chat_id, target_user_id)
                target_user = chat_member.user
            except Exception:
                target_user = query.from_user

        unlocked_text = format_captcha_success_message(target_user, current_boosts, required_boosts)
        try:
            await query.edit_message_text(
                text=unlocked_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )
        except Exception:
            pass
    else:
        remaining = required_boosts - current_boosts
        await query.answer(
            f"⚠️ Captcha Incomplete!\n\nYou currently have {current_boosts}/{required_boosts} active boosts.\nPlease give {remaining} more boost(s) using the boost button to unlock chatting.",
            show_alert=True
        )
        try:
            target_user = query.from_user if clicker_id == target_user_id else None
            if not target_user:
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, target_user_id)
                    target_user = chat_member.user
                except Exception:
                    target_user = query.from_user
            updated_text = format_captcha_message(target_user, chat, current_boosts, required_boosts)
            boost_url = get_chat_boost_url(chat)
            await query.edit_message_text(
                text=updated_text,
                parse_mode=ParseMode.HTML,
                reply_markup=build_boost_markup(boost_url, target_user_id)
            )
        except Exception:
            pass


async def on_chat_boost_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Real-time detection when any user boosts the group."""
    boost_update = getattr(update, "chat_boost", None)
    if not boost_update:
        return

    chat = boost_update.chat
    chat_id = chat.id
    boost = getattr(boost_update, "boost", None)
    if not boost:
        return

    user = None
    source = getattr(boost, "source", None)
    if source and hasattr(source, "user"):
        user = source.user

    if not user:
        return

    user_id = user.id
    settings = get_chat_settings(chat_id)
    if not settings.get("premium_boost_enabled", True):
        return

    required_boosts = settings.get("premium_boost_count", 4)
    current_boosts = await get_user_boost_count(context.bot, chat_id, user_id)

    if current_boosts >= required_boosts:
        await unmute_user_in_chat(context.bot, chat_id, user_id)
        _VERIFIED_BOOST_USERS.add((chat_id, user_id))

        user_mention = f'<a href="tg://user?id={user_id}">{escape(user.first_name)}</a>'
        announcement = (
            f"<blockquote>🎉 <b>Group Boosted!</b>\n\n"
            f"Thank you {user_mention} for boosting the group! ⭐\n"
            f"📊 <b>Total Boosts:</b> {current_boosts}/{required_boosts}\n"
            f"🔓 Chatting permissions have been unlocked!</blockquote>"
        )
        try:
            sent_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=announcement,
                parse_mode=ParseMode.HTML
            )
            if context.job_queue and sent_msg:
                context.job_queue.run_once(
                    delete_message_job,
                    60,
                    data={"chat_id": chat_id, "message_id": sent_msg.message_id}
                )
        except Exception as e:
            logger.error(f"[PREMIUM_BOOST] Failed to send boost unlock announcement: {e}")


async def on_chat_boost_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle removal of a boost from the group."""
    boost_removed = getattr(update, "removed_chat_boost", None)
    if not boost_removed:
        return

    chat = boost_removed.chat
    chat_id = chat.id
    user = None
    source = getattr(boost_removed, "source", None)
    if source and hasattr(source, "user"):
        user = source.user

    if not user:
        return

    user_id = user.id
    settings = get_chat_settings(chat_id)
    required_boosts = settings.get("premium_boost_count", 4)
    current_boosts = await get_user_boost_count(context.bot, chat_id, user_id)

    if current_boosts < required_boosts:
        _VERIFIED_BOOST_USERS.discard((chat_id, user_id))


async def premium_boost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to configure premium boost requirements: /premiumboost [on|off|set <count>]."""
    if not update.effective_chat or not update.effective_user:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != OWNER_ID and not await is_user_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ Admin only command.")
        return

    settings = get_chat_settings(chat_id)
    enabled = settings.get("premium_boost_enabled", True)
    count = settings.get("premium_boost_count", 4)
    boost_url = get_chat_boost_url(update.effective_chat)

    args = context.args or []
    if not args:
        status_text = "🟢 Enabled" if enabled else "🔴 Disabled"
        await update.message.reply_text(
            f"⭐ <b>Premium User Boost Captcha</b>\n\n"
            f"• <b>Status:</b> {status_text}\n"
            f"• <b>Required Boosts:</b> {count}\n"
            f"• <b>Boost URL:</b> <code>{boost_url}</code>\n\n"
            f"<i>Usage:</i>\n"
            f"• <code>/premiumboost on</code> - Enable\n"
            f"• <code>/premiumboost off</code> - Disable\n"
            f"• <code>/premiumboost set &lt;number&gt;</code> - Set required boosts (e.g. 4)\n"
            f"• <code>/setboosturl &lt;link&gt;</code> - Set custom boost link",
            parse_mode=ParseMode.HTML
        )
        return

    action = args[0].lower()
    if action in ["on", "enable", "true"]:
        update_chat_setting(chat_id, "premium_boost_enabled", True)
        await update.message.reply_text(f"✅ Premium boost captcha <b>enabled</b>. Premium members must boost {count} times to chat.", parse_mode=ParseMode.HTML)
    elif action in ["off", "disable", "false"]:
        update_chat_setting(chat_id, "premium_boost_enabled", False)
        await update.message.reply_text("❌ Premium boost captcha <b>disabled</b>.", parse_mode=ParseMode.HTML)
    elif action == "set" and len(args) > 1 and args[1].isdigit():
        new_count = max(1, int(args[1]))
        update_chat_setting(chat_id, "premium_boost_count", new_count)
        await update.message.reply_text(f"✅ Required boosts updated to <b>{new_count}</b>.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Usage: <code>/premiumboost [on|off|set &lt;number&gt;]</code>", parse_mode=ParseMode.HTML)


async def set_boost_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to configure custom boost url: /setboosturl <link>."""
    if not update.effective_chat or not update.effective_user:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id != OWNER_ID and not await is_user_admin(chat_id, user_id, context):
        await update.message.reply_text("❌ Admin only command.")
        return

    args = context.args or []
    if not args:
        current_url = get_chat_boost_url(update.effective_chat)
        await update.message.reply_text(
            f"🔗 <b>Current Boost URL:</b>\n<code>{current_url}</code>\n\n"
            f"<i>To change:</i> <code>/setboosturl https://t.me/boost/Titanic_World_Chatting_Group</code>",
            parse_mode=ParseMode.HTML
        )
        return

    new_url = args[0].strip()
    if not (new_url.startswith("http://") or new_url.startswith("https://") or new_url.startswith("t.me/")):
        await update.message.reply_text("❌ Invalid URL. Please provide a valid https:// link.")
        return

    if not new_url.startswith("http"):
        new_url = f"https://{new_url}"

    update_chat_setting(chat_id, "boost_url", new_url)
    await update.message.reply_text(f"✅ Boost link updated to:\n<code>{new_url}</code>", parse_mode=ParseMode.HTML)


def get_premium_boost_handlers():
    """Return all handlers for the premium boost captcha feature."""
    handlers = [
        CommandHandler(["premiumboost", "boostreq"], premium_boost_command),
        CommandHandler(["setboosturl", "boosturl"], set_boost_url_command),
        CallbackQueryHandler(verify_boost_callback, pattern=r"^verify_boost:"),
        # Detect member joins via status update
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members_boost_check),
        ChatMemberHandler(on_premium_member_joined, ChatMemberHandler.CHAT_MEMBER),
        # Intercept messages from premium users before general processing
        MessageHandler(filters.ALL & ~filters.COMMAND & filters.ChatType.GROUPS, check_premium_user_message),
    ]

    # Add real-time chat boost update handler if PTB supports it
    if ChatBoostHandler:
        handlers.append(ChatBoostHandler(on_chat_boost_updated))

    return handlers
