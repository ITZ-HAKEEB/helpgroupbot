"""
Sticker Manager - Handle sticker commands and usage in bot messages
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from core.database import get_collection, COLLECTIONS
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB collections
stickers_collection = get_collection('premium_stickers')
emojis_collection = get_collection('premium_emojis')
settings_collection = get_collection('bot_settings')

# Owner ID - who can save stickers
OWNER_ID = int(os.getenv('OWNER_ID', 0))

async def save_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save a sticker from replied message"""
    user_id = update.effective_user.id
    
    # Only owner can save stickers
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only bot owner can save stickers!")
        return
    
    # Check if replying to a sticker
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text(
            "📌 Reply to a sticker with:\n"
            "<code>/save_sticker &lt;category&gt;</code>\n\n"
            "Categories: welcome, goodbye, reaction, ban, mute, general",
            parse_mode='HTML'
        )
        return
    
    # Get category
    category = 'general'
    if context.args:
        category = context.args[0].lower()
    
    sticker = update.message.reply_to_message.sticker
    
    # Save sticker
    sticker_data = {
        'file_id': sticker.file_id,
        'unique_id': sticker.unique_id,
        'emoji': sticker.emoji,
        'set_name': sticker.set_name,
        'width': sticker.width,
        'height': sticker.height,
        'is_premium': sticker.premium if hasattr(sticker, 'premium') else False,
        'is_animated': sticker.is_animated,
        'is_video': sticker.is_video,
        'category': category,
        'saved_by': user_id,
        'usage_count': 0
    }
    
    # Check if exists
    existing = stickers_collection.find_one({'unique_id': sticker.unique_id})
    if existing:
        await update.message.reply_text(f"⚠️ Sticker already saved in category: {existing.get('category', 'general')}")
        return
    
    # Save to MongoDB
    stickers_collection.insert_one(sticker_data)
    
    await update.message.reply_text(
        f"✅ Sticker saved!\n\n"
        f"📂 Category: {category}\n"
        f"🎭 Emoji: {sticker.emoji}\n"
        f"🆔 ID: {sticker.unique_id}\n"
        f"⭐ Premium: {sticker_data['is_premium']}\n"
        f"🎬 Animated: {sticker_data['is_animated']}"
    )
    
    logger.info(f"💾 Sticker saved: {sticker.unique_id} in {category}")

async def save_emoji_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save a custom emoji from replied message"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only bot owner can save emojis!")
        return
    
    # Check if replying to a message
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Reply to a message containing custom emoji with:\n"
            "<code>/save_emoji &lt;category&gt;</code>\n\n"
            "Example: <code>/save_emoji premium_pack</code>",
            parse_mode='HTML'
        )
        return
    
    # Get category
    category = 'general'
    if context.args:
        category = context.args[0].lower()
    
    # Extract custom emoji entities
    message = update.message.reply_to_message
    
    # Method 1: Check for custom_emoji_id directly (standalone emoji)
    if hasattr(message, 'custom_emoji_id') and message.custom_emoji_id:
        emoji_id = message.custom_emoji_id
        
        emoji_data = {
            'file_id': str(emoji_id),
            'unique_id': str(emoji_id),
            'category': category,
            'saved_by': user_id,
            'is_premium': True,
            'usage_count': 0
        }
        
        # Check if exists
        existing = emojis_collection.find_one({'unique_id': str(emoji_id)})
        if existing:
            await update.message.reply_text(f"⚠️ Emoji already saved in category: {existing.get('category', 'general')}")
            return
        
        emojis_collection.insert_one(emoji_data)
        await update.message.reply_text(
            f"✅ Custom emoji saved!\n\n"
            f"📂 Category: {category}\n"
            f"🆔 ID: {emoji_id}"
        )
        logger.info(f"💾 Emoji saved: {emoji_id} in {category}")
        return
    
    # Method 2: Check for custom emoji entities in text
    if message.entities:
        for entity in message.entities:
            if entity.type == 'custom_emoji':
                emoji_id = entity.custom_emoji_id
                
                emoji_data = {
                    'file_id': str(emoji_id),
                    'unique_id': str(emoji_id),
                    'category': category,
                    'saved_by': user_id,
                    'is_premium': True,
                    'usage_count': 0
                }
                
                # Check if exists
                existing = emojis_collection.find_one({'unique_id': str(emoji_id)})
                if existing:
                    await update.message.reply_text(f"⚠️ Emoji already saved in category: {existing.get('category', 'general')}")
                    return
                
                emojis_collection.insert_one(emoji_data)
                await update.message.reply_text(
                    f"✅ Custom emoji saved!\n\n"
                    f"📂 Category: {category}\n"
                    f"🆔 ID: {emoji_id}"
                )
                logger.info(f"💾 Emoji saved: {emoji_id}")
                return
    
    await update.message.reply_text(
        "❌ No custom emoji found!\n\n"
        "💡 <b>How to save:</b>\n"
        "1. Send a custom emoji from any premium pack\n"
        "2. Reply to it with: <code>/save_emoji premium_pack</code>"
    )

async def get_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get random sticker from category"""
    category = 'general'
    if context.args:
        category = context.args[0].lower()
    
    # Get random sticker
    sticker = stickers_collection.aggregate([
        {'$match': {'category': category}},
        {'$sample': {'size': 1}}
    ]).to_list(1)
    
    if not sticker:
        await update.message.reply_text(f"❌ No stickers found in category: {category}")
        return
    
    sticker_data = sticker[0]
    
    # Update usage count
    stickers_collection.update_one(
        {'_id': sticker_data['_id']},
        {'$inc': {'usage_count': 1}}
    )
    
    # Send sticker
    await update.message.reply_sticker(sticker_data['file_id'])

async def get_emoji_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get info about saved emojis"""
    category = 'general'
    if context.args:
        category = context.args[0].lower()
    
    # Get random emoji
    emoji = emojis_collection.aggregate([
        {'$match': {'category': category}},
        {'$sample': {'size': 1}}
    ]).to_list(1)
    
    if not emoji:
        await update.message.reply_text(f"❌ No emojis found in category: {category}")
        return
    
    emoji_data = emoji[0]
    
    await update.message.reply_text(
        f"✨ Custom Emoji\n\n"
        f"📂 Category: {category}\n"
        f"🆔 ID: {emoji_data['unique_id']}\n"
        f"📊 Usage count: {emoji_data.get('usage_count', 0)}"
    )

async def list_stickers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all saved stickers by category"""
    # Get all categories
    categories = stickers_collection.distinct('category')
    
    if not categories:
        await update.message.reply_text("❌ No stickers saved yet!")
        return
    
    message = "📦 <b>Saved Stickers</b>\n\n"
    
    for category in categories:
        count = stickers_collection.count_documents({'category': category})
        message += f"📂 {category}: {count} stickers\n"
    
    total = stickers_collection.count_documents({})
    message += f"\n📊 Total: {total} stickers"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def list_emojis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all saved emojis by category"""
    categories = emojis_collection.distinct('category')
    
    if not categories:
        await update.message.reply_text("❌ No emojis saved yet!")
        return
    
    message = "✨ <b>Saved Custom Emojis</b>\n\n"
    
    for category in categories:
        count = emojis_collection.count_documents({'category': category})
        message += f"📂 {category}: {count} emojis\n"
    
    total = emojis_collection.count_documents({})
    message += f"\n📊 Total: {total} emojis"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def delete_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a sticker by ID"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only bot owner can delete stickers!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /delete_sticker <unique_id>")
        return
    
    sticker_id = context.args[0]
    
    result = stickers_collection.delete_one({'unique_id': sticker_id})
    
    if result.deleted_count > 0:
        await update.message.reply_text(f"✅ Sticker deleted: {sticker_id}")
    else:
        await update.message.reply_text(f"❌ Sticker not found: {sticker_id}")

async def sticker_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics about saved stickers and emojis"""
    total_stickers = stickers_collection.count_documents({})
    total_emojis = emojis_collection.count_documents({})
    premium_stickers = stickers_collection.count_documents({'is_premium': True})
    animated_stickers = stickers_collection.count_documents({'is_animated': True})
    
    # Top categories
    top_categories = stickers_collection.aggregate([
        {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]).to_list(None)
    
    message = (
        f"📊 <b>Sticker & Emoji Statistics</b>\n\n"
        f"💾 Total Stickers: {total_stickers}\n"
        f"⭐ Premium Stickers: {premium_stickers}\n"
        f"🎬 Animated Stickers: {animated_stickers}\n"
        f"✨ Custom Emojis: {total_emojis}\n\n"
    )
    
    if top_categories:
        message += "<b>Top Categories:</b>\n"
        for cat in top_categories:
            message += f"  • {cat['_id']}: {cat['count']}\n"
    
    await update.message.reply_text(message, parse_mode='HTML')

def get_sticker_handlers():
    """Get all sticker handlers"""
    from telegram.ext import CommandHandler
    
    return [
        CommandHandler("save_sticker", save_sticker_command),
        CommandHandler("save_emoji", save_emoji_command),
        CommandHandler("get_sticker", get_sticker_command),
        CommandHandler("get_emoji", get_emoji_command),
        CommandHandler("list_stickers", list_stickers_command),
        CommandHandler("list_emojis", list_emojis_command),
        CommandHandler("delete_sticker", delete_sticker_command),
        CommandHandler("sticker_stats", sticker_stats_command),
    ]

def send_sticker_by_category(chat_id, context, category='general'):
    """Send random sticker from category (for use in other modules)"""
    sticker = stickers_collection.aggregate([
        {'$match': {'category': category}},
        {'$sample': {'size': 1}}
    ]).to_list(1)
    
    if sticker:
        sticker_data = sticker[0]
        
        # Update usage count
        stickers_collection.update_one(
            {'_id': sticker_data['_id']},
            {'$inc': {'usage_count': 1}}
        )
        
        # Send sticker
        context.bot.send_sticker(chat_id, sticker_data['file_id'])
        return True
    
    return False
