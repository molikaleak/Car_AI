"""telegram_client.py — Low-level Telegram Client and Alerts Sender

Handles authentication and HTTP requests to the Telegram Bot API.
Exposes functions to send messages, photos, and video alerts.
"""

from __future__ import annotations

import os
from typing import Any, Optional
import dotenv
import requests

# Load environment
dotenv.load_dotenv()

# Read credentials
_TELEGRAM_BOT_TOKEN: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
_TELEGRAM_CHAT_ID: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
_TELEGRAM_API_BASE: str = f"https://api.telegram.org/bot{_TELEGRAM_BOT_TOKEN}"


def _config_is_valid(*, require_chat_id: bool = True) -> bool:
    """Return *True* when the minimum Telegram credentials are available.

    Args:
        require_chat_id: If ``True`` (default), both the bot token **and**
            the default chat ID must be set.
    """
    if not _TELEGRAM_BOT_TOKEN:
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN is not set in environment.")
        return False
    if require_chat_id and not _TELEGRAM_CHAT_ID:
        print("⚠️ Warning: TELEGRAM_CHAT_ID is not set in environment.")
        return False
    return True


def _call_telegram_api(
    method: str,
    data: dict[str, Any],
    files: Optional[dict[str, Any]] = None,
    *,
    timeout: int = 10,
    use_json: bool = False,
) -> bool:
    """Send a request to the Telegram Bot API.

    Args:
        method: Telegram API method name (e.g. ``"sendMessage"``).
        data: Payload parameters.
        files: Optional file dict for multipart uploads.
        timeout: Request timeout in seconds.
        use_json: If ``True``, send *data* as a JSON body instead of
            form-encoded data. Ignored when *files* is provided.

    Returns:
        ``True`` if the API responded with HTTP 200, ``False`` otherwise.
    """
    url = f"{_TELEGRAM_API_BASE}/{method}"
    try:
        if files:
            resp = requests.post(url, data=data, files=files, timeout=timeout)
        elif use_json:
            resp = requests.post(url, json=data, timeout=timeout)
        else:
            resp = requests.post(url, data=data, timeout=timeout)
        return resp.status_code == 200
    except Exception as exc:
        print(f"❌ Error calling Telegram API '{method}': {exc}")
        return False


def send_telegram_message(text: str) -> bool:
    """Send a Markdown text message to the default chat ID.

    Returns:
        ``True`` on success, ``False`` on failure or missing config.
    """
    if not _config_is_valid():
        return False
    return _call_telegram_api(
        "sendMessage",
        {"chat_id": _TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        use_json=True,
    )


def send_telegram_video(video_path: str, caption: Optional[str] = None) -> bool:
    """Send a video file as an alert to the default chat ID.

    Args:
        video_path: Absolute or relative path to the video file.
        caption: Optional Markdown caption.

    Returns:
        ``True`` on success, ``False`` on failure or missing config.
    """
    if not _config_is_valid():
        return False
    if not os.path.exists(video_path):
        print(f"❌ Video file does not exist: {video_path}")
        return False

    data: dict[str, Any] = {"chat_id": _TELEGRAM_CHAT_ID}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "Markdown"

    with open(video_path, "rb") as video_file:
        return _call_telegram_api(
            "sendVideo", data, files={"video": video_file}, timeout=30,
        )


def send_reply(chat_id: int | str, text: str) -> bool:
    """Send a Markdown text reply to a specific *chat_id*.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    return _call_telegram_api(
        "sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        use_json=True,
    )


def send_telegram_photo_reply(
    chat_id: int | str,
    photo_path: str,
    caption: Optional[str] = None,
) -> bool:
    """Send a photo file as a reply to a specific *chat_id*.

    Args:
        chat_id: Target chat.
        photo_path: Path to the image file.
        caption: Optional Markdown caption.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    data: dict[str, Any] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "Markdown"

    with open(photo_path, "rb") as photo_file:
        return _call_telegram_api(
            "sendPhoto", data, files={"photo": photo_file}, timeout=30,
        )
