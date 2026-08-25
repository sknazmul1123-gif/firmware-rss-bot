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
from github import Github, Auth

# ==========================================
# 1. RENDER WEB SERVICE PORT CONFIG
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "Firmware World Bot is Active!"

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

FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
TG_FILE_PATH = "posted_urls.txt"
FB_FILE_PATH = "fb_posted_urls.txt"

CHECK_INTERVAL = 300      # প্রতি ৫ মিনিট পর পর RSS স্ক্যান
TG_BATCH_SIZE = 20
SOUND_INTERVAL = 7200

last_sound_time = 0
db_lock = threading.Lock() # থ্রেড যেন একসাথে ফাইল ওভাররাইট না করে

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

def fetch_rss_entries():
    """ইউজার-এজেন্ট হেডার দিয়ে আরএসএস নিশ্চিতভাবে ফেচ করা"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=15)
        feed = feedparser.parse(response.content)
        entries = list(reversed(feed.entries))
        return entries
    except Exception as e:
        print(f"❌ RSS Fetch Error: {e}")
        return []

# ==========================================
# 4. GITHUB DATABASE HANDLER (THREAD-SAFE)
# ==========================================
def load_github_urls(file_path):
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
        return set()
    with db_lock:
        try:
            auth = Auth.Token(GITHUB_TOKEN)
            g = Github(auth=auth)
            repo = g.get_repo(REPO_NAME)
            contents = repo.get_contents(file_path)
            urls = contents.decoded_content.decode('utf-8').splitlines()
            return set(line.strip() for line in urls if line.strip())
        except Exception:
            return set()

def save_github_urls(file_path, new_urls):
    if not GITHUB_TOKEN or not new_urls:
        return
    with db_lock:
        try:
            auth = Auth.Token(GITHUB_TOKEN)
            g = Github(auth=auth)
            repo = g.get_repo(REPO_NAME)
            urls_to_add = "\n".join(new_urls)
            try:
                contents = repo.get_contents(file_path)
                existing = contents.decoded_content.decode('utf-8')
                updated = (existing + f"\n{urls_to_add}") if not existing.endswith('\n') else (existing + f"{urls_to_add}")
                repo.update_file(path=file_path, message=f"Update {file_path}", content=updated, sha=contents.sha)
            except Exception:
                repo.create_file(path=file_path, message=f"Create {file_path}", content=urls_to_add)
            print(f"📁 GitHub DB আপডেটেড: {file_path}")
        except Exception as e:
            print(f"❌ GitHub Save Error ({file_path}): {e}")

# ==========================================
# 5. TELEGRAM SYSTEM
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
        else:
            print(f"❌ Telegram Send Error Response: {res.text}")
            return False
    except Exception as e:
        print(f"⚠️ Telegram API Error: {e}")
        return False

# ==========================================
# 6. FACEBOOK SYSTEM
# ==========================================
def post_to_facebook_single(title, link, brand):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("❌ FB Credentials (FB_PAGE_ID / FB_ACCESS_TOKEN) পাওয়া যায়নি!")
        return False
    
    try:
        clean_brand = brand.replace(" / ", "_").replace(" ", "")
        post_message = f"💎 {title}\n\n➔ {title}\n\n#{clean_brand} #FirmwareWorld #StockROM #FlashFile"

        # ১. মূল পোস্ট পাবলিশ
        feed_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        feed_payload = {'message': post_message, 'access_token': FB_ACCESS_TOKEN}
        res = requests.post(feed_url, data=feed_payload).json()
        post_id = res.get('id')

        if not post_id:
            print(f"❌ Facebook API Error Response: {res}")
            return False

        # ২. ১ম কমেন্টে ডাউনলোড লিংক ড্রপ
        comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
        comment_payload = {
            'message': f"📥 Download Link:\n🔗 {link}\n\n🌐 Website: https://firmwareworld.com",
            'access_token': FB_ACCESS_TOKEN
        }
        requests.post(comment_url, data=comment_payload)
        print(f"✅ Facebook Post Success: {title}")
        return True
    except Exception as e:
        print(f"⚠️ Facebook Exception: {e}")
        return False

# ==========================================
# 7. PARALLEL WORKERS
# ==========================================
def telegram_worker():
    print("🔵 Telegram Worker Active.")
    while True:
        try:
            tg_posted = load_github_urls(TG_FILE_PATH)
            entries = fetch_rss_entries()
            unposted = [e for e in entries if e.link.strip() not in tg_posted]

            if unposted:
                print(f"📦 TG: {len(unposted)} টি নতুন ফাইল পাওয়া গেছে।")
                for i in range(0, len(unposted), TG_BATCH_SIZE):
                    batch = unposted[i:i + TG_BATCH_SIZE]
                    items = [{"title": e.title, "link": e.link.strip()} for e in batch]
                    if send_telegram_batch(items):
                        batch_urls = [it['link'] for it in items]
                        save_github_urls(TG_FILE_PATH, batch_urls)
                        print(f"✅ TG: {len(batch_urls)} টি লিঙ্ক সেভ হয়েছে।")
            else:
                print("🔵 TG: কোনো নতুন ফাইল নেই।")
        except Exception as e:
            print(f"⚠️ TG Worker Exception: {e}")
            
        time.sleep(CHECK_INTERVAL)

def facebook_worker():
    print("🔵 Facebook Worker Active.")
    while True:
        try:
            fb_posted = load_github_urls(FB_FILE_PATH)
            entries = fetch_rss_entries()
            print(f"🔍 FB Scan: মোট {len(entries)} টি আরএসএস ফাইল পাওয়া গেছে।")
            
            unposted = [e for e in entries if e.link.strip() not in fb_posted]

            if unposted:
                print(f"📲 FB: {len(unposted)} টি ফাইল ফেসবুকে ছাড়া বাকি আছে...")
                for entry in unposted:
                    title = entry.title
                    link = entry.link.strip()
                    brand = detect_brand(title)

                    if post_to_facebook_single(title, link, brand):
                        save_github_urls(FB_FILE_PATH, [link])
                        fb_posted.add(link)

                        delay = random.randint(45, 90)
                        print(f"⏳ FB সেফটি বিরতি: {delay} সেকেন্ড অপেক্ষা...")
                        time.sleep(delay)
            else:
                print("✨ FB: সব আরএসএস ফাইল অলরেডি ফেসবুকে পোস্ট করা আছে।")
        except Exception as e:
            print(f"⚠️ FB Worker Exception: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 8. START THREADS & WEB SERVER
# ==========================================
if __name__ == "__main__":
    t1 = threading.Thread(target=telegram_worker, daemon=True)
    t1.start()

    t2 = threading.Thread(target=facebook_worker, daemon=True)
    t2.start()

    run_web_server()
