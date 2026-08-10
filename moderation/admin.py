import logging
from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, ChatAdministratorRights
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.error import BadRequest
from managers.user_manager_mongo import get_user_id, is_user_admin, can_user_reload
from core.config import OWNER_ID, send_bot_response, edit_bot_response, log_to_channel
from moderation.anonymous_admin import (
    is_anonymous_admin, 
    check_anonymous_admin_promote_permission, 
    check_anonymous_admin_pin_permission, 
    check_anonymous_admin_change_info_permission
)
from managers.staff_manager_mongo import get_staff_stats
from managers.actions import check_admin_permission, check_bot_permission
from managers.admin_manager_mongo import sync_admins, update_admin_cache, remove_admin_cache
import html

# Permission names to display
PERMISSIONS_MAP = {
    "can_change_info": "Change Group Info",
    "can_delete_messages": "Delete Messages",
    "can_restrict_members": "Mute/Unmute Users",
    "can_ban_users": "Ban/Unban Users",
    "can_invite_users": "Invite Users via Link",
    "can_pin_messages": "Pin Messages",
    "can_post_stories": "Post Stories",
    "can_edit_stories": "Edit Stories",
    "can_delete_stories": "Delete Stories",
    "can_manage_video_chats": "Manage Video Chats",
    "is_anonymous": "Remain Anonymous",
    "can_promote_members": "Add New Admins"
}

# Initial default permissions for a new admin
DEFAULT_PERMISSIONS = {
    "can_change_info": False,
    "can_delete_messages": False,
    "can_restrict_members": False,
    "can_ban_users": False,
    "can_invite_users": False,
    "can_pin_messages": False,
    "can_post_stories": False,
    "can_edit_stories": False,
    "can_delete_stories": False,
    "can_manage_video_chats": False,
    "is_anonymous": False,
    "can_promote_members": False
}

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the interactive promotion process."""
    # Permission check for the admin performing the promotion
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return
    user_id, user_name = await get_user_id(update, context)
    # Escape display name so names containing <, > or & (e.g. "<3") cannot
    # break the HTML parse mode used below (fixes "Can't parse entities").
    user_name = html.escape(user_name or "User")

    if not user_id:
        # If username was provided but not found in cache
        if context.args and context.args[0].startswith('@'):
            await send_bot_response(
                update, context,
                f"❌ Could not find user {context.args[0]} in my database.\n\n"
                "**Why?** I only remember users who have spoken or joined since I was added.\n"
                "**Fix:** Please reply to one of their messages instead."
            )
        else:
            await send_bot_response(update, context, "Please reply to a user's message or provide a username/ID to promote them.")
        return

    # Fetch current permissions if user is already an admin
    current_perms = DEFAULT_PERMISSIONS.copy()
    is_already_admin = False
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == 'creator':
            is_already_admin = True
            for key in DEFAULT_PERMISSIONS.keys():
                current_perms[key] = True
        elif member.status == 'administrator':
            is_already_admin = True
            for key in DEFAULT_PERMISSIONS.keys():
                # ChatMemberAdministrator has these as attributes
                current_perms[key] = getattr(member, key, False)
    except Exception as e:
        logging.warning(f"Could not fetch current perms for {user_id}: {e}")

    # Initialize permissions in user_data
    promote_key = f"promote_{user_id}"
    context.user_data[promote_key] = current_perms
    
    # Show the full permission panel directly (Grid Style)
    keyboard = get_promotion_keyboard(user_id, current_perms)
    
    status_text = "Updating permissions for" if is_already_admin else "Promoting"
    await send_bot_response(
        update, context,
        f"{status_text} <b>{user_name}</b> (<code>{user_id}</code>). Select permissions:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def set_admin_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a custom admin title for a user."""
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return

    # Get user and title from command
    if not context.args or len(context.args) < 2:
        await send_bot_response(
            update, context,
            "❌ Usage: /setadmintitle @username or reply to user with title\n\n"
            "Example: /setadmintitle @john Moderator\n"
            "Or reply to a user's message with: /setadmintitle Moderator"
        )
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        if context.args[0].startswith('@'):
            await send_bot_response(
                update, context,
                f"❌ Could not find user {context.args[0]} in my database.\n\n"
                "**Why?** I only remember users who have spoken or joined since I was added.\n"
                "**Fix:** Please reply to one of their messages instead."
            )
        else:
            await send_bot_response(update, context, "Please reply to a user's message or provide a username/ID.")
        return

    # Extract title (everything after the first argument)
    title = " ".join(context.args[1:])
    
    # Title must be 0-16 characters
    if len(title) > 16:
        await send_bot_response(update, context, "❌ Admin title must be 16 characters or less.")
        return

    try:
        # Get current admin status
        member = await context.bot.get_chat_member(chat_id, user_id)
        
        if member.status not in ['creator', 'administrator']:
            await send_bot_response(update, context, "❌ User must be an admin first to set a title.")
            return

        # Promote with the new title (keeping existing permissions)
        promote_kwargs = {
            'chat_id': chat_id,
            'user_id': user_id,
            'can_change_info': member.can_change_info,
            'can_delete_messages': member.can_delete_messages,
            'can_restrict_members': member.can_restrict_members,
            'can_invite_users': member.can_invite_users,
            'can_pin_messages': member.can_pin_messages,
            'can_post_stories': member.can_post_stories,
            'can_edit_stories': member.can_edit_stories,
            'can_delete_stories': member.can_delete_stories,
            'can_manage_video_chats': member.can_manage_video_chats,
            'can_promote_members': member.can_promote_members,
            'is_anonymous': member.is_anonymous,
        }
        
        # Add custom_title only if it's being set
        if title:
            promote_kwargs['custom_title'] = title
        
        await context.bot.promote_chat_member(**promote_kwargs)
        
        # Sync with database
        await sync_admins(chat_id, context)
        
        if title:
            await send_bot_response(
                update, context,
                f"✅ Admin title for {user_name} set to: {title}"
            )
            # Log to channel
            await log_to_channel(context,
                f"👤 User: {user_id}\n"
                f"🏷️ Action: Admin Title Set\n"
                f"📝 Title: {title}\n"
                f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
                f"👤 Admin: {sender_id}"
            )
        else:
            await send_bot_response(
                update, context,
                f"✅ Admin title for {user_name} removed."
            )
            # Log to channel
            await log_to_channel(context,
                f"👤 User: {user_id}\n"
                f"🏷️ Action: Admin Title Removed\n"
                f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
                f"👤 Admin: {sender_id}"
            )
    except BadRequest as e:
        await send_bot_response(update, context, f"❌ Failed to set admin title: {str(e)}")
    except Exception as e:
        await send_bot_response(update, context, f"❌ An error occurred: {str(e)}")

async def delete_admin_title_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete/remove admin title from a user."""
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        if context.args and context.args[0].startswith('@'):
            await send_bot_response(
                update, context,
                f"❌ Could not find user {context.args[0]} in my database.\n\n"
                "**Why?** I only remember users who have spoken or joined since I was added.\n"
                "**Fix:** Please reply to one of their messages instead."
            )
        else:
            await send_bot_response(update, context, "Please reply to a user's message or provide a username/ID.")
        return

    try:
        # Get current admin status
        member = await context.bot.get_chat_member(chat_id, user_id)
        
        if member.status not in ['creator', 'administrator']:
            await send_bot_response(update, context, "❌ User must be an admin to have their title removed.")
            return

        if not member.custom_title:
            await send_bot_response(update, context, "❌ This admin doesn't have a custom title.")
            return

        # Promote with empty title (keeping existing permissions)
        promote_kwargs = {
            'chat_id': chat_id,
            'user_id': user_id,
            'can_change_info': member.can_change_info,
            'can_delete_messages': member.can_delete_messages,
            'can_restrict_members': member.can_restrict_members,
            'can_invite_users': member.can_invite_users,
            'can_pin_messages': member.can_pin_messages,
            'can_post_stories': member.can_post_stories,
            'can_edit_stories': member.can_edit_stories,
            'can_delete_stories': member.can_delete_stories,
            'can_manage_video_chats': member.can_manage_video_chats,
            'can_promote_members': member.can_promote_members,
            'is_anonymous': member.is_anonymous,
            'custom_title': ''
        }
        
        await context.bot.promote_chat_member(**promote_kwargs)
        
        # Sync with database
        await sync_admins(chat_id, context)
        
        await send_bot_response(
            update, context,
            f"✅ Admin title for {user_name} has been removed."
        )
        
        # Log to channel
        await log_to_channel(context,
            f"👤 User: {user_id}\n"
            f"🏷️ Action: Admin Title Deleted\n"
            f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
            f"👤 Admin: {sender_id}"
        )
    except BadRequest as e:
        await send_bot_response(update, context, f"❌ Failed to delete admin title: {str(e)}")
    except Exception as e:
        await send_bot_response(update, context, f"❌ An error occurred: {str(e)}")

def get_promotion_keyboard(user_id, current_perms, back_to_info=False):
    """Generate the keyboard with toggle buttons in a grid layout (rows and columns)."""
    keyboard = []
    
    # Define mobile-optimized labels for the grid
    grid_labels = {
        "can_change_info": "Info",
        "can_delete_messages": "Delete",
        "can_restrict_members": "Mute",
        "can_ban_users": "Ban",
        "can_invite_users": "Invite",
        "can_pin_messages": "Pin",
        "can_post_stories": "Stories",
        "can_edit_stories": "Edit Str",
        "can_delete_stories": "Del Str",
        "can_manage_video_chats": "Video",
        "is_anonymous": "Anon",
        "can_promote_members": "Admins"
    }
    
    # Create grid with 2 columns
    keys = list(grid_labels.keys())
    for i in range(0, len(keys), 2):
        row = []
        key1 = keys[i]
        status1 = "✅" if current_perms.get(key1) else "❌"
        color1 = "green" if current_perms.get(key1) else "red"
        row.append(InlineKeyboardButton(colored_button(f"{grid_labels[key1]} {status1}", color1), callback_data=f"toggle_{user_id}_{key1}"))
        
        if i + 1 < len(keys):
            key2 = keys[i+1]
            status2 = "✅" if current_perms.get(key2) else "❌"
            color2 = "green" if current_perms.get(key2) else "red"
            row.append(InlineKeyboardButton(colored_button(f"{grid_labels[key2]} {status2}", color2), callback_data=f"toggle_{user_id}_{key2}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(colored_button("Confirm Promotion", "default"), callback_data=f"confirm_{user_id}")])
    
    if back_to_info:
        keyboard.append([InlineKeyboardButton(colored_button("🔙 Back to Roles", "default"), callback_data=f"info_roles_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton(colored_button("Cancel", "default"), callback_data=f"cancel_{user_id}")])
    
    return InlineKeyboardMarkup(keyboard)

async def toggle_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle permission toggle buttons."""
    query = update.callback_query
    
    # Permission check for the admin performing the promotion
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await query.answer(error_msg, show_alert=True)
        return

    data = query.data.split("_")
    
    # Format: toggle_user_id_permission_key
    user_id = int(data[1])
    perm_key = "_".join(data[2:])
    
    # Security check: only the person who started the promotion should be able to toggle (simplified here)
    
    promote_key = f"promote_{user_id}"
    if promote_key not in context.user_data:
        await query.answer("Promotion session expired.")
        return

    context.user_data[promote_key][perm_key] = not context.user_data[promote_key][perm_key]
    
    keyboard = get_promotion_keyboard(
        user_id, 
        context.user_data[promote_key], 
        back_to_info=context.user_data[promote_key].get("back_to_info", False)
    )
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except BadRequest:
        # Message might be the same, ignore
        pass
    await query.answer()

async def confirm_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply the permissions and promote the user."""
    query = update.callback_query
    user_id = int(query.data.split("_")[1])
    chat_id = update.effective_chat.id
    sender_id = query.from_user.id
    
    # Permission check for the admin performing the promotion
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await query.answer(error_msg, show_alert=True)
        return

    promote_key = f"promote_{user_id}"
    if promote_key not in context.user_data:
        await query.answer("Promotion session expired.")
        return

    requested_perms = context.user_data[promote_key]
    
    try:
        # Get bot's own permissions to see what it can actually grant
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        # Determine effective perms: bot can only grant what it has
        # Note: 'creator' status has all perms
        is_creator = bot_member.status == 'creator'
        
        final_perms = {}
        missing_rights = []
        
        for key in PERMISSIONS_MAP.keys():
            requested_val = requested_perms.get(key, False)
            # Bot must have the right to grant it
            # Special case: can_ban_users maps to can_restrict_members for Telegram's check
            check_key = "can_restrict_members" if key == "can_ban_users" else key
            bot_has_right = is_creator or getattr(bot_member, check_key, False)
            
            if requested_val and not bot_has_right:
                missing_rights.append(PERMISSIONS_MAP[key])
                final_perms[key] = False
            else:
                final_perms[key] = requested_val

        if missing_rights:
            rights_str = ", ".join(missing_rights)
            await query.answer(f"⚠️ I cannot grant: {rights_str} (I don't have these rights myself)", show_alert=True)
            # We don't return here, we proceed with the rights I DO have
            # or the user can toggle them off.

        # Calculate effective Telegram can_restrict_members
        # ONLY grant native Telegram restriction right if 'can_ban_users' is selected.
        # 'can_restrict_members' (Mute) in our bot will be handled internally (bot-only).
        effective_can_restrict = final_perms.get('can_ban_users', False)

        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_change_info=final_perms.get('can_change_info', False),
            can_delete_messages=final_perms.get('can_delete_messages', False),
            can_restrict_members=effective_can_restrict,
            can_invite_users=final_perms.get('can_invite_users', False),
            can_pin_messages=final_perms.get('can_pin_messages', False),
            can_post_stories=final_perms.get('can_post_stories', False),
            can_edit_stories=final_perms.get('can_edit_stories', False),
            can_delete_stories=final_perms.get('can_delete_stories', False),
            can_manage_video_chats=final_perms.get('can_manage_video_chats', False),
            can_promote_members=final_perms.get('can_promote_members', False),
            is_anonymous=final_perms.get('is_anonymous', False)
        )
        
        # Update database cache - use merge=False to overwrite with the full set of bot permissions
        update_admin_cache(chat_id, user_id, final_perms, merge=False)
        
        # Build summary message
        summary = []
        for key, label in PERMISSIONS_MAP.items():
            status = "✅" if final_perms.get(key) else "❌"
            summary.append(f"• {label}: {status}")
        
        summary_text = "\n".join(summary)
        success_msg = (
            f"✅ <b>Successfully promoted user to administrator!</b>\n\n"
            f"<b>Permissions Summary:</b>\n{summary_text}"
        )

        if requested_perms.get("back_to_info"):
            await query.answer("Successfully promoted user.")
            query.data = f"info_roles_{user_id}"
            from bot import info_callback_handler
            await info_callback_handler(update, context)
            del context.user_data[promote_key]
            return

        await edit_bot_response(query, context, success_msg, parse_mode='HTML')
        
        # Log to channel
        await log_to_channel(context, 
            f"👤 User: {user_id}\n"
            f"🛡️ Action: Promoted to Admin\n"
            f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
            f"👤 Admin: {query.from_user.id}"
        )
        
        del context.user_data[promote_key]
    except Exception as e:
        error_msg = str(e)
        if "Right_forbidden" in error_msg:
            await edit_bot_response(
                query, context,
                "❌ **Promotion Failed (Right_forbidden)**\n\n"
                "**Reason:** You are trying to give this user a permission that I (the bot) do not have.\n\n"
                "**Fix:**\n"
                "1. Ensure I have ALL the permissions you are trying to give (like 'Remain Anonymous', 'Manage Video Chats', etc.).\n"
                "2. Ensure I have the 'Add New Admins' permission."
            )
        elif "Not_enough_rights" in error_msg:
             await edit_bot_response(query, context, "❌ I don't have enough rights to promote this user.")
        else:
            await edit_bot_response(query, context, f"Failed to promote: {error_msg}")
    
    await query.answer()

async def cancel_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the promotion process."""
    query = update.callback_query
    user_id = int(query.data.split("_")[1])
    promote_key = f"promote_{user_id}"
    
    if promote_key in context.user_data:
        del context.user_data[promote_key]
    
    await edit_bot_response(query, context, "Promotion cancelled.")
    await query.answer()

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demotes an administrator to a regular user."""
    # Permission check - require 'Add New Admins' (can_promote_members)
    has_perm, error_msg = await check_admin_permission(update, context, 'can_promote_members')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_promote_members')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return

    user_id, user_name = await get_user_id(update, context)
    if not user_id:
        await send_bot_response(update, context, "Please reply to a user's message or provide a username/ID to demote them.")
        return

    try:
        # Check if user is actually an admin
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator']:
            await send_bot_response(update, context, f"{user_name} is not an administrator or is the chat owner.")
            return

        # Demote by setting all permissions to False
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_change_info=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False,
            can_manage_video_chats=False,
            can_promote_members=False,
            is_anonymous=False
        )
        
        # Remove from database cache
        remove_admin_cache(chat_id, user_id)
        
        await send_bot_response(update, context, f"✅ Successfully demoted {user_name} to a regular member.")
        
        # Log to channel
        await log_to_channel(context, 
            f"👤 User: {user_name} ({user_id})\n"
            f"📉 Action: Demoted from Admin\n"
            f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
            f"👤 Admin: {update.effective_user.first_name}"
        )
    except Exception as e:
        await send_bot_response(update, context, f"Failed to demote: {str(e)}")

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reloads the admin list and refreshes the bot's presence in the group."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check if user has specific reload permissions
    if not await can_user_reload(chat_id, user_id, context):
        await send_bot_response(update, context, "Only admins with 'Add Admins', 'Ban Users', and 'Change Group Info' permissions can use the /reload command.")
        return

    try:
        # 1. Update the bot's own administrative rights cache (by calling get_chat_member for the bot)
        # This ensures the bot knows its latest permissions
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        # 2. Get the latest admin list from Telegram and sync with MongoDB
        # This is useful for groups where admins have changed recently
        admin_count = await sync_admins(chat_id, context)
        
        # 3. Refresh group settings (like reaction blocking)
        from managers.settings_manager_mongo import get_chat_settings
        settings = get_chat_settings(chat_id)
        if settings.get("block_reactions", False):
            try:
                await context.bot.set_chat_available_reactions(chat_id, reactions=[])
            except: pass
        
        # 4. Success message (Green themed)
        reload_msg = (
            f"✅ **Group Reloaded Successfully!**\n\n"
            f"• **Admin List:** Updated ({admin_count} admins found)\n"
            f"• **Bot Permissions:** Refreshed\n"
            f"• **Group Cache:** Synced\n\n"
            f"Everything is up to date!"
        )
        
        await send_bot_response(update, context, reload_msg, parse_mode="MARKDOWN")
        
        # Log to channel
        await log_to_channel(context, 
            f"🔄 #RELOAD\n"
            f"📍 Group: {update.effective_chat.title} ({chat_id})\n"
            f"👤 Admin: {update.effective_user.first_name}"
        )
    except Exception as e:
        logging.error(f"Error during reload: {e}")
        await send_bot_response(update, context, f"❌ Failed to reload group: {e}")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pins the message that is replied to."""
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_pin_messages')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_pin_messages')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return

    if not update.message.reply_to_message:
        await send_bot_response(update, context, "Please reply to a message you want to pin.")
        return

    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=update.message.reply_to_message.message_id)
        await send_bot_response(update, context, "✅ Message pinned successfully!")
        
    except Exception as e:
        await send_bot_response(update, context, f"Failed to pin message: {str(e)}")

async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unpins the message that is replied to, or the last pinned message if no reply."""
    # Permission check
    has_perm, error_msg = await check_admin_permission(update, context, 'can_pin_messages')
    if not has_perm:
        await send_bot_response(update, context, error_msg)
        return

    chat_id = update.effective_chat.id
    # Bot permission check
    has_bot_perm, bot_error_msg = await check_bot_permission(update, context, 'can_pin_messages')
    if not has_bot_perm:
        await send_bot_response(update, context, bot_error_msg)
        return

    try:
        if update.message.reply_to_message:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=update.message.reply_to_message.message_id)
            await send_bot_response(update, context, "✅ Message unpinned successfully!")
        else:
            await context.bot.unpin_all_chat_messages(chat_id=chat_id)
            await send_bot_response(update, context, "✅ All messages unpinned successfully!")
        
    except Exception as e:
        await send_bot_response(update, context, f"Failed to unpin message: {str(e)}")

async def staffstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin performance analytics."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Permission check: Change Group Info AND Ban Users
    # We check them one by one
    has_info_perm, _ = await check_admin_permission(update, context, 'can_change_info')
    has_ban_perm, _ = await check_admin_permission(update, context, 'can_ban_users')
    
    if not (has_info_perm and has_ban_perm):
        return await send_bot_response(update, context, "❌ You need both 'Change Group Info' and 'Ban Users' permissions to view staff statistics.")

    stats = get_staff_stats(chat.id)
    
    if not stats:
        return await send_bot_response(update, context, "📈 No staff statistics recorded yet for this group.")

    text = f"📊 <b>Admin Performance - {chat.title}</b>\n\n"
    
    # Show top 10 admins
    for i, s in enumerate(stats[:10], 1):
        admin_id = s.get("admin_id")
        actions = s.get("actions", {})
        total = s.get("total_actions", 0)
        
        # Try to get admin name
        try:
            member = await chat.get_member(admin_id)
            name = member.user.first_name
        except:
            name = f"Admin {admin_id}"
            
        text += f"{i}. <b>{name}</b> (<code>{admin_id}</code>)\n"
        text += f"   └ Total Actions: <code>{total}</code>\n"
        
        details = []
        if actions.get("ban"): details.append(f"Bans: {actions['ban']}")
        if actions.get("mute"): details.append(f"Mutes: {actions['mute']}")
        if actions.get("warn"): details.append(f"Warns: {actions['warn']}")
        if actions.get("purge"): details.append(f"Purged: {actions['purge']} msgs")
        
        if details:
            text += f"   └ " + " | ".join(details) + "\n"
        text += "\n"

    await send_bot_response(update, context, text, parse_mode=ParseMode.HTML)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to get bot logs (OWNER only)."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only the bot owner can access system logs.")
        return
        
    try:
        import subprocess
        # Get last 100 lines of systemd journal logs
        result = subprocess.run(
            ["journalctl", "-u", "titanic-bot.service", "-n", "100", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logs = result.stdout
        if not logs.strip():
            logs = "No logs found or failed to read journalctl."
            
        # If too long, send as a text file
        if len(logs) > 3000:
            import io
            bio = io.BytesIO(logs.encode('utf-8'))
            bio.name = "bot_logs.txt"
            await update.message.reply_document(document=bio, filename="bot_logs.txt", caption="📋 Here are the latest bot logs:")
        else:
            await update.message.reply_text(f"<pre>{logs}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to retrieve logs: {str(e)}")

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to pull latest changes from git and restart the bot (OWNER only)."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only the bot owner can trigger updates.")
        return
        
    status_msg = await update.message.reply_text("🔄 Initiating git pull and update process...")
    try:
        import subprocess
        # Run git pull
        git_res = subprocess.run(
            ["git", "pull"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        pull_output = git_res.stdout or git_res.stderr
        
        await status_msg.edit_text(f"📥 Git Pull Output:\n<pre>{pull_output}</pre>\n\n🔄 Restarting bot service...", parse_mode="HTML")
        
        # Restart the systemd service.
        subprocess.Popen(["systemctl", "restart", "titanic-bot.service"])
    except Exception as e:
        await status_msg.edit_text(f"❌ Update failed: {str(e)}")

def get_admin_handlers():
    return [
        CommandHandler("promote", promote_user),
        CommandHandler("demote", demote_command),
        CommandHandler("reload", reload_command),
        CommandHandler("pin", pin_command),
        CommandHandler("unpin", unpin_command),
        CommandHandler("staffstats", staffstats_command),
        CommandHandler("setadmintitle", set_admin_title_command),
        CommandHandler("deladmintitle", delete_admin_title_command),
        CommandHandler("logs", logs_command),
        CommandHandler("update", update_command),
        CallbackQueryHandler(toggle_permission, pattern="^toggle_"),
        CallbackQueryHandler(confirm_promotion, pattern="^confirm_"),
        CallbackQueryHandler(cancel_promotion, pattern="^cancel_")
    ]
