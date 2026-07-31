import os
import re
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
# Environment Variables (Set inside Render)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Repository Details
REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
FILE_PATH = "posted_urls.txt"
RSS_FEED_URL = "https://firmwareworld.com/rss.xml" # আপনার সাইটের RSS Feed Link

CHECK_INTERVAL = 300 # প্রতি ৫ মিনিট পর পর চেক করবে

# ==========================================
# 3. GITHUB DATABASE FUNCTIONS
# ==========================================
def load_posted_urls():
    """GitHub এর posted_urls.txt থেকে সেভ করা লিংক নিয়ে আসবে"""
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

def save_posted_url(new_url):
    """নতুন পোস্টের লিংক GitHub এর posted_urls.txt ফাইলে Push করবে"""
    if not GITHUB_TOKEN:
        return
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(FILE_PATH)
        
        existing_content = contents.decoded_content.decode('utf-8')
        if existing_content and not existing_content.endswith('\n'):
            updated_content = existing_content + f"\n{new_url}"
        else:
            updated_content = existing_content + f"{new_url}"

        repo.update_file(
            path=FILE_PATH,
            message="Bot: Add new posted URL",
            content=updated_content,
            sha=contents.sha
        )
        print(f"✅ GitHub-এ নতুন লিংক সফলভাবে সেভ হয়েছে: {new_url}")
    except Exception as e:
        print(f"⚠️ GitHub-এ লিংক সেভ করার সময় ভুল হয়েছে: {e}")

# ==========================================
# 4. TELEGRAM NOTIFICATION FUNCTION
# ==========================================
def send_telegram_message(title, link):
    """টেলিগ্রাম চ্যানেলে মেসেজ পাঠাবে"""
    message = f"📌 **New Firmware Released!**\n\n📁 **{title}**\n\n🔗 [Download Link]({link})"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, data=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ Telegram Send Error: {e}")
        return False

# ==========================================
# 5. MAIN RSS BOT LOOP
# ==========================================
def run_rss_bot():
    print("🚀 RSS Bot চালু হচ্ছে...")
    
    # শুরতেই গিটহাব থেকে সেভ করা লিংকগুলো মেমোরিতে লোড করে নেওয়া
    posted_urls = load_posted_urls()

    while True:
        try:
            feed = feedparser.parse(RSS_FEED_URL)
            for entry in reversed(feed.entries): # পুরনো থেকে নতুন অর্ডারে পোস্ট করবে
                post_url = entry.link.strip()
                post_title = entry.title
                
                # যদি লিংকটি গিটহাব ডাটাবেজে না থাকে
                if post_url not in posted_urls:
                    print(f"🆕 নতুন পোস্ট পাওয়া গেছে: {post_title}")
                    
                    # টেলিগ্রামে পোস্ট পাঠানো
                    success = send_telegram_message(post_title, post_url)
                    
                    if success:
                        posted_urls.add(post_url)
                        # গিটহাব ডাটাবেজে ফাইল পুশ করা
                        save_posted_url(post_url)
                        time.sleep(3) # রিকোয়েস্ট স্প্যাম এড়াতে ৩ সেকেন্ড পজ
                        
        except Exception as e:
            print(f"⚠️ RSS Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 6. START THREADS
# ==========================================
if __name__ == "__main__":
    # ব্যাকগ্রাউন্ডে RSS Bot রান করানো
    bot_thread = threading.Thread(target=run_rss_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # রেন্ডার সার্ভারের জন্য ওয়েবসাইট স্পিন আপ
    run_web_server()
