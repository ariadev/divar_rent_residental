import os
import json
import time
import asyncio
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = [cid.strip() for cid in os.getenv('TELEGRAM_CHAT_IDS', '').split(',') if cid.strip()]
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 900))
SENT_POSTS_FILE = 'sent_posts.json'

# Divar API configuration
DIVAR_API_URL = "https://api.divar.ir/v8/web-search/5/residential-rent"
API_PAYLOAD = {
    "json_schema": {
        "category": {"value": "residential-rent"},
        "cities": ["5"]
    },
    "last-post-date": int(time.time() * 1000)  # Current timestamp in milliseconds
}

def load_sent_posts():
    """Load sent post tokens from file"""
    try:
        if os.path.exists(SENT_POSTS_FILE):
            with open(SENT_POSTS_FILE, 'r') as f:
                return set(json.load(f))
    except Exception as e:
        logger.error(f"Error loading sent posts: {e}")
    return set()

def save_sent_posts(sent_posts):
    """Save sent post tokens to file"""
    try:
        with open(SENT_POSTS_FILE, 'w') as f:
            json.dump(list(sent_posts), f)
    except Exception as e:
        logger.error(f"Error saving sent posts: {e}")

def search_divar(last_post_date=None):
    """Search for posts on Divar"""
    payload = API_PAYLOAD.copy()
    if last_post_date:
        payload["last-post-date"] = last_post_date
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.post(DIVAR_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching data from Divar: {e}")
        return None

async def send_telegram_message(bot, post_data, chat_ids):
    """Send post to Telegram users"""
    try:
        token = post_data.get('token')
        title = post_data.get('title', 'No title')
        image_url = post_data.get('image_url')
        
        # Extract description information
        description = post_data.get('description', '')
        district = post_data.get('district', '')
        
        post_url = f"https://divar.ir/v/{token}"
        
        message = f"🏠 <b>{title}</b>\n\n"
        if district:
            message += f"📍 {district}\n"
        if description:
            message += f"📝 {description}\n"
        message += f"\n🔗 <a href='{post_url}'>View Post</a>"
        
        success_count = 0
        for chat_id in chat_ids:
            try:
                if image_url and image_url.startswith('http'):
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=message,
                        parse_mode='HTML'
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
                success_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error sending to {chat_id}: {e}")
        
        return success_count > 0
    except Exception as e:
        logger.error(f"Error sending to Telegram: {e}")
        return False

def get_new_posts():
    """Get new posts from Divar"""
    sent_posts = load_sent_posts()
    new_posts = []
    
    result = search_divar()
    if not result:
        return new_posts, sent_posts
    
    # Process the first page
    post_list = result.get('web_widgets', {}).get('post_list', [])
    
    for post in post_list:
        if post.get('widget_type') == 'POST_ROW':
            data = post.get('data', {})
            token = data.get('token')
            
            if token and token not in sent_posts:
                new_posts.append(data)
                sent_posts.add(token)
                logger.info(f"Found new post: {data.get('title', 'No title')}")
    
    # Save sent posts immediately to avoid duplicates
    if new_posts:
        save_sent_posts(sent_posts)
    
    return new_posts, sent_posts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("🔍 Check New Posts", callback_data='check_new')],
        [InlineKeyboardButton("ℹ️ Info", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "🏠 <b>Divar Post Notifier Bot</b>\n\n"
        f"👋 Welcome {user.first_name}!\n\n"
        "📍 <b>Search Area:</b> Tehran\n"
        "💰 <b>Max Price:</b> 200,000,000 Tomans\n"
        "🏠 <b>Max Rent:</b> 13,000,000 Tomans\n\n"
        "Click the button below to check for new posts:"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    main_keyboard = [
        [InlineKeyboardButton("🔍 Check New Posts", callback_data='check_new')],
        [InlineKeyboardButton("ℹ️ Info", callback_data='info')]
    ]
    
    if query.data == 'check_new':
        await query.edit_message_text(
            '🔄 Checking for new posts...',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]])
        )
        
        new_posts, sent_posts = get_new_posts()
        
        if new_posts:
            await query.edit_message_text(
                f'📬 Found {len(new_posts)} new posts. Sending...',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]])
            )
            
            sent_count = 0
            for post in new_posts:
                try:
                    success = await send_telegram_message(context.bot, post, TELEGRAM_CHAT_IDS)
                    if success:
                        sent_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error sending post: {e}")
            
            await query.edit_message_text(
                f'✅ {sent_count} posts sent successfully.',
                reply_markup=InlineKeyboardMarkup(main_keyboard)
            )
        else:
            await query.edit_message_text(
                '✅ No new posts found.',
                reply_markup=InlineKeyboardMarkup(main_keyboard)
            )
            
    elif query.data == 'info':
        info_text = (
            "📍 <b>Search Area:</b> Tehran\n"
            "💰 <b>Max Price:</b> 200,000,000 Tomans\n"
            "🏠 <b>Max Rent:</b> 13,000,000 Tomans\n"
            f"⏰ <b>Check Interval:</b> {CHECK_INTERVAL} seconds\n"
        )
        await query.edit_message_text(
            info_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back')]]),
            parse_mode='HTML'
        )
        
    elif query.data == 'back':
        await query.edit_message_text(
            '🏠 <b>Divar Post Notifier Bot</b>\n\nMain menu:',
            reply_markup=InlineKeyboardMarkup(main_keyboard),
            parse_mode='HTML'
        )

async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    """Periodic check for new posts"""
    logger.info("Starting periodic check...")
    
    try:
        new_posts, sent_posts = get_new_posts()
        
        if new_posts:
            logger.info(f"Found {len(new_posts)} new posts")
            
            sent_count = 0
            for post in new_posts:
                try:
                    success = await send_telegram_message(context.bot, post, TELEGRAM_CHAT_IDS)
                    if success:
                        sent_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error sending post in periodic check: {e}")
            
            logger.info(f"Periodic check completed - {sent_count} posts sent")
        else:
            logger.info("Periodic check completed - no new posts found")
    except Exception as e:
        logger.error(f"Error in periodic check: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Error: {context.error}")

def main():
    """Main function"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is required")
        return
    
    if not TELEGRAM_CHAT_IDS:
        logger.error("TELEGRAM_CHAT_IDS is required")
        return
    
    logger.info("Starting Divar Bot...")
    logger.info(f"Users: {len(TELEGRAM_CHAT_IDS)}")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # Setup periodic job
    job_queue = application.job_queue
    job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL, first=10)
    
    # Start bot
    logger.info("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()