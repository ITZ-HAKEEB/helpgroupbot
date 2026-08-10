import logging
import datetime
from core.database import get_collection, COLLECTIONS

# Warning Functions
def get_user_warns(chat_id, user_id):
    """Get user warn count from MongoDB."""
    try:
        warns_col = get_collection(COLLECTIONS["warns"])
        if warns_col is None:
            return 0
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        warn_doc = warns_col.find_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return warn_doc.get("warn_count", 0) if warn_doc else 0
    except Exception as e:
        logging.error(f"Error getting user warns: {e}")
        return 0

def add_warn(chat_id, user_id):
    """Add a warn to a user in MongoDB."""
    try:
        warns_col = get_collection(COLLECTIONS["warns"])
        if warns_col is None:
            return 0
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = warns_col.update_one(
            {"chat_id": chat_id_str, "user_id": user_id_str},
            {
                "$inc": {"warn_count": 1},
                "$setOnInsert": {
                    "chat_id": chat_id_str,
                    "user_id": user_id_str,
                    "created_at": datetime.datetime.now()
                },
                "$set": {"updated_at": datetime.datetime.now()}
            },
            upsert=True
        )
        
        # Get the new warn count
        warn_doc = warns_col.find_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return warn_doc.get("warn_count", 0) if warn_doc else 0
    except Exception as e:
        logging.error(f"Error adding warn: {e}")
        return 0

def reset_warns(chat_id, user_id):
    """Reset warns for a user in MongoDB."""
    try:
        warns_col = get_collection(COLLECTIONS["warns"])
        if warns_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = warns_col.update_one(
            {"chat_id": chat_id_str, "user_id": user_id_str},
            {"$set": {"warn_count": 0, "updated_at": datetime.datetime.now()}}
        )
        
        return result.modified_count > 0
    except Exception as e:
        logging.error(f"Error resetting warns: {e}")
        return False

def delete_user_warns(chat_id, user_id):
    """Completely delete warn record for a user."""
    try:
        warns_col = get_collection(COLLECTIONS["warns"])
        if warns_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = warns_col.delete_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error deleting user warns: {e}")
        return False

# Muter Functions
def is_muter(chat_id, user_id):
    """Check if a user has muter role in MongoDB."""
    try:
        muters_col = get_collection(COLLECTIONS["muters"])
        if muters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        muter_doc = muters_col.find_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return muter_doc is not None
    except Exception as e:
        logging.error(f"Error checking muter: {e}")
        return False

def add_muter(chat_id, user_id):
    """Add a user as muter in MongoDB."""
    try:
        muters_col = get_collection(COLLECTIONS["muters"])
        if muters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = muters_col.update_one(
            {"chat_id": chat_id_str, "user_id": user_id_str},
            {
                "$setOnInsert": {
                    "chat_id": chat_id_str,
                    "user_id": user_id_str,
                    "created_at": datetime.datetime.now()
                }
            },
            upsert=True
        )
        
        return result.upserted_id is not None or result.modified_count > 0
    except Exception as e:
        logging.error(f"Error adding muter: {e}")
        return False

def remove_muter(chat_id, user_id):
    """Remove a user from muters in MongoDB."""
    try:
        muters_col = get_collection(COLLECTIONS["muters"])
        if muters_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = muters_col.delete_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error removing muter: {e}")
        return False

def get_all_muters(chat_id):
    """Returns a list of user IDs for all muters in a chat."""
    try:
        muters_col = get_collection(COLLECTIONS["muters"])
        if muters_col is None:
            return []
        
        chat_id_str = str(chat_id)
        cursor = muters_col.find({"chat_id": chat_id_str})
        
        return [doc["user_id"] for doc in cursor]
    except Exception as e:
        logging.error(f"Error getting all muters: {e}")
        return []

# Voice Chat Manager Functions
def is_voice_chat_manager(chat_id, user_id):
    """Check if a user can manage voice chats in MongoDB."""
    try:
        vcm_col = get_collection(COLLECTIONS["voice_chat_managers"])
        if vcm_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        manager_doc = vcm_col.find_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return manager_doc is not None
    except Exception as e:
        logging.error(f"Error checking voice chat manager: {e}")
        return False

def add_voice_chat_manager(chat_id, user_id):
    """Add a user as voice chat manager in MongoDB."""
    try:
        vcm_col = get_collection(COLLECTIONS["voice_chat_managers"])
        if vcm_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = vcm_col.update_one(
            {"chat_id": chat_id_str, "user_id": user_id_str},
            {
                "$setOnInsert": {
                    "chat_id": chat_id_str,
                    "user_id": user_id_str,
                    "created_at": datetime.datetime.now()
                }
            },
            upsert=True
        )
        
        return result.upserted_id is not None or result.modified_count > 0
    except Exception as e:
        logging.error(f"Error adding voice chat manager: {e}")
        return False

def remove_voice_chat_manager(chat_id, user_id):
    """Remove a user from voice chat managers in MongoDB."""
    try:
        vcm_col = get_collection(COLLECTIONS["voice_chat_managers"])
        if vcm_col is None:
            return False
        
        chat_id_str = str(chat_id)
        user_id_str = str(user_id)
        
        result = vcm_col.delete_one({
            "chat_id": chat_id_str,
            "user_id": user_id_str
        })
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error removing voice chat manager: {e}")
        return False

def get_all_voice_chat_managers(chat_id):
    """Returns a list of user IDs for all voice chat managers in a chat."""
    try:
        vcm_col = get_collection(COLLECTIONS["voice_chat_managers"])
        if vcm_col is None:
            return []
        
        chat_id_str = str(chat_id)
        cursor = vcm_col.find({"chat_id": chat_id_str})
        
        return [doc["user_id"] for doc in cursor]
    except Exception as e:
        logging.error(f"Error getting all voice chat managers: {e}")
        return []

# Banned Channels Functions
def is_channel_banned(chat_id, channel_id):
    """Checks if a channel (sender chat) is banned in a specific chat."""
    try:
        banned_col = get_collection(COLLECTIONS["banned_channels"])
        if banned_col is None:
            return False
        
        chat_id_str = str(chat_id)
        channel_id_str = str(channel_id)
        
        banned_doc = banned_col.find_one({
            "chat_id": chat_id_str,
            "channel_id": channel_id_str
        })
        
        return banned_doc is not None
    except Exception as e:
        logging.error(f"Error checking banned channel: {e}")
        return False

def add_banned_channel(chat_id, channel_id):
    """Adds a channel to the banned list for a chat in MongoDB."""
    try:
        banned_col = get_collection(COLLECTIONS["banned_channels"])
        if banned_col is None:
            return False
        
        chat_id_str = str(chat_id)
        channel_id_str = str(channel_id)
        
        result = banned_col.update_one(
            {"chat_id": chat_id_str, "channel_id": channel_id_str},
            {
                "$setOnInsert": {
                    "chat_id": chat_id_str,
                    "channel_id": channel_id_str,
                    "created_at": datetime.datetime.now()
                }
            },
            upsert=True
        )
        
        return result.upserted_id is not None or result.modified_count > 0
    except Exception as e:
        logging.error(f"Error adding banned channel: {e}")
        return False

def remove_banned_channel(chat_id, channel_id):
    """Removes a channel from the banned list for a chat in MongoDB."""
    try:
        banned_col = get_collection(COLLECTIONS["banned_channels"])
        if banned_col is None:
            return False
        
        chat_id_str = str(chat_id)
        channel_id_str = str(channel_id)
        
        result = banned_col.delete_one({
            "chat_id": chat_id_str,
            "channel_id": channel_id_str
        })
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error removing banned channel: {e}")
        return False

def get_all_banned_channels(chat_id):
    """Get all banned channels for a chat."""
    try:
        banned_col = get_collection(COLLECTIONS["banned_channels"])
        if banned_col is None:
            return []
        
        chat_id_str = str(chat_id)
        cursor = banned_col.find({"chat_id": chat_id_str})
        
        return [doc["channel_id"] for doc in cursor]
    except Exception as e:
        logging.error(f"Error getting banned channels: {e}")
        return []
