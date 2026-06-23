"""get_chat_id.py — Telegram Chat ID Discovery

Fetches the most recent chat ID from the Telegram Bot API and
updates the .env file. Run this script after sending a message
to the bot on Telegram.
"""

import os
import sys
import dotenv
import requests


def main() -> None:
    # Load current env
    dotenv.load_dotenv()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file.")
        print("👉 Please add your bot token to the .env file: TELEGRAM_BOT_TOKEN=your_token_here")
        sys.exit(1)

    print("🔍 Fetching updates from ChomRok_Car_DetectionBot...")
    print("👉 If you haven't yet, please open Telegram, go to t.me/ChomRok_Car_DetectionBot, and press 'Start' or send any message.")
    print("Checking for messages...")

    url = f"https://api.telegram.org/bot{token}/getUpdates"
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

                    # Update .env file using config_manager
                    try:
                        from backend import config_manager
                    except ImportError:
                        import config_manager  # type: ignore[no-redef]
                    
                    config_manager.update_env_value("TELEGRAM_CHAT_ID", str(chat_id))
                    print("💾 Successfully updated your .env file with Chat ID!")
                else:
                    print("❌ Found updates but could not parse a valid user message.")
        else:
            print(f"❌ Failed to reach Telegram API: HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ Error occurred: {e}")


if __name__ == "__main__":
    main()
