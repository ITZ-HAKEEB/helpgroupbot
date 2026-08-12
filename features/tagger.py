import logging
import asyncio
import html
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
import features.voice_chat as voice_chat
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import is_user_admin

logger = logging.getLogger(__name__)

# Track active tagging tasks per chat to allow stopping them
# Format: {chat_id: stop_event}
ACTIVE_TAGS = {}


def parse_tag_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract custom message, is_quote flag (-q), and reply_to_message_id."""
    raw_args = list(context.args) if context.args else []
    is_quote = False

    # Check for -q or --quote flag
    if "-q" in raw_args:
        is_quote = True
        raw_args.remove("-q")
    elif "--quote" in raw_args:
        is_quote = True
        raw_args.remove("--quote")

    reply_msg = update.effective_message.reply_to_message if update.effective_message else None
    reply_to_id = reply_msg.message_id if reply_msg else None

    text_arg = " ".join(raw_args).strip()

    if text_arg:
        custom_text = html.escape(text_arg)
    elif reply_msg:
        if reply_msg.text_html:
            custom_text = reply_msg.text_html
        elif reply_msg.caption_html:
            custom_text = reply_msg.caption_html
        elif reply_msg.text:
            custom_text = html.escape(reply_msg.text)
        elif reply_msg.caption:
            custom_text = html.escape(reply_msg.caption)
        else:
            custom_text = "Attention everyone! 📢"
    else:
        custom_text = "Attention everyone! 📢"

    if is_quote:
        custom_text = f"<blockquote>{custom_text}</blockquote>"

    return custom_text, reply_to_id, is_quote


async def tag_everyone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tags everyone in the group, 1 single user per message.

    Supports -q flag for Telegram HTML blockquote formatting.
    Requires the Voice Monitor (Telethon user session) to list group members.
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

    # Telethon (user session) check
    tele = voice_chat.telethon_client
    if not tele or not tele.is_connected():
        return await update.message.reply_text(
            "❌ <b>Tagger unavailable:</b> the Voice Monitor (Telethon user session) is not connected.\n\n"
            "The bot's own API account can't list group members -- a logged-in user session is "
            "required. Ask the bot owner to refresh <code>STRING_SESSION</code> in <code>.env</code> "
            "and restart the bot.",
            parse_mode=ParseMode.HTML,
        )

    custom_message, reply_to_id, is_quote = parse_tag_input(update, context)

    # Start tagging
    stop_event = asyncio.Event()
    ACTIVE_TAGS[chat.id] = stop_event

    try:
        clean_id = int(str(chat.id).replace('-100', ''))
        try:
            entity = await tele.get_entity(clean_id)
        except Exception as e:
            logger.error(f"tag_everyone get_entity failed for {chat.id}: {e}")
            return await update.message.reply_text(
                f"❌ Could not resolve this chat via the user session: <code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )

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

        status = await update.message.reply_text(f"🚀 Starting to tag {total} users (1 per message)...")

        tagged = 0
        for u in users_to_tag:
            if stop_event.is_set():
                break

            name = html.escape(u.first_name or "User")
            user_mention = f'<a href="tg://user?id={u.id}">{name}</a>'
            tag_text = f"{custom_message}\n\n{user_mention}"

            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=tag_text,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=reply_to_id
                )
                tagged += 1
            except Exception as e:
                logger.error(f"Error sending tag to user {u.id}: {e}")
                if "Flood control exceeded" in str(e) or "Too Many Requests" in str(e):
                    await asyncio.sleep(10)
                else:
                    pass

            # Pause 1.5 seconds between tags to avoid flood wait limits
            await asyncio.sleep(1.5)

            if status and tagged % 5 == 0:
                try:
                    await status.edit_text(f"🚀 Tagging… {tagged}/{total}")
                except Exception:
                    pass

        if stop_event.is_set():
            await update.message.reply_text(f"🛑 Tagging stopped. Tagged {tagged}/{total}.")
        else:
            try:
                await status.edit_text(f"✅ All users have been tagged ({total}).")
            except Exception:
                await update.message.reply_text(f"✅ All users have been tagged ({total}).")

    except Exception as e:
        logger.error(f"Error in tag_everyone: {e}")
        await update.message.reply_text(f"❌ An error occurred: {html.escape(str(e))}")
    finally:
        if chat.id in ACTIVE_TAGS:
            del ACTIVE_TAGS[chat.id]


async def tag_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tags all admins in the group, 1 single user per message. Supports -q flag."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ["group", "supergroup"]:
        return

    # Check if user is admin
    if not await is_user_admin(chat.id, user.id, context):
        return await update.message.reply_text("❌ Only admins can use this command.")

    # Check for stop command
    if context.args and context.args[0].lower() == "stop":
        if chat.id in ACTIVE_TAGS:
            ACTIVE_TAGS[chat.id].set()
            return await update.message.reply_text("🛑 Tagging process stopped.")
        return await update.message.reply_text("❌ No active tagging process found.")

    if chat.id in ACTIVE_TAGS:
        return await update.message.reply_text(
            "❌ A tagging process is already running. Use <code>/atag stop</code> to cancel it.",
            parse_mode=ParseMode.HTML,
        )

    custom_message, reply_to_id, is_quote = parse_tag_input(update, context)

    stop_event = asyncio.Event()
    ACTIVE_TAGS[chat.id] = stop_event

    try:
        admins = await chat.get_administrators()
        if not admins:
            return await update.message.reply_text("❌ Could not find any admins.")

        human_admins = [a for a in admins if not a.user.is_bot]
        if not human_admins:
            return await update.message.reply_text("❌ No human admins found.")

        total = len(human_admins)
        status = await update.message.reply_text(f"🚀 Starting to tag {total} admins (1 per message)...")

        tagged = 0
        for admin in human_admins:
            if stop_event.is_set():
                break

            name = html.escape(admin.user.first_name or "Admin")
            user_mention = f'<a href="tg://user?id={admin.user.id}">{name}</a>'
            tag_text = f"{custom_message}\n\n{user_mention}"

            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=tag_text,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=reply_to_id
                )
                tagged += 1
            except Exception as e:
                logger.error(f"Error sending tag to admin {admin.user.id}: {e}")

            await asyncio.sleep(1.5)

        if stop_event.is_set():
            await update.message.reply_text(f"🛑 Tagging stopped. Tagged {tagged}/{total} admins.")
        else:
            try:
                await status.edit_text(f"✅ All admins have been tagged ({total}).")
            except Exception:
                await update.message.reply_text(f"✅ All admins have been tagged ({total}).")

    except Exception as e:
        logger.error(f"Error in tag_admins: {e}")
        await update.message.reply_text(f"❌ An error occurred: {html.escape(str(e))}")
    finally:
        if chat.id in ACTIVE_TAGS:
            del ACTIVE_TAGS[chat.id]


def get_tagger_handlers():
    """Returns tagger handlers."""
    return [
        CommandHandler(["tag", "all", "everyone", "tagall"], tag_everyone),
        CommandHandler(["atag", "admins", "adm", "tagadmin"], tag_admins),
    ]
