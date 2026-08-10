"""
Enhanced Translation Features
Adds reply-to-translate functionality with TranslateAI API
"""

import http.client
import json
import logging
from core.config import colored_button
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
from core.config import send_bot_response
from features.translator_ai import translate_text as translate_with_ai

# API Configuration
RAPIDAPI_KEY = "79115cebe8msh7aeb0698c33cb2bp140b6cjsn20d3c311c6f4"
RAPIDAPI_HOST = "deep-translate1.p.rapidapi.com"
API_ENDPOINT = "/language/translate/v2"

# Common languages for quick selection
LANGUAGES = {
    "en": "🇬🇧 English",
    "es": "🇪🇸 Spanish",
    "fr": "🇫🇷 French",
    "de": "🇩🇪 German",
    "it": "🇮🇹 Italian",
    "pt": "🇵🇹 Portuguese",
    "ru": "🇷🇺 Russian",
    "zh": "🇨🇳 Chinese",
    "ja": "🇯🇵 Japanese",
    "ko": "🇰🇷 Korean",
    "ar": "🇸🇦 Arabic",
    "hi": "🇮🇳 Hindi",
    "bn": "🇧🇩 Bengali",
    "ur": "🇵🇰 Urdu",
    "tr": "🇹🇷 Turkish",
    "nl": "🇳🇱 Dutch",
    "pl": "🇵🇱 Polish",
    "sv": "🇸🇪 Swedish",
    "da": "🇩🇰 Danish",
    "fi": "🇫🇮 Finnish",
    "el": "🇬🇷 Greek",
    "he": "🇮🇱 Hebrew",
    "th": "🇹🇭 Thai",
    "vi": "🇻🇳 Vietnamese",
    "id": "🇮🇩 Indonesian",
    "ms": "🇲🇾 Malay",
    "ta": "🇮🇳 Tamil",
    "te": "🇮🇳 Telugu",
    "mr": "🇮🇳 Marathi",
    "gu": "🇮🇳 Gujarati"
}

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Translation command handler.
    Can be used in two ways:
    1. Reply to a message with /tr hi - translates replied message to Hindi
    2. /tr hi text - translates text to Hindi
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Check if it's a reply to a message
    if update.message.reply_to_message:
        # Get the text to translate from replied message
        replied_message = update.message.reply_to_message
        text_to_translate = replied_message.text or replied_message.caption
        
        if not text_to_translate:
            await send_bot_response(
                update, context,
                "❌ Replied message has no text to translate."
            )
            return
        
        # If no language specified, default to Hindi
        if not context.args:
            target_lang = "hi"  # Default to Hindi
        else:
            target_lang = context.args[0].lower()
        
        # Validate language code
        if target_lang not in LANGUAGES:
            await send_bot_response(
                update, context,
                f"❌ Unsupported language code: {target_lang}\n\n"
                f"Use /langs to see available languages.\n"
                f"Default is Hindi (hi)"
            )
            return
        
        # Show typing action
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Perform translation using AI
        translated_text = await translate_with_ai(text_to_translate, "en", target_lang)
        
        if translated_text:
            # Get user info from replied message
            if replied_message.from_user:
                original_user = replied_message.from_user.first_name
            else:
                original_user = "User"
            
            target_name = LANGUAGES.get(target_lang, target_lang)
            
            # Format response
            response = (
                f"🌐 <b>Translation</b>\n\n"
                f"<b>Original ({original_user}'s message):</b>\n"
                f"{text_to_translate}\n\n"
                f"<b>Translated ({target_name}):</b>\n"
                f"{translated_text}"
            )
            
            await send_bot_response(update, context, response, parse_mode=ParseMode.HTML)
        else:
            await send_bot_response(update, context, "❌ Translation failed. Please try again.")
        return
    
    # Not a reply, check if text is provided
    if not context.args or len(context.args) < 2:
        await send_translate_help(update, context)
        return
    
    target_lang = context.args[0].lower()
    text = " ".join(context.args[1:])
    
    # Validate language code
    if target_lang not in LANGUAGES:
        await send_bot_response(
            update, context,
            f"❌ Unsupported language code: {target_lang}\n\n"
            f"Use /translate list to see available languages."
        )
        return
    
    # Show typing action
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Get translation using AI
    translated_text = await translate_with_ai(text, "en", target_lang)
    
    if translated_text:
        target_name = LANGUAGES.get(target_lang, target_lang)
        
        response = (
            f"🌐 <b>Translation</b>\n\n"
            f"<b>Original:</b> {text}\n\n"
            f"<b>Translated ({target_name}):</b>\n"
            f"{translated_text}"
        )
        
        await send_bot_response(update, context, response, parse_mode=ParseMode.HTML)
    else:
        await send_bot_response(update, context, "❌ Translation failed. Please try again.")

async def translate_text(text: str, source: str, target: str) -> str:
    """
    Translate text using RapidAPI Translation service.
    
    Args:
        text: Text to translate
        source: Source language code (use 'en' as default, 'auto' not supported)
        target: Target language code
    
    Returns:
        Translated text or None if error
    """
    try:
        # API doesn't support 'auto', default to 'en' if auto specified
        if source == 'auto' or not source:
            source = 'en'
        
        payload = json.dumps({
            "q": text,
            "source": source,
            "target": target
        })
        
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': RAPIDAPI_HOST,
            'Content-Type': "application/json"
        }
        
        # Make API request
        conn = http.client.HTTPSConnection("deep-translate1.p.rapidapi.com")
        conn.request("POST", API_ENDPOINT, payload, headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            response_data = json.loads(data.decode("utf-8"))
            
            # Extract translated text from actual API response structure
            # Format: {"data": {"translations": {"translatedText": ["translated text"]}}}
            if ("data" in response_data and 
                "translations" in response_data["data"] and
                "translatedText" in response_data["data"]["translations"]):
                translated_list = response_data["data"]["translations"]["translatedText"]
                if isinstance(translated_list, list) and len(translated_list) > 0:
                    return translated_list[0]
            
            logging.error(f"Unexpected translation API response: {response_data}")
            return None
        else:
            logging.error(f"Translation API error: {res.status} - {data.decode('utf-8')}")
            return None
            
    except Exception as e:
        logging.error(f"Error in Translation API: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

async def translate_language_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of available languages."""
    language_list = "\n".join([f"• <code>{code}</code> - {name}" for code, name in LANGUAGES.items()])
    
    response = (
        f"🌐 <b>Available Languages</b>\n\n"
        f"{language_list}\n\n"
        f"<b>Usage:</b>\n"
        f"• Reply to message with /tr hi\n"
        f"• /translate &lt;lang&gt; &lt;text&gt;\n"
        f"• /tl &lt;text&gt; - Open menu"
    )
    
    await send_bot_response(update, context, response, parse_mode=ParseMode.HTML)

async def translate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show translation menu with language options."""
    # Check if it's a reply
    if update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption
        if not text:
            await send_bot_response(update, context, "❌ Replied message has no text.")
            return
    elif context.args:
        text = " ".join(context.args)
    else:
        await send_translate_help(update, context)
        return
    
    # Create keyboard with popular languages
    keyboard = [
        [
            InlineKeyboardButton(colored_button("🇬🇧 English", "default"), callback_data="translate_en"),
            InlineKeyboardButton(colored_button("🇮🇳 Hindi", "default"), callback_data="translate_hi"),
        ],
        [
            InlineKeyboardButton(colored_button("🇪🇸 Spanish", "default"), callback_data="translate_es"),
            InlineKeyboardButton(colored_button("🇫🇷 French", "default"), callback_data="translate_fr"),
        ],
        [
            InlineKeyboardButton(colored_button("🇩🇪 German", "default"), callback_data="translate_de"),
            InlineKeyboardButton(colored_button("🇮🇹 Italian", "default"), callback_data="translate_it"),
        ],
        [
            InlineKeyboardButton(colored_button("🇷🇺 Russian", "default"), callback_data="translate_ru"),
            InlineKeyboardButton(colored_button("🇨🇳 Chinese", "default"), callback_data="translate_zh"),
        ],
        [
            InlineKeyboardButton(colored_button("🇯🇵 Japanese", "default"), callback_data="translate_ja"),
            InlineKeyboardButton(colored_button("🇸🇦 Arabic", "default"), callback_data="translate_ar"),
        ],
        [InlineKeyboardButton(colored_button("❌ Cancel", "default"), callback_data="translate_cancel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store text in user_data for callback access
    context.user_data[f"translate_text_{update.effective_user.id}"] = text
    
    response = (
        f"📝 <b>Text to translate:</b>\n\n"
        f"\"{text}\"\n\n"
        f"👇 <b>Select target language:</b>"
    )
    
    await send_bot_response(update, context, response, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def translate_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle translation callback queries."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Get stored text
    text = context.user_data.get(f"translate_text_{user_id}")
    if not text:
        await query.edit_message_text("❌ No text found for translation. Use /tl <text> or reply with /tl.")
        return
    
    data = query.data
    
    if data == "translate_cancel":
        await query.edit_message_text("❌ Translation cancelled.")
        return
    
    # Extract language code
    target_lang = data.replace("translate_", "")
    
    # Show typing action
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    
    # Perform translation using AI
    translated_text = await translate_with_ai(text, "en", target_lang)
    
    if translated_text:
        target_name = LANGUAGES.get(target_lang, target_lang)
        
        response = (
            f"🌐 <b>Translation</b>\n\n"
            f"<b>Original:</b> {text}\n\n"
            f"<b>Translated ({target_name}):</b>\n"
            f"{translated_text}"
        )
        
        await query.edit_message_text(response, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text("❌ Translation failed. Please try again.")

async def send_translate_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send translation help message."""
    response = (
        f"🌐 <b>Translation Service</b>\n\n"
        f"<b>Commands:</b>\n"
        f"• Reply with /tr hi - Translate replied message to Hindi\n"
        f"• Reply with /tr en - Translate replied message to English\n"
        f"• /translate &lt;lang&gt; &lt;text&gt; - Translate text\n"
        f"• /tr &lt;lang&gt; &lt;text&gt; - Short command\n"
        f"• /tl &lt;text&gt; - Open language menu\n"
        f"• /tl (reply) - Open menu for replied message\n"
        f"• /langs - Show available languages\n\n"
        f"<b>Examples:</b>\n"
        f"• Reply with /tr hi\n"
        f"• Reply with /tr es\n"
        f"• /translate es Hello World\n"
        f"• /tr fr Good morning\n"
        f"• /tl How are you?\n\n"
        f"<b>Default:</b> If no language specified in reply, translates to Hindi 🇮🇳"
    )
    
    await send_bot_response(update, context, response, parse_mode=ParseMode.HTML)

def get_translation_handlers():
    """Return all translation handlers."""
    return [
        CommandHandler("translate", translate_command),
        CommandHandler("tr", translate_command),
        CommandHandler("tl", translate_menu),
        CommandHandler("langs", translate_language_list),
        CallbackQueryHandler(translate_callback_handler, pattern="^translate_")
    ]
