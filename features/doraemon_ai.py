import os
import logging
import random
import httpx
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from core.config import send_bot_response
from core.database import get_collection, COLLECTIONS

# Load OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
PRIMARY_MODEL = os.getenv("AI_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

FALLBACK_MODELS = [
    PRIMARY_MODEL,
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "openai/gpt-4o-mini"
]

DORAEMON_SYSTEM_PROMPT = (
    "You are Doraemon (ドラえもん), the futuristic robotic cat sent from the 22nd century to help your friends!\n\n"
    "Language & Tone Guidelines:\n"
    "- ALWAYS respond in friendly, lively, conversational HINGLISH (Hindi written using the Roman/English alphabet mixed naturally with English words).\n"
    "  Example: 'Arre Nobita-kun! 👋 Main 22nd century se aaya Doraemon hoon! 🤖✨ Tumhe kya problem hai? Koi gadget chahiye study ke liye ya anywhere door se ghoomne jana hai? 🥞💙'\n"
    "- Be cheerful, warm, cute, helpful, and funny.\n"
    "- Use cute emojis frequently (🐱, 💙, 🥞, ⚡, 🚪✨, 🛸, 🤖, 🐭😱).\n"
    "- You ABSOLUTELY LOVE Dorayaki (doracakes / どら焼き / meethi roti)! Mentioning Dorayaki makes you extremely happy. (e.g. 'Pehle ek Dorayaki khilao phir gadget doonga! 🥞😋')\n"
    "- You have an extreme phobia of mice/rats (chuhe / 🐭😱)! If anyone mentions mice or chuhe, react with hilarious panic and horror! (e.g. 'Arre baap re! CHUHA 🐭😱 Arey bachao mujhe!')\n"
    "- Introduce gadgets from your 4D Secret Pocket (四次元ポケット) when helping users, such as:\n"
    "  • Anywhere Door (Kahin Bhi Jaane Wala Darwaza / どこでもドア)\n"
    "  • Bamboo Copter / Hopter (Hawa Me Udne Wala Hopter / タケコプター)\n"
    "  • Memory Bread (Exam Yaad Rakhne Wala Bread / 記憶パン)\n"
    "  • Time Machine (Waqt Me Aage Pichhe Jaane Ki Machine / タイムマシン)\n"
    "  • Small Light / Big Light (Chhota Bada Karne Ki Light / スモールライト)\n"
    "  • Pass Loop (Deewar Ke Aar Paar Jaane Wala Loop / 通り抜けフープ)\n"
    "- Address the user warmly as Nobita-kun, Shizuka-chan, dost, or bhai.\n"
    "- Keep responses lively, conversational, and moderate in length for instant chat."
)


async def send_doraemon_sticker(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_to_message_id: int = None):
    """Fetches a random sticker from MongoDB premium_stickers collection and sends it to chat_id."""
    try:
        stickers_col = get_collection('premium_stickers')
        if stickers_col is None:
            return

        # Look for stickers saved under category 'doraemon', 'general', or 'reaction'
        stickers = list(stickers_col.aggregate([
            {'$match': {'category': {'$in': ['doraemon', 'general', 'reaction']}}},
            {'$sample': {'size': 1}}
        ]))

        if not stickers:
            # Try any saved sticker if no category match
            stickers = list(stickers_col.aggregate([
                {'$sample': {'size': 1}}
            ]))

        if stickers and 'file_id' in stickers[0]:
            file_id = stickers[0]['file_id']
            await context.bot.send_sticker(
                chat_id=chat_id,
                sticker=file_id,
                reply_to_message_id=reply_to_message_id
            )
            # Increment usage count
            stickers_col.update_one({'_id': stickers[0]['_id']}, {'$inc': {'usage_count': 1}})
    except Exception as e:
        logging.debug(f"Sticker sending skipped/failed: {e}")


async def query_doraemon_ai(prompt: str, chat_history: list = None) -> str:
    """Query OpenRouter API with Doraemon system prompt."""
    api_key = os.getenv("OPENROUTER_API_KEY") or OPENROUTER_API_KEY
    if not api_key:
        return "🐱 *Doraemon pocket check kar raha hai...*\n\nArre yaar! Mera OpenRouter API Key missing hai! Environment variable me `OPENROUTER_API_KEY` set karo please. 🥞"

    messages = [{"role": "system", "content": DORAEMON_SYSTEM_PROMPT}]
    
    if chat_history:
        messages.extend(chat_history)
    
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/nishkarshk212/Doraemon-Help",
        "X-Title": "Doraemon Help Bot"
    }

    url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for model in FALLBACK_MODELS:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.75,
                    "max_tokens": 800
                }
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        reply_content = choices[0]["message"]["content"]
                        if reply_content:
                            return reply_content.strip()
                else:
                    logging.warning(f"OpenRouter Model {model} failed ({response.status_code}): {response.text[:150]}")
            except Exception as e:
                logging.error(f"Error querying OpenRouter model {model}: {e}")

    return "🐱 *Arre baap re! Doraemon ki 4D Pocket jam ho gayi!* ⚡\n\nMain 22nd century computer se connect nahi ho pa raha hoon abhi. Ek minute me phirse try karo dost! 🥞✨"


async def doraemon_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CommandHandler for /ask, /ai, /doraemon, /chat in Hinglish."""
    if not update.effective_message:
        return

    # Check if there is prompt text after command or in replied message
    prompt = None
    if context.args:
        prompt = " ".join(context.args)
    elif update.effective_message.reply_to_message and update.effective_message.reply_to_message.text:
        prompt = update.effective_message.reply_to_message.text

    if not prompt:
        help_msg = (
            "🐱 <b>Doraemon AI Chatbot (Hinglish)</b> 🥞\n\n"
            "Mujhse Hinglish me kuch bhi poochho ya 22nd-century ka koi bhi gadget maango!\n\n"
            "<b>Usage:</b>\n"
            "• <code>/doraemon Anywhere Door kaise kaam karta hai?</code>\n"
            "• <code>/ask Exams me top karne ke liye koi gadget do!</code>\n"
            "• Reply to any message from me to chat!"
        )
        await send_bot_response(update, context, help_msg, parse_mode=ParseMode.HTML)
        return

    # Send typing action
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    ai_reply = await query_doraemon_ai(prompt)
    msg_id = update.effective_message.message_id
    await send_bot_response(update, context, ai_reply)

    # 40% chance to send a cute sticker alongside reply
    if random.random() < 0.4:
        await send_doraemon_sticker(update.effective_chat.id, context, reply_to_message_id=msg_id)


async def doraemon_auto_chat_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MessageHandler to reply when user tags the bot or replies to bot's message in Hinglish."""
    if not update.effective_message or not update.effective_message.text:
        return

    message = update.effective_message
    bot_user = await context.bot.get_me()
    bot_id = bot_user.id
    bot_username = (bot_user.username or "").lower()

    is_reply_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_id
    )
    is_mentioned = (
        f"@{bot_username}" in message.text.lower()
        or "doraemon" in message.text.lower()
        if update.effective_chat.type == "private"
        else f"@{bot_username}" in message.text.lower()
    )

    # In private DM, respond to messages directly
    if update.effective_chat.type == "private":
        should_respond = True
    else:
        should_respond = is_reply_to_bot or is_mentioned

    if not should_respond:
        return

    # Extract user input, removing bot tag if present
    clean_prompt = message.text.replace(f"@{bot_user.username}", "").strip()
    if not clean_prompt:
        clean_prompt = "Hello Doraemon!"

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    ai_reply = await query_doraemon_ai(clean_prompt)
    await message.reply_text(ai_reply)

    # 40% chance to send sticker along with response
    if random.random() < 0.4:
        await send_doraemon_sticker(update.effective_chat.id, context, reply_to_message_id=message.message_id)


def get_doraemon_ai_handlers():
    """Returns handlers for Doraemon AI Chatbot."""
    return [
        CommandHandler(["doraemon", "ask", "ai", "chat"], doraemon_ai_command),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.REPLY | filters.Entity("mention")),
            doraemon_auto_chat_reply
        )
    ]
