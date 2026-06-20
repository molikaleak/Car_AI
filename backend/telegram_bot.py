import os
import time
import requests
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Relative import compatibility
try:
    import database
except ImportError:
    from backend import database

def get_telegram_config():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id

def send_telegram_message(text):
    """Sends a text message to the default chat ID."""
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set in environment.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        return False

def send_telegram_video(video_path, caption=None):
    """Sends a video file as an alert to the default chat ID."""
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set in environment.")
        return False
    if not os.path.exists(video_path):
        print(f"❌ Video file does not exist: {video_path}")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "Markdown"
            r = requests.post(url, data=data, files=files, timeout=30)
            return r.status_code == 200
    except Exception as e:
        print(f"❌ Error sending Telegram video: {e}")
        return False

def send_reply(chat_id, text):
    """Sends a text message reply to a specific chat ID."""
    token, _ = get_telegram_config()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Error sending reply: {e}")

def format_report(period, data):
    """Formats list of crossing counts into a clean text report."""
    counts = {
        "Car": {"IN": 0, "OUT": 0},
        "Person": {"IN": 0, "OUT": 0}
    }
    for row in data:
        obj = row.get("object_type")
        direction = row.get("direction")
        count = row.get("count", 0)
        if obj in counts and direction in counts[obj]:
            counts[obj][direction] = count
            
    report = f"📊 *{period} Warehouse Gateway Report*\n\n"
    report += "*Vehicles (Cars):*\n"
    report += f"  🔹 IN: {counts['Car']['IN']}\n"
    report += f"  🔹 OUT: {counts['Car']['OUT']}\n\n"
    report += "*People/Visitors:*\n"
    report += f"  🔹 IN: {counts['Person']['IN']}\n"
    report += f"  🔹 OUT: {counts['Person']['OUT']}\n"
    return report

def run_polling():
    """Runs a long-polling bot receiver to handle user command requests."""
    token, _ = get_telegram_config()
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in environment. Cannot start Telegram Bot.")
        return

    print("🤖 Telegram Bot command receiver started. Listening for messages...")
    offset = 0
    
    while True:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {"offset": offset, "timeout": 30}
        try:
            r = requests.get(url, params=params, timeout=35)
            if r.status_code == 200:
                result = r.json().get("result", [])
                for update in result:
                    update_id = update["update_id"]
                    offset = update_id + 1
                    
                    message = update.get("message")
                    if not message:
                        continue
                    
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "").strip()
                    
                    if text.startswith("/start"):
                        welcome = (
                            "👋 Welcome to the Warehouse Security Gateway Bot!\n\n"
                            "Here are the available commands:\n"
                            "🔹 `/today` - Today's traffic counts\n"
                            "🔹 `/week` - Weekly traffic report\n"
                            "🔹 `/month` - Monthly traffic report\n"
                            "🔹 `/recent` - Last 10 crossing events\n"
                            "🔹 `/status` - System status check"
                        )
                        send_reply(chat_id, welcome)
                    elif text.startswith("/today"):
                        report = format_report("Daily", database.get_today_report())
                        send_reply(chat_id, report)
                    elif text.startswith("/week"):
                        report = format_report("Weekly", database.get_weekly_report())
                        send_reply(chat_id, report)
                    elif text.startswith("/month"):
                        report = format_report("Monthly", database.get_monthly_report())
                        send_reply(chat_id, report)
                    elif text.startswith("/recent"):
                        events = database.get_recent_events(10)
                        if not events:
                            send_reply(chat_id, "No crossing events logged yet.")
                        else:
                            reply = "📋 *Recent Crossing Events:*\n\n"
                            for ev in events:
                                reply += f"🔹 {ev['timestamp']} | *{ev['object_type']}* | ID #{ev['track_id']} | *{ev['direction']}*\n"
                            send_reply(chat_id, reply)
                    elif text.startswith("/status"):
                        send_reply(chat_id, "✅ Warehouse Gateway Tracking System is ONLINE and monitoring.")
        except Exception as e:
            print(f"⚠️ Polling connection error: {e}")
            time.sleep(5)
            
        time.sleep(1)

if __name__ == "__main__":
    run_polling()
