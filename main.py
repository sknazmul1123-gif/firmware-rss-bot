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
    return "Bot is active!"

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
TG_FILE_PATH = "posted_urls.txt"       # আপনার আগের টেলিগ্রাম ট্র্যাকার ফাইল
FB_FILE_PATH = "fb_posted_urls.txt"    # শুধু ফেসবুকের জন্য আলাদা ট্র্যাকার ফাইল

CHECK_INTERVAL = 900      # প্রতি ১৫ মিনিট পর পর RSS চেক করবে
BATCH_SIZE = 20           # টেলিগ্রামের ব্যাচ সাইজ
SOUND_INTERVAL = 7200     # ২ ঘণ্টা সাউন্ড গ্যাপিং

last_sound_time = 0

BRANDS = [
    "SAMSUNG", "XIAOMI", "REDMI", "POCO", "REALME", "OPPO", "VIVO", 
    "TECNO", "INFINIX", "ITEL", "ONEPLUS", "NOTHING", "HONOR", "HUAWEI",
    "NOKIA", "MOTOROLA", "LAVA", "SYMPHONY", "WALTON", "ASUS", "GOOGLE"
]

# ==========================================
# 3. HELPER FUNCTION: BRAND DETECTION & RSS
# ==========================================
def detect_brand(title):
    title_upper = title.upper()
    for brand in BRANDS:
        if brand in title_upper:
            if brand in ["REDMI", "POCO"]:
                return "XIAOMI / REDMI / POCO"
            return brand
    return "OTHER FIRMWARE"

def fetch_rss_entries():
    """ইউজার-এজেন্ট হেডার দিয়ে আরএসএস নিশ্চিতভাবে ফেচ করা"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=15)
        feed = feedparser.parse(response.content)
        return list(reversed(feed.entries))
    except Exception as e:
        print(f"⚠️ RSS Fetch Error: {e}")
        return []

# ==========================================
# 4. GITHUB DATABASE FUNCTIONS (TG + FB)
# ==========================================
def load_github_urls(file_path):
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
        return set()
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(file_path)
        urls = contents.decoded_content.decode('utf-8').splitlines()
        return set(line.strip() for line in urls if line.strip())
    except Exception:
        return set()

def save_github_urls(file_path, new_urls):
    if not GITHUB_TOKEN or not new_urls:
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        urls_to_add = "\n".join(new_urls)
        try:
            contents = repo.get_contents(file_path)
            existing_content = contents.decoded_content.decode('utf-8')
            updated_content = (existing_content + f"\n{urls_to_add}") if not existing_content.endswith('\n') else (existing_content + f"{urls_to_add}")
            repo.update_file(
                path=file_path,
                message=f"Bot: Add {len(new_urls)} URLs to {file_path}",
                content=updated_content,
                sha=contents.sha
            )
        except Exception:
            repo.create_file(path=file_path, message=f"Bot: Create {file_path}", content=urls_to_add)
        print(f"✅ GitHub-এ {file_path}-এ সফলভাবে সেভ হয়েছে!")
    except Exception as e:
        print(f"❌ GitHub Save Error ({file_path}): {e}")

# ==========================================
# 5. TELEGRAM BATCH NOTIFICATION (অপরিবর্তিত)
# ==========================================
def send_telegram_batch(items):
    global last_sound_time
    
    bd_tz = pytz.timezone('Asia/Dhaka')
    now_bd = datetime.now(bd_tz)
    formatted_date = now_bd.strftime('%d-%m-%Y')
    formatted_time = now_bd.strftime('%I:%M %p')
    
    current_timestamp = time.time()
    
    if (current_timestamp - last_sound_time) >= SOUND_INTERVAL:
        disable_sound = False
        print("🔔 ২ ঘণ্টার পর পোস্ট বা ১ম পোস্ট -> নোটিফিকেশন সাউন্ড অন!")
    else:
        disable_sound = True
        remaining_time = int((SOUND_INTERVAL - (current_timestamp - last_sound_time)) / 60)
        print(f"🔕 ২ ঘণ্টার বেশি হয়নি (বাকি {remaining_time} মিনিট) -> সাইলেন্ট পাঠানো হচ্ছে।")

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
            
            file_entry = (
                f"🔥 NEW FILE 🔥\n"
                f"➡️ <b>{clean_title}</b>\n"
                f"🔗 Link: <a href=\"{clean_link}\">Download</a>\n"
            )
            quote_lines.append(file_entry)
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
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            if not disable_sound:
                last_sound_time = current_timestamp
            return True
        else:
            print(f"⚠️ Telegram API Error: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Telegram Send Error: {e}")
        return False

# ==========================================
# 6. FACEBOOK ENGINE (SINGLE POST + 1ST COMMENT)
# ==========================================
def post_to_facebook_single(title, link, brand):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ Facebook credentials পাওয়া যায়নি!")
        return False
    
    try:
        clean_brand = brand.replace(" / ", "_").replace(" ", "")
        
        # আপনার ক্লিন সিঙ্গেল পোস্ট ফরম্যাট
        post_message = (
            f"💎 {title}\n\n"
            f"➔ {title}\n\n"
            f"#{clean_brand} #FirmwareWorld #StockROM #FlashFile"
        )

        # ১. মূল পোস্ট পাবলিশ
        feed_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        feed_payload = {'message': post_message, 'access_token': FB_ACCESS_TOKEN}
        res = requests.post(feed_url, data=feed_payload).json()
        post_id = res.get('id')

        if not post_id:
            print(f"❌ Facebook Post Failed: {res}")
            return False

        # ২. ১ম কমেন্টে ডাউনলোড লিংক প্রদান
        comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
        comment_payload = {
            'message': f"📥 Download Link:\n🔗 {link}\n\n🌐 Website: https://firmwareworld.com",
            'access_token': FB_ACCESS_TOKEN
        }
        requests.post(comment_url, data=comment_payload)
        print(f"✅ Facebook: সিঙ্গেল পোস্ট ও ১ম কমেন্টে লিংক সফল -> {title}")
        return True
    except Exception as e:
        print(f"⚠️ Facebook API Error: {e}")
        return False

# ==========================================
# 7. PARALLEL BACKGROUND WORKERS
# ==========================================
def telegram_worker():
    """টেলিগ্রামের নিজস্ব ব্যাকগ্রাউন্ড লুপ (posted_urls.txt ব্যবহার করে)"""
    print("🚀 Telegram Engine চালু হচ্ছে...")
    posted_urls = load_github_urls(TG_FILE_PATH)

    while True:
        try:
            all_entries = fetch_rss_entries()
            unposted_items = []
            
            for entry in all_entries:
                post_url = entry.link.strip()
                if post_url not in posted_urls:
                    unposted_items.append({"title": entry.title, "link": post_url})

            if unposted_items:
                print(f"📦 Telegram: মোট নতুন ফাইল পাওয়া গেছে: {len(unposted_items)} টি")
                for i in range(0, len(unposted_items), BATCH_SIZE):
                    batch = unposted_items[i:i + BATCH_SIZE]
                    success = send_telegram_batch(batch)
                    
                    if success:
                        batch_urls = [item['link'] for item in batch]
                        for url in batch_urls:
                            posted_urls.add(url)
                        save_github_urls(TG_FILE_PATH, batch_urls)
                        time.sleep(3)
        except Exception as e:
            print(f"⚠️ Telegram Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

def facebook_worker():
    """ফেসবুকের নিজস্ব ব্যাকগ্রাউন্ড লুপ (fb_posted_urls.txt ব্যবহার করে)"""
    print("🚀 Facebook Engine চালু হচ্ছে...")
    fb_posted = load_github_urls(FB_FILE_PATH)

    while True:
        try:
            all_entries = fetch_rss_entries()
            unposted_items = [e for e in all_entries if e.link.strip() not in fb_posted]

            if unposted_items:
                print(f"📲 Facebook: পেন্ডিং পোস্ট রয়েছে: {len(unposted_items)} টি")
                for entry in unposted_items:
                    title = entry.title
                    link = entry.link.strip()
                    brand = detect_brand(title)

                    if post_to_facebook_single(title, link, brand):
                        fb_posted.add(link)
                        save_github_urls(FB_FILE_PATH, [link])

                        # ফেসবুক পেজ সেফটি বিরতি (১ থেকে ২ মিনিট)
                        delay = random.randint(60, 120)
                        print(f"⏳ FB সেফটি ডিলে: {delay} সেকেন্ড অপেক্ষা...")
                        time.sleep(delay)
            else:
                print("✨ Facebook: সব ফাইল অলরেডি ফেসবুকে পোস্ট করা আছে।")
        except Exception as e:
            print(f"⚠️ Facebook Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 8. START THREADS & WEB SERVER
# ==========================================
if __name__ == "__main__":
    tg_thread = threading.Thread(target=telegram_worker, daemon=True)
    tg_thread.start()

    fb_thread = threading.Thread(target=facebook_worker, daemon=True)
    fb_thread.start()
    
    run_web_server()
