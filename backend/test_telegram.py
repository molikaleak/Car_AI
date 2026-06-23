"""test_telegram.py — Telegram Bot Connection Test

Sends a test message via the configured Telegram bot to verify
that the bot token and chat ID are correctly set up.
"""

import os
import sys

# Set path relative to project root
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend import telegram_bot


def main() -> None:
    """Send a test message to verify Telegram bot connectivity."""
    print("Sending test message via Telegram...")
    success = telegram_bot.send_telegram_message(
        "🔔 *Warehouse Gateway Connection Test*\n\n"
        "Your Telegram bot is successfully connected to the warehouse camera tracker!"
    )

    if success:
        print("\n✅ Telegram connection works! You should have received a notification in your Telegram app.")
    else:
        print("\n❌ Telegram connection failed!")
        print("👉 Please ensure that your '.env' file is configured with the correct values for:")
        print("   1. TELEGRAM_BOT_TOKEN")
        print("   2. TELEGRAM_CHAT_ID")
        print("👉 You can get your TELEGRAM_CHAT_ID by messaging the bot and running 'python3 backend/get_chat_id.py'.")


if __name__ == "__main__":
    main()
