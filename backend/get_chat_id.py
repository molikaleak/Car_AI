import requests
import re
import os
import dotenv

# Load current env
dotenv.load_dotenv()

TOKEN = "8087248288:AAFWqMhPw116Gp2J1xAZovrNuuXpqaV5gsE"
print("🔍 Fetching updates from ChomRok_Car_DetectionBot...")
print("👉 If you haven't yet, please open Telegram, go to t.me/ChomRok_Car_DetectionBot, and press 'Start' or send any message.")
print("Checking for messages...")

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
try:
    r = requests.get(url, timeout=10)
    if r.status_code == 200:
        updates = r.json().get("result", [])
        if not updates:
            print("\n❌ No messages found yet.")
            print("Please make sure you sent a message to the bot on Telegram, then run this script again.")
        else:
            # Find the most recent chat id
            last_msg = None
            for u in reversed(updates):
                if "message" in u:
                    last_msg = u["message"]
                    break
            
            if last_msg:
                chat_id = last_msg["chat"]["id"]
                first_name = last_msg["chat"].get("first_name", "User")
                username = last_msg["chat"].get("username", "None")
                print(f"\n✅ Found message from {first_name} (@{username})!")
                print(f"🆔 Chat ID: {chat_id}")
                
                # Update .env file
                env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
                if os.path.exists(env_path):
                    with open(env_path, "r") as f:
                        lines = f.readlines()
                    
                    new_lines = []
                    for line in lines:
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            new_lines.append(f"TELEGRAM_BOT_TOKEN={TOKEN}\n")
                        elif line.startswith("TELEGRAM_CHAT_ID="):
                            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                        else:
                            new_lines.append(line)
                            
                    with open(env_path, "w") as f:
                        f.writelines(new_lines)
                    print("💾 Successfully updated your .env file with Bot Token and Chat ID!")
                else:
                    print("⚠️ Warning: .env file not found. Please create it manually.")
            else:
                print("❌ Found updates but could not parse a valid user message.")
    else:
        print(f"❌ Failed to reach Telegram API: HTTP {r.status_code}")
except Exception as e:
    print(f"❌ Error occurred: {e}")
