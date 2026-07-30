from datetime import datetime
import os
import re
import time
import feedparser
import pytz
import requests

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
RSS_URL = os.environ.get("RSS_URL")

POSTED_FILE = "posted_urls.txt"
MAX_POSTED_URLS = 3000
FILES_PER_MESSAGE = 20

BRANDS = [
    "VIVO",
    "OPPO",
    "REALME",
    "XIAOMI",
    "REDMI",
    "POCO",
    "SAMSUNG",
    "ONEPLUS",
    "TECNO",
    "INFINIX",
    "ITEL",
    "MOTOROLA",
    "NOKIA",
]


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_posted_urls():
  if os.path.exists(POSTED_FILE):
    with open(POSTED_FILE, "r") as f:
      lines = [line.strip() for line in f if line.strip()]
      return set(lines), lines
  return set(), []


def save_posted_urls(new_urls, all_lines_list):
  all_lines_list.extend(new_urls)
  if len(all_lines_list) > MAX_POSTED_URLS:
    all_lines_list = all_lines_list[-MAX_POSTED_URLS:]
  with open(POSTED_FILE, "w") as f:
    for url in all_lines_list:
      f.write(url + "\n")


def clean_url(url):
  prefix = "https://www.google.com/search?q="
  if url.startswith(prefix):
    url = url[len(prefix) :]
  return url.strip()


def detect_brand(title):
  title_upper = title.upper()
  for brand in BRANDS:
    if re.search(r"\b" + brand + r"\b", title_upper):
      return brand
  return "OTHER"


def send_telegram_message(html_text):
  url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": CHANNEL_ID,
      "text": html_text,
      "parse_mode": "HTML",
      "disable_web_page_preview": True,
  }
  try:
    response = requests.post(url, json=payload)
    return response.status_code == 200
  except Exception as e:
    print(f"Error sending message: {e}")
    return False


def build_and_send_chunk(entries_chunk, date_str, time_str):
  grouped_files = {}
  chunk_posted_urls = []

  for title, link in entries_chunk:
    brand = detect_brand(title)
    if brand not in grouped_files:
      grouped_files[brand] = []
    grouped_files[brand].append((title, link))
    chunk_posted_urls.append(link)

  message_lines = ["<blockquote>"]
  message_lines.append(f"📅 Today's Update: {date_str} | ⏰ {time_str}")
  message_lines.append("🌐 Official Website: https://firmwareworld.com/\n")

  for brand, files in grouped_files.items():
    message_lines.append(f"--- 📱 {brand} FIRMWARE ---\n")
    for title, link in files:
      message_lines.append("🔥 File Name:")
      message_lines.append(f"{title}")
      message_lines.append(f"🔗 File Link: {link}\n")

  message_lines.append("</blockquote>")

  full_message = "\n".join(message_lines)
  success = send_telegram_message(full_message)
  return success, chunk_posted_urls


def check_rss():
  posted_set, posted_list = get_posted_urls()
  feed = feedparser.parse(RSS_URL)

  new_entries = []
  for entry in feed.entries:
    raw_link = entry.get("link", "")
    link = clean_url(raw_link)
    if link and link not in posted_set:
      new_entries.append((entry.get("title", "").strip(), link))

  if not new_entries:
    return

  new_entries = list(reversed(new_entries))

  bd_tz = pytz.timezone("Asia/Dhaka")
  now = datetime.now(bd_tz)
  date_str = now.strftime("%d %B %Y")
  time_str = now.strftime("%I:%M %p")

  for i in range(0, len(new_entries), FILES_PER_MESSAGE):
    chunk = new_entries[i : i + FILES_PER_MESSAGE]
    success, sent_urls = build_and_send_chunk(chunk, date_str, time_str)
    if success:
      save_posted_urls(sent_urls, posted_list)
      print(f"Successfully posted a batch of {len(chunk)} files.")
    else:
      print("Failed to post batch. Stopping further posts for this cycle.")
      break
    time.sleep(3)


# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
  print("RSS Auto-Poster Bot Started...")
  while True:
    try:
      check_rss()
    except Exception as e:
      print(f"Error in loop: {e}")

    # ৬০০ সেকেন্ড = ১০ মিনিট
    time.sleep(600)
