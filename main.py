
import os
import html
import time
import random
import threading
from datetime import datetime
import feedparser
import pytz
import requests
from flask import Flask
from github import Github

# ==========================================
# 1. RENDER WEB SERVICE PORT CONFIG
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "Firmware World Bot is active and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 2. CONFIGURATION & CONSTANTS
# ==========================================
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHANNEL_ID")
RSS_FEED_URL = os.environ.get("RSS_URL", "https://firmwareworld.com/rss.xml")

# Facebook Config
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
TG_FILE_PATH = "posted_urls.txt"       # টেলিগ্রামের মূল ফাইল (অপরিবর্তিত)
FB_FILE_PATH = "fb_posted_urls.txt"    # শুধু ফেসবুকের জন্য আলাদা ফাইল

CHECK_INTERVAL = 600      # প্রতি ১০ মিনিট পর পর চেক
TG_BATCH_SIZE = 20        # টেলিগ্রামের ব্যাচ সাইজ
SOUND_INTERVAL = 7200     # টেলিগ্রাম ২ ঘণ্টা সাউন্ড কন্ট্রোল

last_sound_time = 0

BRANDS = [
    "SAMSUNG", "XIAOMI", "REDMI", "POCO", "REALME", "OPPO", "VIVO", 
    "TECNO", "INFINIX", "ITEL", "ONEPLUS", "NOTHING", "HONOR", "HUAWEI",
    "NOKIA", "MOTOROLA", "LAVA", "SYMPHONY", "WALTON", "ASUS", "GOOGLE", "IQOO"
]

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def detect_brand(title):
    title_upper = title.upper()
    for brand in BRANDS:
        if brand in title_upper:
            if brand in ["REDMI", "POCO"]:
                return "XIAOMI / REDMI / POCO"
            return brand
    return "FIRMWARE"

# ==========================================
# 4. GITHUB DATABASE HANDLER
# ==========================================
def load_urls_from_github(file_path):
    if not GITHUB_TOKEN:
        return set()
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(file_path)
        urls = contents.decoded_content.decode('utf-8').splitlines()
        return set(line.strip() for line in urls if line.strip())
    except Exception:
        return set()

def save_urls_to_github(file_path, new_urls):
    if not GITHUB_TOKEN or not new_urls:
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        urls_to_add = "\n".join(new_urls)
        try:
            contents = repo.get_contents(file_path)
            existing_content = contents.decoded_content.decode('utf-8')
            updated = (existing_content + f"\n{urls_to_add}") if not existing_content.endswith('\n') else (existing_content + f"{urls_to_add}")
            repo.update_file(path=file_path, message=f"Bot: Update {file_path}", content=updated, sha=contents.sha)
        except Exception:
            repo.create_file(path=file_path, message=f"Bot: Create {file_path}", content=urls_to_add)
    except Exception as e:
        print(f"❌ GitHub Save Error ({file_path}): {e}")

# ==========================================
# 5. TELEGRAM SYSTEM (আপনার আগের হুবহু অপরিবর্তিত কোড)
# ==========================================
def send_telegram_batch(items):
    global last_sound_time
    
    bd_tz = pytz.timezone('Asia/Dhaka')
    now_bd = datetime.now(bd_tz)
    formatted_date = now_bd.strftime('%d-%m-%Y')
    formatted_time = now_bd.strftime('%I:%M %p')
    
    current_timestamp = time.time()
    disable_sound = (current_timestamp - last_sound_time) < SOUND_INTERVAL

    grouped_items = {}
    for item in items:
        brand = detect_brand(item['title'])
        if brand not in grouped_items:
            grouped_items[brand] = []
        grouped_items[brand].append(item)

    message_lines = [
        f"📌 <b>NEW FILES ADDED</b>",
        f"📅 <b>Date:</b> {formatted_date} | ⏰ <b>Time:</b> {formatted_time}",
        f"🌐 <b>Website:</b> <a href=\"https://firmwareworld.com\">Firmware World</a>\n"
    ]
    
    quote_lines = ["<blockquote>"]
    for brand, brand_items in grouped_items.items():
        quote_lines.append(f"🔹 <b>{brand} FIRMWARE</b>\n")
        for item in brand_items:
            clean_title = html.escape(item['title'])
            clean_link = item['link'].strip()
            quote_lines.append(f"🔥 NEW FILE 🔥\n➡️ <b>{clean_title}</b>\n🔗 Link: <a href=\"{clean_link}\">Download</a>\n")
        quote_lines.append("")
        
    quote_lines.append("</blockquote>")
    
    final_message = "\n".join(message_lines) + "\n".join(quote_lines)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": final_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": disable_sound
    }
    
    try:
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            if not disable_sound:
                last_sound_time = current_timestamp
            return True
        return False
    except Exception as e:
        print(f"⚠️ Telegram Send Error: {e}")
        return False

def telegram_loop():
    """টেলিগ্রামের সম্পূর্ণ আলাদা লুপ (posted_urls.txt ব্যবহার করবে)"""
    print("🚀 Telegram Engine চালু হয়েছে...")
    while True:
        try:
            tg_posted = load_urls_from_github(TG_FILE_PATH)
            feed = feedparser.parse(RSS_FEED_URL)
            all_entries = list(reversed(feed.entries))

            unposted = [e for e in all_entries if e.link.strip() not in tg_posted]
            if unposted:
                print(f"📦 Telegram: {len(unposted)} টি নতুন ফাইল পাওয়া গেছে।")
                for i in range(0, len(unposted), TG_BATCH_SIZE):
                    batch = unposted[i:i + TG_BATCH_SIZE]
                    items = [{"title": e.title, "link": e.link.strip()} for e in batch]
                    
                    if send_telegram_batch(items):
                        batch_urls = [it['link'] for it in items]
                        save_urls_to_github(TG_FILE_PATH, batch_urls)
                        print(f"✅ Telegram: {len(batch_urls)} টি ফাইল পোস্টেড এবং posted_urls.txt-এ সেভ হয়েছে।")
        except Exception as e:
            print(f"⚠️ Telegram Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 6. FACEBOOK SEPARATE SYSTEM (সিঙ্গেল পোস্ট + ১ম কমেন্টে লিংক)
# ==========================================
def post_to_facebook_single(title, link, brand):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ Facebook credentials পাওয়া যায়নি!")
        return False
    
    try:
        clean_brand = brand.replace(" / ", "_").replace(" ", "")
        
        # আপনার স্ক্রিনশটের স্টাইলে মূল পোস্ট
        post_message = (
            f"💎 {title}\n\n"
            f"➔ {title}\n\n"
            f"#{clean_brand} #FirmwareWorld #StockROM #FlashFile"
        )

        # ১. ফেসবুকে মূল পোস্ট
        feed_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        feed_payload = {
            'message': post_message,
            'access_token': FB_ACCESS_TOKEN
        }
        res = requests.post(feed_url, data=feed_payload).json()
        post_id = res.get('id')

        if not post_id:
            print(f"❌ Facebook Post Failed: {res}")
            return False

        # ২. ১ম কমেন্টে ডাউনলোড লিংক ড্রপ করা
        comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
        comment_payload = {
            'message': f"📥 Download Link:\n🔗 {link}\n\n🌐 Website: https://firmwareworld.com",
            'access_token': FB_ACCESS_TOKEN
        }
        requests.post(comment_url, data=comment_payload)
        print(f"✅ Facebook: সিঙ্গেল পোস্ট ও ১ম কমেন্টে লিংক সফল -> {title}")
        return True

    except Exception as e:
        print(f"⚠️ Facebook Post Error: {e}")
        return False

def facebook_loop():
    """ফেসবুকের সম্পূর্ণ আলাদা লুপ (fb_posted_urls.txt ব্যবহার করবে)"""
    print("🚀 Facebook Engine চালু হয়েছে...")
    while True:
        try:
            fb_posted = load_urls_from_github(FB_FILE_PATH)
            feed = feedparser.parse(RSS_FEED_URL)
            all_entries = list(reversed(feed.entries))

            unposted = [e for e in all_entries if e.link.strip() not in fb_posted]
            if unposted:
                print(f"📲 Facebook: {len(unposted)} টি পেন্ডিং পোস্ট রয়েছে।")
                for entry in unposted:
                    title = entry.title
                    link = entry.link.strip()
                    brand = detect_brand(title)

                    if post_to_facebook_single(title, link, brand):
                        save_urls_to_github(FB_FILE_PATH, [link])
                        fb_posted.add(link)

                        # ফেসবুক পেজ সুরক্ষায় ১ থেকে ২ মিনিট বিরতি
                        delay = random.randint(60, 120)
                        print(f"⏳ FB সেফটি বিরতি: {delay} সেকেন্ড অপেক্ষা করা হচ্ছে...")
                        time.sleep(delay)
            else:
                print("✨ Facebook: সব আরএসএস ফাইল অলরেডি ফেসবুক পেজে পোস্ট করা আছে।")

        except Exception as e:
            print(f"⚠️ Facebook Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 7. START PARALLEL THREADS & WEB SERVER
# ==========================================
if __name__ == "__main__":
    # ১. টেলিগ্রামের স্বাধীন থ্রেড চালু
    tg_thread = threading.Thread(target=telegram_loop, daemon=True)
    tg_thread.start()

    # ২. ফেসবুকের স্বাধীন থ্রেড চালু
    fb_thread = threading.Thread(target=facebook_loop, daemon=True)
    fb_thread.start()

    # ৩. Render পোর্ট চালু রাখা
    run_web_server()
