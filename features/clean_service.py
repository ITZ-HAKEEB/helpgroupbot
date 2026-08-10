import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from core.config import delete_message_job

async def clean_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically deletes service messages based on group settings."""
    if not update.message:
        return
        
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    
    if not settings.get("clean_service_enabled", True):
        return

    should_delete = False
    
    # 1. New Member Joins
    if update.message.new_chat_members:
        if settings.get("clean_join", True):
            should_delete = True
        
    # 2. Member Leaves
    elif update.message.left_chat_member:
        if settings.get("clean_left", True):
            should_delete = True
        
    # 3. Video/Voice Chat Messages
    elif update.message.video_chat_started:
        if settings.get("clean_video_chat_started", True):
            should_delete = True
    elif update.message.video_chat_ended:
        if settings.get("clean_video_chat_ended", True):
            should_delete = True
    elif update.message.video_chat_participants_invited:
        if settings.get("clean_video_chat_invited", True):
            should_delete = True
    elif update.message.video_chat_scheduled:
        if settings.get("clean_video_chat_scheduled", True):
            should_delete = True
            
    # 4. Other Standard Service Messages
    elif update.message.pinned_message:
        if settings.get("clean_pinned_message", True):
            should_delete = True
    elif update.message.new_chat_title:
        if settings.get("clean_title", True):
            # Name change notification should delete in 15 seconds
            context.job_queue.run_once(
                delete_message_job,
                15,
                data={"chat_id": chat_id, "message_id": update.message.message_id}
            )
            return
    elif update.message.new_chat_photo or update.message.delete_chat_photo:
        if settings.get("clean_photo", True):
            should_delete = True
            
    # 5. Fallback for ALL other service messages
    # If it's any status update and master clean is enabled, we delete it
    # This covers CHAT_CREATED, MIGRATE, AUTO_DELETE_TIMER_CHANGED, etc.
    else:
        # Check if it's actually a service message (any property that makes it a StatusUpdate)
        m = update.message
        if any([
            m.group_chat_created, m.supergroup_chat_created, m.channel_chat_created,
            m.migrate_to_chat_id, m.migrate_from_chat_id,
            m.message_auto_delete_timer_changed,
            m.proximity_alert_triggered,
            m.forum_topic_created, m.forum_topic_edited,
            m.forum_topic_closed, m.forum_topic_reopened,
            m.general_forum_topic_hidden, m.general_forum_topic_unhidden,
            m.write_access_allowed, m.web_app_data,
            m.successful_payment, m.connected_website, m.passport_data
        ]):
            should_delete = True

    if should_delete:
        try:
            await update.message.delete()
        except Exception as e:
            logging.error(f"Failed to delete service message in {chat_id}: {e}")

def get_clean_service_handlers():
    """Return handlers for cleaning service messages."""
    return [
        MessageHandler(
            filters.StatusUpdate.ALL, # Catch everything
            clean_service_messages
        )
    ]
