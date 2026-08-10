import logging
from datetime import datetime
from core.database import get_collection

COLLECTION_NAME = "staff_stats"

def increment_staff_stat(chat_id, admin_id, action_type, count=1):
    """Increment a specific action count for an admin in a chat."""
    try:
        col = get_collection(COLLECTION_NAME)
        if col is None:
            return False
            
        # Use string IDs for MongoDB keys consistency if preferred, 
        # but here we'll stick to what the rest of the bot uses.
        query = {
            "chat_id": str(chat_id),
            "admin_id": int(admin_id)
        }
        
        update = {
            "$inc": {f"actions.{action_type}": count},
            "$set": {"last_action_at": datetime.utcnow()}
        }
        
        col.update_one(query, update, upsert=True)
        return True
    except Exception as e:
        logging.error(f"Error incrementing staff stat: {e}")
        return False

def get_staff_stats(chat_id):
    """Get all staff stats for a chat, sorted by total actions."""
    try:
        col = get_collection(COLLECTION_NAME)
        if col is None:
            return []
            
        stats = list(col.find({"chat_id": str(chat_id)}))
        
        # Calculate total actions for sorting
        for s in stats:
            s["total_actions"] = sum(s.get("actions", {}).values())
            
        # Sort by total actions descending
        stats.sort(key=lambda x: x["total_actions"], reverse=True)
        return stats
    except Exception as e:
        logging.error(f"Error getting staff stats: {e}")
        return []
