import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from telethon.sessions import StringSession
    from telethon import TelegramClient
except ImportError:
    print("Installing Telethon...")
    os.system("pip install telethon")
    from telethon.sessions import StringSession
    from telethon import TelegramClient

async def main():
    print("=" * 60)
    print("  Telethon String Session Generator")
    print("=" * 60)
    
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")

    if not api_id or not api_hash or api_id == "0":
        api_id = input("\nEnter your Telegram API_ID: ").strip()
        api_hash = input("Enter your Telegram API_HASH: ").strip()

    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ Invalid API_ID! Must be an integer.")
        return

    print("\nConnecting to Telegram... (You will be prompted for your phone number & OTP code)")
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_str = client.session.save()
        print("\n" + "=" * 60)
        print("✅ YOUR NEW STRING SESSION:")
        print("=" * 60)
        print(session_str)
        print("=" * 60)
        print("\nCopy the string above and set it as STRING_SESSION in your .env file or Heroku Config Vars!\n")

if __name__ == "__main__":
    asyncio.run(main())
