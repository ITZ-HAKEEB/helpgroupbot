"""
Night Mode Module - Restrict group activities during specified hours
"""

try:
    import pytz
except ImportError:
    try:
        import zoneinfo
        class PytzFallback:
            def timezone(self, name):
                try:
                    return zoneinfo.ZoneInfo(name)
                except Exception:
                    import datetime
                    return datetime.timezone.utc
        pytz = PytzFallback()
    except ImportError:
        import datetime
        class PytzFallback:
            def timezone(self, name):
                return datetime.timezone.utc
        pytz = PytzFallback()
from core.config import colored_button
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings
from managers.user_manager_mongo import is_user_admin
from core.config import OWNER_ID

def is_night_time(chat_id):
    """Checks if it's currently night time for the chat."""
    settings = get_chat_settings(chat_id)
    if not settings.get("nightmode_enabled", False):
        return False

    start_hour = settings.get("nightmode_start", 23)
    end_hour = settings.get("nightmode_end", 9)
    timezone_str = settings.get("nightmode_timezone", "Asia/Kolkata")

    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")

    now = datetime.now(tz)
    current_hour = now.hour

    if start_hour > end_hour:
        # Overnights (e.g., 23 to 9)
        return current_hour >= start_hour or current_hour < end_hour
    else:
        # Same day (e.g., 22 to 23)
        return start_hour <= current_hour < end_hour

async def handle_nightmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles night mode restrictions."""
    if not update.effective_chat or not update.effective_user or update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_night_time(chat_id):
        return

    # Get settings
    settings = get_chat_settings(chat_id)
    message = update.effective_message
    
    # Check "Apply On" setting
    apply_on = settings.get("nightmode_apply_on", "members")
    is_admin = user_id == OWNER_ID or await is_user_admin(chat_id, user_id, context)
    
    # Logic for "Apply On"
    if apply_on == "members":
        if is_admin:
            return # Skip admins and owner
    elif apply_on == "admins":
        if not is_admin:
            return # Skip regular members
        if user_id == OWNER_ID:
            return # Still skip owner
    elif apply_on == "everyone":
        if user_id == OWNER_ID:
            return # Still skip owner

    # Debug logging (optional, can be removed after verification)
    # logging.info(f"[NIGHTMODE] Checking message from {user_id} in chat {chat_id}. Night time: {is_night_time(chat_id)}")

    should_delete = False
    
    # Check restrictions
    if settings.get("nightmode_global_silence", False):
        # Global silence blocks everything except commands (already filtered by the handler filter)
        should_delete = True
    elif settings.get("nightmode_restrict_links", False) and (message.entities or message.caption_entities):
        # Check if any entity is a link
        entities = (message.entities or []) + (message.caption_entities or [])
        if any(e.type in ['url', 'text_link'] for e in entities):
            should_delete = True
            logging.info(f"[NIGHTMODE] Link detected in chat {chat_id} from user {user_id}. apply_on={apply_on}, is_admin={is_admin}")
    elif settings.get("nightmode_restrict_text", False) and message.text:
        should_delete = True
    elif settings.get("nightmode_restrict_media", False) and (
        message.photo or message.video or message.audio or message.document or 
        message.animation or message.voice or message.video_note
    ):
        should_delete = True
    elif settings.get("nightmode_restrict_stickers", False) and message.sticker:
        should_delete = True

    if should_delete:
        try:
            await message.delete()
            logging.info(f"[NIGHTMODE] Deleted message from {user_id} in chat {chat_id}")
            # Optional: Send a temporary warning if advised
            if settings.get("nightmode_advise_enabled", True):
                # We can use a job to avoid spamming warnings
                job_key = f"night_warn_{chat_id}_{user_id}"
                if job_key not in context.user_data or (datetime.now().timestamp() - context.user_data[job_key]) > 60:
                    warn = await context.bot.send_message(
                        chat_id,
                        f"🌙 <b>Night Mode is Active</b>\n\n"
                        f"Restrictions are currently in place. Please wait until morning!",
                        parse_mode='HTML'
                    )
                    context.user_data[job_key] = datetime.now().timestamp()
                    # Auto delete warning
                    context.job_queue.run_once(
                        lambda c: c.bot.delete_message(chat_id, warn.message_id),
                        10
                    )
        except Exception as e:
            logging.error(f"Error in nightmode deletion: {e}")

async def handle_nightmode_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles configuration input for night mode settings."""
    state_data = context.user_data.get('config_state')
    logging.info(f"[NIGHTMODE_CONFIG] State data: {state_data}")
    
    if not state_data or not isinstance(state_data, tuple) or state_data[0] not in ['nightmode_time', 'nightmode_timezone']:
        return False
    
    state, chat_id = state_data
    
    if update.message and (update.message.text == "/cancel" or update.message.text == "❌ Cancel"):
        context.user_data['config_state'] = None
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text("❌ Configuration cancelled.", reply_markup=ReplyKeyboardRemove())
        return True

    # Handle Location for TimeZone
    if state == 'nightmode_timezone':
        import pytz
        from timezonefinder import TimezoneFinder
        tf = TimezoneFinder()
        
        timezone_str = None
        if update.message.location:
            lat = update.message.location.latitude
            lng = update.message.location.longitude
            logging.info(f"[NIGHTMODE_CONFIG] Received location: {lat}, {lng}")
            timezone_str = tf.timezone_at(lng=lng, lat=lat)
            logging.info(f"[NIGHTMODE_CONFIG] Detected timezone: {timezone_str}")
        elif update.message.text:
            text = update.message.text
            logging.info(f"[NIGHTMODE_CONFIG] Received text: {text}")
            # Check if it's a valid timezone name
            try:
                pytz.timezone(text)
                timezone_str = text
            except:
                # Try to search for it? For now just fail
                pass

        if timezone_str:
            from managers.settings_manager_mongo import update_chat_setting
            update_chat_setting(chat_id, "nightmode_timezone", timezone_str)
            
            from telegram import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
            # Calculate current time in that timezone
            try:
                tz = pytz.timezone(timezone_str)
                now = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
            except:
                now = "Unknown"

            success_text = (
                f"Time Zone set to <b>{timezone_str}</b>\n"
                f"Current time: <b>{now}</b>"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(colored_button("🔙 Back", "default"), callback_data="set_view_nightmode")]
            ])
            
            # Reset state
            context.user_data['config_state'] = None
            
            await update.message.reply_text(
                success_text, 
                parse_mode='HTML', 
                reply_markup=ReplyKeyboardRemove()
            )
            # Send the inline keyboard separately
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="<i>Use the button below to return to settings:</i>",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return True
        else:
            # If we are in this state but couldn't detect TZ, don't return False
            # instead inform user and stay in state
            if update.message.location or update.message.text:
                await update.message.reply_text("❌ Could not detect Time Zone. Please enter a valid name like <code>Asia/Kolkata</code> or send your location.", parse_mode='HTML')
                return True
            return False

    text = update.message.text
    if not text:
        return False

    if state == 'nightmode_time':
        try:
            parts = text.split()
            if len(parts) != 2: raise ValueError
            start_hour = int(parts[0])
            end_hour = int(parts[1])
            if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23): raise ValueError
            
            from managers.settings_manager_mongo import update_chat_setting
            update_chat_setting(chat_id, "nightmode_start", start_hour)
            update_chat_setting(chat_id, "nightmode_end", end_hour)
            
            await update.message.reply_text(f"✅ Night Mode time slot set to: <b>{start_hour} to {end_hour}</b>", parse_mode='HTML')
        except:
            await update.message.reply_text("❌ Invalid format. Please enter two numbers between 0 and 23 (e.g., <code>23 9</code>).", parse_mode='HTML')
            return True
            
    elif state == 'nightmode_timezone':
        try:
            pytz.timezone(text)
            from managers.settings_manager_mongo import update_chat_setting
            update_chat_setting(chat_id, "nightmode_timezone", text)
            
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            # Calculate current time in that timezone
            try:
                tz = pytz.timezone(text)
                now = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
            except:
                now = "Unknown"

            success_text = (
                f"Time Zone set to <b>{text}</b>\n"
                f"Current time: <b>{now}</b>"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(colored_button("🔙 Back", "default"), callback_data="set_view_nightmode")]
            ])
            
            await update.message.reply_text(success_text, parse_mode='HTML', reply_markup=keyboard)
            return True
        except:
            await update.message.reply_text("❌ Invalid timezone. Examples: <code>Asia/Kolkata</code>, <code>UTC</code>, <code>Europe/London</code>.", parse_mode='HTML')
            return True

    # Reset state and return to nightmode menu
    context.user_data['config_state'] = None
    from features.settings import settings_callback
    # We can't easily trigger the callback without a query, so we just prompt to reopen
    await update.message.reply_text("Settings updated! Please reopen /settings to see the changes.")
    return True

def get_nightmode_handlers():
    """Returns nightmode message handlers."""
    from telegram.ext import MessageHandler, filters
    return [
        # Catch location and text in private chat if config_state is active
        # MUST BE IN GROUP 0 or a low group to catch before other handlers
        MessageHandler((filters.LOCATION | filters.TEXT) & filters.ChatType.PRIVATE, handle_nightmode_config_input),
        MessageHandler(filters.ALL & ~filters.COMMAND & filters.ChatType.GROUPS, handle_nightmode)
    ]
