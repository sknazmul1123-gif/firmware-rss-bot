import os
import html
import time
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
    return "Firmware World Telegram Bot is Active!"

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

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
TG_FILE_PATH = "posted_urls.txt"

CHECK_INTERVAL = 7200     # ২ ঘণ্টা পর পর চেক
TG_BATCH_SIZE = 20

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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=15)
        feed = feedparser.parse(response.content)
        return list(reversed(feed.entries))
    except Exception as e:
        print(f"❌ RSS Fetch Error: {e}")
        return []

# ==========================================
# 4. GITHUB DATABASE HANDLER
# ==========================================
def load_github_urls(file_path):
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
        return set()
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
        print(f"📁 GitHub DB আপডেটেড: {len(new_urls)} টি লিঙ্ক সেভ হয়েছে।")
    except Exception as e:
        print(f"❌ GitHub Save Error ({file_path}): {e}")

# ==========================================
# 5. TELEGRAM SYSTEM (সাইলেন্ট নোটিফিকেশন)
# ==========================================
def send_telegram_batch(items):
    bd_tz = pytz.timezone('Asia/Dhaka')
    now_bd = datetime.now(bd_tz)
    formatted_date = now_bd.strftime('%d-%m-%Y')
    formatted_time = now_bd.strftime('%I:%M %p')

    grouped_items = {}
    for item in items:
        brand = detect_brand(item['title'])
        if brand not in grouped_items:
            grouped_items[brand] = []
        grouped_items[brand].append(item)

    message_lines = [
        f"📌 <b>NEW FIRMWARE UPDATE</b>",
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
        "disable_notification": True
    }
    
    try:
        res = requests.post(url, data=payload)
        return res.status_code == 200
    except Exception as e:
        print(f"⚠️ Telegram API Error: {e}")
        return False

# ==========================================
# 6. WORKER LOOP
# ==========================================
def telegram_worker():
    print("🚀 Telegram 2-Hour Silent Digest Engine চালু হয়েছে...")
    
    while True:
        try:
            tg_posted = load_github_urls(TG_FILE_PATH)
            entries = fetch_rss_entries()
            unposted = [e for e in entries if e.link.strip() not in tg_posted]

            if unposted:
                print(f"📦 গত ২ ঘণ্টায় মোট {len(unposted)} টি নতুন ফাইল পাওয়া গেছে।")
                
                for i in range(0, len(unposted), TG_BATCH_SIZE):
                    batch = unposted[i:i + TG_BATCH_SIZE]
                    items = [{"title": e.title, "link": e.link.strip()} for e in batch]
                    
                    if send_telegram_batch(items):
                        batch_urls = [it['link'] for it in items]
                        for u in batch_urls:
                            tg_posted.add(u)
                        save_github_urls(TG_FILE_PATH, batch_urls)
                        time.sleep(3)
            else:
                print("🔵 গত ২ ঘণ্টায় কোনো নতুন ফাইল আপলোড হয়নি।")
        except Exception as e:
            print(f"⚠️ TG Worker Exception: {e}")
            
        print(f"⏳ পরবর্তী আপডেটের জন্য ২ ঘণ্টা অপেক্ষা করা হচ্ছে...")
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 7. START ENGINE & WEB SERVER
# ==========================================
if __name__ == "__main__":
    t1 = threading.Thread(target=telegram_worker, daemon=True)
    t1.start()

    run_web_server()
