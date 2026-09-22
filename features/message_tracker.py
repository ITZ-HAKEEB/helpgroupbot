from collections import defaultdict, deque
import logging
import asyncio
from core.database import get_collection

logger = logging.getLogger(__name__)

# Fast in-memory cache: (chat_id, user_id) -> deque of recent message_ids (up to 100)
_RECENT_USER_MESSAGES = defaultdict(lambda: deque(maxlen=100))

def track_user_message(chat_id: int, user_id: int, message_id: int):
    """
    Tracks a message ID for a user in a specific chat.
    Stored in memory for immediate access and in MongoDB for persistence across dyno restarts.
    """
    if not chat_id or not user_id or not message_id:
        return
        
    try:
        # 1. Update memory
        _RECENT_USER_MESSAGES[(chat_id, user_id)].append(message_id)
        
        # 2. Async persistence to MongoDB (non-blocking)
        def _persist():
            try:
                col = get_collection("recent_user_messages")
                if col is not None:
                    col.update_one(
                        {"chat_id": chat_id, "user_id": user_id},
                        {"$push": {"message_ids": {"$each": [message_id], "$slice": -100}}},
                        upsert=True
                    )
            except Exception as e:
                logger.debug(f"[TRACKER] MongoDB persist error: {e}")

        asyncio.create_task(asyncio.to_thread(_persist))
    except Exception as e:
        logger.debug(f"[TRACKER] Error tracking user message: {e}")

def get_tracked_user_messages(chat_id: int, user_id: int) -> list:
    """Returns all tracked message IDs for a user in a chat from memory and MongoDB."""
    if not chat_id or not user_id:
        return []

    msg_ids = set()
    
    # 1. Memory cache
    if (chat_id, user_id) in _RECENT_USER_MESSAGES:
        msg_ids.update(_RECENT_USER_MESSAGES[(chat_id, user_id)])
        
    # 2. MongoDB
    try:
        col = get_collection("recent_user_messages")
        if col is not None:
            doc = col.find_one({"chat_id": chat_id, "user_id": user_id})
            if doc and "message_ids" in doc:
                msg_ids.update(doc["message_ids"])
    except Exception as e:
        logger.debug(f"[TRACKER] Error fetching tracked messages: {e}")
        
    return sorted(list(msg_ids))

def clear_tracked_user_messages(chat_id: int, user_id: int):
    """Clears tracked message IDs after messages have been deleted."""
    try:
        if (chat_id, user_id) in _RECENT_USER_MESSAGES:
            _RECENT_USER_MESSAGES[(chat_id, user_id)].clear()
            
        def _clear_db():
            try:
                col = get_collection("recent_user_messages")
                if col is not None:
                    col.delete_one({"chat_id": chat_id, "user_id": user_id})
            except Exception as e:
                logger.debug(f"[TRACKER] MongoDB delete error: {e}")

        asyncio.create_task(asyncio.to_thread(_clear_db))
    except Exception as e:
        logger.debug(f"[TRACKER] Error clearing tracked messages: {e}")
