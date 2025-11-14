import os
import json
import time
import requests
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# تنظیمات logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# تنظیمات از environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')  # لیست آیدی‌ها با کاما
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 900))
DIVAR_API_URL = "https://api.divar.ir/v8/web-search/5/residential-rent"

# فایل برای ذخیره آگهی‌های ارسال شده
SENT_POSTS_FILE = '/data/sent_posts.json'

def load_sent_posts():
    """بارگذاری لیست توکن‌های آگهی‌های ارسال شده"""
    try:
        if os.path.exists(SENT_POSTS_FILE):
            with open(SENT_POSTS_FILE, 'r') as f:
                return set(json.load(f))
        return set()
    except Exception as e:
        logger.error(f"خطا در بارگذاری فایل: {e}")
        return set()

def save_sent_posts(sent_posts):
    """ذخیره لیست توکن‌های آگهی‌های ارسال شده"""
    try:
        os.makedirs(os.path.dirname(SENT_POSTS_FILE), exist_ok=True)
        with open(SENT_POSTS_FILE, 'w') as f:
            json.dump(list(sent_posts), f)
    except Exception as e:
        logger.error(f"خطا در ذخیره فایل: {e}")

def search_divar(page_data=None):
    """جستجوی آگهی‌ها در دیوار"""
    if page_data is None:
        payload = {
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
    else:
        payload = {
            "city_ids": ["5"],
            "source_view": "FILTER",
            "pagination_data": page_data,
            "disable_recommendation": False,
            "map_state": {"camera_info": {"bbox": {}}},
            "search_data": {
                "form_data": {
                    "data": {
                        "category": {"str": {"value": "residential-rent"}},
                        "credit": {"number_range": {"maximum": "200000000"}},
                        "rent": {"number_range": {"maximum": "13000000"}},
                        "bbox": {
                            "repeated_float": {
                                "value": [
                                    {"value": 45.8892288},
                                    {"value": 37.7328644},
                                    {"value": 46.4927254},
                                    {"value": 38.4841843}
                                ]
                            }
                        }
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
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.post(DIVAR_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"خطا در دریافت داده از دیوار: {e}")
        return None

async def send_to_telegram_users(bot, post_data, chat_ids):
    """ارسال آگهی به لیست کاربران"""
    try:
        data = post_data.get('data', {})
        token = data.get('token')
        title = data.get('title', 'بدون عنوان')
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
        message += f"\n🔗 <a href='{post_url}'>مشاهده آگهی</a>"
        
        logger.info(f"📢 ارسال آگهی: {title} (Token: {token})")
        
        for chat_id in chat_ids:
            try:
                if image_url:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"✅ تصویر ارسال شد به {chat_id}")
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"✅ پیام متنی ارسال شد به {chat_id}")
                time.sleep(0.5)  # تاخیر بین ارسال به کاربران مختلف
            except Exception as e:
                logger.error(f"❌ خطا در ارسال به {chat_id}: {e}")
        
        return True
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به تلگرام: {e}")
        return False

def get_new_posts():
    """دریافت آگهی‌های جدید"""
    sent_posts = load_sent_posts()
    new_posts = []
    
    result = search_divar()
    if not result:
        return new_posts, sent_posts
    
    page_count = 1
    while result:
        logger.info(f"پردازش صفحه {page_count}")
        
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
    
    new_posts.reverse()  # از قدیمی به جدید
    return new_posts, sent_posts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    chat_id = update.effective_chat.id
    
    logger.info(f"👤 کاربر جدید: {user_name} (ID: {user_id}) - Chat ID: {chat_id}")
    
    # نمایش فیلترهای فعلی
    filter_info = (
        "📍 <b>محدوده جغرافیایی:</b>\n"
        "• شهر: تهران\n"
        "• طول جغرافیایی: 45.88° تا 46.49°\n"
        "• عرض جغرافیایی: 37.73° تا 38.48°\n\n"
        
        "💰 <b>فیلترهای قیمت:</b>\n"
        "• حداکثر قیمت رهن: 200,000,000 تومان\n"
        "• حداکثر اجاره: 13,000,000 تومان\n\n"
        
        "📋 <b>سایر تنظیمات:</b>\n"
        "• نوع: آگهی‌های برای اجاره\n"
        "• مرتب‌سازی: بر اساس تاریخ (جدیدترین)\n"
        "• بررسی خودکار هر {CHECK_INTERVAL} ثانیه\n\n"
        
        "دکمه زیر را برای جستجوی آگهی‌های جدید بزنید:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 آگهی‌های جدید", callback_data='check_new')],
        [InlineKeyboardButton("ℹ️ اطلاعات", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f'🏠 <b>ربات اعلان آگهی‌های دیوار</b>\n\n'
        f'👋 خوش‌آمدید {user_name}!\n\n' +
        filter_info,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌ها"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"🔘 دکمه {query.data} فشار داده شد توسط {user_id}")
    await query.answer()
    
    if query.data == 'check_new':
        logger.info(f"📍 شروع بررسی آگهی‌های جدید برای کاربر {user_id}")
        await query.edit_message_text('🔄 در حال بررسی آگهی‌های جدید...')
        
        new_posts, sent_posts = get_new_posts()
        logger.info(f"📊 تعداد آگهی‌های جدید: {len(new_posts)}")
        
        if new_posts:
            await query.edit_message_text(f'📬 {len(new_posts)} آگهی جدید پیدا شد. در حال ارسال...')
            logger.info(f"📤 ارسال {len(new_posts)} آگهی به کاربران...")
            
            sent_count = 0
            for post in new_posts:
                try:
                    await send_to_telegram_users(context.bot, post, TELEGRAM_CHAT_IDS)
                    sent_count += 1
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ خطا در ارسال آگهی: {e}")
            
            save_sent_posts(sent_posts)
            logger.info(f"✅ {sent_count} آگهی با موفقیت ارسال شد")
            
            keyboard = [[InlineKeyboardButton("🔍 آگهی‌های جدید", callback_data='check_new')]]
            await query.message.reply_text(
                f'✅ {sent_count} آگهی ارسال شد.',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            logger.info(f"ℹ️ آگهی جدیدی برای کاربر {user_id} یافت نشد")
            keyboard = [[InlineKeyboardButton("🔍 آگهی‌های جدید", callback_data='check_new')]]
            await query.edit_message_text(
                '✅ آگهی جدیدی یافت نشد.',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    elif query.data == 'info':
        logger.info(f"ℹ️ کاربر {user_id} درخواست اطلاعات کرد")
        info_text = (
            "📍 <b>محدوده جغرافیایی:</b>\n"
            "• شهر: تهران\n"
            "• طول جغرافیایی: 45.88° تا 46.49°\n"
            "• عرض جغرافیایی: 37.73° تا 38.48°\n\n"
            
            "💰 <b>فیلترهای قیمت:</b>\n"
            "• حداکثر قیمت رهن: 200,000,000 تومان\n"
            "• حداکثر اجاره: 13,000,000 تومان\n\n"
            
            "📋 <b>سایر تنظیمات:</b>\n"
            "• نوع: آگهی‌های برای اجاره\n"
            "• مرتب‌سازی: بر اساس تاریخ (جدیدترین)\n"
            f"• بررسی خودکار هر {CHECK_INTERVAL} ثانیه\n"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='back')]]
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    elif query.data == 'back':
        logger.info(f"🔙 کاربر {user_id} به منو اصلی بازگشت")
        keyboard = [
            [InlineKeyboardButton("🔍 آگهی‌های جدید", callback_data='check_new')],
            [InlineKeyboardButton("ℹ️ اطلاعات", callback_data='info')]
        ]
        await query.edit_message_text(
            '🏠 <b>ربات اعلان آگهی‌های دیوار</b>\n\n'
            'منوی اصلی:',
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    """بررسی دوره‌ای آگهی‌ها"""
    logger.info("🕐 شروع بررسی دوره‌ای آگهی‌ها...")
    
    try:
        new_posts, sent_posts = get_new_posts()
        
        if new_posts:
            logger.info(f"🎉 {len(new_posts)} آگهی جدید یافت شد")
            
            for post in new_posts:
                try:
                    await send_to_telegram_users(context.bot, post, TELEGRAM_CHAT_IDS)
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ خطا در ارسال آگهی در بررسی دوره‌ای: {e}")
            
            save_sent_posts(sent_posts)
            logger.info(f"✅ بررسی دوره‌ای انجام شد - {len(new_posts)} آگهی ارسال شد")
        else:
            logger.info("ℹ️ بررسی دوره‌ای انجام شد - آگهی جدیدی یافت نشد")
    except Exception as e:
        logger.error(f"❌ خطا در بررسی دوره‌ای: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج خطاها"""
    logger.error(f"❌ خطا: {context.error}")

def main():
    """تابع اصلی"""
    global TELEGRAM_CHAT_IDS
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN باید تنظیم شود")
        return
    
    if not TELEGRAM_CHAT_IDS or TELEGRAM_CHAT_IDS == ['']:
        logger.error("❌ TELEGRAM_CHAT_IDS باید تنظیم شود")
        return
    
    # پاک کردن فضاهای خالی از لیست
    TELEGRAM_CHAT_IDS = [cid.strip() for cid in TELEGRAM_CHAT_IDS if cid.strip()]
    
    logger.info(f"════════════════════════════════════════")
    logger.info(f"🤖 ربات دیوار شروع به کار می‌کند")
    logger.info(f"════════════════════════════════════════")
    logger.info(f"📍 محدوده جغرافیایی: 45.88° تا 46.49° (طول)")
    logger.info(f"📍 محدوده جغرافیایی: 37.73° تا 38.48° (عرض)")
    logger.info(f"💰 حداکثر قیمت رهن: 200,000,000 تومان")
    logger.info(f"💰 حداکثر اجاره: 13,000,000 تومان")
    logger.info(f"👥 تعداد کاربران: {len(TELEGRAM_CHAT_IDS)}")
    logger.info(f"🕐 بررسی خودکار هر {CHECK_INTERVAL} ثانیه")
    logger.info(f"════════════════════════════════════════")
    
    # ساخت application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # اضافه کردن handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # تنظیم job برای بررسی دوره‌ای
    job_queue = application.job_queue
    job = job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL, first=10)
    logger.info(f"✅ کار دوره‌ای ثبت شد: هر {CHECK_INTERVAL} ثانیه اجرا شود")
    
    # معالج برای خروج صحیح
    def signal_handler(sig, frame):
        logger.info("🛑 دریافت سیگنال خروج...")
        application.stop()
    
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # اجرای بات
    try:
        logger.info("🚀 بات در حال فعالیت است...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("⏹️  بات متوقف شد (Keyboard Interrupt)")
    except Exception as e:
        logger.error(f"❌ خطا در اجرای بات: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    main()
