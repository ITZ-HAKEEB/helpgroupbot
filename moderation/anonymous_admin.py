"""
Anonymous Admin Permission Handler

This module handles permission checking for anonymous admins in Telegram groups.
When an admin sends messages anonymously, Telegram uses the special ID 1087968824
(Group Anonymous Bot). This module checks the actual permissions of the anonymous
admin by examining the chat's admin list and the anonymous admin configuration.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from core.config import OWNER_ID

# Telegram's ID for anonymous admins (Group Anonymous Bot)
ANONYMOUS_ADMIN_ID = 1087968824


def is_anonymous_admin(user_id):
    """Check if the user ID belongs to an anonymous admin."""
    return user_id == ANONYMOUS_ADMIN_ID


async def get_anonymous_admin_permissions(chat_id, context):
    """
    Get the permissions of the anonymous admin in a specific chat.
    
    Returns a dict with permission booleans or None if anonymous admin is not configured.
    """
    try:
        # Get all administrators in the chat
        admins = await context.bot.get_chat_administrators(chat_id)
        
        # Find anonymous admins (those with is_anonymous=True)
        anonymous_admins = [admin for admin in admins if admin.is_anonymous]
        
        if not anonymous_admins:
            logging.info(f"No anonymous admins found in chat {chat_id}")
            return None
        
        # We check if ANY anonymous admin has the required permissions.
        # If at least one anonymous admin has the permission, we allow the action.
        # This is more permissive but necessary since we can't distinguish between them.
        
        combined_permissions = {
            'can_change_info': False,
            'can_delete_messages': False,
            'can_restrict_members': False,
            'can_invite_users': False,
            'can_pin_messages': False,
            'can_post_stories': False,
            'can_edit_stories': False,
            'can_delete_stories': False,
            'can_manage_video_chats': False,
            'can_promote_members': False,
            'can_ban_users': False,  # Custom permission
            'is_anonymous': True,
        }
        
        from managers.admin_manager_mongo import get_stored_admin_permissions
        
        for anon_admin in anonymous_admins:
            # Use OR logic - if any anonymous admin has the permission, enable it
            if anon_admin.can_change_info:
                combined_permissions['can_change_info'] = True
            if anon_admin.can_delete_messages:
                combined_permissions['can_delete_messages'] = True
            if anon_admin.can_restrict_members:
                combined_permissions['can_restrict_members'] = True
            if anon_admin.can_invite_users:
                combined_permissions['can_invite_users'] = True
            if anon_admin.can_pin_messages:
                combined_permissions['can_pin_messages'] = True
            if hasattr(anon_admin, 'can_post_stories') and anon_admin.can_post_stories:
                combined_permissions['can_post_stories'] = True
            if hasattr(anon_admin, 'can_edit_stories') and anon_admin.can_edit_stories:
                combined_permissions['can_edit_stories'] = True
            if hasattr(anon_admin, 'can_delete_stories') and anon_admin.can_delete_stories:
                combined_permissions['can_delete_stories'] = True
            if anon_admin.can_manage_video_chats:
                combined_permissions['can_manage_video_chats'] = True
            if anon_admin.can_promote_members:
                combined_permissions['can_promote_members'] = True
            
            # Check our custom database cache for additional permissions
            admin_data = get_stored_admin_permissions(chat_id, anon_admin.user.id)
            if admin_data:
                if admin_data.get('can_ban_users'):
                    combined_permissions['can_ban_users'] = True
        
        logging.info(f"Found {len(anonymous_admins)} anonymous admin(s) in chat {chat_id}. Combined permissions (OR logic): {combined_permissions}")
        return combined_permissions
    except Exception as e:
        logging.error(f"Error getting anonymous admin permissions in chat {chat_id}: {e}")
        return None


async def anonymous_admin_has_permission(chat_id, context, permission_key):
    """
    Check if the anonymous admin has a specific permission.
    
    Args:
        chat_id: The chat ID
        context: The bot context
        permission_key: The permission to check (e.g., 'can_restrict_members')
    
    Returns:
        bool: True if anonymous admin has the permission, False otherwise
    """
    permissions = await get_anonymous_admin_permissions(chat_id, context)
    
    if permissions is None:
        # No anonymous admins configured
        return False
    
    return permissions.get(permission_key, False)


async def check_anonymous_admin_ban_permission(chat_id, context):
    """
    Check if anonymous admin can ban/restrict members.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    # Check both Telegram's restriction right AND our custom ban permission
    permissions = await get_anonymous_admin_permissions(chat_id, context)
    
    if permissions is None:
        return False, "❌ No anonymous admins found."
    
    # If ANY anonymous admin has the custom ban permission, allow it.
    # Fallback: if we don't have custom data but they have Telegram restriction right, allow it.
    has_perm = permissions.get('can_ban_users', False) or permissions.get('can_restrict_members', False)
    
    logging.info(f"Anonymous admin ban permission check for chat {chat_id}: {has_perm}")
    
    if has_perm:
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Ban Users' permission. Please enable 'Ban Users' permission for anonymous admins in group settings."


async def check_anonymous_admin_mute_permission(chat_id, context):
    """
    Check if anonymous admin can mute/restrict members.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    has_perm = await anonymous_admin_has_permission(chat_id, context, 'can_restrict_members')
    logging.info(f"Anonymous admin mute permission check for chat {chat_id}: {has_perm}")
    
    if has_perm:
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Mute/Restrict Users' permission. Please enable 'Mute/Restrict Users' permission for anonymous admins in group settings."


async def check_anonymous_admin_promote_permission(chat_id, context):
    """
    Check if anonymous admin can promote/demote members.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_promote_members'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Add New Admins' permission."


async def check_anonymous_admin_pin_permission(chat_id, context):
    """
    Check if anonymous admin can pin messages.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_pin_messages'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Pin Messages' permission."


async def check_anonymous_admin_delete_permission(chat_id, context):
    """
    Check if anonymous admin can delete messages.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_delete_messages'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Delete Messages' permission."


async def check_anonymous_admin_invite_permission(chat_id, context):
    """
    Check if anonymous admin can invite users.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_invite_users'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Invite Users' permission."


async def check_anonymous_admin_change_info_permission(chat_id, context):
    """
    Check if anonymous admin can change group info.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_change_info'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Change Group Info' permission."


async def check_anonymous_admin_video_chat_permission(chat_id, context):
    """
    Check if anonymous admin can manage video chats.
    
    Returns:
        tuple: (has_permission, error_message)
    """
    if await anonymous_admin_has_permission(chat_id, context, 'can_manage_video_chats'):
        return True, None
    return False, "❌ Anonymous admin doesn't have 'Manage Video Chats' permission."


async def validate_anonymous_admin_action(chat_id, context, action, required_permission):
    """
    Generic validator for anonymous admin actions.
    
    Args:
        chat_id: The chat ID
        context: The bot context
        action: The action being performed (for logging)
        required_permission: The permission key required
    
    Returns:
        tuple: (is_allowed, error_message)
    """
    has_perm, error_msg = await globals()[f"check_anonymous_admin_{required_permission}_permission"](chat_id, context)
    
    if not has_perm:
        logging.warning(f"Anonymous admin attempted {action} without required permission in chat {chat_id}")
        return False, error_msg
    
    logging.info(f"Anonymous admin performed {action} in chat {chat_id}")
    return True, None
