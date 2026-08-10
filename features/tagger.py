import logging
import asyncio
import html
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
import features.voice_chat
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import is_user_admin
from core.config import delete_message_job

logger = logging.getLogger(__name__)

# Track active tagging tasks per chat to allow stopping them
# Format: {chat_id: stop_event}
ACTIVE_TAGS = {}


async def tag_everyone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tags everyone in the group in batches.

    Requires the Voice Monitor (Telethon user session) because the Bot API
    cannot enumerate all group members -- only a logged-in user account can.
    """
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ["group", "supergroup"]:
        return

    # Check if feature is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("tagger_enabled", True):
        return await update.message.reply_text("❌ Tagger feature is disabled in this group.")

    # Check if user is admin
    if not await is_user_admin(chat.id, user.id, context):
        return await update.message.reply_text("❌ Only admins can use this command.")

    # Telethon (user session) check -- the Bot API cannot list all members
    tele = voice_chat.telethon_client
    if not tele or not tele.is_connected():
        return await update.message.reply_text(
            "❌ <b>Tagger unavailable:</b> the Voice Monitor (Telethon user session) is not connected.\n\n"
            "The bot's own API account can't list group members -- a logged-in user session is "
            "required. Ask the bot owner to refresh <code>STRING_SESSION</code> in <code>.env</code> "
            "and restart the bot.",
            parse_mode=ParseMode.HTML,
        )

    # Check for stop command
    if context.args and context.args[0].lower() == "stop":
        if chat.id in ACTIVE_TAGS:
            ACTIVE_TAGS[chat.id].set()
            return await update.message.reply_text("🛑 Tagging process stopped.")
        return await update.message.reply_text("❌ No active tagging process found.")

    if chat.id in ACTIVE_TAGS:
        return await update.message.reply_text(
            "❌ A tagging process is already running. Use <code>/tag stop</code> to cancel it.",
            parse_mode=ParseMode.HTML,
        )

    custom_message = html.escape(" ".join(context.args)) if context.args else "Attention everyone! 📢"

    # Start tagging
    stop_event = asyncio.Event()
    ACTIVE_TAGS[chat.id] = stop_event

    try:
        # Resolve the chat entity the same way voice_chat.py does (warms Telethon cache).
        # For -100xxx supergroups this yields the bare channel id; for legacy groups the
        # negative id. get_entity() handles both and populates the entity cache.
        clean_id = int(str(chat.id).replace('-100', ''))
        try:
            entity = await tele.get_entity(clean_id)
        except Exception as e:
            logger.error(f"tag_everyone get_entity failed for {chat.id}: {e}")
            return await update.message.reply_text(
                f"❌ Could not resolve this chat via the user session: <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )

        # Stream participants (memory-safe for very large groups)
        me = await tele.get_me()
        users_to_tag = []
        async for p in tele.iter_participants(entity):
            if p.bot:
                continue
            if me and p.id == me.id:
                continue
            users_to_tag.append(p)

        total = len(users_to_tag)
        if total == 0:
            return await update.message.reply_text("❌ Could not find any users to tag.")

        status = await update.message.reply_text(f"🚀 Starting to tag {total} users...")

        # Tag in batches of 5
        batch_size = 5
        tagged = 0
        for i in range(0, total, batch_size):
            if stop_event.is_set():
                break

            batch = users_to_tag[i:i + batch_size]
            mentions = []
            for u in batch:
                name = html.escape(u.first_name or "User")
                mentions.append(f'<a href="tg://user?id={u.id}">{name}</a>')

            tag_text = f"{custom_message}\n\n" + " ".join(mentions)

            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=tag_text,
                    parse_mode=ParseMode.HTML,
                )
                tagged += len(batch)
            except Exception as e:
                logger.error(f"Error sending tag batch: {e}")
                if "Flood control exceeded" in str(e):
                    await asyncio.sleep(15)
                else:
                    break

            # Wait between batches to avoid flood
            await asyncio.sleep(2)
            if status and (i // batch_size) % 10 == 0:
                try:
                    await status.edit_text(f"🚀 Tagging… {min(i + batch_size, total)}/{total}")
                except Exception:
                    pass

        if stop_event.is_set():
            await update.message.reply_text(f"🛑 Tagging stopped. Tagged {tagged}/{total}.")
        else:
            await update.message.reply_text(f"✅ All users have been tagged ({total}).")

    except Exception as e:
        logger.error(f"Error in tag_everyone: {e}")
        await update.message.reply_text(f"❌ An error occurred: {html.escape(str(e))}")
    finally:
        if chat.id in ACTIVE_TAGS:
            del ACTIVE_TAGS[chat.id]


async def tag_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tags all admins in the group. Uses the Bot API (no Telethon needed)."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ["group", "supergroup"]:
        return

    # Check if user is admin
    if not await is_user_admin(chat.id, user.id, context):
        return await update.message.reply_text("❌ Only admins can use this command.")

    custom_message = html.escape(" ".join(context.args)) if context.args else "Admins, attention needed! 🛠"

    try:
        admins = await chat.get_administrators()
        if not admins:
            return await update.message.reply_text("❌ Could not find any admins.")

        mentions = []
        for admin in admins:
            if admin.user.is_bot:
                continue
            name = html.escape(admin.user.first_name or "Admin")
            mentions.append(f'<a href="tg://user?id={admin.user.id}">{name}</a>')

        if not mentions:
            return await update.message.reply_text("❌ No human admins found.")

        # Tag admins in one or two messages (usually not many admins)
        batch_size = 10
        for i in range(0, len(mentions), batch_size):
            batch = mentions[i:i + batch_size]
            tag_text = f"{custom_message}\n\n" + " ".join(batch)
            await context.bot.send_message(
                chat_id=chat.id,
                text=tag_text,
                parse_mode=ParseMode.HTML,
            )
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Error in tag_admins: {e}")
        await update.message.reply_text(f"❌ An error occurred: {html.escape(str(e))}")


def get_tagger_handlers():
    """Returns tagger handlers."""
    return [
        CommandHandler(["tag", "all", "everyone"], tag_everyone),
        CommandHandler(["atag", "admins", "adm"], tag_admins),
    ]
