import logging
import datetime
from core.database import get_collection, COLLECTIONS

def get_chat_filters(chat_id):
    """Get all filters for a chat from MongoDB."""
    try:
        filters_col = get_collection(COLLECTIONS["filters"])
        if filters_col is None:
            return {}
        
        chat_id_str = str(chat_id)
        cursor = filters_col.find({"chat_id": chat_id_str})
        
        filters_dict = {}
        for doc in cursor:
            filters_dict[doc["trigger"]] = doc.get("content", "")
        
        return filters_dict
    except Exception as e:
        logging.error(f"Error getting chat filters: {e}")
        return {}

def add_chat_filter(chat_id, trigger, content):
    """Add or update a filter for a chat in MongoDB."""
    try:
        filters_col = get_collection(COLLECTIONS["filters"])
        if filters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        trigger_lower = trigger.lower()
        
        result = filters_col.update_one(
            {"chat_id": chat_id_str, "trigger": trigger_lower},
            {
                "$set": {
                    "content": content,
                    "updated_at": datetime.datetime.now()
                },
                "$setOnInsert": {
                    "chat_id": chat_id_str,
                    "trigger": trigger_lower,
                    "created_at": datetime.datetime.now()
                }
            },
            upsert=True
        )
        
        return result.upserted_id is not None or result.modified_count > 0
    except Exception as e:
        logging.error(f"Error adding chat filter: {e}")
        return False

def remove_chat_filter(chat_id, trigger):
    """Remove a specific filter from a chat in MongoDB."""
    try:
        filters_col = get_collection(COLLECTIONS["filters"])
        if filters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        trigger_lower = trigger.lower()
        
        result = filters_col.delete_one({
            "chat_id": chat_id_str,
            "trigger": trigger_lower
        })
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error removing chat filter: {e}")
        return False

def remove_all_chat_filters(chat_id):
    """Remove all filters for a chat in MongoDB."""
    try:
        filters_col = get_collection(COLLECTIONS["filters"])
        if filters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        result = filters_col.delete_many({"chat_id": chat_id_str})
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error removing all chat filters: {e}")
        return False

def get_filter_count(chat_id):
    """Get the number of filters for a chat."""
    try:
        filters_col = get_collection(COLLECTIONS["filters"])
        if filters_col is None:
            return 0
        
        chat_id_str = str(chat_id)
        return filters_col.count_documents({"chat_id": chat_id_str})
    except Exception as e:
        logging.error(f"Error getting filter count: {e}")
        return 0
