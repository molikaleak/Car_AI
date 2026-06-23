"""bot_commands.py — Telegram Command Handlers and Dispatch

Defines all bot command responses (e.g. status, config, set commands, reports)
and exposes the command dispatch mapping table.
"""

from __future__ import annotations

import os
from typing import Any

# Relative-import compatibility (standalone script vs. package)
try:
    from backend import database
    from backend import config_manager
    from backend.visual_report import generate_visual_report_card
    from backend.telegram_client import send_reply, send_telegram_photo_reply
except ImportError:
    import database  # type: ignore[import-untyped]
    import config_manager  # type: ignore[import-untyped]
    from telegram_client import send_reply, send_telegram_photo_reply  # type: ignore[import-untyped]

    try:
        from visual_report import generate_visual_report_card  # type: ignore[import-untyped]
    except ImportError:
        generate_visual_report_card = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _extract_car_counts(db_data: list[dict[str, Any]]) -> dict[str, int]:
    """Extract Car IN/OUT counts from a database report result set."""
    counts: dict[str, int] = {"IN": 0, "OUT": 0}
    for row in db_data:
        if row.get("object_type") == "Car" and row.get("direction") in counts:
            counts[row["direction"]] = row.get("count", 0)
    return counts


def format_report(period: str, data: list[dict[str, Any]]) -> str:
    """Format a list of crossing counts into a clean Markdown text report."""
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
    """Generate and send a visual report card, falling back to text."""
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
# Command handlers
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
        "🔹 `/setdevice auto` — Device to run model (auto/cpu/mps/cuda)\n"
        "🔹 `/setdetectevery 3` — Skip-frame rate (run detection every N frames)\n"
        "🔹 `/setcamera 0` — Camera source (0/IP/RTSP URL)\n"
        "🔹 `/setclips True` — Record crossing clips (True/False)\n"
        "🔹 `/setbuffer 5` — Pre-crossing buffer (seconds)\n"
        "🔹 `/setduration 5` — Post-crossing duration (seconds)\n"
        "🔹 `/setgui True` — Show local GUI window (True/False)\n"
        "🔹 `/setgrayscale True` — Grayscale mode (True/False)\n"
        "🔹 `/setslow 1.0` — Playback speed multiplier (1.0/0.5)\n"
        "🔹 `/settimemode auto` — TimeMode classification (auto/day/night)\n"
        "🔹 `/restart` — Restart tracker with new settings\n\n"
        "*⚙️ Tracker Settings:*\n"
        "🔹 `/settrackertype bytetrack` — Tracker algorithm type\n"
        "🔹 `/settrackhigh 0.25` — High confidence detection threshold\n"
        "🔹 `/settracklow 0.1` — Low confidence detection threshold\n"
        "🔹 `/setnewtrack 0.25` — Score threshold to start a track\n"
        "🔹 `/settrackbuffer 150` — Frames to keep lost tracks active\n"
        "🔹 `/setmatchthresh 0.8` — Association IoU threshold\n"
        "🔹 `/setfusescore True` — Fuse detection score with track (True/False)\n\n"
        "*🎨 Styling & HUD:*\n"
        "🔹 `/sethudwidth 360` — HUD box width\n"
        "🔹 `/sethudheight 100` — HUD box height\n"
        "🔹 `/sethudopacity 0.65` — HUD opacity (0.0–1.0)\n"
        "🔹 `/sethudbg 0,0,0` — HUD background color (BGR)\n"
        "🔹 `/sethudtext 255,255,255` — HUD text color (BGR)\n"
        "🔹 `/setboxcolor 255,0,255` — Bounding box color (BGR)\n"
        "🔹 `/setgatecolor 255,0,0` — Gate line color (BGR)\n"
        "🔹 `/setgatethick 3` — Gate line thickness\n"
        "🔹 `/setnightthresh 60` — Night mode threshold (0–255)"
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
        "*🔍 Detection & Hardware:*\n"
        f"  Confidence: `{cfg['CONFIDENCE_THRESHOLD']}`\n"
        f"  Device: `{cfg['DEVICE']}`\n"
        f"  Detect Every: `{cfg['DETECT_EVERY']} frames`\n\n"
        "*⚙️ Tracker Settings:*\n"
        f"  Tracker Type: `{cfg['TRACKER_TYPE']}`\n"
        f"  Track High Thresh: `{cfg['TRACK_HIGH_THRESH']}`\n"
        f"  Track Low Thresh: `{cfg['TRACK_LOW_THRESH']}`\n"
        f"  New Track Thresh: `{cfg['NEW_TRACK_THRESH']}`\n"
        f"  Track Buffer: `{cfg['TRACK_BUFFER']} frames`\n"
        f"  Match Thresh: `{cfg['MATCH_THRESH']}`\n"
        f"  Fuse Score: `{cfg['FUSE_SCORE']}`\n\n"
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
        "*🎨 Styling & HUD:*\n"
        f"  HUD Width: `{cfg['HUD_WIDTH']}`\n"
        f"  HUD Height: `{cfg['HUD_HEIGHT']}`\n"
        f"  HUD Opacity: `{cfg['HUD_OPACITY']}`\n"
        f"  HUD BG Color: `{cfg['HUD_BACKGROUND_COLOR']}`\n"
        f"  HUD Text Color: `{cfg['HUD_TEXT_COLOR']}`\n"
        f"  Box Color: `{cfg['BOX_COLOR_DEFAULT']}`\n"
        f"  Gate Color: `{cfg['GATE_LINE_COLOR']}`\n"
        f"  Gate Thickness: `{cfg['GATE_LINE_THICKNESS']}`\n"
        f"  Night Threshold: `{cfg['NIGHT_BRIGHTNESS_THRESHOLD']}`\n\n"
        f"*📡 System:*\n"
        f"  {tracker_status}\n\n"
        "_Use_ `/setline`, `/setangle`, `/setdir`, `/setconf`, `/setcamera` "
        "_or styling/tracker commands to change settings, then_ `/restart` _to apply._"
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


def _handle_setclips(chat_id: int | str, text: str) -> None:
    """Set whether to record event clips (True/False)."""
    parts = text.split()
    if len(parts) < 2 or parts[1].lower() not in ["true", "false", "1", "0"]:
        send_reply(chat_id, "❌ Usage: `/setclips True` or `/setclips False` (saves short MP4 clips of crossings).")
        return
    val = "True" if parts[1].lower() in ["true", "1"] else "False"
    config_manager.update_env_value("RECORD_CLIPS", val)
    send_reply(chat_id, f"✅ Record clips set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_setbuffer(chat_id: int | str, text: str) -> None:
    """Set pre-event recording buffer seconds."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setbuffer 5` (seconds to capture before gate crossing).")
        return
    try:
        val = int(parts[1])
        if val < 0 or val > 30:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid number. Must be an integer between 0 and 30.")
        return
    config_manager.update_env_value("CLIP_BUFFER_SECONDS", str(val))
    send_reply(chat_id, f"✅ Clip pre-buffer set to `{val}s`\n_Run_ `/restart` _to apply._")


def _handle_setduration(chat_id: int | str, text: str) -> None:
    """Set post-event recording duration seconds."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setduration 5` (seconds to capture after gate crossing).")
        return
    try:
        val = int(parts[1])
        if val < 0 or val > 30:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid number. Must be an integer between 0 and 30.")
        return
    config_manager.update_env_value("CLIP_DURATION_SECONDS", str(val))
    send_reply(chat_id, f"✅ Clip post-duration set to `{val}s`\n_Run_ `/restart` _to apply._")


def _handle_setgui(chat_id: int | str, text: str) -> None:
    """Set whether to show the local GUI window (True/False)."""
    parts = text.split()
    if len(parts) < 2 or parts[1].lower() not in ["true", "false", "1", "0"]:
        send_reply(chat_id, "❌ Usage: `/setgui True` or `/setgui False` (displays GUI window on tracker machine).")
        return
    val = "True" if parts[1].lower() in ["true", "1"] else "False"
    config_manager.update_env_value("SHOW_GUI", val)
    send_reply(chat_id, f"✅ Show GUI set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_setgrayscale(chat_id: int | str, text: str) -> None:
    """Set whether to run tracking in grayscale (True/False)."""
    parts = text.split()
    if len(parts) < 2 or parts[1].lower() not in ["true", "false", "1", "0"]:
        send_reply(chat_id, "❌ Usage: `/setgrayscale True` or `/setgrayscale False` (grayscale preprocessing).")
        return
    val = "True" if parts[1].lower() in ["true", "1"] else "False"
    config_manager.update_env_value("GRAYSCALE", val)
    send_reply(chat_id, f"✅ Grayscale mode set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_setslow(chat_id: int | str, text: str) -> None:
    """Set processing speed multiplier (1.0 or 0.5)."""
    parts = text.split()
    if len(parts) < 2 or parts[1] not in ["1.0", "0.5", "1", "0.5"]:
        send_reply(chat_id, "❌ Usage: `/setslow 1.0` (normal) or `/setslow 0.5` (half-speed simulation).")
        return
    val = "0.5" if parts[1] == "0.5" else "1.0"
    config_manager.update_env_value("SLOW_SPEED", val)
    send_reply(chat_id, f"✅ Video speed multiplier set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_settimemode(chat_id: int | str, text: str) -> None:
    """Set environment mode classification (auto/day/night)."""
    parts = text.split()
    modes = ["auto", "day", "night"]
    if len(parts) < 2 or parts[1].lower() not in modes:
        send_reply(chat_id, f"❌ Usage: `/settimemode auto` | `day` | `night` (brightness-sensitive mode).")
        return
    val = parts[1].lower()
    config_manager.update_env_value("TIME_MODE", val)
    send_reply(chat_id, f"✅ Time Mode set to `{val}`\n_Run_ `/restart` _to apply._")


def _validate_color(text: str) -> bool:
    """Helper to validate if a string represents a B,G,R color."""
    try:
        parts = [int(p.strip()) for p in text.split(",")]
        return len(parts) == 3 and all(0 <= p <= 255 for p in parts)
    except ValueError:
        return False


def _handle_sethudwidth(chat_id: int | str, text: str) -> None:
    """Set HUD width (positive integer)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/sethudwidth 360`\nValue must be a positive integer.")
        return
    try:
        value = int(parts[1])
        if value <= 0 or value > 2000:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid HUD width. Must be an integer between 1 and 2000.")
        return
    config_manager.update_env_value("HUD_WIDTH", str(value))
    send_reply(chat_id, f"✅ HUD width set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_sethudheight(chat_id: int | str, text: str) -> None:
    """Set HUD height (positive integer)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/sethudheight 100`\nValue must be a positive integer.")
        return
    try:
        value = int(parts[1])
        if value <= 0 or value > 1000:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid HUD height. Must be an integer between 1 and 1000.")
        return
    config_manager.update_env_value("HUD_HEIGHT", str(value))
    send_reply(chat_id, f"✅ HUD height set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_sethudopacity(chat_id: int | str, text: str) -> None:
    """Set HUD opacity (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/sethudopacity 0.65`\nValue must be between 0.0 and 1.0.")
        return
    try:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid opacity. Must be a float between 0.0 and 1.0.")
        return
    config_manager.update_env_value("HUD_OPACITY", str(value))
    send_reply(chat_id, f"✅ HUD opacity set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_sethudbg(chat_id: int | str, text: str) -> None:
    """Set HUD background color in B,G,R format."""
    parts = text.split()
    if len(parts) < 2 or not _validate_color(parts[1]):
        send_reply(chat_id, "❌ Usage: `/sethudbg 0,0,0`\nValue must be B,G,R format (three integers 0-255 separated by commas).")
        return
    value = parts[1].strip()
    config_manager.update_env_value("HUD_BACKGROUND_COLOR", value)
    send_reply(chat_id, f"✅ HUD background color set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_sethudtext(chat_id: int | str, text: str) -> None:
    """Set HUD text color in B,G,R format."""
    parts = text.split()
    if len(parts) < 2 or not _validate_color(parts[1]):
        send_reply(chat_id, "❌ Usage: `/sethudtext 255,255,255`\nValue must be B,G,R format (three integers 0-255 separated by commas).")
        return
    value = parts[1].strip()
    config_manager.update_env_value("HUD_TEXT_COLOR", value)
    send_reply(chat_id, f"✅ HUD text color set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setboxcolor(chat_id: int | str, text: str) -> None:
    """Set default bounding box color in B,G,R format."""
    parts = text.split()
    if len(parts) < 2 or not _validate_color(parts[1]):
        send_reply(chat_id, "❌ Usage: `/setboxcolor 255,0,255`\nValue must be B,G,R format (three integers 0-255 separated by commas).")
        return
    value = parts[1].strip()
    config_manager.update_env_value("BOX_COLOR_DEFAULT", value)
    send_reply(chat_id, f"✅ Bounding box color set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setgatecolor(chat_id: int | str, text: str) -> None:
    """Set gate line color in B,G,R format."""
    parts = text.split()
    if len(parts) < 2 or not _validate_color(parts[1]):
        send_reply(chat_id, "❌ Usage: `/setgatecolor 255,0,0`\nValue must be B,G,R format (three integers 0-255 separated by commas).")
        return
    value = parts[1].strip()
    config_manager.update_env_value("GATE_LINE_COLOR", value)
    send_reply(chat_id, f"✅ Gate line color set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setgatethick(chat_id: int | str, text: str) -> None:
    """Set gate line thickness (positive integer)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setgatethick 3`\nValue must be a positive integer.")
        return
    try:
        value = int(parts[1])
        if value <= 0 or value > 20:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid thickness. Must be an integer between 1 and 20.")
        return
    config_manager.update_env_value("GATE_LINE_THICKNESS", str(value))
    send_reply(chat_id, f"✅ Gate line thickness set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setnightthresh(chat_id: int | str, text: str) -> None:
    """Set night mode brightness threshold (0 to 255)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setnightthresh 60`\nValue must be between 0 and 255.")
        return
    try:
        value = int(parts[1])
        if not 0 <= value <= 255:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid threshold. Must be an integer between 0 and 255.")
        return
    config_manager.update_env_value("NIGHT_BRIGHTNESS_THRESHOLD", str(value))
    send_reply(chat_id, f"✅ Night brightness threshold set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setdevice(chat_id: int | str, text: str) -> None:
    """Set model execution device (auto/cpu/mps/cuda)."""
    parts = text.split()
    valid_devices = ["auto", "cpu", "mps", "cuda"]
    if len(parts) < 2 or parts[1].lower() not in valid_devices:
        send_reply(chat_id, f"❌ Usage: `/setdevice auto` | `cpu` | `mps` | `cuda` (hardware target).")
        return
    val = parts[1].lower()
    config_manager.update_env_value("DEVICE", val)
    send_reply(chat_id, f"✅ Device set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_setdetectevery(chat_id: int | str, text: str) -> None:
    """Set detection frequency skip frame rate (positive integer)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setdetectevery 3` (run detection every N frames).")
        return
    try:
        value = int(parts[1])
        if value <= 0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid frame rate. Must be a positive integer >= 1.")
        return
    config_manager.update_env_value("DETECT_EVERY", str(value))
    send_reply(chat_id, f"✅ Detection skip rate set to every `{value}` frame(s)\n_Run_ `/restart` _to apply._")


def _handle_settrackertype(chat_id: int | str, text: str) -> None:
    """Set tracker algorithm type (e.g. bytetrack)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/settrackertype bytetrack`")
        return
    val = parts[1].strip()
    config_manager.update_env_value("TRACKER_TYPE", val)
    send_reply(chat_id, f"✅ Tracker type set to `{val}`\n_Run_ `/restart` _to apply._")


def _handle_settrackhigh(chat_id: int | str, text: str) -> None:
    """Set high-confidence detection tracking threshold (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/settrackhigh 0.25`\nValue must be between 0.0 and 1.0.")
        return
    try:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid value. Must be a float between 0.0 and 1.0.")
        return
    config_manager.update_env_value("TRACK_HIGH_THRESH", str(value))
    send_reply(chat_id, f"✅ High tracking threshold set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_settracklow(chat_id: int | str, text: str) -> None:
    """Set low-confidence detection tracking threshold (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/settracklow 0.1`\nValue must be between 0.0 and 1.0.")
        return
    try:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid value. Must be a float between 0.0 and 1.0.")
        return
    config_manager.update_env_value("TRACK_LOW_THRESH", str(value))
    send_reply(chat_id, f"✅ Low tracking threshold set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setnewtrack(chat_id: int | str, text: str) -> None:
    """Set score threshold to start a track (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setnewtrack 0.25`\nValue must be between 0.0 and 1.0.")
        return
    try:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid value. Must be a float between 0.0 and 1.0.")
        return
    config_manager.update_env_value("NEW_TRACK_THRESH", str(value))
    send_reply(chat_id, f"✅ New track threshold set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_settrackbuffer(chat_id: int | str, text: str) -> None:
    """Set track buffer size in frames (positive integer)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/settrackbuffer 150`\nValue must be a positive integer.")
        return
    try:
        value = int(parts[1])
        if value <= 0 or value > 5000:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid buffer size. Must be an integer between 1 and 5000.")
        return
    config_manager.update_env_value("TRACK_BUFFER", str(value))
    send_reply(chat_id, f"✅ Track buffer set to `{value}` frames\n_Run_ `/restart` _to apply._")


def _handle_setmatchthresh(chat_id: int | str, text: str) -> None:
    """Set tracker match threshold IoU (0.0 to 1.0)."""
    parts = text.split()
    if len(parts) < 2:
        send_reply(chat_id, "❌ Usage: `/setmatchthresh 0.8`\nValue must be between 0.0 and 1.0.")
        return
    try:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError
    except ValueError:
        send_reply(chat_id, "❌ Invalid value. Must be a float between 0.0 and 1.0.")
        return
    config_manager.update_env_value("MATCH_THRESH", str(value))
    send_reply(chat_id, f"✅ Match threshold set to `{value}`\n_Run_ `/restart` _to apply._")


def _handle_setfusescore(chat_id: int | str, text: str) -> None:
    """Set whether to fuse detection score with track (True/False)."""
    parts = text.split()
    if len(parts) < 2 or parts[1].lower() not in ["true", "false", "1", "0"]:
        send_reply(chat_id, "❌ Usage: `/setfusescore True` or `/setfusescore False`.")
        return
    val = "True" if parts[1].lower() in ["true", "1"] else "False"
    config_manager.update_env_value("FUSE_SCORE", val)
    send_reply(chat_id, f"✅ Fuse score set to `{val}`\n_Run_ `/restart` _to apply._")


# ---------------------------------------------------------------------------
# Command → handler dispatch table
# ---------------------------------------------------------------------------

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
    "/setdevice": _handle_setdevice,
    "/setdetectevery": _handle_setdetectevery,
    "/setcamera": _handle_setcamera,
    "/setclips": _handle_setclips,
    "/setbuffer": _handle_setbuffer,
    "/setduration": _handle_setduration,
    "/setgui": _handle_setgui,
    "/setgrayscale": _handle_setgrayscale,
    "/setslow": _handle_setslow,
    "/settimemode": _handle_settimemode,
    "/sethudwidth": _handle_sethudwidth,
    "/sethudheight": _handle_sethudheight,
    "/sethudopacity": _handle_sethudopacity,
    "/sethudbg": _handle_sethudbg,
    "/sethudtext": _handle_sethudtext,
    "/setboxcolor": _handle_setboxcolor,
    "/setgatecolor": _handle_setgatecolor,
    "/setgatethick": _handle_setgatethick,
    "/setnightthresh": _handle_setnightthresh,
    "/settrackertype": _handle_settrackertype,
    "/settrackhigh": _handle_settrackhigh,
    "/settracklow": _handle_settracklow,
    "/setnewtrack": _handle_setnewtrack,
    "/settrackbuffer": _handle_settrackbuffer,
    "/setmatchthresh": _handle_setmatchthresh,
    "/setfusescore": _handle_setfusescore,
    "/restart": _handle_restart,
}
