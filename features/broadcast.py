import asyncio
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import Forbidden, BadRequest, RetryAfter

from core.config import OWNER_ID
from core.database import get_collection, get_all_chats, COLLECTIONS
from moderation.sudo import is_sudo


def _get_all_user_ids():
    """Return every cached user id from MongoDB (deduped)."""
    users_col = get_collection(COLLECTIONS["users"])
    if users_col is None:
        return []
    try:
        return list(dict.fromkeys(d["id"] for d in users_col.find({}, {"id": 1}) if d.get("id")))
    except Exception as e:
        logging.error(f"[BROADCAST] Failed to load users: {e}")
        return []


def _get_all_chat_ids():
    """Return every group chat id the bot knows about (as int)."""
    ids = []
    for doc in get_all_chats():
        cid = doc.get("chat_id")
        if cid is None or cid == "":
            continue
        try:
            ids.append(int(cid))  # DB stores chat_id as str; Bot API needs int
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(ids))


async def _resolve_targets(bot, raw_ids, private_ok=True):
    """Resolve raw ids to Chat objects via get_chat (carries access_hash).

    copy_message needs the chat's access_hash, which is only available from a
    fully resolved Chat object -- not from a bare cached id. Resolving each
    target also lets us skip chats the bot was removed from / private chats.

    Returns (targets, skipped).
    """
    targets, skipped = [], 0
    for tid in raw_ids:
        try:
            chat = await bot.get_chat(tid)
            if not private_ok and chat.type == "private":
                skipped += 1
                continue
            targets.append(chat)
        except (Forbidden, BadRequest):
            skipped += 1  # bot removed from chat / invalid
        except Exception as e:
            logging.warning(f"[BROADCAST] resolve {tid}: {e}")
            skipped += 1
    return targets, skipped


async def _deliver(bot, targets, source_msg, progress=None):
    """Copy source_msg to each resolved target; returns (sent, failed).

    `targets` is a list of either:
      - Chat objects (groups) -- use chat.id (carries access_hash)
      - int user ids (best-effort user broadcast, no access_hash available)
    Handles Telegram flood waits.
    """
    sent = failed = 0
    total = len(targets)
    for i, t in enumerate(targets, 1):
        tid = t.id if hasattr(t, "id") else t
        try:
            await bot.copy_message(tid, source_msg.chat_id, source_msg.message_id)
            sent += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.copy_message(tid, source_msg.chat_id, source_msg.message_id)
                sent += 1
            except Exception:
                failed += 1
        except (Forbidden, BadRequest):
            failed += 1
        except Exception as e:
            logging.error(f"[BROADCAST] {tid}: {e}")
            failed += 1
        # ~20 msgs/sec, safely under Telegram limits
        await asyncio.sleep(0.05)
        if progress and (i % 25 == 0 or i == total):
            try:
                await progress(f"📢 Broadcasting… {i}/{total}  ✅{sent} ❌{failed}")
            except Exception:
                pass
    return sent, failed


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner or sudo. Reply to a message with /broadcast to send it to users/groups.

    Flags: /broadcast            -> send to all users
           /broadcast chats      -> send to all groups
           /broadcast all        -> send to users + groups
    """
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text(
            "❌ This command is only available to the <b>bot owner or sudo users</b>.",
            parse_mode="HTML",
        )
        return

    msg = update.message.reply_to_message
    if not msg:
        await update.message.reply_text(
            "📢 <b>Broadcast</b>\n\n"
            "Reply to any message with:\n"
            "• <code>/broadcast</code> — send to all users\n"
            "• <code>/broadcast chats</code> — send to all groups\n"
            "• <code>/broadcast all</code> — send to users + groups",
            parse_mode="HTML",
        )
        return

    mode = (context.args[0].lower() if context.args else "users")
    if mode == "chats":
        do_users, do_chats, label = False, True, "groups"
    elif mode == "all":
        do_users, do_chats, label = True, True, "users + groups"
    else:
        do_users, do_chats, label = True, False, "users"

    await update.message.reply_text(f"🔍 Resolving {label} targets…", parse_mode="HTML")

    raw_users = _get_all_user_ids() if do_users else []
    raw_chats = _get_all_chat_ids() if do_chats else []

    # Groups need get_chat() to obtain the access_hash required by copy_message.
    # Users are delivered best-effort by raw id: the bot only stores user ids
    # (no access_hash), so pre-resolving via get_chat would skip ~100% of them
    # and take hours for large user bases. We deliver directly and count failures.
    users = raw_users
    users_skipped = 0
    chats, chats_skipped = (await _resolve_targets(context.bot, raw_chats, private_ok=True)) if do_chats else ([], 0)

    total = len(users) + len(chats)
    if not total:
        await update.message.reply_text("⚠️ No reachable targets found.")
        return

    status = await update.message.reply_text(
        f"📢 Broadcasting to {total} {label}…", parse_mode="HTML"
    )

    u_sent = u_failed = c_sent = c_failed = 0
    if do_users:
        u_sent, u_failed = await _deliver(context.bot, users, msg, progress=status.edit_text)
    if do_chats:
        c_sent, c_failed = await _deliver(context.bot, chats, msg, progress=status.edit_text)

    lines = ["✅ <b>Broadcast complete</b>\n"]
    if do_users:
        lines.append(f"👤 <b>Users:</b> {len(users)}  •  ✅ {u_sent}  ❌ {u_failed}")
    if do_chats:
        lines.append(f"👥 <b>Groups:</b> {len(chats)} (skipped {chats_skipped})  •  ✅ {c_sent}  ❌ {c_failed}")
    if do_users and u_sent == 0 and len(users) > 0:
        lines.append(
            "\n⚠️ <b>User delivery was 0.</b> The bot can only message users it has "
            "an active access-hash for (recently interacted). Consider broadcasting "
            "to <code>/broadcast chats</code> (groups) for reliable reach."
        )
    lines.append(f"\n📊 <b>Total sent:</b> <code>{u_sent + c_sent}</code>  |  "
                 f"<b>Failed:</b> <code>{u_failed + c_failed}</code>")
    try:
        await status.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception:
        pass


def get_broadcast_handlers():
    return [CommandHandler(["broadcast", "gcast", "bcast"], broadcast_command)]
