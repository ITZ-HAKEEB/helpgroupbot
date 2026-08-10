from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from managers.settings_manager_mongo import get_chat_settings, update_chat_setting
from core.config import send_bot_response, edit_bot_response
import logging
import datetime
import asyncio

async def get_recurring_keyboard(settings):
    recurring_messages = settings.get("recurring_messages", [])
    keyboard = []
    
    # "Add message" button
    if len(recurring_messages) < 5: # Limit to 5 slots
        keyboard.append([InlineKeyboardButton(colored_button("➕ Add message", "default"), callback_data="set_recurring_add")])
    
    for msg in recurring_messages:
        msg_id = msg['id']
        active_status = "✅ Active" if msg.get('active', False) else "❌ Inactive"
        
        # Row with [Slot Button] [Active/Inactive Toggle] [Delete Button]
        keyboard.append([
            InlineKeyboardButton(colored_button(f"🗯 {msg_id}", "default"), callback_data=f"set_recurring_config_text_{msg_id}"),
            InlineKeyboardButton(colored_button(f"{active_status}", "default"), callback_data=f"set_recurring_toggle_active_{msg_id}"),
            InlineKeyboardButton(colored_button("🗑", "default"), callback_data=f"set_recurring_delete_{msg_id}")
        ])
        
    keyboard.append([InlineKeyboardButton(colored_button("🔙 Back", "default"), callback_data="set_view_main")])
    return InlineKeyboardMarkup(keyboard)

async def recurring_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = context.user_data.get('settings_chat_id', update.effective_chat.id)
    settings = get_chat_settings(chat_id)
    recurring_messages = settings.get("recurring_messages", [])
    
    if data == "set_view_recurring" or data.startswith("set_recurring_toggle_") or data.startswith("set_recurring_delete_") or data == "set_recurring_add":
        # Handle additions
        if data == "set_recurring_add":
            new_id = 1
            if recurring_messages:
                new_id = max(m['id'] for m in recurring_messages) + 1
            
            new_msg = {
                "id": new_id,
                "active": False,
                "type": "time",
                "interval": 1440,
                "message_interval": 100,
                "text": None,
                "media": None,
                "media_type": None,
                "last_sent_at": None,
                "current_message_count": 0
            }
            recurring_messages.append(new_msg)
            update_chat_setting(chat_id, "recurring_messages", recurring_messages)
            settings = get_chat_settings(chat_id)
            await query.answer("New message slot added!")
            
        # Handle deletions
        elif data.startswith("set_recurring_delete_"):
            msg_id = int(data.split("_")[-1])
            recurring_messages = [m for m in recurring_messages if m['id'] != msg_id]
            update_chat_setting(chat_id, "recurring_messages", recurring_messages)
            settings = get_chat_settings(chat_id)
            await query.answer("Message slot deleted!")

        # Handle toggles
        elif data.startswith("set_recurring_toggle_active_"):
            msg_id = int(data.split("_")[-1])
            for msg in recurring_messages:
                if msg['id'] == msg_id:
                    msg['active'] = not msg.get('active', False)
                    break
            update_chat_setting(chat_id, "recurring_messages", recurring_messages)
            settings = get_chat_settings(chat_id)
            await query.answer("Status updated!")

        # Build message text
        text = "🕑 <b>Recurring messages</b>\n"
        text += "From this menu you can set messages that will be sent repeatedly to the group every few minutes/hours or every few messages.\n\n"
        text += f"<b>Current time:</b> {datetime.datetime.now().strftime('%d %b %Y, %H:%M')}\n\n"
        
        if not recurring_messages:
            text += "<i>No recurring messages set.</i>"
        else:
            for msg in recurring_messages:
                msg_id = msg['id']
                active_icon = "✅" if msg.get('active', False) else "❌"
                
                # Format ID emoji (1 -> 1️⃣)
                id_emoji = f"{msg_id}️⃣" if msg_id <= 10 else f"{msg_id}"
                
                text += f"🗯 {id_emoji} • <b>Active</b> {active_icon}\n"
                
                # Last sent time
                last_sent = msg.get('last_sent_at')
                if last_sent:
                    if isinstance(last_sent, str):
                        try:
                            last_sent = datetime.datetime.fromisoformat(last_sent)
                            time_str = last_sent.strftime("%H:%M")
                        except:
                            time_str = "N/A"
                    else:
                        time_str = last_sent.strftime("%H:%M")
                else:
                    time_str = "Never"
                
                text += f" ├ <i>Time: {time_str}</i>\n"
                
                # Interval
                msg_type = msg.get('type', 'time')
                if msg_type == 'time':
                    interval = msg.get('interval', 1440)
                    if interval >= 1440:
                        interval_str = f"{interval // 1440} hours" if interval == 1440 else f"{interval // 1440} days"
                        # Correction: 1440 mins is 24 hours. The screenshot says "Every 24 hours"
                        if interval % 1440 == 0:
                            interval_str = f"{interval // 60} hours"
                        else:
                            interval_str = f"{interval} minutes"
                    elif interval >= 60:
                        interval_str = f"{interval // 60} hours"
                    else:
                        interval_str = f"{interval} minutes"
                    text += f" ├ <i>Every {interval_str}</i>\n"
                else:
                    interval = msg.get('message_interval', 100)
                    text += f" ├ <i>Every {interval} messages</i>\n"
                
                # Message content status
                msg_text = msg.get('text')
                msg_media = msg.get('media')
                if msg_text or msg_media:
                    content_preview = msg_text[:20] + "..." if msg_text and len(msg_text) > 20 else (msg_text or "Media only")
                    text += f" └ <i>Message: {content_preview}</i>\n"
                else:
                    text += f" └ <i>Message is not set.</i>\n"
                text += "\n"

        await edit_bot_response(
            query, context,
            text,
            reply_markup=await get_recurring_keyboard(settings),
            parse_mode='HTML'
        )
        return

    if data.startswith("set_recurring_config_text_"):
        msg_id = int(data.split("_")[-1])
        context.user_data['config_recurring_id'] = msg_id
        
        # Show sub-menu for message configuration
        msg = next((m for m in recurring_messages if m['id'] == msg_id), None)
        msg_type = msg.get('type', 'time')
        type_label = "🕒 Time" if msg_type == 'time' else "💬 Messages"
        
        keyboard = [
            [InlineKeyboardButton(colored_button(f"Type: {type_label}", "default"), callback_data=f"set_recurring_toggle_type_{msg_id}")],
            [InlineKeyboardButton(colored_button("⚙️ Set Interval", "default"), callback_data=f"set_recurring_config_interval_{msg_id}")],
            [InlineKeyboardButton(colored_button("📝 Set Message Text/Media", "default"), callback_data=f"set_recurring_prompt_text_{msg_id}")],
            [InlineKeyboardButton(colored_button("🔙 Back to List", "default"), callback_data="set_view_recurring")]
        ]
        
        await edit_bot_response(
            query, context,
            f"⚙️ <b>Configuring Recurring Message {msg_id}</b>\n\nChoose what you want to change:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        await query.answer()
        return

    if data.startswith("set_recurring_config_interval_"):
        msg_id = int(data.split("_")[-1])
        context.user_data['config_recurring_id'] = msg_id
        context.user_data['config_state'] = 'awaiting_recurring_interval'
        
        msg = next((m for m in recurring_messages if m['id'] == msg_id), None)
        msg_type = msg.get('type', 'time')
        
        if msg_type == 'time':
            instruction = "Please enter the interval in minutes (e.g., 60 for 1 hour, 1440 for 1 day):"
        else:
            instruction = "Please enter the message interval (e.g., 100 for every 100 messages):"
            
        await edit_bot_response(
            query, context,
            f"⚙️ <b>Configuring Interval for Message {msg_id}</b>\n\n{instruction}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(colored_button("Cancel", "default"), callback_data=f"set_recurring_config_text_{msg_id}")]]),
            parse_mode='HTML'
        )
        await query.answer()
        return

    if data.startswith("set_recurring_toggle_type_"):
        msg_id = int(data.split("_")[-1])
        for msg in recurring_messages:
            if msg['id'] == msg_id:
                msg['type'] = 'messages' if msg.get('type', 'time') == 'time' else 'time'
                break
        update_chat_setting(chat_id, "recurring_messages", recurring_messages)
        # Refresh the config menu
        query.data = f"set_recurring_config_text_{msg_id}"
        await recurring_callback(update, context)
        return

    if data.startswith("set_recurring_prompt_text_"):
        msg_id = int(data.split("_")[-1])
        context.user_data['config_recurring_id'] = msg_id
        context.user_data['config_state'] = 'awaiting_recurring_text'
        
        await edit_bot_response(
            query, context,
            f"📝 <b>Configuring Text for Message {msg_id}</b>\n\nPlease send the message you want to be sent repeatedly. You can include media (photo/video).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(colored_button("Cancel", "default"), callback_data="set_view_recurring")]]),
            parse_mode='HTML'
        )
        await query.answer()
        return

async def handle_recurring_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('config_state')
    if not isinstance(state, str) or not state.startswith('awaiting_recurring_'):
        return False
    
    if update.message and update.message.text == "/cancel":
        context.user_data['config_state'] = None
        await update.message.reply_text("❌ Configuration cancelled.")
        return True

    chat_id = context.user_data.get('settings_chat_id')
    if not chat_id:
        return False
        
    msg_id = context.user_data.get('config_recurring_id')
    settings = get_chat_settings(chat_id)
    recurring_messages = settings.get("recurring_messages", [])
    
    target_msg = next((m for m in recurring_messages if m['id'] == msg_id), None)
    if not target_msg:
        return False
        
    if state == 'awaiting_recurring_interval':
        try:
            val = int(update.message.text)
            if val <= 0: raise ValueError
            
            if target_msg['type'] == 'time':
                target_msg['interval'] = val
            else:
                target_msg['message_interval'] = val
                
            update_chat_setting(chat_id, "recurring_messages", recurring_messages)
            await send_bot_response(update, context, "✅ Interval updated successfully!")
        except:
            await send_bot_response(update, context, "❌ Invalid input. Please enter a positive number.")
            return True
            
    elif state == 'awaiting_recurring_text':
        if update.message.text:
            target_msg['text'] = update.message.text
            target_msg['media'] = None
            target_msg['media_type'] = None
        elif update.message.photo:
            target_msg['text'] = update.message.caption
            target_msg['media'] = update.message.photo[-1].file_id
            target_msg['media_type'] = 'photo'
        elif update.message.video:
            target_msg['text'] = update.message.caption
            target_msg['media'] = update.message.video.file_id
            target_msg['media_type'] = 'video'
        elif update.message.animation:
            target_msg['text'] = update.message.caption
            target_msg['media'] = update.message.animation.file_id
            target_msg['media_type'] = 'animation'
        else:
            await send_bot_response(update, context, "❌ Unsupported message type. Please send text, photo, video, or GIF.")
            return True
            
        update_chat_setting(chat_id, "recurring_messages", recurring_messages)
        await send_bot_response(update, context, "✅ Message content updated successfully!")

    # Reset state and show recurring menu
    context.user_data['config_state'] = None
    from features.settings import show_settings_panel
    await show_settings_panel(update, context, chat_id, is_private=True)
    # We should actually show the recurring menu specifically
    settings = get_chat_settings(chat_id)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🕑 <b>Recurring Messages</b>\n\nUpdated view:",
        reply_markup=await get_recurring_keyboard(settings),
        parse_mode='HTML'
    )
    return True

async def check_recurring_messages(context: ContextTypes.DEFAULT_TYPE):
    """Background job to send recurring messages."""
    from managers.settings_manager_mongo import get_all_chat_settings, update_chat_setting
    
    all_settings = get_all_chat_settings()
    now = datetime.datetime.now()
    
    for chat_id_str, settings in all_settings.items():
        chat_id = int(chat_id_str)
        recurring_messages = settings.get("recurring_messages", [])
        changed = False
        
        for msg in recurring_messages:
            if not msg.get('active', False) or msg.get('type') != 'time':
                continue
                
            last_sent = msg.get('last_sent_at')
            interval_mins = msg.get('interval', 1440)
            
            should_send = False
            if last_sent is None:
                should_send = True
            else:
                if isinstance(last_sent, str):
                    last_sent = datetime.datetime.fromisoformat(last_sent)
                
                if (now - last_sent).total_seconds() / 60 >= interval_mins:
                    should_send = True
            
            if should_send:
                try:
                    text = msg.get('text')
                    media = msg.get('media')
                    media_type = msg.get('media_type')
                    
                    if not text and not media:
                        continue
                        
                    if media:
                        if media_type == 'photo':
                            await context.bot.send_photo(chat_id=chat_id, photo=media, caption=text)
                        elif media_type == 'video':
                            await context.bot.send_video(chat_id=chat_id, video=media, caption=text)
                        elif media_type == 'animation':
                            await context.bot.send_animation(chat_id=chat_id, animation=media, caption=text)
                    else:
                        await context.bot.send_message(chat_id=chat_id, text=text)
                        
                    msg['last_sent_at'] = now.isoformat()
                    changed = True
                except Exception as e:
                    logging.error(f"Error sending recurring message to {chat_id}: {e}")
                    
        if changed:
            update_chat_setting(chat_id, "recurring_messages", recurring_messages)

async def count_recurring_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message handler to count messages for message-based intervals."""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        return
        
    # Only count actual new messages, ignore edits and reactions
    if not update.message:
        return
        
    chat_id = update.effective_chat.id
    settings = get_chat_settings(chat_id)
    recurring_messages = settings.get("recurring_messages", [])
    changed = False
    
    for msg in recurring_messages:
        if not msg.get('active', False) or msg.get('type') != 'messages':
            continue
            
        msg['current_message_count'] = msg.get('current_message_count', 0) + 1
        
        if msg['current_message_count'] >= msg.get('message_interval', 100):
            try:
                text = msg.get('text')
                media = msg.get('media')
                media_type = msg.get('media_type')
                
                if text or media:
                    if media:
                        if media_type == 'photo':
                            await context.bot.send_photo(chat_id=chat_id, photo=media, caption=text)
                        elif media_type == 'video':
                            await context.bot.send_video(chat_id=chat_id, video=media, caption=text)
                        elif media_type == 'animation':
                            await context.bot.send_animation(chat_id=chat_id, animation=media, caption=text)
                    else:
                        await context.bot.send_message(chat_id=chat_id, text=text)
                        
                    msg['current_message_count'] = 0
                    changed = True
            except Exception as e:
                logging.error(f"Error sending message-based recurring message to {chat_id}: {e}")
                
    if changed:
        update_chat_setting(chat_id, "recurring_messages", recurring_messages)

def get_recurring_handlers():
    return [
        CallbackQueryHandler(recurring_callback, pattern="^set_(view_recurring|recurring_)"),
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_recurring_config_input)
    ]
