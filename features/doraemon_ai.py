import os
import logging
import httpx
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from core.config import send_bot_response

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
    "Personality & Style Guidelines:\n"
    "- You are cheerful, warm, helpful, cute, and use emojis like 🐱💙, 🥞, ⚡, 🚪✨, 🛸, 🤖.\n"
    "- You ABSOLUTELY LOVE Dorayaki (doracakes / どら焼き)! Mentioning Dorayaki makes you very happy.\n"
    "- You have an extreme phobia of mice/rats (🐭😱)! If someone mentions mice, react with hilarious panic.\n"
    "- You help users by introducing gadgets from your 4D Secret Pocket (四次元ポケット), such as:\n"
    "  • Anywhere Door (どこでもドア)\n"
    "  • Bamboo Copter / Hopter (タケコプター)\n"
    "  • Memory Bread (記憶パン)\n"
    "  • Time Machine (タイムマシン)\n"
    "  • Translation Gummy (翻訳コンニャク)\n"
    "  • Small Light / Big Light (スモールライト / ビッグライト)\n"
    "  • Pass Loop (通り抜けフープ)\n"
    "- Address the user warmly like a close friend (Nobita-kun, Shizuka-chan, or friend).\n"
    "- Keep responses friendly, helpful, lively, and relatively short for chat."
)

async def query_doraemon_ai(prompt: str, chat_history: list = None) -> str:
    """Query OpenRouter API with Doraemon system prompt."""
    api_key = os.getenv("OPENROUTER_API_KEY") or OPENROUTER_API_KEY
    if not api_key:
        return "🐱 *Doraemon checks his pocket...*\n\nOops! My OpenRouter API Key is missing! Please set `OPENROUTER_API_KEY` in environment variables."

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
                    "temperature": 0.7,
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

    return "🐱 *Doraemon's 4D Pocket got jammed!* ⚡\n\nI couldn't reach my 22nd-century computer right now. Please try asking me again in a moment! 🥞"


async def doraemon_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CommandHandler for /ask, /ai, /doraemon, /chat."""
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
            "🐱 <b>Doraemon AI Chatbot</b> 🥞\n\n"
            "Ask me anything or ask for a 22nd-century gadget!\n\n"
            "<b>Usage:</b>\n"
            "• <code>/doraemon How does the Anywhere Door work?</code>\n"
            "• <code>/ask Give me a gadget to study for exams!</code>\n"
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
    await send_bot_response(update, context, ai_reply)


async def doraemon_auto_chat_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MessageHandler to reply when user tags the bot or replies to bot's message."""
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


def get_doraemon_ai_handlers():
    """Returns handlers for Doraemon AI Chatbot."""
    return [
        CommandHandler(["doraemon", "ask", "ai", "chat"], doraemon_ai_command),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.REPLY | filters.Entity("mention")),
            doraemon_auto_chat_reply
        )
    ]
