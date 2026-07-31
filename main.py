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

CHECK_INTERVAL = 300 # প্রতি ৫ মিনিট পর পর RSS চেক করবে
BATCH_SIZE = 20      # এক পোস্টে সর্বোচ্চ ২০টি ফাইলের লিস্ট করবে

last_sound_date = None

# ==========================================
# 3. GITHUB DATABASE FUNCTIONS
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
# 4. TELEGRAM BATCH NOTIFICATION FUNCTION (HTML PARSE MODE)
# ==========================================
def send_telegram_batch(items):
    global last_sound_date
    
    bd_tz = pytz.timezone('Asia/Dhaka')
    now_bd = datetime.now(bd_tz)
    today_date = now_bd.strftime('%Y-%m-%d')
    formatted_date = now_bd.strftime('%d-%m-%Y')
    
    # দিনে ১ বার সাউন্ড কন্ট্রোল
    if last_sound_date != today_date:
        disable_sound = False
        print("🔔 আজকের ১ম ব্যাচ পোস্ট -> নোটিফিকেশন সাউন্ড অন!")
    else:
        disable_sound = True
        print("🔕 আজকের ২য়+ ব্যাচ পোস্ট -> সাইলেন্ট পাঠানো হচ্ছে।")

    # কাস্টম হেডার লেআউট (HTML Format)
    message_lines = [
        f"📌 <b>NEW FILES ADDED</b> 📅 <b>{formatted_date}</b>",
        f"🌐 <b>Website:</b> <a href=\"https://firmwareworld.com\">Firmware World</a>\n"
    ]
    
    # ২০টি ফাইল লিস্টের লেআউট (আগুন ইমোজি + এইচটিএমএল লিংক)
    for item in items:
        # টাইটেলের স্পেশাল ক্যারেক্টার সেফ করার জন্য html.escape
        clean_title = html.escape(item['title'])
        clean_link = item['link'].strip()
        
        message_lines.append("🔥 NEW FILE 🔥")
        message_lines.append(f"📁 <b>{clean_title}</b>")
        message_lines.append(f"🔗 Link: <a href=\"{clean_link}\">Download</a>\n")
    
    final_message = "\n".join(message_lines)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": final_message,
        "parse_mode": "HTML", # মার্কডাউন বাদ দিয়ে এইচটিএমএল করা হলো
        "disable_web_page_preview": True,
        "disable_notification": disable_sound
    }
    
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            last_sound_date = today_date
            return True
        else:
            print(f"⚠️ Telegram API Error: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Telegram Send Error: {e}")
        return False

# ==========================================
# 5. MAIN RSS BOT LOOP (BATCHING LOGIC)
# ==========================================
def run_rss_bot():
    print("🚀 RSS Bot চালু হচ্ছে...")
    posted_urls = load_posted_urls()

    while True:
        try:
            feed = feedparser.parse(RSS_FEED_URL)
            unposted_items = []
            
            # ফিড থেকে নতুন ফাইলগুলো আলাদা করা (পুরনো থেকে নতুন অর্ডারে)
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
                
                # ২০টা ২০টা করে ব্যাচ ভাগ করে পাঠানো
                for i in range(0, len(unposted_items), BATCH_SIZE):
                    batch = unposted_items[i:i + BATCH_SIZE]
                    
                    success = send_telegram_batch(batch)
                    if success:
                        batch_urls = [item['link'] for item in batch]
                        for url in batch_urls:
                            posted_urls.add(url)
                        
                        # গিটহাবে ২০টি লিংক সেভ করা
                        save_posted_urls_batch(batch_urls)
                        time.sleep(3)
                        
        except Exception as e:
            print(f"⚠️ RSS Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 6. START THREADS
# ==========================================
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_rss_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    run_web_server()
