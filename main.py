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
import google.generativeai as genai

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

# Gemini Config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
FILE_PATH = "posted_urls.txt"

CHECK_INTERVAL = 1800     # প্রতি ৩০ মিনিট পর RSS চেক
BATCH_SIZE = 20           # টেলিগ্রামে এক পোস্টে ২০টি ফাইল
SOUND_INTERVAL = 7200     # ২ ঘণ্টা সাউন্ড কন্ট্রোল

last_sound_time = 0

BRANDS = [
    "SAMSUNG", "XIAOMI", "REDMI", "POCO", "REALME", "OPPO", "VIVO", 
    "TECNO", "INFINIX", "ITEL", "ONEPLUS", "NOTHING", "HONOR", "HUAWEI",
    "NOKIA", "MOTOROLA", "LAVA", "SYMPHONY", "WALTON", "ASUS", "GOOGLE"
]

# ==========================================
# 3. HELPER FUNCTIONS: BRAND & GEMINI SEO
# ==========================================
def detect_brand(title):
    title_upper = title.upper()
    for brand in BRANDS:
        if brand in title_upper:
            if brand in ["REDMI", "POCO"]:
                return "XIAOMI / REDMI / POCO"
            return brand
    return "OTHER FIRMWARE"

def generate_seo_caption_and_hashtags(title, brand):
    """Gemini API দিয়ে SEO ক্যাপশন ও রিলেটেড হ্যাশট্যাগ তৈরি করা"""
    if not GEMINI_API_KEY:
        # Gemini API Key না থাকলে ডিফল্ট হ্যাশট্যাগ
        clean_brand = brand.replace(" / ", "_").replace(" ", "")
        return f"🔥 New Firmware Update Available!\n\n📌 File: {title}\n\n#{clean_brand} #FirmwareUpdate #StockROM #FlashFile #FirmwareWorld"
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        Act as an SEO and Social Media expert for a mobile firmware download website.
        Generate an engaging Facebook post caption with 5-8 relevant trending SEO hashtags for this firmware file:
        File Title: "{title}"
        Brand: "{brand}"

        Rules:
        1. Keep it short, attractive and professional.
        2. Do NOT add any download links inside the text.
        3. Mention that the download link is provided in the FIRST COMMENT.
        4. Include relevant SEO hashtags (e.g., #{brand.replace(' ', '')}, #Firmware, #FlashFile, #StockROM, #AndroidUpdate, etc.).
        5. Return only the post text without explanations.
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Gemini API Error: {e}")
        return f"🔥 New Update Available!\n\n📌 File: {title}\n👉 Check the 1st Comment for direct download link.\n\n#Firmware #FlashFile #StockROM #{brand.replace(' ', '')}"

# ==========================================
# 4. FACEBOOK POST & 1ST COMMENT LOGIC
# ==========================================
def post_to_facebook(title, link, brand):
    """ফেসবুকে মূল পোস্ট এবং ফার্স্ট কমেন্টে লিঙ্ক যোগ করার ফাংশন"""
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ Facebook credentials (FB_PAGE_ID / FB_ACCESS_TOKEN) পাওয়া যায়নি!")
        return False
    
    try:
        # ১. Gemini দিয়ে পোস্ট কনটেন্ট ও হ্যাশট্যাগ জেনারেট
        post_content = generate_seo_caption_and_hashtags(title, brand)

        # ২. ফেসবুকে মূল পোস্ট পাঠানো
        feed_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
        feed_payload = {
            'message': post_content,
            'access_token': FB_ACCESS_TOKEN
        }
        res = requests.post(feed_url, data=feed_payload).json()
        post_id = res.get('id')

        if not post_id:
            print(f"❌ Facebook Post Failed: {res}")
            return False

        # ৩. ফার্স্ট কমেন্টে ডাউনলোড লিঙ্ক ড্রপ করা
        comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
        comment_payload = {
            'message': f"📥 Download Link: {link}\n\n🌐 Visit: https://firmwareworld.com",
            'access_token': FB_ACCESS_TOKEN
        }
        requests.post(comment_url, data=comment_payload)
        print(f"✅ Facebook-এ সফলভাবে পোস্ট ও ফার্স্ট কমেন্ট হয়েছে: {title}")
        return True

    except Exception as e:
        print(f"⚠️ Facebook API Error: {e}")
        return False

# ==========================================
# 5. GITHUB DATABASE FUNCTIONS
# ==========================================
def load_posted_urls():
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
        return set()
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(FILE_PATH)
        urls = contents.decoded_content.decode('utf-8').splitlines()
        print(f"✅ GitHub থেকে {len(urls)} টি পোস্ট করা লিংক লোড হয়েছে।")
        return set(line.strip() for line in urls if line.strip())
    except Exception as e:
        print(f"⚠️ GitHub ফাইল পড়ার সময় ভুল হয়েছে: {e}")
        return set()

def save_posted_urls_batch(new_urls):
    if not GITHUB_TOKEN or not new_urls:
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
        print(f"✅ GitHub-এ একসাথে {len(new_urls)} টি নতুন লিংক সফলভাবে সেভ হয়েছে!")
    except Exception as e:
        print(f"❌ GitHub-এ লিংক সেভ করতে ব্যর্থ! কারণ: {e}")

# ==========================================
# 6. TELEGRAM BATCH NOTIFICATION
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
# 7. MAIN RSS BOT LOOP (BATCHING & SYNC LOGIC)
# ==========================================
def run_rss_bot():
    print("🚀 RSS Bot চালু হচ্ছে...")
    posted_urls = load_posted_urls()

    while True:
        try:
            feed = feedparser.parse(RSS_FEED_URL)
            unposted_items = []
            
            for entry in reversed(feed.entries):
                post_url = entry.link.strip()
                post_title = entry.title
                
                if post_url not in posted_urls:
                    unposted_items.append({
                        "title": post_title,
                        "link": post_url
                    })

            if unposted_items:
                print(f"📦 মোট নতুন ফাইল পাওয়া গেছে: {len(unposted_items)} টি")
                
                # ২০টি ২০টি করে ব্যাচ টেলিগ্রামে পাঠানো
                for i in range(0, len(unposted_items), BATCH_SIZE):
                    batch = unposted_items[i:i + BATCH_SIZE]
                    
                    # ১. টেলিগ্রামে পোস্ট করা
                    telegram_success = send_telegram_batch(batch)
                    
                    if telegram_success:
                        batch_urls = [item['link'] for item in batch]
                        for url in batch_urls:
                            posted_urls.add(url)
                        
                        # গিটহাবে সেভ
                        save_posted_urls_batch(batch_urls)
                        
                        # ২. ফেসবুকে প্রতিটি ফাইল আলাদা আলাদা পোস্ট করা (১-২ মিনিট বিরতি দিয়ে)
                        print(f"📲 ফেসবুকে {len(batch)}টি ফাইল পোস্ট করা শুরু হচ্ছে...")
                        for item in batch:
                            brand = detect_brand(item['title'])
                            post_to_facebook(item['title'], item['link'], brand)
                            
                            # ১ থেকে ২ মিনিটের র্যান্ডম গ্যাপ (স্প্যাম প্রোটেকশন)
                            delay = random.randint(60, 120)
                            print(f"⏳ পরবর্তী ফেসবুক পোস্টের জন্য {delay} সেকেন্ড অপেক্ষা করা হচ্ছে...")
                            time.sleep(delay)
                            
        except Exception as e:
            print(f"⚠️ RSS Loop Error: {e}")
            
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 8. START THREADS & WEB SERVER
# ==========================================
if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_rss_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    run_web_server()
