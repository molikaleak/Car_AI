"""Telegram bot integration for Warehouse Gateway Tracking System.

Provides functions to send alerts (text, video, photo) to Telegram,
format traffic reports, and run a long-polling command receiver.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

import dotenv
import requests

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Relative-import compatibility (standalone script vs. package)
# ---------------------------------------------------------------------------
try:
    from backend import database
    from backend.visual_report import generate_visual_report_card
    from backend import config_manager
except ImportError:
    # Running as a standalone script inside backend/
    import database  # type: ignore[import-untyped]
    import config_manager  # type: ignore[import-untyped]

    try:
        from visual_report import generate_visual_report_card  # type: ignore[import-untyped]
    except ImportError:
        generate_visual_report_card = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Telegram configuration (read once, cached at module level)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Low-level Telegram API helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public message-sending functions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _extract_car_counts(db_data: list[dict[str, Any]]) -> dict[str, int]:
    """Extract Car IN/OUT counts from a database report result set.

    Args:
        db_data: Rows returned by one of the ``database.get_*_report()``
            functions.  Each row is expected to have ``object_type``,
            ``direction``, and ``count`` keys.

    Returns:
        A dict of the form ``{"IN": <n>, "OUT": <n>}``.
    """
    counts: dict[str, int] = {"IN": 0, "OUT": 0}
    for row in db_data:
        if row.get("object_type") == "Car" and row.get("direction") in counts:
            counts[row["direction"]] = row.get("count", 0)
    return counts


def format_report(period: str, data: list[dict[str, Any]]) -> str:
    """Format a list of crossing counts into a clean Markdown text report.

    Args:
        period: Human-readable period label (e.g. ``"Daily"``).
        data: Database rows with crossing counts.

    Returns:
        A formatted Markdown string ready to send via Telegram.
    """
    counts = _extract_car_counts(data)
    return (
        f"📊 *{period} Warehouse Gateway Report*\n\n"
        f"*Vehicles (Cars):*\n"
        f"  🔹 IN: {counts['IN']}\n"
        f"  🔹 OUT: {counts['OUT']}\n"
    )


def send_visual_report(
    chat_id: int | str,
    period_label: str,
    db_data: list[dict[str, Any]],
    text_report: str,
) -> None:
    """Generate and send a visual report card, falling back to text.

    If the ``visual_report`` module is unavailable or image generation
    fails, the plain *text_report* is sent instead.

    Args:
        chat_id: Target Telegram chat.
        period_label: Label such as ``"Daily"``, ``"Weekly"``, etc.
        db_data: Raw database rows for count extraction.
        text_report: Pre-formatted text report used as a fallback.
    """
    if generate_visual_report_card is None:
        send_reply(chat_id, text_report)
        return

    counts = _extract_car_counts(db_data)
    img_filename = f"{period_label.lower()}_report_{chat_id}.png"

    try:
        generate_visual_report_card(
            f"{period_label} Traffic", counts["IN"], counts["OUT"], img_filename,
        )
        success = send_telegram_photo_reply(
            chat_id, img_filename, caption=f"📊 *{period_label} Gateway Visual Card*",
        )
        if not success:
            send_reply(chat_id, text_report)
    except Exception as exc:
        print(f"❌ Failed to generate visual report: {exc}")
        send_reply(chat_id, text_report)
    finally:
        if os.path.exists(img_filename):
            try:
                os.remove(img_filename)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Command handlers (each receives the chat_id of the requesting user)
# ---------------------------------------------------------------------------

def _handle_start(chat_id: int | str, text: str = "") -> None:
    """Greet the user and list available commands."""
    welcome = (
        "👋 Welcome to the Warehouse Security Gateway Bot!\n\n"
        "*📊 Reports:*\n"
        "🔹 `/today` — Today's traffic counts\n"
        "🔹 `/week` — Weekly traffic report\n"
        "🔹 `/month` — Monthly traffic report\n"
        "🔹 `/recent` — Last 10 crossing events\n"
        "🔹 `/status` — System status check\n\n"
        "*⚙️ Configuration:*\n"
        "🔹 `/config` — View current settings\n"
        "🔹 `/setline 0.50` — Gate line position (0.0–1.0)\n"
        "🔹 `/setangle 90` — Gate line angle (0–180°)\n"
        "🔹 `/setdir right` — IN direction (right/left/up/down)\n"
        "🔹 `/setconf 0.25` — Detection confidence (0.0–1.0)\n"
        "🔹 `/setcamera 0` — Camera source (0/IP/RTSP URL)\n"
        "🔹 `/restart` — Restart tracker with new settings"
    )
    send_reply(chat_id, welcome)


def _handle_report(
    chat_id: int | str,
    period_label: str,
    fetch_fn: Any,
) -> None:
    """Fetch data and send a visual (or text) report for the given period."""
    raw_data = fetch_fn()
    text_report = format_report(period_label, raw_data)
    send_visual_report(chat_id, period_label, raw_data, text_report)


def _handle_recent(chat_id: int | str, text: str = "") -> None:
    """Send the last 10 crossing events."""
    events = database.get_recent_events(10)
    if not events:
        send_reply(chat_id, "No crossing events logged yet.")
        return

    lines = ["📋 *Recent Crossing Events:*\n"]
    for ev in events:
        lines.append(
            f"🔹 {ev['timestamp']} | *{ev['object_type']}* "
            f"| ID #{ev['track_id']} | *{ev['direction']}*"
        )
    send_reply(chat_id, "\n".join(lines))


def _handle_status(chat_id: int | str, text: str = "") -> None:
    """Show system status including tracker process state."""
    tracker_status = config_manager.get_tracker_status()
    msg = (
        "✅ *Warehouse Gateway System Status*\n\n"
        f"🤖 Telegram Bot: 🟢 Running\n"
        f"📹 {tracker_status}"
    )
    send_reply(chat_id, msg)


# ---------------------------------------------------------------------------
# Configuration command handlers
# ---------------------------------------------------------------------------

def _handle_config(chat_id: int | str, text: str = "") -> None:
    """Show all current configuration values."""
    cfg = config_manager.get_current_config()
    tracker_status = config_manager.get_tracker_status()

    msg = (
        "⚙️ *Current Configuration*\n\n"
        "*🚧 Gate Line:*\n"
        f"  Position: `{cfg['LINE_POS']}`\n"
        f"  Angle: `{cfg['LINE_ANGLE']}°`\n"
        f"  IN Direction: `{cfg['IN_DIRECTION']}`\n\n"
        "*🔍 Detection:*\n"
        f"  Confidence: `{cfg['CONFIDENCE_THRESHOLD']}`\n\n"
        "*📹 Camera:*\n"
        f"  Source: `{cfg['CAMERA_IP']}`\n\n"
        "*🎬 Recording:*\n"
        f"  Record Clips: `{cfg['RECORD_CLIPS']}`\n"
        f"  Buffer (before): `{cfg['CLIP_BUFFER_SECONDS']}s`\n"
        f"  Duration (after): `{cfg['CLIP_DURATION_SECONDS']}s`\n\n"
        "*🖥️ Display:*\n"
        f"  GUI: `{cfg['SHOW_GUI']}`\n"
        f"  Grayscale: `{cfg['GRAYSCALE']}`\n"
        f"  Speed: `{cfg['SLOW_SPEED']}`\n"
        f"  Time Mode: `{cfg['TIME_MODE']}`\n\n"
        f"*📡 System:*\n"
        f"  {tracker_status}\n\n"
        "_Use_ `/setline`, `/setangle`, `/setdir`, `/setconf`, `/setcamera` "
        "_to change settings, then_ `/restart` _to apply._"
    )
    send_reply(chat_id, msg)


def _handle_setline(chat_id: int | str, text: str) -> None:
    """Set gate line position (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setline 0.50`\nValue must be between 0.0 and 1.0.")
        return

    try:
        value = float(parts[1])
    except ValueError:
        send_reply(chat_id, f"❌ Invalid number: `{parts[1]}`")
        return

    if not 0.0 <= value <= 1.0:
        send_reply(chat_id, f"❌ Value `{value}` out of range. Must be between 0.0 and 1.0.")
        return

    config_manager.update_env_value("LINE_POS", str(value))
    send_reply(
        chat_id,
        f"✅ Gate line position set to `{value}`\n"
        f"_Run_ `/restart` _to apply this change._",
    )


def _handle_setangle(chat_id: int | str, text: str) -> None:
    """Set gate line angle (0 to 180 degrees)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(
            chat_id,
            "❌ Usage: `/setangle 90`\n"
            "Value must be between 0 and 180.\n"
            "• `0` = horizontal line\n"
            "• `90` = vertical line\n"
            "• Other values = diagonal",
        )
        return

    try:
        value = float(parts[1])
    except ValueError:
        send_reply(chat_id, f"❌ Invalid number: `{parts[1]}`")
        return

    if not 0.0 <= value <= 180.0:
        send_reply(chat_id, f"❌ Value `{value}` out of range. Must be between 0 and 180.")
        return

    config_manager.update_env_value("LINE_ANGLE", str(value))
    send_reply(
        chat_id,
        f"✅ Gate line angle set to `{value}°`\n"
        f"_Run_ `/restart` _to apply this change._",
    )


def _handle_setdir(chat_id: int | str, text: str) -> None:
    """Set the IN direction (right, left, up, down)."""
    parts = text.split()
    valid_dirs = ["right", "left", "up", "down"]

    if len(parts) < 2 or parts[1].lower() not in valid_dirs:
        send_reply(
            chat_id,
            "❌ Usage: `/setdir right`\n"
            f"Valid directions: `{', '.join(valid_dirs)}`\n\n"
            "• For vertical gate line → use `right` or `left`\n"
            "• For horizontal gate line → use `up` or `down`",
        )
        return

    direction = parts[1].lower()
    config_manager.update_env_value("IN_DIRECTION", direction)
    send_reply(
        chat_id,
        f"✅ IN direction set to `{direction}`\n"
        f"_Run_ `/restart` _to apply this change._",
    )


def _handle_setconf(chat_id: int | str, text: str) -> None:
    """Set YOLO detection confidence threshold (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(
            chat_id,
            "❌ Usage: `/setconf 0.25`\n"
            "Value must be between 0.0 and 1.0.\n"
            "• Lower = detect more (but more false positives)\n"
            "• Higher = detect less (but more accurate)",
        )
        return

    try:
        value = float(parts[1])
    except ValueError:
        send_reply(chat_id, f"❌ Invalid number: `{parts[1]}`")
        return

    if not 0.0 <= value <= 1.0:
        send_reply(chat_id, f"❌ Value `{value}` out of range. Must be between 0.0 and 1.0.")
        return

    config_manager.update_env_value("CONFIDENCE_THRESHOLD", str(value))
    send_reply(
        chat_id,
        f"✅ Detection confidence set to `{value}`\n"
        f"_Run_ `/restart` _to apply this change._",
    )


def _handle_setcamera(chat_id: int | str, text: str) -> None:
    """Set camera source (webcam ID, IP address, or RTSP/HTTP URL)."""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        send_reply(
            chat_id,
            "❌ Usage: `/setcamera <source>`\n\n"
            "Examples:\n"
            "• `/setcamera 0` — Built-in webcam\n"
            "• `/setcamera http://192.168.1.50:8080/video` — IP Webcam app\n"
            "• `/setcamera rtsp://192.168.1.50:554/stream` — RTSP camera",
        )
        return

    source = parts[1].strip()
    config_manager.update_env_value("CAMERA_IP", source)
    send_reply(
        chat_id,
        f"✅ Camera source set to `{source}`\n"
        f"_Run_ `/restart` _to apply this change._",
    )


def _handle_restart(chat_id: int | str, text: str = "") -> None:
    """Restart the YOLO tracker process with current .env settings."""
    send_reply(chat_id, "🔄 Restarting tracker... Please wait.")

    success, message = config_manager.restart_tracker()

    if success:
        # Show the config that was applied
        cfg = config_manager.get_current_config()
        reply = (
            f"✅ *{message}*\n\n"
            "*Applied settings:*\n"
            f"  Gate Line: pos=`{cfg['LINE_POS']}` angle=`{cfg['LINE_ANGLE']}°`\n"
            f"  IN Direction: `{cfg['IN_DIRECTION']}`\n"
            f"  Confidence: `{cfg['CONFIDENCE_THRESHOLD']}`\n"
            f"  Camera: `{cfg['CAMERA_IP']}`"
        )
    else:
        reply = f"❌ *Restart failed:* {message}"

    send_reply(chat_id, reply)


# ---------------------------------------------------------------------------
# Command → handler dispatch table
# ---------------------------------------------------------------------------
# All handlers accept (chat_id, text). For commands without arguments,
# the ``text`` parameter has a default value and is safely ignored.

_COMMAND_DISPATCH: dict[str, Any] = {
    # Reports
    "/start": _handle_start,
    "/today": lambda cid, txt: _handle_report(cid, "Daily", database.get_today_report),
    "/week": lambda cid, txt: _handle_report(cid, "Weekly", database.get_weekly_report),
    "/month": lambda cid, txt: _handle_report(cid, "Monthly", database.get_monthly_report),
    "/recent": _handle_recent,
    "/status": _handle_status,
    # Configuration
    "/config": _handle_config,
    "/setline": _handle_setline,
    "/setangle": _handle_setangle,
    "/setdir": _handle_setdir,
    "/setconf": _handle_setconf,
    "/setcamera": _handle_setcamera,
    "/restart": _handle_restart,
}


# ---------------------------------------------------------------------------
# Long-polling receiver
# ---------------------------------------------------------------------------

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
                params={"offset": offset, "timeout": 30},
                timeout=35,
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
            time.sleep(5)

        time.sleep(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_polling()
