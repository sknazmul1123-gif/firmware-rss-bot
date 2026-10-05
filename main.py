from datetime import datetime
import html
import os
import threading
import time
import feedparser
from flask import Flask
from github import Auth, Github
import pytz
import requests

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

RSS_FEED_URL = os.environ.get(
    "RSS_URL", "https://firmwareworld.com/index.php?a=rss"
)

REPO_NAME = "sknazmul1123-gif/firmware-rss-bot"
TG_FILE_PATH = "posted_urls.txt"

# টাইমিং ও কিউ সেটিংস
ACTIVE_START_HOUR = 9  # সকাল ৯:০০ টা থেকে সক্রিয়
FETCH_INTERVAL = 300  # প্রতি ৫ মিনিট পর পর RSS চেক করে কিউতে জমা রাখবে
FLUSH_INTERVAL = (
    1800  # প্রতি ৩০ মিনিট পর পর কিউতে জমা হওয়া ফাইলগুলো একসাথে পোস্ট করবে
)
NIGHT_SLEEP_INTERVAL = 600  # রাতে স্লিপ মোডে প্রতি ১০ মিনিট পর পর ঘড়ি চেক
TG_BATCH_SIZE = 5  # প্রতি মেসেজে সর্বোচ্চ ৫টি ফাইল থাকবে

BRANDS = [
    "SAMSUNG",
    "XIAOMI",
    "REDMI",
    "POCO",
    "REALME",
    "OPPO",
    "VIVO",
    "TECNO",
    "INFINIX",
    "ITEL",
    "ONEPLUS",
    "NOTHING",
    "HONOR",
    "HUAWEI",
    "NOKIA",
    "MOTOROLA",
    "LAVA",
    "SYMPHONY",
    "WALTON",
    "ASUS",
    "GOOGLE",
    "IQOO",
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
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
    print("❌ GITHUB_TOKEN পাওয়া যায়নি!")
    return set()
  try:
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(file_path)
    urls = contents.decoded_content.decode("utf-8").splitlines()
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
      existing = contents.decoded_content.decode("utf-8")
      updated = (
          (existing + f"\n{urls_to_add}")
          if not existing.endswith("\n")
          else (existing + f"{urls_to_add}")
      )
      repo.update_file(
          path=file_path,
          message=f"Update {file_path}",
          content=updated,
          sha=contents.sha,
      )
    except Exception:
      repo.create_file(
          path=file_path, message=f"Create {file_path}", content=urls_to_add
      )
    print(f"📁 GitHub DB আপডেটেড: {len(new_urls)} টি লিঙ্ক সেভ হয়েছে।")
  except Exception as e:
    print(f"❌ GitHub Save Error ({file_path}): {e}")


# ==========================================
# 5. TELEGRAM SYSTEM
# ==========================================
def send_telegram_batch(items):
  bd_tz = pytz.timezone("Asia/Dhaka")
  now_bd = datetime.now(bd_tz)
  formatted_date = now_bd.strftime("%d-%m-%Y")
  formatted_time = now_bd.strftime("%I:%M %p")

  grouped_items = {}
  for item in items:
    brand = detect_brand(item["title"])
    if brand not in grouped_items:
      grouped_items[brand] = []
    grouped_items[brand].append(item)

  message_lines = [
      "📌 <b>NEW FIRMWARE UPDATE</b>",
      f"📅 <b>Date:</b> {formatted_date} | ⏰ <b>Time:</b> {formatted_time}",
      '🌐 <b>Website:</b> <a href="https://firmwareworld.com">Firmware'
      " World</a>\n",
  ]

  quote_lines = ["<blockquote>"]
  for brand, brand_items in grouped_items.items():
    quote_lines.append(f"🔹 <b>{brand} FIRMWARE</b>\n")
    for item in brand_items:
      clean_title = html.escape(item["title"])
      clean_link = item["link"].strip()
      quote_lines.append(
          f"🔥 NEW FILE 🔥\n➡️ <b>{clean_title}</b>\n🔗 Link: <a"
          f' href="{clean_link}">Download</a>\n'
      )
    quote_lines.append("")

  quote_lines.append("</blockquote>")

  final_message = "\n".join(message_lines) + "\n".join(quote_lines)
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": final_message,
      "parse_mode": "HTML",
      "disable_web_page_preview": True,
      "disable_notification": True,
  }

  try:
    res = requests.post(url, data=payload, timeout=15)
    if res.status_code == 200:
      return True
    else:
      print(
          f"⚠️ Telegram API Rejected! Code: {res.status_code}, Response:"
          f" {res.text}"
      )
      return False
  except Exception as e:
    print(f"⚠️ Telegram Request Error: {e}")
    return False


# ==========================================
# 6. WORKER LOOP (QUEUE + 30-MIN BATCH POSTING)
# ==========================================
def telegram_worker():
  print("🚀 Telegram Smart Queue Engine চালু হয়েছে...")
  bd_tz = pytz.timezone("Asia/Dhaka")

  # ইন-মেমোরি কিউ
  queue = []
  queued_urls = set()
  last_flush_time = time.time()

  while True:
    try:
      now_bd = datetime.now(bd_tz)
      current_hour = now_bd.hour

      # রাত ১২:০০ টা (0) থেকে সকাল ৯:০০ টা (8:59) পর্যন্ত স্লিপ মোড
      if current_hour < ACTIVE_START_HOUR:
        print(
            f"🌙 [স্লিপ মোড]: এখন সময় {now_bd.strftime('%I:%M %p')}। সার্ভার"
            " ফ্রি রাখতে সকাল ৯:০০ টা পর্যন্ত বট স্লিপ মোডে থাকবে।"
        )
        time.sleep(NIGHT_SLEEP_INTERVAL)
        continue

      # ১. গিটহাব থেকে অলরেডি পোস্ট হওয়া লিংক ফেচ
      tg_posted = load_github_urls(TG_FILE_PATH)
      entries = fetch_rss_entries()

      # ২. নতুন ফাইল পেলে কিউতে জমা করা (পোস্ট করা হবে না)
      new_added = 0
      for e in entries:
        link = getattr(e, "link", "").strip()
        title = getattr(e, "title", "").strip()
        if link and (link not in tg_posted) and (link not in queued_urls):
          queue.append({"title": title, "link": link})
          queued_urls.add(link)
          new_added += 1

      if new_added > 0:
        print(
            f"📥 কিউতে নতুন {new_added} টি ফাইল জমা হয়েছে। (বর্তমানে কিউতে মোট:"
            f" {len(queue)} টি ফাইল জমা আছে)"
        )

      # ৩. ৩০ মিনিট পূর্ণ হলো কি না চেক করা
      elapsed_time = time.time() - last_flush_time

      if elapsed_time >= FLUSH_INTERVAL:
        if queue:
          print(
              f"🚀 ৩০ মিনিট পূর্ণ হয়েছে! কিউতে জমে থাকা {len(queue)} টি ফাইল"
              " একসাথে টেলিগ্রামে পোস্ট করা হচ্ছে..."
          )

          success_urls = []
          for i in range(0, len(queue), TG_BATCH_SIZE):
            batch = queue[i : i + TG_BATCH_SIZE]
            if send_telegram_batch(batch):
              batch_urls = [it["link"] for it in batch]
              success_urls.extend(batch_urls)
              time.sleep(3)
            else:
              print("⚠️ টেলিগ্রামে মেসেজ পাঠানো যায়নি।")

          # পোস্ট সফল হলে গিটহাবে ডাটাবেজ আপডেট এবং কিউ ফাঁকা করা
          if success_urls:
            save_github_urls(TG_FILE_PATH, success_urls)
            queue = [item for item in queue if item["link"] not in success_urls]
            queued_urls = set(item["link"] for item in queue)
            print("✅ কিউ সফলভাবে খালি করা হয়েছে।")
        else:
          print("ℹ️ ৩০ মিনিট পূর্ণ হয়েছে, তবে কোনো নতুন ফাইল জমা নেই।")

        # ৩০ মিনিটের টাইমার আবার নতুন করে শুরু
        last_flush_time = time.time()

    except Exception as e:
      print(f"⚠️ TG Worker Exception: {e}")

    # ৫ মিনিট পর পর আরএসএস চেক করবে
    time.sleep(FETCH_INTERVAL)


# ==========================================
# 7. START ENGINE & WEB SERVER
# ==========================================
if __name__ == "__main__":
  t1 = threading.Thread(target=telegram_worker, daemon=True)
  t1.start()

  run_web_server()
