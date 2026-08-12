import datetime
import logging
from core.database import get_database, get_collection
from core.redis_db import get_redis_client

logger = logging.getLogger(__name__)

def _get_chat_counts_col():
    return get_collection("chat_counts")


def _get_dates():
    now = datetime.datetime.utcnow()
    daily_key = now.strftime("%Y-%m-%d")
    # Year-Week number
    weekly_key = now.strftime("%Y-%W")
    return daily_key, weekly_key

def increment_user_count(chat_id: int, user_id: int, user_name: str, points: int = 1):
    """
    Increment message count for a specific user in a specific group.
    Group isolated: chat_id is part of every key and document filter.
    """
    chat_id_str = str(chat_id)
    user_id_str = str(user_id)
    daily_key, weekly_key = _get_dates()

    # 1. Update Redis if available
    r = get_redis_client()
    if r is not None:
        try:
            r.hincrby(f"chatcount:{chat_id_str}:daily:{daily_key}", user_id_str, points)
            r.hincrby(f"chatcount:{chat_id_str}:weekly:{weekly_key}", user_id_str, points)
            r.hincrby(f"chatcount:{chat_id_str}:overall", user_id_str, points)
            r.hset(f"chatusers:{chat_id_str}", user_id_str, user_name)
        except Exception as e:
            logger.error(f"Redis increment error: {e}")

    # 2. Update MongoDB for permanent persistence
    col = _get_chat_counts_col()
    if col is not None:
        try:
            filter_query = {
                "chat_id": chat_id,
                "user_id": user_id
            }
            update_query = {
                "$set": {
                    "user_name": user_name,
                    "updated_at": datetime.datetime.utcnow()
                },
                "$inc": {
                    f"daily.{daily_key}": points,
                    f"weekly.{weekly_key}": points,
                    "overall": points
                }
            }
            col.update_one(filter_query, update_query, upsert=True)
        except Exception as e:
            logger.error(f"MongoDB chat count increment error: {e}")

def get_top_chatters(chat_id: int, timeframe: str = "daily", limit: int = 10):
    """
    Retrieve top users for a specific group.
    timeframe: 'daily', 'weekly', or 'overall'
    """
    chat_id_str = str(chat_id)
    daily_key, weekly_key = _get_dates()
    top_users = []

    # Try Redis first
    r = get_redis_client()
    if r is not None:
        try:
            if timeframe == "daily":
                redis_key = f"chatcount:{chat_id_str}:daily:{daily_key}"
            elif timeframe == "weekly":
                redis_key = f"chatcount:{chat_id_str}:weekly:{weekly_key}"
            else:
                redis_key = f"chatcount:{chat_id_str}:overall"

            data = r.hgetall(redis_key)
            if data:
                names_map = r.hgetall(f"chatusers:{chat_id_str}") or {}
                sorted_items = sorted(data.items(), key=lambda x: int(x[1]), reverse=True)[:limit]
                for uid, count in sorted_items:
                    name = names_map.get(uid, f"User {uid}")
                    top_users.append({
                        "name": name,
                        "count": int(count)
                    })
                return top_users
        except Exception as e:
            logger.error(f"Redis fetch top chatters error: {e}")

    # Fallback to MongoDB
    col = _get_chat_counts_col()
    if col is not None:
        try:
            field_name = f"daily.{daily_key}" if timeframe == "daily" else (f"weekly.{weekly_key}" if timeframe == "weekly" else "overall")
            cursor = col.find(
                {"chat_id": chat_id, field_name: {"$gt": 0}},
                {"user_name": 1, field_name: 1}
            ).sort(field_name, -1).limit(limit)

            for doc in cursor:
                count_val = doc.get(field_name, 0)
                if isinstance(count_val, dict):
                    count_val = count_val.get(daily_key if timeframe == "daily" else weekly_key, 0)
                top_users.append({
                    "name": doc.get("user_name", "User"),
                    "count": int(count_val)
                })
        except Exception as e:
            logger.error(f"MongoDB fetch top chatters error: {e}")

    return top_users

def reset_group_count(chat_id: int):
    """Reset chat counts for a specific group."""
    chat_id_str = str(chat_id)
    daily_key, weekly_key = _get_dates()

    r = get_redis_client()
    if r is not None:
        try:
            r.delete(f"chatcount:{chat_id_str}:daily:{daily_key}")
            r.delete(f"chatcount:{chat_id_str}:weekly:{weekly_key}")
            r.delete(f"chatcount:{chat_id_str}:overall")
        except Exception as e:
            logger.error(f"Redis reset error: {e}")

    col = _get_chat_counts_col()
    if col is not None:
        try:
            col.delete_many({"chat_id": chat_id})
        except Exception as e:
            logger.error(f"MongoDB reset error: {e}")
