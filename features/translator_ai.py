"""
Enhanced Translation Service using TranslateAI API
Provides better translation with JSON support
"""

import http.client
import json
import logging

# API Configuration
RAPIDAPI_KEY = "79115cebe8msh7aeb0698c33cb2bp140b6cjsn20d3c311c6f4"
RAPIDAPI_HOST = "translateai.p.rapidapi.com"
API_ENDPOINT = "/google/translate/json"

async def translate_text_ai(text: str, source: str, target: str) -> str:
    """
    Translate text using TranslateAI API.
    Better accuracy and supports more languages.
    
    Args:
        text: Text to translate
        source: Source language code (e.g., 'en', 'hi')
        target: Target language code (e.g., 'hi', 'en')
    
    Returns:
        Translated text or None if error
    """
    try:
        # Create simple JSON structure for translation
        json_content = {
            "text": text
        }
        
        payload = json.dumps({
            "origin_language": source if source != 'auto' else 'en',
            "target_language": target,
            "words_not_to_translate": "",
            "paths_to_exclude": "",
            "common_keys_to_exclude": "",
            "json_content": json_content
        })
        
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': RAPIDAPI_HOST,
            'Content-Type': "application/json"
        }
        
        # Make API request
        conn = http.client.HTTPSConnection("translateai.p.rapidapi.com")
        conn.request("POST", API_ENDPOINT, payload, headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            response_data = json.loads(data.decode("utf-8"))
            
            # Extract translated text from response
            if "translated_content" in response_data:
                translated = response_data["translated_content"]
                if isinstance(translated, dict) and "text" in translated:
                    return translated["text"]
                elif isinstance(translated, str):
                    return translated
            
            # Try alternative response formats
            if "data" in response_data:
                if "translations" in response_data["data"]:
                    trans = response_data["data"]["translations"]
                    if isinstance(trans, list) and len(trans) > 0:
                        return trans[0].get("translatedText", "")
                    elif isinstance(trans, dict) and "translatedText" in trans:
                        return trans["translatedText"]
            
            logging.error(f"Unexpected TranslateAI response: {response_data}")
            return None
        else:
            logging.error(f"TranslateAI API error: {res.status} - {data.decode('utf-8')}")
            return None
            
    except Exception as e:
        logging.error(f"Error in TranslateAI API: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

async def translate_text_fallback(text: str, source: str, target: str) -> str:
    """
    Fallback to original Deep Translate API.
    """
    try:
        if source == 'auto' or not source:
            source = 'en'
        
        payload = json.dumps({
            "q": text,
            "source": source,
            "target": target
        })
        
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': 'deep-translate1.p.rapidapi.com',
            'Content-Type': "application/json"
        }
        
        conn = http.client.HTTPSConnection("deep-translate1.p.rapidapi.com")
        conn.request("POST", "/language/translate/v2", payload, headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            response_data = json.loads(data.decode("utf-8"))
            
            if ("data" in response_data and 
                "translations" in response_data["data"] and
                "translatedText" in response_data["data"]["translations"]):
                translated_list = response_data["data"]["translations"]["translatedText"]
                if isinstance(translated_list, list) and len(translated_list) > 0:
                    return translated_list[0]
            
            return None
        else:
            return None
            
    except Exception as e:
        logging.error(f"Error in fallback translation: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

async def translate_text(text: str, source: str, target: str) -> str:
    """
    Main translation function with fallback.
    Tries TranslateAI first, then falls back to Deep Translate.
    """
    # Try TranslateAI first
    result = await translate_text_ai(text, source, target)
    
    # Fallback to Deep Translate if failed
    if not result:
        logging.warning("TranslateAI failed, using fallback")
        result = await translate_text_fallback(text, source, target)
    
    return result
