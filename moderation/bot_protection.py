import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ChatMemberHandler, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from core.config import send_bot_response
from managers.user_manager_mongo import is_user_admin
from core.config import OWNER_ID

ANONYMOUS_ADMIN_ID = 1087968824

async def can_user_add_bots(chat_id, user_id, context):
    """Allow owners/creators and admins with Change Info + Ban Users to add bots."""
    if not user_id:
        return False

    if user_id in (OWNER_ID, ANONYMOUS_ADMIN_ID):
        return True

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return True
        if member.status == "administrator":
            return bool(member.can_change_info and member.can_restrict_members)
    except Exception as e:
        logging.error(f"Bot Protection: Failed to check add-bot permission for {user_id} in chat {chat_id}: {e}")

    return False

async def kick_if_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, user, added_by_user=None):
    """Kicks the bot if added by a member (not admin) and Bot Protection is enabled."""
    if not user.is_bot or user.id == context.bot.id:
        return

    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    
    if not settings.get("bot_protection_enabled", False):
        return

    apply_on = settings.get("bot_protection_apply_on", "members")

    should_kick = True
    if added_by_user:
        try:
            is_admin = await is_user_admin(chat_id, added_by_user.id, context)
            can_add = await can_user_add_bots(chat_id, added_by_user.id, context)
            is_owner = added_by_user.id == OWNER_ID

            if apply_on == "members":
                should_kick = not (is_admin or is_owner)
            elif apply_on == "admins":
                should_kick = is_admin and not can_add and not is_owner
            elif apply_on == "everyone":
                should_kick = not can_add and not is_owner
            else:
                should_kick = not (is_admin or is_owner)

            if not should_kick:
                logging.info(
                    f"Bot Protection: Allowing bot {user.id} added by user {added_by_user.id} in chat {chat_id}. "
                    f"apply_on={apply_on}, is_admin={is_admin}, can_add={can_add}"
                )
                return
        except Exception as e:
            logging.error(f"Bot Protection: Failed to check admin status in chat {chat_id}: {e}")

    if not should_kick:
        return

    try:
        # Check bot permissions
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not (bot_member.status == 'creator' or (bot_member.status == 'administrator' and bot_member.can_restrict_members)):
            await send_bot_response(
                update, context,
                "⚠️ <b>Bot Protection Alert:</b> A bot was added, but I don't have the 'Ban Users' permission to kick it. Please promote me to administrator with all rights.",
                parse_mode=ParseMode.HTML
            )
            return

        # Kick the added bot
        await context.bot.ban_chat_member(chat_id, user.id)
        await context.bot.unban_chat_member(chat_id, user.id)
        
        # Notify the group
        added_by_text = ""
        if added_by_user:
            added_by_text = f" Added by <code>{added_by_user.id}</code>."
        await send_bot_response(
            update, context,
            "🚫 <b>Bot Protection:</b> Kicked an added bot. "
            f"Only owners or admins with <b>Change Group Info</b> and <b>Ban Users</b> can add bots when this protection applies.{added_by_text}",
            parse_mode=ParseMode.HTML
        )
        logging.info(
            f"Bot Protection: Kicked bot {user.id} in chat {chat_id}. "
            f"apply_on={apply_on}, added_by={getattr(added_by_user, 'id', None)}"
        )
    except Exception as e:
        logging.error(f"Bot Protection: Failed to kick bot {user.id} in chat {chat_id}: {e}")

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects bot additions via ChatMemberHandler."""
    if not update.chat_member or not update.chat_member.new_chat_member:
        return
        
    # Only act if someone is newly joined/added
    status = update.chat_member.new_chat_member.status
    if status in ['member', 'administrator']:
        # The user who performed the action (added the bot)
        added_by_user = update.chat_member.from_user
        await kick_if_bot(update, context, update.chat_member.new_chat_member.user, added_by_user)

async def on_new_members_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects bot additions via MessageHandler (legacy/service messages)."""
    if not update.message or not update.message.new_chat_members:
        return
        
    for user in update.message.new_chat_members:
        # The message sender is the one who added the bot
        added_by_user = update.message.from_user
        await kick_if_bot(update, context, user, added_by_user)

def get_bot_protection_handlers():
    """Returns the handlers for bot protection."""
    return [
        ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members_message)
    ]
