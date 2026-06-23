"""telegram_bot.py — Telegram Bot Command Polling Service and Alert Dispatcher

Combines the low-level Telegram Client and the Bot Command Dispatcher
to run a long-polling service.
"""

from __future__ import annotations

import time
import requests

# Relative-import compatibility
try:
    from backend.telegram_client import (
        send_telegram_message,
        send_telegram_video,
        send_reply,
        send_telegram_photo_reply,
        _TELEGRAM_BOT_TOKEN,
        _TELEGRAM_API_BASE,
    )
    from backend.bot_commands import _COMMAND_DISPATCH
except ImportError:
    from telegram_client import (  # type: ignore[import-untyped]
        send_telegram_message,
        send_telegram_video,
        send_reply,
        send_telegram_photo_reply,
        _TELEGRAM_BOT_TOKEN,
        _TELEGRAM_API_BASE,
    )
    from bot_commands import _COMMAND_DISPATCH  # type: ignore[import-untyped]

# Re-export key functions so callers importing backend.telegram_bot don't break
__all__ = [
    "send_telegram_message",
    "send_telegram_video",
    "send_reply",
    "send_telegram_photo_reply",
    "run_polling",
]

# Polling configuration
_POLLING_TIMEOUT_SEC: int = 30
_POLLING_REQUEST_TIMEOUT_SEC: int = 35
_POLLING_RETRY_DELAY_SEC: int = 5
_POLLING_INTERVAL_SEC: int = 1


def run_polling() -> None:
    """Run a long-polling loop to receive and handle Telegram commands.

    Blocks indefinitely.  Exits early if the bot token is missing.
    """
    if not _TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in environment. Cannot start Telegram Bot.")
        return

    print("🤖 Telegram Bot command receiver started. Listening for messages...")
    offset: int = 0

    while True:
        try:
            resp = requests.get(
                f"{_TELEGRAM_API_BASE}/getUpdates",
                params={"offset": offset, "timeout": _POLLING_TIMEOUT_SEC},
                timeout=_POLLING_REQUEST_TIMEOUT_SEC,
            )
            if resp.status_code != 200:
                continue

            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "").strip()

                # Match the incoming text to a known command prefix.
                for command, handler in _COMMAND_DISPATCH.items():
                    if text.startswith(command):
                        handler(chat_id, text)
                        break

        except Exception as exc:
            print(f"⚠️ Polling connection error: {exc}")
            time.sleep(_POLLING_RETRY_DELAY_SEC)

        time.sleep(_POLLING_INTERVAL_SEC)


if __name__ == "__main__":
    run_polling()
