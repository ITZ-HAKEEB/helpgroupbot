"""
Language Detection & Filtering Module
Detects message language and filters based on group settings
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

# Supported languages
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'hi': 'Hindi',
    'hinglish': 'Hinglish'  # Hindi + English mix
}

# Language detection based on Unicode ranges
def detect_language(text: str) -> tuple[str, dict]:
    """
    Detect the language of the text.
    Returns: (lang_code, stats_dict)
    lang_code: 'en', 'hi', 'hinglish', 'other', or 'safe'
    stats_dict: {'emojis': int, 'total_alphabetic': int, 'punctuation': int, ...}
    """
    if not text:
        return 'unknown', {}
    
    # Count characters in different categories
    hindi_chars = 0
    latin_chars = 0
    other_chars = 0
    numbers = 0
    emojis = 0
    punctuation = 0
    spaces = 0
    stylish_fonts = 0
    total_alphabetic = 0
    
    for char in text:
        if '\u0900' <= char <= '\u097F':  # Devanagari (Hindi)
            hindi_chars += 1
            total_alphabetic += 1
        elif char.isascii() and char.isalpha():  # Latin alphabet (English)
            latin_chars += 1
            total_alphabetic += 1
        elif is_stylish_font(char):  # Stylish/font characters
            stylish_fonts += 1
            total_alphabetic += 1
            # Check if it's Cyrillic/Greek used as aesthetic
            cp = ord(char)
            if (0x0400 <= cp <= 0x04FF) or (0x0370 <= cp <= 0x03FF):
                # Only count as Latin if mixed with other stylish/Latin chars
                # This allows ѕαмαєℓ but detects pure Russian
                pass  # Don't add to latin_chars yet
            else:
                latin_chars += 1  # Count other stylish fonts as Latin
        elif char.isalpha():  # Other alphabets (Russian, Arabic, Chinese, etc.)
            other_chars += 1
            total_alphabetic += 1
        elif char.isdigit():  # Numbers
            numbers += 1
        elif char.isspace():  # Spaces
            spaces += 1
        elif is_emoji(char):  # Emojis
            emojis += 1
        else:  # Punctuation, special characters
            punctuation += 1
    
    stats = {
        'hindi_chars': hindi_chars,
        'latin_chars': latin_chars,
        'other_chars': other_chars,
        'numbers': numbers,
        'emojis': emojis,
        'punctuation': punctuation,
        'spaces': spaces,
        'stylish_fonts': stylish_fonts,
        'total_alphabetic': total_alphabetic
    }

    # If no alphabetic characters, it's safe (emojis, numbers, punctuation only)
    if total_alphabetic == 0:
        return 'safe', stats
    
    # Check if Cyrillic/Greek chars are aesthetic (mixed with other stylish) or real Russian
    # Count Cyrillic/Greek that are in stylish_font range
    aesthetic_chars = 0
    for char in text:
        cp = ord(char)
        if is_stylish_font(char) and ((0x0400 <= cp <= 0x04FF) or (0x0370 <= cp <= 0x03FF)):
            aesthetic_chars += 1
    
    # If there's a mix of aesthetic Cyrillic/Greek + other stylish fonts, treat as English
    # If it's ONLY Cyrillic/Greek with no other stylish, treat as 'other' (real Russian/Greek)
    if aesthetic_chars > 0 and stylish_fonts > aesthetic_chars:
        # Mixed aesthetic (ѕαмαєℓ with other stylish) - count as English
        latin_chars += aesthetic_chars
    elif aesthetic_chars > 0 and stylish_fonts == aesthetic_chars:
        # Pure Cyrillic/Greek aesthetic without other stylish - check context
        # If mostly Cyrillic, it might be real Russian
        pass  # Let the detection logic below handle it
    
    # Calculate percentages based on alphabetic characters only
    hindi_pct = (hindi_chars / total_alphabetic) * 100
    latin_pct = (latin_chars / total_alphabetic) * 100
    other_pct = (other_chars / total_alphabetic) * 100
    
    # Detection logic
    if other_pct > 50:
        return 'other', stats  # Mostly non-Hindi, non-English characters
    elif hindi_pct > 70:
        return 'hi', stats  # Pure Hindi
    elif latin_pct > 70:
        return 'en', stats  # Pure English
    elif hindi_pct > 20 and latin_pct > 20:
        return 'hinglish', stats  # Mix of Hindi and English
    elif hindi_pct > 50:
        return 'hi', stats  # Mostly Hindi
    elif latin_pct > 50:
        return 'en', stats  # Mostly English
    else:
        return 'other', stats  # Mixed or other languages

def is_emoji(char: str) -> bool:
    """Check if character is an emoji."""
    code_point = ord(char)
    # Common emoji ranges
    return (
        0x1F600 <= code_point <= 0x1F64F or  # Emoticons
        0x1F300 <= code_point <= 0x1F5FF or  # Misc Symbols and Pictographs
        0x1F680 <= code_point <= 0x1F6FF or  # Transport and Map
        0x1F1E0 <= code_point <= 0x1F1FF or  # Regional Indicators (flags)
        0x2600 <= code_point <= 0x26FF or    # Misc symbols
        0x2700 <= code_point <= 0x27BF or    # Dingbats
        0xFE00 <= code_point <= 0xFE0F or    # Variation Selectors
        0x1F900 <= code_point <= 0x1F9FF or  # Supplemental Symbols
        0x1FA00 <= code_point <= 0x1FA6F or  # Chess Symbols
        0x1FA70 <= code_point <= 0x1FAFF     # Symbols and Pictographs Extended
    )

def is_stylish_font(char: str) -> bool:
    """Check if character is a stylish/font character (mathematical alphanumerics, small caps, etc.)."""
    code_point = ord(char)
    # Mathematical Alphanumerics and other font styles
    return (
        0x1D400 <= code_point <= 0x1D7FF or  # Mathematical Alphanumerics
        0x1D00 <= code_point <= 0x1D7F or    # Phonetic Extensions
        0x1D80 <= code_point <= 0x1DBF or    # Phonetic Extensions Supplement
        0x0250 <= code_point <= 0x02AF or    # IPA Extensions
        0x1E00 <= code_point <= 0x1EFF or    # Latin Extended Additional
        0x2090 <= code_point <= 0x209C or    # Subscript
        0x2070 <= code_point <= 0x209F or    # Superscripts and Subscripts
        0x2100 <= code_point <= 0x214F or    # Letterlike Symbols (includes ℓ)
        0x2C60 <= code_point <= 0x2C7F or    # Latin Extended-C
        0xA720 <= code_point <= 0xA7FF or    # Latin Extended-D (includes small caps)
        0xFB00 <= code_point <= 0xFB06 or    # Alphabetic Presentation Forms
        0xFF01 <= code_point <= 0xFF5E or    # Fullwidth ASCII variants
        0x2460 <= code_point <= 0x24FF or    # Enclosed Alphanumerics (circled letters)
        0x0400 <= code_point <= 0x04FF or    # Cyrillic (used as aesthetic Latin lookalikes: ѕ, м, є, etc.)
        0x0370 <= code_point <= 0x03FF or    # Greek (used as aesthetic: α, β, etc.)
        0x20D0 <= code_point <= 0x20FF or    # Combining Diacritical Marks (⃝, etc.)
        0xA700 <= code_point <= 0xA71F or    # Modifier Tone Letters
        0xA600 <= code_point <= 0xA6FF or    # Bamum (decorative)
        0xA500 <= code_point <= 0xA63F or    # Yi Syllables (decorative)
        0xA78F <= code_point <= 0xA78F or    # Latin letter (decorative)
        0xAA00 <= code_point <= 0xAA5F or    # Cham (decorative)
        0xAA60 <= code_point <= 0xAA7F or    # Myanmar Extended-A
        0xAA80 <= code_point <= 0xAADF or    # Tai Viet
        0x16A0 <= code_point <= 0x16EA or    # Runic (decorative)
        0x10300 <= code_point <= 0x1032F or  # Old Italic (decorative)
        0x10330 <= code_point <= 0x1034F or  # Gothic letters (decorative)
        0x16800 <= code_point <= 0x16A3F or  # Bamum Supplement (decorative symbols)
        0x16F00 <= code_point <= 0x16F9F or  # Miao (decorative)
        0x1B000 <= code_point <= 0x1B0FF     # Kana Supplement (decorative)
    )

async def check_language_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if message language is allowed in the group.
    Returns True if message should be deleted, False if allowed.
    """
    from managers.settings_manager_mongo import get_chat_settings
    from core.database import is_connected
    
    if not is_connected():
        return False
    
    chat_id = update.effective_chat.id
    message = update.message
    if not message:
        return False
    
    # Get group settings
    settings = get_chat_settings(chat_id)
    
    # Check if language filter is enabled
    if not settings.get('language_filter_enabled', False):
        return False
    
    # Get allowed languages (default: en, hi, hinglish)
    allowed_languages = settings.get('allowed_languages', ['en', 'hi', 'hinglish'])
    
    # Get message text
    text = message.text or message.caption
    if not text:
        return False  # Don't filter non-text messages
    
    # Detect language
    detected_lang, stats = detect_language(text)
    
    # Handle safe messages (emojis, numbers, punctuation only)
    if detected_lang == 'safe':
        emojis = stats.get('emojis', 0)
        punctuation = stats.get('punctuation', 0)
        total_alphabetic = stats.get('total_alphabetic', 0)
        numbers = stats.get('numbers', 0)

        # Check if emoji blocking is enabled
        if emojis > 0 and settings.get('emoji_block_enabled', False):
            if settings.get('block_emoji_only', True) and total_alphabetic == 0:
                # Delete emoji-only messages if blocking enabled
                pass  # Will be deleted below
            else:
                return False  # Allow mixed content
        
        # Check if punctuation blocking is enabled  
        if punctuation > 0 and settings.get('block_punctuation_only', True):
            if total_alphabetic == 0 and emojis == 0 and numbers == 0:
                # Delete punctuation-only messages if blocking enabled
                pass  # Will be deleted below
            else:
                return False  # Allow mixed content
        
        # If no blocking enabled for safe content, allow
        if not settings.get('emoji_block_enabled', False) and not settings.get('block_punctuation_only', True):
            return False  # Don't delete safe messages
    
    # If detected language is not allowed, delete message
    if detected_lang not in allowed_languages and detected_lang != 'safe':
        try:
            # Delete the message
            await message.delete()
            
            # Send warning message
            warning_msg = (
                f"⚠️ <b>Language Filter Active</b>\n\n"
                f"Your message was deleted because it was not in an allowed language.\n\n"
                f"<b>Detected:</b> {detected_lang.upper()}\n"
                f"<b>Allowed:</b> {', '.join([SUPPORTED_LANGUAGES.get(lang, lang) for lang in allowed_languages])}\n\n"
                f"Please use one of the allowed languages."
            )
            
            # Send warning and auto-delete using helper
            from handlers.blocking_handler import send_blocking_notification
            await send_blocking_notification(update, context, settings, warning_msg)
            
            return True  # Message was deleted
            
        except Exception as e:
            logging.error(f"Error deleting message: {e}")
            return False
    
    return False  # Message is allowed

async def delete_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int):
    """Delete a message after specified delay in seconds."""
    import asyncio
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logging.error(f"Error deleting warning message: {e}")

async def language_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle message language filtering."""
    # Only check in groups
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    # Check language filter
    deleted = await check_language_filter(update, context)
    
    if deleted:
        logging.info(f"Message deleted due to language filter in chat {update.effective_chat.id}")

def get_language_name(code: str) -> str:
    """Get language name from code."""
    return SUPPORTED_LANGUAGES.get(code, code)

def get_language_handlers():
    """Return language filter handlers."""
    from telegram.ext import MessageHandler, filters
    return [
        MessageHandler(filters.TEXT | filters.CAPTION, language_filter_handler)
    ]
