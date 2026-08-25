import os
import re
import html
import time
import random
import threading
from datetime import datetime
from bs4 import BeautifulSoup
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
    return "Telegram-to-FB Scraper & RSS Bot is active!"

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
TG_FILE_PATH = "posted_urls.txt"       # টেলিগ্রাম ট্র্যাকার ফাইল
FB_FILE_PATH = "fb_posted_urls.txt"    # ফেসবুক ট্র্যাকার ফাইল

CHECK_INTERVAL = 900      # প্রতি ১৫ মিনিট পর পর RSS ও ব্যাকলগ চেক
BATCH_SIZE = 20           # টেলিগ্রামের জন্য ব্যাচ সাইজ
SOUND_INTERVAL = 7200     # ২ ঘণ্টা সাউন্ড ইন্টারভাল

last_sound_time = 0

BRANDS = [
    "SAMSUNG", "XIAOMI", "REDMI", "POCO", "REALME", "OPPO", "VIVO", 
    "TECNO", "INFINIX", "ITEL", "ONEPLUS", "NOTHING", "HONOR", "HUAWEI",
    "NOKIA", "MOTOROLA", "LAVA", "SYMPHONY", "WALTON", "ASUS", "GOOGLE", "IQOO"
]

# ==========================================
# 3. HELPER FUNCTIONS: BRAND IDENTIFICATION
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
# 4. TELEGRAM CHANNEL SCRAPER (পুরনো ফাইল স্ক্র্যাপিং)
# ==========================================
def scrape_telegram_channel_history():
    """টেলিগ্রাম চ্যানেল থেকে পুরনো পোস্ট করা ফাইল ও লিঙ্ক স্ক্র্যাপ করে আনা"""
    clean_channel = TELEGRAM_CHAT_ID.replace("@", "").replace("-100", "").strip() if TELEGRAM_CHAT_ID else ""
    if not clean_channel or clean_channel.isdigit():
        # যদি চ্যানেল ইউজারনেম না হয়ে আইডি হয়, তবে ডিফল্ট ফার্মওয়্যার চ্যানেল
        channel_url = "https://t.me/s/firmwareworld"
    else:
        channel_url = f"https://t.me/s/{clean_channel}"

    scraped_files = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(channel_url, headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message_text')
            
            for msg in messages:
                text = msg.get_text("\n")
                # প্রতিটি ফাইলের টাইটেল এবং ডাউনলোড লিংক আলাদা করা
                links = msg.find_all('a', href=True)
                download_links = [a['href'] for a in links if 'firmwareworld.com' in a['href'] or 'download' in a['href'].lower()]
                
                # ব্লকের ভেতর থেকে ফাইলের নাম বের করা
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                for i, line in enumerate(lines):
                    if "➡️" in line or "NEW FILE" in line:
                        title_line = line.replace("➡️", "").replace("🔥", "").replace("NEW FILE", "").strip()
                        if not title_line and (i + 1) < len(lines):
                            title_line = lines[i + 1].strip()
                        
                        # লিঙ্ক ম্যাচিং
                        if title_line and download_links:
                            for d_link in download_links:
                                scraped_files.append({
                                    "title": title_line,
                                    "link": d_link
                                })
                                break
        print(f"🔍 টেলিগ্রাম চ্যানেল থেকে {len(scraped_files)} টি ফাইল স্ক্র্যাপ করা হয়েছে।")
    except Exception as e:
        print(f"⚠️ Telegram Scraping Error: {e}")
        
    return scraped_files

# ==========================================
# 5. FACEBOOK POST & 1ST COMMENT ENGINE
# ==========================================
def post_to_facebook_single(title, link, brand):
    """ফেসবুকে পোস্ট ও ফার্স্ট কমেন্টে ডাউনলোড লিঙ্ক"""
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ Facebook credentials পাওয়া যায়নি!")
        return False
    
    try:
        clean_brand = brand.replace(" / ", "_").replace(" ", "")
        
        post_message = (
            f"💎 {title}\n\n"
            f"➔ {title}\n\n"
            f"#{clean_brand} #FirmwareWorld #StockROM #FlashFile"
        )

        # ১. মূল পোস্ট পাবলিশ
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

        # ২. ১ম কমেন্টে ডাউনলোড লিঙ্ক ড্রপ
        comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
        comment_payload = {
            'message': f"📥 Download Link:\n🔗 {link}\n\n🌐 Website: https://firmwareworld.com",
            'access_token': FB_ACCESS_TOKEN
        }
        requests.post(comment_url, data=comment_payload)
        print(f"✅ Facebook-এ সফলভাবে পোস্ট ও ফার্স্ট কমেন্ট হয়েছে: {title}")
        return True

    except Exception as e:
        print(f"⚠️ Facebook API Error: {e}")
        return False

# ==========================================
# 6. GITHUB DATABASE FUNCTIONS
# ==========================================
def load_github_urls(file_path):
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

def save_github_single_url(file_path, new_url):
    if not GITHUB_TOKEN or not new_url:
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(file_path)
            existing_content = contents.decoded_content.decode('utf-8')
            updated = (existing_content + f"\n{new_url}") if existing_content.endswith('\n') == False else (existing_content + f"{new_url}")
            repo.update_file(path=file_path, message="Bot: Add URL", content=updated, sha=contents.sha)
        except Exception:
            repo.create_file(path=file_path, message="Bot: Create file", content=new_url)
    except Exception as e:
        print(f"❌ GitHub Save Error ({file_path}): {e}")

def save_github_batch_urls(file_path, new_urls):
    if not GITHUB_TOKEN or not new_urls:
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        urls_to_add = "\n".join(new_urls)
        try:
            contents = repo.get_contents(file_path)
            existing_content = contents.decoded_content.decode('utf-8')
            updated = (existing_content + f"\n{urls_to_add}") if existing_content.endswith('\n') == False else (existing_content + f"{urls_to_add}")
            repo.update_file(path=file_path, message=f"Bot: Add {len(new_urls)} URLs", content=updated, sha=contents.sha)
        except Exception:
            repo.create_file(path=file_path, message="Bot: Create file", content=urls_to_add)
    except Exception as e:
        print(f"❌ GitHub Batch Save Error ({file_path}): {e}")

# ==========================================
# 7. TELEGRAM BATCH NOTIFICATION
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
    except Exception:
        return False

# ==========================================
# 8. MAIN RSS & BACKLOG LOOP
# ==========================================
def run_rss_bot():
    print("🚀 Auto Scraper & RSS Bot চালু হচ্ছে...")
    tg_posted = load_github_urls(TG_FILE_PATH)
    fb_posted = load_github_urls(FB_FILE_PATH)

    while True:
        try:
            # ধাপ ১: RSS চেক করা
            feed = feedparser.parse(RSS_FEED_URL)
            all_entries = list(reversed(feed.entries))

            tg_unposted = [e for e in all_entries if e.link.strip() not in tg_posted]
            
            if tg_unposted:
                # নতুন ফাইল পাওয়া গেলে টেলিগ্রামে পোস্ট
                print(f"📦 নতুন RSS ফাইল পাওয়া গেছে: {len(tg_unposted)} টি")
                for i in range(0, len(tg_unposted), BATCH_SIZE):
                    batch_entries = tg_unposted[i:i + BATCH_SIZE]
                    batch_items = [{"title": e.title, "link": e.link.strip()} for e in batch_entries]
                    
                    if send_telegram_batch(batch_items):
                        batch_urls = [it['link'] for it in batch_items]
                        for u in batch_urls:
                            tg_posted.add(u)
                        save_github_batch_urls(TG_FILE_PATH, batch_urls)

            # ধাপ ২: ফেসবুকে বাকি থাকা ফাইলের ব্যাকলগ চেক
            # (ক) RSS থেকে যেগুলা ফেসবুকে যায় নাই
            fb_unposted_rss = [e for e in all_entries if e.link.strip() not in fb_posted]
            
            # (খ) যদি RSS-এ নতুন কিছু না থাকে, তবে টেলিগ্রাম চ্যানেল থেকে পুরনো ফাইল স্ক্র্যাপ করবে
            unposted_pool = []
            for e in fb_unposted_rss:
                unposted_pool.append({"title": e.title, "link": e.link.strip()})
            
            if not unposted_pool:
                print("🔄 RSS-এ নতুন কোনো ফাইল নেই। টেলিগ্রাম চ্যানেল স্ক্র্যাপ করা হচ্ছে...")
                scraped_files = scrape_telegram_channel_history()
                unposted_pool = [item for item in scraped_files if item['link'] not in fb_posted]

            # ফেসবুকে একটা একটা করে পোস্ট ও ফার্স্ট কমেন্ট
            if unposted_pool:
                print(f"📲 ফেসবুকে বাকি থাকা পোস্টের সংখ্যা: {len(unposted_pool)} টি")
                
                # প্রতি চক্করে ১ থেকে ৩টি ফাইল পোস্ট হবে (পেজের সেফটির জন্য)
                for item in unposted_pool[:3]:
                    brand = detect_brand(item['title'])
                    if post_to_facebook_single(item['title'], item['link'], brand):
                        fb_posted.add(item['link'])
                        save_github_single_url(FB_FILE_PATH, item['link'])
                        
                        # ফেসবুক সেফটি ডিলে (২ থেকে ৩ মিনিট বিরতি)
                        delay = random.randint(120, 180)
                        print(f"⏳ পরবর্তী ফেসবুক পোস্টের জন্য {delay} সেকেন্ড বিরতি...")
                        time.sleep(delay)

        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 9. START THREADS & WEB SERVER
# ==========================================
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_rss_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    run_web_server()
