import logging
import datetime
import asyncio
from core.database import get_collection, COLLECTIONS
from core.config import OWNER_ID, delete_message_job
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

# In-memory cache for recently cached users to avoid redundant DB calls
# Format: {user_id: last_cached_timestamp}
USER_CACHE = {}
CACHE_TTL = 3600 # Cache for 1 hour

def cache_user(user_id, username, first_name):
    """Saves user mapping for later resolution and tracks stats using MongoDB in background."""
    now_ts = datetime.datetime.now().timestamp()
    
    # Skip if recently cached
    if user_id in USER_CACHE and (now_ts - USER_CACHE[user_id]) < CACHE_TTL:
        # Still increment message count but skip full cache update
        asyncio.create_task(asyncio.to_thread(increment_message_count, user_id))
        return True

    # Update memory cache
    USER_CACHE[user_id] = now_ts

    # Move DB operations to background
    asyncio.create_task(asyncio.to_thread(_cache_user_db, user_id, username, first_name))
    return True

def _cache_user_db(user_id, username, first_name):
    """Internal function to handle DB operations for caching."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is None:
            return False
        
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Use upsert to simplify find + update/insert into one operation
        update_data = {
            "name": first_name,
            "last_updated": datetime.datetime.now()
        }
        if username:
            update_data["username"] = username.lower().replace('@', '')
        
        users_col.update_one(
            {"id": user_id},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "joined_date": now,
                    "created_at": datetime.datetime.now()
                },
                "$inc": {"msg_count": 1} # Also increment msg count here
            },
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error in background caching user: {e}")
        return False

def increment_message_count(user_id):
    """Increments the message count for a user using MongoDB."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is None:
            return False
        
        result = users_col.update_one(
            {"id": user_id},
            {"$inc": {"msg_count": 1}}
        )
        return result.modified_count > 0
    except Exception as e:
        logging.error(f"Error incrementing message count: {e}")
        return False

def get_user_stats(user_id):
    """Returns user stats from MongoDB."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is None:
            return None
        
        user_doc = users_col.find_one({"id": user_id})
        if user_doc:
            return {
                "id": user_doc["id"],
                "name": user_doc.get("name"),
                "username": user_doc.get("username"),
                "joined_date": user_doc.get("joined_date", "Unknown"),
                "msg_count": user_doc.get("msg_count", 0)
            }
        return None
    except Exception as e:
        logging.error(f"Error getting user stats: {e}")
        return None

def resolve_username(username):
    """Returns (user_id, first_name) if found in MongoDB."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is None:
            return None, None
        
        username = username.lower().replace('@', '')
        user_doc = users_col.find_one({"username": username})
        
        if user_doc:
            return user_doc["id"], user_doc.get("name")
        return None, None
    except Exception as e:
        logging.error(f"Error resolving username: {e}")
        return None, None

async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Extracts user ID or Chat ID from reply, mention, or argument.
    Supports: Reply, Mention (@user), Text Mention, Username (with or without @), and ID number.
    Returns: (user_id, first_name)
    """
    # Method 1: Check if it's a reply
    if update.message and update.message.reply_to_message:
        reply = update.message.reply_to_message
        # Check if it's a post from a channel or anonymous admin
        if reply.sender_chat:
            return reply.sender_chat.id, reply.sender_chat.title or reply.sender_chat.username
        if reply.from_user:
            user = reply.from_user
            return user.id, user.first_name
    
    # Method 2: Check for mentions in entities (real-time resolution)
    if update.message and update.message.entities:
        for entity in update.message.entities:
            if entity.type == 'mention':
                username_text = update.message.text[entity.offset:entity.offset+entity.length]
                user_id, user_name = resolve_username(username_text)
                if user_id: return user_id, user_name
                
                # If not in cache, try to get chat info directly from Telegram
                try:
                    chat = await context.bot.get_chat(username_text)
                    return chat.id, chat.title or chat.username
                except: pass
            elif entity.type == 'text_mention':
                # This is for users without usernames
                return entity.user.id, entity.user.first_name

    # Method 3: Check arguments (ID or Username)
    if context.args:
        arg = context.args[0]
        if arg is None:
            return None, None
            
        # 3a. Try to parse as User/Chat ID (numbers or -100...)
        clean_arg = str(arg).replace('@', '')
        if clean_arg.isdigit() or (clean_arg.startswith('-') and clean_arg[1:].isdigit()):
            try:
                target_id = int(clean_arg)
                # Try to get info from Telegram for a better name
                try:
                    chat = await context.bot.get_chat(target_id)
                    return chat.id, chat.title or chat.first_name or chat.username or str(chat.id)
                except:
                    # Fallback to cache
                    uid, name = resolve_username(str(target_id))
                    if uid: return uid, name
                    # Last resort: just the ID
                    return target_id, str(target_id)
            except: pass
        
        # 3b. Try to resolve as username (even without @)
        user_id, user_name = resolve_username(clean_arg)
        if user_id: return user_id, user_name
        
        # 3c. Try to resolve via bot directly (needs @ for usernames)
        try:
            lookup_username = f"@{clean_arg}" if not clean_arg.startswith('@') else clean_arg
            chat = await context.bot.get_chat(lookup_username)
            return chat.id, chat.title or chat.first_name or chat.username
        except: pass
            
    return None, None

async def is_user_admin(chat_id, user_id, context):
    """Check if the user is an admin or owner."""
    if not user_id: return False
    
    # Telegram's ID for anonymous admins (Group Anonymous Bot)
    ANONYMOUS_ADMIN_ID = 1087968824
    if user_id == ANONYMOUS_ADMIN_ID:
        return True
        
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def can_user_configure_settings(chat_id, user_id, context):
    """Check if a user can configure settings (Owner, Creator, or Admin with Change Info + Ban perms)."""
    if not user_id: return False
    
    # Anonymous admins are allowed to configure settings as we can't check specific rights easily
    ANONYMOUS_ADMIN_ID = 1087968824
    if user_id == ANONYMOUS_ADMIN_ID:
        return True
        
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == 'creator':
            return True
        if member.status == 'administrator':
            # Check for both "Change Group Info" and "Ban Users" (can_restrict_members)
            return member.can_change_info and member.can_restrict_members
        return False
    except:
        return False

async def can_user_reload(chat_id, user_id, context):
    """Check if a user can reload (Owner, Creator, or Admin with Change Info + Ban + Add Admin perms)."""
    if not user_id: return False
    
    # Anonymous admins are allowed to reload as we can't check specific rights easily
    ANONYMOUS_ADMIN_ID = 1087968824
    if user_id == ANONYMOUS_ADMIN_ID:
        return True
        
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == 'creator':
            return True
        if member.status == 'administrator':
            # Check for "Change Group Info", "Ban Users" (can_restrict_members), and "Add New Admins" (can_promote_members)
            return member.can_change_info and member.can_restrict_members and member.can_promote_members
        return False
    except:
        return False

async def cache_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MessageHandler to cache user data and detect name changes."""
    user = update.effective_user
    if not user or user.is_bot:
        return

    user_id = user.id
    username = user.username
    first_name = user.first_name
    
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is None:
            return

        existing_user = users_col.find_one({"id": user_id})
        
        if existing_user:
            old_name = existing_user.get("name")
            if old_name and old_name != first_name:
                # Name changed!
                chat = update.effective_chat
                if chat and chat.type in ["group", "supergroup"]:
                    change_msg = (
                        f"<blockquote>\n"
                        f"υѕєя ¢нαηgє ηαмє ƒяσм {old_name} тσ {first_name}\n"
                        f"</blockquote>"
                    )
                    try:
                        sent_msg = await context.bot.send_message(
                            chat_id=chat.id,
                            text=change_msg,
                            parse_mode='HTML'
                        )
                        
                        # Auto delete name change notification after 15 seconds using job queue
                        if context.job_queue:
                            context.job_queue.run_once(
                                delete_message_job,
                                15,
                                data={"chat_id": chat.id, "message_id": sent_msg.message_id}
                            )
                    except Exception as e:
                        logging.error(f"Error sending name change message: {e}")
                
                # Track name history for Sangmata feature
                history_col = get_collection("name_history")
                if history_col is not None:
                    history_col.insert_one({
                        "user_id": user_id,
                        "old_name": old_name,
                        "new_name": first_name,
                        "changed_at": datetime.datetime.now()
                    })

            # Update cache
            update_data = {
                "name": first_name,
                "last_updated": datetime.datetime.now()
            }
            if username:
                update_data["username"] = username.lower().replace('@', '')
            
            users_col.update_one({"id": user_id}, {"$set": update_data})
        else:
            # First time seeing this user
            user_doc = {
                "id": user_id,
                "name": first_name,
                "username": username.lower().replace('@', '') if username else None,
                "joined_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "msg_count": 0,
                "created_at": datetime.datetime.now(),
                "last_updated": datetime.datetime.now()
            }
            users_col.insert_one(user_doc)
            
    except Exception as e:
        logging.error(f"Error in cache_user_handler: {e}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sangmata feature: Show name history of a user."""
    if update.effective_chat and update.effective_chat.type != 'private':
        from managers.settings_manager_mongo import check_command_access
        if not await check_command_access(update.effective_chat.id, update.effective_user.id, "history", context):
            return await update.message.reply_text("❌ You don't have permission to use this command.")

    user_id, name = await get_user_id(update, context)
    if not user_id:
        user_id = update.effective_user.id
        name = update.effective_user.first_name
    
    try:
        history_col = get_collection("name_history")
        if history_col is None:
            return await update.message.reply_text("❌ Database error.")
        
        history = list(history_col.find({"user_id": user_id}).sort("changed_at", -1))
        
        if not history:
            return await update.message.reply_text(f"🔍 No name history found for <b>{name}</b>.", parse_mode='HTML')
        
        text = f"📜 <b>Name History for {name}</b>\n\n"
        for i, entry in enumerate(history[:10]): # Show last 10 changes
            old = entry['old_name']
            new = entry['new_name']
            date = entry['changed_at'].strftime("%Y-%m-%d")
            text += f"{i+1}. <code>{old}</code> ➜ <code>{new}</code> ({date})\n"
        
        await update.message.reply_text(text, parse_mode='HTML')
    except Exception as e:
        logging.error(f"Error in history_command: {e}")
        await update.message.reply_text("❌ Error fetching history.")

def get_sangmata_handlers():
    """Return Sangmata handlers."""
    return [CommandHandler(["history", "sg"], history_command)]

def mark_user_started_dm(user_id: int):
    """Mark that user has initiated DM conversation with the bot."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is not None:
            users_col.update_one({"id": user_id}, {"$set": {"started_dm": True}}, upsert=True)
    except Exception as e:
        logging.error(f"Error marking user DM status for {user_id}: {e}")

def has_user_started_dm(user_id: int) -> bool:
    """Check if user has initiated DM conversation with the bot."""
    try:
        users_col = get_collection(COLLECTIONS["users"])
        if users_col is not None:
            doc = users_col.find_one({"id": user_id}, {"started_dm": 1})
            return bool(doc and doc.get("started_dm"))
    except Exception:
        pass
    return False

async def cache_user_handler_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy wrapper for existing bot.py usage if needed."""
    await cache_user_handler(update, context)
