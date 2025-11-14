import os
import json
import time
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
    "city_ids": ["5"],
    "source_view": "FILTER",
    "disable_recommendation": False,
    "map_state": {
        "camera_info": {
            "bbox": {
                "min_latitude": 37.73286437988281,
                "min_longitude": 45.88922882080078,
                "max_latitude": 38.48418426513672,
                "max_longitude": 46.49272537231445
            },
            "place_hash": "5||residential-rent",
            "zoom": 9.370656250950889
        },
        "page_state": "HALF_STATE"
    },
    "search_data": {
        "form_data": {
            "data": {
                "bbox": {
                    "repeated_float": {
                        "value": [
                            {"value": 45.8892288},
                            {"value": 37.7328644},
                            {"value": 46.4927254},
                            {"value": 38.4841843}
                        ]
                    }
                },
                "credit": {"number_range": {"maximum": "200000000"}},
                "rent": {"number_range": {"maximum": "13000000"}},
                "category": {"str": {"value": "residential-rent"}}
            }
        },
        "server_payload": {
            "@type": "type.googleapis.com/widgets.SearchData.ServerPayload",
            "additional_form_data": {
                "data": {
                    "sort": {"str": {"value": "sort_date"}}
                }
            }
        }
    }
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

def search_divar(page_data=None):
    """Search for posts on Divar"""
    payload = API_PAYLOAD.copy()
    if page_data:
        payload["pagination_data"] = page_data
    
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
        data = post_data.get('data', {})
        token = data.get('token')
        title = data.get('title', 'No title')
        image_url = data.get('image_url')
        top_desc = data.get('top_description_text', '')
        middle_desc = data.get('middle_description_text', '')
        red_text = data.get('red_text', '')
        
        post_url = f"https://divar.ir/v/{token}"
        
        message = f"🏠 <b>{title}</b>\n\n"
        if top_desc:
            message += f"💰 {top_desc}\n"
        if middle_desc:
            message += f"💵 {middle_desc}\n"
        if red_text:
            message += f"⚠️ {red_text}\n"
        message += f"\n🔗 <a href='{post_url}'>View Post</a>"
        
        success_count = 0
        for chat_id in chat_ids:
            try:
                if image_url:
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
                await asyncio.sleep(0.5)  # Use asyncio.sleep instead of time.sleep
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
    
    page_count = 1
    while result:
        logger.info(f"Processing page {page_count}")
        
        widgets = result.get('list_widgets', [])
        for widget in widgets:
            if widget.get('widget_type') == 'POST_ROW':
                data = widget.get('data', {})
                token = data.get('token')
                
                if token and token not in sent_posts:
                    new_posts.append(widget)
                    sent_posts.add(token)
        
        pagination = result.get('pagination', {})
        if not pagination.get('has_next_page'):
            break
        
        page_data = pagination.get('data')
        if page_data:
            page_count += 1
            time.sleep(2)
            result = search_divar(page_data)
        else:
            break
    
    new_posts.reverse()
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ Cancel", callback_data='back')]])
        )
        
        new_posts, sent_posts = get_new_posts()
        
        if new_posts:
            await query.edit_message_text(
                f'📬 Found {len(new_posts)} new posts. Sending...',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ Cancel", callback_data='back')]])
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
            
            save_sent_posts(sent_posts)
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
            
            for post in new_posts:
                try:
                    await send_telegram_message(context.bot, post, TELEGRAM_CHAT_IDS)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error sending post in periodic check: {e}")
            
            save_sent_posts(sent_posts)
            logger.info(f"Periodic check completed - {len(new_posts)} posts sent")
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
    import asyncio
    main()