import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from core.config import OWNER_ID, send_bot_response
from core.database import get_collection, COLLECTIONS
from managers.user_manager_mongo import get_user_id, is_user_admin

# Collection that stores the bot-wide sudo users (besides the owner).
SUDO_COLLECTION = "sudo_users"


def _sudo_col():
    try:
        return get_collection(SUDO_COLLECTION)
    except Exception:
        return None


def is_sudo(user_id):
    """Return True if the user is the bot owner or a stored sudo user.

    The owner is ALWAYS sudo even if not present in the collection, so the
    feature can never lock the owner out.
    """
    if user_id == OWNER_ID:
        return True
    try:
        col = _sudo_col()
        if col is None:
            return False
        return col.count_documents({"user_id": int(user_id)}) > 0
    except Exception as e:
        logging.error(f"[SUDO] is_sudo failed: {e}")
        return False


def add_sudo(user_id, name=None):
    """Add a user to the sudo list. Returns True on success."""
    try:
        col = _sudo_col()
        if col is None:
            return False
        col.update_one(
            {"user_id": int(user_id)},
            {"$set": {"user_id": int(user_id), "name": name},
             "$setOnInsert": {"added_at": __import__("datetime").datetime.now()}},
            upsert=True,
        )
        return True
    except Exception as e:
        logging.error(f"[SUDO] add_sudo failed: {e}")
        return False


def del_sudo(user_id):
    """Remove a user from the sudo list. Returns True if removed (or not present)."""
    try:
        col = _sudo_col()
        if col is None:
            return False
        col.delete_one({"user_id": int(user_id)})
        return True
    except Exception as e:
        logging.error(f"[SUDO] del_sudo failed: {e}")
        return False


def list_sudo():
    """Return list of {user_id, name} sudo docs (excluding the owner)."""
    try:
        col = _sudo_col()
        if col is None:
            return []
        return [{"user_id": d["user_id"], "name": d.get("name")}
                for d in col.find({}, {"user_id": 1, "name": 1})]
    except Exception as e:
        logging.error(f"[SUDO] list_sudo failed: {e}")
        return []


async def sudo_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gate helper for owner-only sudo management commands."""
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id != OWNER_ID:
        await send_bot_response(
            update, context,
            "❌ This command is only available to the <b>bot owner</b>.",
            parse_mode=ParseMode.HTML,
        )
        return False
    return True


async def addsudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only. Grant sudo:
       • reply to a user's message with /addsudo
       • /addsudo <user_id>
       • /addsudo @username
    """
    if not await sudo_check(update, context):
        return

    target_id, name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(
            update, context,
            "Usage:\n"
            "• Reply to a user with <code>/addsudo</code>\n"
            "• <code>/addsudo &lt;user_id&gt;</code>\n"
            "• <code>/addsudo @username</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(target_id)
    if target_id == OWNER_ID:
        await send_bot_response(update, context, "ℹ️ The owner already has full access.")
        return

    # Best-effort friendly name
    if not name or str(name).isdigit():
        try:
            chat = await context.bot.get_chat(target_id)
            name = chat.first_name or chat.username or str(target_id)
        except Exception:
            name = str(target_id)

    if add_sudo(target_id, name):
        await send_bot_response(
            update, context,
            f"✅ <b>{name}</b> (<code>{target_id}</code>) is now a <b>sudo user</b>. "
            f"They can use owner-only commands such as <code>/broadcast</code>.",
            parse_mode=ParseMode.HTML,
        )
        logging.info(f"[SUDO] {target_id} granted sudo by owner")
    else:
        await send_bot_response(update, context, "❌ Failed to add sudo user (database error).")


async def delsudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only. Revoke sudo:
       • reply to a user's message with /delsudo
       • /delsudo <user_id>
       • /delsudo @username
    """
    if not await sudo_check(update, context):
        return

    target_id, name = await get_user_id(update, context)
    if not target_id:
        await send_bot_response(
            update, context,
            "Usage:\n"
            "• Reply to a user with <code>/delsudo</code>\n"
            "• <code>/delsudo &lt;user_id&gt;</code>\n"
            "• <code>/delsudo @username</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(target_id)
    if target_id == OWNER_ID:
        await send_bot_response(update, context, "❌ The owner cannot be removed from sudo.")
        return

    if del_sudo(target_id):
        await send_bot_response(
            update, context,
            f"✅ <b>{name or target_id}</b> (<code>{target_id}</code>) is no longer a sudo user.",
            parse_mode=ParseMode.HTML,
        )
        logging.info(f"[SUDO] {target_id} removed from sudo by owner")
    else:
        await send_bot_response(update, context, "❌ Failed to remove sudo user (database error).")


async def sudolist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only. List all sudo users."""
    if not await sudo_check(update, context):
        return

    sudoers = list_sudo()
    lines = [f"👑 <b>Sudo Users</b> (Bot Owner: <code>{OWNER_ID}</code>)\n"]
    if not sudoers:
        lines.append("\nℹ️ No extra sudo users. Use <code>/addsudo</code> to add one.")
    else:
        for i, s in enumerate(sudoers, 1):
            nm = s.get("name") or s["user_id"]
            lines.append(f"{i}. <b>{nm}</b> — <code>{s['user_id']}</code>")
    await send_bot_response(update, context, "\n".join(lines), parse_mode=ParseMode.HTML)


def get_sudo_handlers():
    return [
        CommandHandler("addsudo", addsudo_command),
        CommandHandler("delsudo", delsudo_command),
        CommandHandler("sudolist", sudolist_command),
    ]
