import logging
import asyncio
import re
from typing import Optional
from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from managers.moderation_manager_mongo import get_user_warns, add_warn, reset_warns
from managers.user_manager_mongo import is_user_admin
from moderation.moderation import mute_user, kick_user, ban_user
from telegram.error import BadRequest
from core.config import delete_message_job

# URL Regex to detect links, domains, and @mentions in bio
URL_PATTERN = re.compile(
    r'(https?://\S+|'
    r'www\.\S+|'
    r't\.me/\S*|'
    r'telegram\.me/\S*|'
    r'tg://\S+|'
    r'@\w+|'
    r'\b(?:[a-zA-Z0-9-]+\.)+(?:com|net|org|me|info|biz|io|co|xyz|top|link|tk|ga|ml|cf|gq|in|us|uk|dev|app|online|store|tech|site|club|ru|br|au|ca|de|fr|es|it|nl|se|no|dk|fi|pl|cz|hu|ro|sk|hr|si|bg|rs|ua|tr|ae|sa|il|eg|za|ng|ke|pk|bd|ph|id|my|sg|th|vn|cn|hk|tw|jp|kr|ee|ai)\b(?:/\S*)?)',
    re.IGNORECASE
)


async def get_telethon_client():
    """Import and return telethon_client from voice_chat."""
    try:
        from features.voice_chat import telethon_client
        return telethon_client
    except ImportError:
        return None


async def _resolve_user_entity(client, user_id, chat_id=None):
    """Resolve a Telethon input entity for user_id.

    A bare user_id usually has no cached access_hash, so GetFullUserRequest
    fails with 'Could not find the input entity'. The reliable path is to
    resolve the user via the group they just messaged in (which carries the
    access_hash), so we try that first when a chat_id is available.
    """
    # 1. Try resolving via the group's participant list (has access_hash)
    if chat_id is not None:
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            res = await client(GetParticipantRequest(channel=chat_id, participant=user_id))
            users = getattr(res, 'users', None)
            if users:
                return users[0]
        except Exception:
            pass
        # Fallback: search the participant list for this user
        try:
            entity = await client.get_entity(user_id)
            return entity
        except Exception:
            try:
                participants = await client.get_participants(chat_id, search='')
                for p in participants:
                    if getattr(p, 'id', None) == user_id:
                        return p
            except Exception:
                pass
    # 2. Last resort: let Telethon try its cache directly
    try:
        return await client.get_entity(user_id)
    except Exception:
        return user_id


async def check_user_bio(user_id, chat_id=None, bot=None):
    """Checks user bio for links using Telegram Bot API first, then Telethon fallback.

    Returns (has_link, bio).
    """
    from features.font_normalizer import normalize_text

    bio = None

    # 1. Primary: Try Bot API get_chat if bot instance is available
    if bot:
        try:
            user_chat = await bot.get_chat(user_id)
            if hasattr(user_chat, 'bio') and user_chat.bio:
                bio = user_chat.bio
        except Exception as e:
            logging.debug(f"Bot API get_chat bio fetch skipped/failed for {user_id}: {e}")

    # 2. Fallback: Telethon if Bot API did not yield a bio
    if not bio:
        client = await get_telethon_client()
        if client and client.is_connected():
            try:
                from telethon.tl.functions.users import GetFullUserRequest
                async def fetch_bio():
                    entity = await _resolve_user_entity(client, user_id, chat_id)
                    full_user = await client(GetFullUserRequest(entity))
                    return getattr(getattr(full_user, 'full_user', None), 'about', None)

                bio = await asyncio.wait_for(fetch_bio(), timeout=8.0)
            except asyncio.TimeoutError:
                logging.warning(f"Timeout checking bio for {user_id} via Telethon")
            except Exception as e:
                err = str(e)
                if "not registered in the system" in err or "AUTH_KEY" in err or "Unauthorized" in err:
                    logging.error(
                        "Bio Link Check: Telethon session is invalid/revoked "
                        f"('{err}'). Update STRING_SESSION in .env if needed."
                    )
                elif "Could not find the input entity" not in err and "User not found" not in err:
                    logging.error(f"Error checking bio for {user_id} via Telethon: {e}")

    if bio:
        norm_bio = normalize_text(bio)
        if URL_PATTERN.search(bio.strip()) or URL_PATTERN.search(norm_bio.strip()):
            logging.info(f"🚨 Bio Link detected for {user_id}: {bio}")
            return True, bio

    return False, None


async def apply_bio_penalty(update: Update, context, user_id: int, bio: Optional[str] = None):
    """Applies the configured penalty for having a link in bio."""
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)

    penalty = settings.get("bio_link_penalty", "warn").lower()
    if penalty == "off":
        return

    user_id_str = f"<code>{user_id}</code>"

    limit = settings.get("bio_link_warn_limit", 3)
    current_warns = add_warn(chat_id, user_id)

    keyboard = [
        [
            InlineKeyboardButton(colored_button("➕ Add Warn", "red"), callback_data=f"edit_warn_add_{user_id}"),
            InlineKeyboardButton(colored_button("🔄 Reset Warns", "green"), callback_data=f"edit_warn_reset_{user_id}"),
        ]
    ]

    bot = context.bot if hasattr(context, 'bot') else context

    msg_text = ""
    if current_warns >= limit:
        reset_warns(chat_id, user_id)

    if penalty == "mute" or penalty == "warn":
        try:
            await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            keyboard.insert(0, [InlineKeyboardButton(colored_button("🔊 Unmute", "green"), callback_data=f"edit_unmute_{user_id}")])
            msg_text = f"🚫 User {user_id_str} has been muted for reaching the warn limit (Link in bio)."
        except Exception as e:
            logging.error(f"Failed to mute user in bio check: {e}")
            msg_text = f"⚠️ User {user_id_str}, links are not allowed in your bio! ({current_warns}/{limit})"
    elif penalty == "kick":
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            msg_text = f"👢 User {user_id_str} has been kicked for reaching the warn limit (Link in bio)."
        except Exception as e:
            logging.error(f"Failed to kick user in bio check: {e}")
            msg_text = f"⚠️ User {user_id_str}, links are not allowed in your bio! ({current_warns}/{limit})"
    elif penalty == "ban":
        try:
            await bot.ban_chat_member(chat_id, user_id)
            msg_text = f"🔨 User {user_id_str} has been banned for reaching the warn limit (Link in bio)."
        except Exception as e:
            logging.error(f"Failed to ban user in bio check: {e}")
            msg_text = f"⚠️ User {user_id_str}, links are not allowed in your bio! ({current_warns}/{limit})"
    else:
        msg_text = (
            f"⚠️ User {user_id_str}, links are not allowed in your bio! "
            f"({current_warns}/{limit})\nPlease remove it to avoid further penalties."
        )

    try:
        sent_msg = await bot.send_message(
            chat_id=chat_id,
            text=msg_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Auto delete warning message after custom time (default 5 minutes)
        warn_delete_time = settings.get("warning_delete_time", 300)

        # If we have a job_queue, use it
        job_queue = getattr(context, 'job_queue', None)
        if job_queue:
            job_queue.run_once(
                delete_message_job,
                warn_delete_time,
                data={"chat_id": chat_id, "message_id": sent_msg.message_id}
            )
        else:
            # Fallback for when we don't have job_queue (e.g. called from voice_chat.py with ptb_application)
            async def fallback_delete():
                await asyncio.sleep(warn_delete_time)
                try:
                    await bot.delete_message(chat_id, sent_msg.message_id)
                except Exception:
                    pass

            asyncio.create_task(fallback_delete())

        if hasattr(update, 'message') and update.message:
            try:
                await update.message.delete()
            except Exception:
                pass

    except Exception as e:
        logging.error(f"Error in apply_bio_penalty: {e}")


async def bio_link_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks bio link when a user sends a message."""
    if not update.effective_chat or not update.effective_user or update.effective_user.is_bot:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    settings = get_chat_settings(chat_id)
    if not settings.get("bio_link_check_enabled", False):
        return

    # Check target (members, admin, everyone)
    target = settings.get("bio_link_target", "members").lower()
    is_admin = await is_user_admin(chat_id, user_id, context)

    if target == "members" and is_admin:
        return
    elif target == "admin" and not is_admin:
        return
    # if target is "everyone", we don't return early

    # Run the check in the background to not block the main message loop
    async def run_background_check():
        try:
            # Small delay to ensure Telethon has a chance to "see" the user
            await asyncio.sleep(0.5)
            has_link, bio = await check_user_bio(user_id, chat_id, bot=context.bot)
            if has_link:
                # If bio link detected, delete the triggering message immediately if it exists
                if update.message:
                    try:
                        await update.message.delete()
                    except Exception as e:
                        logging.error(f"Failed to delete message after bio link detection: {e}")

                await apply_bio_penalty(update, context, user_id, bio)
        except Exception as e:
            logging.error(f"Error in background bio check for {user_id}: {e}")

    asyncio.create_task(run_background_check())


def get_bio_handlers():
    """Returns the bio link message handler."""
    return [
        MessageHandler(filters.ChatType.GROUPS & (~filters.COMMAND), bio_link_message_handler)
    ]
