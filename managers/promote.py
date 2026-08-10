"""
Manager Promote/Demote - Admin management
Ported from AnnieXMusic to python-telegram-bot
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, ChatAdministratorRights
from telegram.ext import ContextTypes, CommandHandler
from managers.actions import parse_time, is_admin, check_admin_permission, check_bot_permission
from managers.settings_manager_mongo import get_chat_settings
from moderation.anonymous_admin import is_anonymous_admin, check_anonymous_admin_promote_permission
from managers.admin_manager_mongo import sync_admins, remove_admin_cache
from managers.user_manager_mongo import get_user_id

# Privilege presets
LIMITED_PRIVS = ChatAdministratorRights(
    can_change_info=False,
    can_delete_messages=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_restrict_members=False,
    can_promote_members=False,
    can_manage_chat=True,
    can_manage_video_chats=True,
    is_anonymous=False,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
)

FULL_PRIVS = ChatAdministratorRights(
    can_manage_chat=True,
    can_change_info=True,
    can_delete_messages=True,
    can_invite_users=True,
    can_restrict_members=True,
    can_pin_messages=True,
    can_promote_members=True,
    can_manage_video_chats=True,
    is_anonymous=False,
    can_post_stories=True,
    can_edit_stories=True,
    can_delete_stories=True,
)

DEMOTE_PRIVS = ChatAdministratorRights(
    can_change_info=False,
    can_delete_messages=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_manage_chat=False,
    can_manage_video_chats=False,
    is_anonymous=False,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
)


async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote user with limited rights."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_promote_enabled", True):
        return await update.message.reply_text("❌ The /promote command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /promote @username [title] or reply with /promote [title]")
    
    # Extract title: if the first arg was the user_id/username, title is the rest.
    # If it was a reply, title is all arguments.
    if update.message.reply_to_message:
        title = " ".join(context.args) if context.args else None
    else:
        title = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    try:
        member = await chat.get_member(user_id)
        if member.status == 'administrator':
            return await update.message.reply_text("User is already an admin.")
        
        await context.bot.promote_chat_member(
            chat.id, user_id,
            can_change_info=LIMITED_PRIVS.can_change_info,
            can_delete_messages=LIMITED_PRIVS.can_delete_messages,
            can_invite_users=LIMITED_PRIVS.can_invite_users,
            can_pin_messages=LIMITED_PRIVS.can_pin_messages,
            can_restrict_members=LIMITED_PRIVS.can_restrict_members,
            can_promote_members=LIMITED_PRIVS.can_promote_members,
            can_manage_chat=LIMITED_PRIVS.can_manage_chat,
        )
        
        if title:
            try:
                await context.bot.set_chat_administrator_custom_title(chat.id, user_id, title)
            except:
                title = "⚠️ Couldn't set custom title (not a supergroup)"
        
        # Sync with database
        await sync_admins(chat.id, context)
        
        admin_name = user.full_name
        text = f"» Promoted a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if title:
            text += f"\nTitle: {title}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to promote user: {str(e)}")

async def fullpromote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote user with full rights."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /fullpromote @username [title] or reply with /fullpromote [title]")
    
    # Extract title
    if update.message.reply_to_message:
        title = " ".join(context.args) if context.args else None
    else:
        title = " ".join(context.args[1:]) if len(context.args) > 1 else None
    
    try:
        member = await chat.get_member(user_id)
        if member.status == 'administrator':
            return await update.message.reply_text("User is already an admin.")
        
        await context.bot.promote_chat_member(
            chat.id, user_id,
            can_change_info=FULL_PRIVS.can_change_info,
            can_delete_messages=FULL_PRIVS.can_delete_messages,
            can_invite_users=FULL_PRIVS.can_invite_users,
            can_pin_messages=FULL_PRIVS.can_pin_messages,
            can_restrict_members=FULL_PRIVS.can_restrict_members,
            can_promote_members=FULL_PRIVS.can_promote_members,
            can_manage_chat=FULL_PRIVS.can_manage_chat,
        )
        
        if title:
            try:
                await context.bot.set_chat_administrator_custom_title(chat.id, user_id, title)
            except:
                title = "⚠️ Couldn't set custom title (not a supergroup)"
        
        # Sync with database
        await sync_admins(chat.id, context)
        
        admin_name = user.full_name
        text = f"» Fully promoted a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if title:
            text += f"\nTitle: {title}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to fully promote user: {str(e)}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demote user (remove admin rights)."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if command is enabled
    settings = get_chat_settings(chat.id)
    if not settings.get("manager_demote_enabled", True):
        return await update.message.reply_text("❌ The /demote command is currently disabled.")
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /demote @username or reply to a user with /demote")
    
    try:
        member = await chat.get_member(user_id)
        if member.status != 'administrator':
            return await update.message.reply_text("User is not an admin.")
        
        await context.bot.promote_chat_member(
            chat.id, user_id,
            can_change_info=DEMOTE_PRIVS.can_change_info,
            can_delete_messages=DEMOTE_PRIVS.can_delete_messages,
            can_invite_users=DEMOTE_PRIVS.can_invite_users,
            can_pin_messages=DEMOTE_PRIVS.can_pin_messages,
            can_restrict_members=DEMOTE_PRIVS.can_restrict_members,
            can_promote_members=DEMOTE_PRIVS.can_promote_members,
            can_manage_chat=DEMOTE_PRIVS.can_manage_chat,
        )
        
        # Remove from database cache
        remove_admin_cache(chat.id, user_id)
        
        admin_name = user.full_name
        text = f"» Demoted a user in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Failed to demote user: {str(e)}")

async def tempadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote user temporarily."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        return await update.message.reply_text(error_msg)
    
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        return await update.message.reply_text(bot_error_msg)
    
    user_id, name = await get_user_id(update, context)
    if not user_id:
        return await update.message.reply_text("Usage: /tempadmin @username <time> [title] or reply with /tempadmin <time> [title]")

    # Extract time and title
    if update.message.reply_to_message:
        if len(context.args) < 1:
            return await update.message.reply_text("Usage: /tempadmin @username <time> [title] or reply with /tempadmin <time> [title]")
        time_str = context.args[0]
        title = " ".join(context.args[1:]) if len(context.args) > 1 else None
    else:
        # First arg was user ID/username, second is time, rest is title
        if len(context.args) < 2:
            return await update.message.reply_text("Usage: /tempadmin @username <time> [title] or reply with /tempadmin <time> [title]")
        time_str = context.args[1]
        title = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    delta = parse_time(time_str)
    if not delta:
        return await update.message.reply_text("Invalid time format. Use s/m/h/d suffix (e.g., 1h, 30m, 2d).")
    
    try:
        member = await chat.get_member(user_id)
        if member.status == 'administrator':
            return await update.message.reply_text("User is already an admin.")
        
        await context.bot.promote_chat_member(
            chat.id, user_id,
            can_change_info=FULL_PRIVS.can_change_info,
            can_delete_messages=FULL_PRIVS.can_delete_messages,
            can_invite_users=FULL_PRIVS.can_invite_users,
            can_pin_messages=FULL_PRIVS.can_pin_messages,
            can_restrict_members=FULL_PRIVS.can_restrict_members,
            can_promote_members=FULL_PRIVS.can_promote_members,
            can_manage_chat=FULL_PRIVS.can_manage_chat,
        )
        
        if title:
            try:
                await context.bot.set_chat_administrator_custom_title(chat.id, user_id, title)
            except:
                title = "⚠️ Couldn't set custom title (not a supergroup)"
        
        # Sync with database
        await sync_admins(chat.id, context)
        
        admin_name = user.full_name
        text = f"» Temp-promoted for {time_str} in {chat.title}\n"
        text += f" User  : {name}\n"
        text += f" Admin : {admin_name}"
        if title:
            text += f"\nTitle: {title}"
        
        await update.message.reply_text(text)
        
        # Auto-demote after time
        async def auto_demote():
            await asyncio.sleep(delta.total_seconds())
            try:
                await context.bot.promote_chat_member(
                    chat.id, user_id,
                    can_change_info=DEMOTE_PRIVS.can_change_info,
                    can_delete_messages=DEMOTE_PRIVS.can_delete_messages,
                    can_invite_users=DEMOTE_PRIVS.can_invite_users,
                    can_pin_messages=DEMOTE_PRIVS.can_pin_messages,
                    can_restrict_members=DEMOTE_PRIVS.can_restrict_members,
                    can_promote_members=DEMOTE_PRIVS.can_promote_members,
                    can_manage_chat=DEMOTE_PRIVS.can_manage_chat,
                )
                
                # Remove from database cache
                remove_admin_cache(chat.id, user_id)
                
                await context.bot.send_message(chat.id, f"Auto-demoted {name} after {time_str}.")
            except:
                pass
        
        asyncio.create_task(auto_demote())
        
    except Exception as e:
        await update.message.reply_text(f"Failed to temporarily promote user: {str(e)}")

def get_promote_handlers():
    """Return promote handlers."""
    return [
        CommandHandler("spromote", promote_user),
        CommandHandler("fullpromote", fullpromote_user),
        CommandHandler("sdemote", demote_user),
        CommandHandler("tempadmin", tempadmin),
    ]
