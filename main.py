import os
import html
import time
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

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
FILE_PATH = "posted_urls.txt"

CHECK_INTERVAL = 600      # প্রতি ১০ মিনিট পর পর RSS চেক করবে
BATCH_SIZE = 20           # এক পোস্টে সর্বোচ্চ ২০টি ফাইলের লিস্ট করবে
SOUND_INTERVAL = 7200     # ২ ঘণ্টা (৭২০০ সেকেন্ড) সাউন্ড গ্যাপিং

last_sound_time = 0       # সর্বশেষ কখন সাউন্ড দেওয়া হয়েছিল তা ধরে রাখবে

# জনপ্রিয় মোবাইল ব্র্যান্ডের লিস্ট (স্বয়ংক্রিয় ফিল্টারিংয়ের জন্য)
BRANDS = [
    "SAMSUNG", "XIAOMI", "REDMI", "POCO", "REALME", "OPPO", "VIVO", 
    "TECNO", "INFINIX", "ITEL", "ONEPLUS", "NOTHING", "HONOR", "HUAWEI",
    "NOKIA", "MOTOROLA", "LAVA", "SYMPHONY", "WALTON", "ASUS", "GOOGLE"
]

# ==========================================
# 3. HELPER FUNCTION: BRAND DETECTION
# ==========================================
def detect_brand(title):
    """ফাইলের টাইটেল থেকে মোবাইল ব্র্যান্ড শনাক্ত করবে"""
    title_upper = title.upper()
    for brand in BRANDS:
        if brand in title_upper:
            if brand in ["REDMI", "POCO"]:
                return "XIAOMI / REDMI / POCO"
            return brand
    return "OTHER FIRMWARE"

# ==========================================
# 4. GITHUB DATABASE FUNCTIONS
# ==========================================
def load_posted_urls():
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
        return set()
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(FILE_PATH)
        urls = contents.decoded_content.decode('utf-8').splitlines()
        print(f"✅ GitHub থেকে {len(urls)} টি পোস্ট করা লিংক লোড হয়েছে।")
        return set(line.strip() for line in urls if line.strip())
    except Exception as e:
        print(f"⚠️ GitHub ফাইল পড়ার সময় ভুল হয়েছে: {e}")
        return set()

def save_posted_urls_batch(new_urls):
    if not GITHUB_TOKEN or not new_urls:
        print("❌ GITHUB_TOKEN নেই অথবা নতুন কোনো URL সেভ করার জন্য পাওয়া যায়নি!")
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(FILE_PATH)
        
        existing_content = contents.decoded_content.decode('utf-8')
        urls_to_add = "\n".join(new_urls)
        
        if existing_content and not existing_content.endswith('\n'):
            updated_content = existing_content + f"\n{urls_to_add}"
        else:
            updated_content = existing_content + f"{urls_to_add}"

        repo.update_file(
            path=FILE_PATH,
            message=f"Bot: Add {len(new_urls)} new posted URLs",
            content=updated_content,
            sha=contents.sha
        )
        print(f"✅ GitHub-এ একসাথে {len(new_urls)} টি নতুন লিংক সফলভাবে সেভ হয়েছে!")
    except Exception as e:
        print(f"❌ GitHub-এ লিংক সেভ করতে ব্যর্থ! কারণ: {e}")

# ==========================================
# 5. TELEGRAM BATCH NOTIFICATION (BRAND GROUPED + 2 HOUR SOUND LOGIC)
# ==========================================
def send_telegram_batch(items):
    global last_sound_time
    
    bd_tz = pytz.timezone('Asia/Dhaka')
    now_bd = datetime.now(bd_tz)
    formatted_date = now_bd.strftime('%d-%m-%Y')
    formatted_time = now_bd.strftime('%I:%M %p')
    
    current_timestamp = time.time()
    
    # ২ ঘণ্টা সাউন্ড কন্ট্রোল লজিক
    if (current_timestamp - last_sound_time) >= SOUND_INTERVAL:
        disable_sound = False
        print("🔔 ২ ঘণ্টার পর পোস্ট বা ১ম পোস্ট -> নোটিফিকেশন সাউন্ড অন!")
    else:
        disable_sound = True
        remaining_time = int((SOUND_INTERVAL - (current_timestamp - last_sound_time)) / 60)
        print(f"🔕 ২ ঘণ্টার বেশি হয়নি (বাকি {remaining_time} মিনিট) -> সাইলেন্ট পাঠানো হচ্ছে।")

    # ফাইলগুলোকে ব্র্যান্ড অনুসারে ডিকশনারিতে ভাগ করা
    grouped_items = {}
    for item in items:
        brand = detect_brand(item['title'])
        if brand not in grouped_items:
            grouped_items[brand] = []
        grouped_items[brand].append(item)

    # কাস্টম হেডার লেআউট
    message_lines = [
        f"📌 <b>NEW FILES ADDED</b>",
        f"📅 <b>Date:</b> {formatted_date} | ⏰ <b>Time:</b> {formatted_time}",
        f"🌐 <b>Website:</b> <a href=\"https://firmwareworld.com\">Firmware World</a>\n"
    ]
    
    # ব্র্যান্ড অনুসারে লিস্ট তৈরি করা
    for brand, brand_items in grouped_items.items():
        message_lines.append(f"🔹 <b>{brand} FIRMWARE</b>")
        for item in brand_items:
            clean_title = html.escape(item['title'])
            clean_link = item['link'].strip()
            
            quote_block = (
                f"<blockquote>"
                f"🔥 NEW FILE 🔥\n\n"
                f"➡️ <b>{clean_title}</b>\n\n"
                f"🔗 Link: <a href=\"{clean_link}\">Download</a>"
                f"</blockquote>"
            )
            message_lines.append(quote_block)
        message_lines.append("") # ব্র্যান্ডগুলোর মাঝে স্পেস
    
    final_message = "\n".join(message_lines)
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
            # পোস্ট সফল হলে এবং সাউন্ডে পাঠানো হলে সময় কাউন্ট আপডেট করা
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
# 6. MAIN RSS BOT LOOP (BATCHING LOGIC)
# ==========================================
def run_rss_bot():
    print("🚀 RSS Bot চালু হচ্ছে...")
    posted_urls = load_posted_urls()

    while True:
        try:
            feed = feedparser.parse(RSS_FEED_URL)
            unposted_items = []
            
            # ফিড থেকে নতুন ফাইল আলাদা করা (পুরনো থেকে নতুন ক্রমানুসারে)
            for entry in reversed(feed.entries):
                post_url = entry.link.strip()
                post_title = entry.title
                
                if post_url not in posted_urls:
                    unposted_items.append({
                        "title": post_title,
                        "link": post_url
                    })

            if unposted_items:
                print(f"📦 মোট নতুন ফাইল পাওয়া গেছে: {len(unposted_items)} টি")
                
                # ২০টি ২০টি করে ব্যাচ ভাগ করে পাঠানো
                for i in range(0, len(unposted_items), BATCH_SIZE):
                    batch = unposted_items[i:i + BATCH_SIZE]
                    
                    success = send_telegram_batch(batch)
                    if success:
                        batch_urls = [item['link'] for item in batch]
                        for url in batch_urls:
                            posted_urls.add(url)
                        
                        # গিটহাবে সেভ করা
                        save_posted_urls_batch(batch_urls)
                        time.sleep(3)
                        
        except Exception as e:
            print(f"⚠️ RSS Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 7. START THREADS
# ==========================================
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_rss_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    run_web_server()
