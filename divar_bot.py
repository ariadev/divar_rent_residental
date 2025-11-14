import os
import json
import time
import requests
from datetime import datetime
import logging

# تنظیمات logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# تنظیمات از environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# Optional comma-separated list of chat ids. If set, this takes precedence over TELEGRAM_CHAT_ID.
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS')

# Normalize chat ids into a list used by send_to_telegram. Keep as strings (Telegram accepts both).
if TELEGRAM_CHAT_IDS:
    TELEGRAM_CHAT_IDS_LIST = [c.strip() for c in TELEGRAM_CHAT_IDS.split(',') if c.strip()]
elif TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_IDS_LIST = [TELEGRAM_CHAT_ID]
else:
    TELEGRAM_CHAT_IDS_LIST = []
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 900))  # 15 دقیقه (900 ثانیه)
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
        # درخواست اولیه
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
        # درخواست صفحه‌بندی
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

def send_to_telegram(post_data):
    """ارسال آگهی به تلگرام"""
    try:
        data = post_data.get('data', {})
        token = data.get('token')
        title = data.get('title', 'بدون عنوان')
        image_url = data.get('image_url')
        top_desc = data.get('top_description_text', '')
        middle_desc = data.get('middle_description_text', '')
        red_text = data.get('red_text', '')
        
        # ساخت لینک آگهی
        post_url = f"https://divar.ir/v/{token}"
        
        # ساخت متن پیام
        message = f"🏠 <b>{title}</b>\n\n"
        if top_desc:
            message += f"💰 {top_desc}\n"
        if middle_desc:
            message += f"💵 {middle_desc}\n"
        if red_text:
            message += f"⚠️ {red_text}\n"
        message += f"\n🔗 <a href='{post_url}'>مشاهده آگهی</a>"
        
        # ارسال به همه chat idهای تنظیم شده
        if image_url:
            base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        else:
            base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        success = True
        for chat in TELEGRAM_CHAT_IDS_LIST:
            try:
                if image_url:
                    payload = {
                        'chat_id': chat,
                        'photo': image_url,
                        'caption': message,
                        'parse_mode': 'HTML'
                    }
                else:
                    payload = {
                        'chat_id': chat,
                        'text': message,
                        'parse_mode': 'HTML'
                    }

                response = requests.post(base_url, json=payload, timeout=30)
                response.raise_for_status()
            except Exception as e:
                logger.error(f"خطا در ارسال به تلگرام برای chat_id={chat}: {e}")
                success = False
        return success
    except Exception as e:
        logger.error(f"خطا در ارسال به تلگرام: {e}")
        return False

def process_posts():
    """پردازش و ارسال آگهی‌های جدید"""
    sent_posts = load_sent_posts()
    new_posts = []
    
    # دریافت صفحه اول
    result = search_divar()
    if not result:
        logger.warning("خطا در دریافت داده‌ها")
        return
    
    # پردازش تمام صفحات
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
        
        # بررسی وجود صفحه بعدی
        pagination = result.get('pagination', {})
        if not pagination.get('has_next_page'):
            break
        
        # درخواست صفحه بعدی
        page_data = pagination.get('data')
        if page_data:
            page_count += 1
            time.sleep(2)  # تاخیر بین درخواست‌ها
            result = search_divar(page_data)
        else:
            break
    
    # ارسال آگهی‌های جدید (از قدیمی به جدید)
    logger.info(f"تعداد آگهی‌های جدید: {len(new_posts)}")
    new_posts.reverse()
    
    for post in new_posts:
        if send_to_telegram(post):
            logger.info(f"آگهی ارسال شد: {post['data'].get('token')}")
            time.sleep(1)  # تاخیر بین پیام‌ها
    
    # ذخیره لیست آگهی‌های ارسال شده
    save_sent_posts(sent_posts)

def main():
    """تابع اصلی"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS_LIST:
        logger.error("TELEGRAM_BOT_TOKEN و حداقل یک TELEGRAM_CHAT_ID یا TELEGRAM_CHAT_IDS باید تنظیم شوند")
        return
    
    logger.info("بات شروع به کار کرد")
    logger.info(f"بررسی هر {CHECK_INTERVAL} ثانیه")
    
    while True:
        try:
            logger.info("شروع بررسی آگهی‌های جدید...")
            process_posts()
            logger.info(f"پایان بررسی. منتظر {CHECK_INTERVAL} ثانیه...")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("بات متوقف شد")
            break
        except Exception as e:
            logger.error(f"خطای غیرمنتظره: {e}")
            time.sleep(60)

if __name__ == '__main__':
    main()
