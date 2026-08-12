import os
import logging
import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL")
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if not REDIS_URL:
        logger.warning("REDIS_URL environment variable is not set. Falling back to MongoDB only.")
        return None

    try:
        # Handles heroku redis ssl or standard redis url
        url = REDIS_URL
        if url.startswith("redis://") or url.startswith("rediss://"):
            _redis_client = redis.from_url(url, decode_responses=True, socket_connect_timeout=3)
        else:
            _redis_client = redis.Redis(host=REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        _redis_client.ping()
        logger.info("Connected to Redis server successfully!")
        return _redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}. Falling back to MongoDB.")
        _redis_client = None
        return None
