import logging
import datetime
from core.database import get_collection, COLLECTIONS

def add_blocked_content(chat_id, content_type, content_value):
    """Adds a specific content to the block list for a chat in MongoDB."""
    try:
        blocked_col = get_collection(COLLECTIONS["blocked_content"])
        if blocked_col is None:
            return False
        
        chat_id_str = str(chat_id)
        
        # Find or create the document for this chat
        blocked_doc = blocked_col.find_one({"chat_id": chat_id_str})
        
        if not blocked_doc:
            # Create new document
            blocked_doc = {
                "chat_id": chat_id_str,
                "text": [],
                "media": [],
                "stickerpack": [],
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now()
            }
            blocked_col.insert_one(blocked_doc)
        
        # Add the content based on type
        if content_type == "text":
            content_value = content_value.lower().strip()
            if content_value not in blocked_doc["text"]:
                blocked_col.update_one(
                    {"chat_id": chat_id_str},
                    {
                        "$push": {"text": content_value},
                        "$set": {"updated_at": datetime.datetime.now()}
                    }
                )
                return True
        elif content_type == "media":
            if content_value not in blocked_doc["media"]:
                blocked_col.update_one(
                    {"chat_id": chat_id_str},
                    {
                        "$push": {"media": content_value},
                        "$set": {"updated_at": datetime.datetime.now()}
                    }
                )
                return True
        elif content_type == "stickerpack":
            if content_value not in blocked_doc.get("stickerpack", []):
                blocked_col.update_one(
                    {"chat_id": chat_id_str},
                    {
                        "$push": {"stickerpack": content_value},
                        "$set": {"updated_at": datetime.datetime.now()}
                    }
                )
                return True
        
        return False
    except Exception as e:
        logging.error(f"Error adding blocked content: {e}")
        return False

def remove_blocked_content(chat_id, content_type, content_value):
    """Removes a specific content from the block list for a chat in MongoDB."""
    try:
        blocked_col = get_collection(COLLECTIONS["blocked_content"])
        if blocked_col is None:
            return False
        
        chat_id_str = str(chat_id)
        
        if content_type == "text":
            content_value = content_value.lower().strip()
            result = blocked_col.update_one(
                {"chat_id": chat_id_str},
                {
                    "$pull": {"text": content_value},
                    "$set": {"updated_at": datetime.datetime.now()}
                }
            )
            return result.modified_count > 0
        elif content_type == "media":
            result = blocked_col.update_one(
                {"chat_id": chat_id_str},
                {
                    "$pull": {"media": content_value},
                    "$set": {"updated_at": datetime.datetime.now()}
                }
            )
            return result.modified_count > 0
        elif content_type == "stickerpack":
            result = blocked_col.update_one(
                {"chat_id": chat_id_str},
                {
                    "$pull": {"stickerpack": content_value},
                    "$set": {"updated_at": datetime.datetime.now()}
                }
            )
            return result.modified_count > 0
        
        return False
    except Exception as e:
        logging.error(f"Error removing blocked content: {e}")
        return False

def get_blocked_content(chat_id):
    """Returns all blocked content for a chat from MongoDB."""
    try:
        blocked_col = get_collection(COLLECTIONS["blocked_content"])
        if blocked_col is None:
            return {"text": [], "media": []}
        
        chat_id_str = str(chat_id)
        blocked_doc = blocked_col.find_one({"chat_id": chat_id_str})
        
        if blocked_doc:
            return {
                "text": blocked_doc.get("text", []),
                "media": blocked_doc.get("media", []),
                "stickerpack": blocked_doc.get("stickerpack", [])
            }
        
        return {"text": [], "media": [], "stickerpack": []}
    except Exception as e:
        logging.error(f"Error getting blocked content: {e}")
        return {"text": [], "media": [], "stickerpack": []}

def is_content_blocked(chat_id, message):
    """Checks if a message contains blocked content."""
    blocked = get_blocked_content(chat_id)
    
    # Check sticker pack
    if message.sticker and message.sticker.set_name:
        logging.info(f"[BLOCK] Checking sticker set: {message.sticker.set_name} against {blocked.get('stickerpack', [])}")
        if message.sticker.set_name in blocked.get("stickerpack", []):
            return True, f"stickerpack: {message.sticker.set_name}"
            
    # Check text
    if message.text or message.caption:
        text = (message.text or message.caption).lower()
        for word in blocked.get("text", []):
            if word in text:
                return True, f"text: {word}"
                
    # Check media (photo, video, animation, document, sticker, audio, voice)
    media_file_id = None
    if message.photo: media_file_id = message.photo[-1].file_id
    elif message.video: media_file_id = message.video.file_id
    elif message.animation: media_file_id = message.animation.file_id
    elif message.document: media_file_id = message.document.file_id
    elif message.sticker: media_file_id = message.sticker.file_id
    elif message.audio: media_file_id = message.audio.file_id
    elif message.voice: media_file_id = message.voice.file_id
    
    if media_file_id and media_file_id in blocked.get("media", []):
        return True, "media"
        
    return False, None

def clear_all_blocked_content(chat_id):
    """Clear all blocked content for a chat."""
    try:
        blocked_col = get_collection(COLLECTIONS["blocked_content"])
        if blocked_col is None:
            return False
        
        chat_id_str = str(chat_id)
        result = blocked_col.delete_one({"chat_id": chat_id_str})
        
        return result.deleted_count > 0
    except Exception as e:
        logging.error(f"Error clearing blocked content: {e}")
        return False
