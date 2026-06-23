"""
config_manager.py — Remote Configuration Manager

Reads and writes settings in the .env file, and provides
a mechanism to restart the YOLO tracker process so that
configuration changes take effect.

Used by the Telegram bot to handle /config, /setline, /setangle,
/setdir, /setconf, /setcamera, and /restart commands.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Optional

import dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
TRACKER_PID_FILE = os.path.join(PROJECT_ROOT, ".tracker.pid")


# ---------------------------------------------------------------------------
# .env Read / Write
# ---------------------------------------------------------------------------

def read_env_value(key: str) -> Optional[str]:
    """Read a single value from the .env file.

    Returns:
        The value string, or ``None`` if the key is not found.
    """
    if not os.path.exists(ENV_PATH):
        return None

    with open(ENV_PATH, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            k, _, v = stripped.partition("=")
            if k.strip() == key:
                return v.strip()
    return None


def update_env_value(key: str, value: str) -> bool:
    """Update (or append) a key-value pair in the .env file.

    Preserves all comments, ordering, and other keys.

    Args:
        key: The environment variable name.
        value: The new value to set.

    Returns:
        ``True`` if the file was updated successfully.
    """
    if not os.path.exists(ENV_PATH):
        return False

    with open(ENV_PATH, "r") as f:
        lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            if k.strip() == key:
                new_lines.append(f"{key}={value}\n")
                found = True
                continue
        new_lines.append(line)

    # If the key didn't exist, append it
    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(new_lines)

    # Also update the live os.environ so that modules using os.environ.get()
    # pick up the change immediately (useful for modules that re-read on demand).
    os.environ[key] = value

    return True


def get_current_config() -> dict[str, str]:
    """Return all configurable settings as a dict.

    Reads directly from the .env file (not from os.environ) so the
    values always reflect what's on disk.
    """
    keys = [
        "LINE_POS",
        "LINE_ANGLE",
        "IN_DIRECTION",
        "CONFIDENCE_THRESHOLD",
        "CAMERA_IP",
        "RECORD_CLIPS",
        "CLIP_BUFFER_SECONDS",
        "CLIP_DURATION_SECONDS",
        "SHOW_GUI",
        "GRAYSCALE",
        "SLOW_SPEED",
        "TIME_MODE",
        "HUD_WIDTH",
        "HUD_HEIGHT",
        "HUD_OPACITY",
        "HUD_BACKGROUND_COLOR",
        "HUD_TEXT_COLOR",
        "BOX_COLOR_DEFAULT",
        "GATE_LINE_COLOR",
        "GATE_LINE_THICKNESS",
        "NIGHT_BRIGHTNESS_THRESHOLD",
        "DEVICE",
        "DETECT_EVERY",
        "TRACKER_TYPE",
        "TRACK_HIGH_THRESH",
        "TRACK_LOW_THRESH",
        "NEW_TRACK_THRESH",
        "TRACK_BUFFER",
        "MATCH_THRESH",
        "FUSE_SCORE",
    ]
    config: dict[str, str] = {}
    for key in keys:
        val = read_env_value(key)
        config[key] = val if val is not None else "(not set)"
    return config


# ---------------------------------------------------------------------------
# Tracker Process Management
# ---------------------------------------------------------------------------

def _read_tracker_pid() -> Optional[int]:
    """Read the tracker PID from the PID file."""
    if not os.path.exists(TRACKER_PID_FILE):
        return None
    try:
        with open(TRACKER_PID_FILE, "r") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is still alive."""
    try:
        os.kill(pid, 0)  # Signal 0 = just check existence
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_tracker(pid: int) -> bool:
    """Gracefully stop the tracker process."""
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait up to 5 seconds for it to stop
        for _ in range(50):
            if not _is_process_running(pid):
                return True
            time.sleep(0.1)
        # Force kill if still running
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
        return not _is_process_running(pid)
    except (OSError, ProcessLookupError):
        return True  # Already dead


def restart_tracker() -> tuple[bool, str]:
    """Restart the YOLO tracker process.

    1. Reads the PID file written by main.py.
    2. Kills the old tracker process (if running).
    3. Starts a new tracker process in the background.
    4. Returns (success, message).

    Returns:
        A tuple of ``(success: bool, message: str)``.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)

    # 1. Kill existing tracker
    old_pid = _read_tracker_pid()
    if old_pid and _is_process_running(old_pid):
        killed = _kill_tracker(old_pid)
        if not killed:
            return False, f"Failed to stop old tracker (PID {old_pid})."
        print(f"🛑 Stopped old tracker process (PID {old_pid}).")
    else:
        print("ℹ️ No running tracker found. Starting fresh.")

    # Clean up stale PID file
    if os.path.exists(TRACKER_PID_FILE):
        try:
            os.remove(TRACKER_PID_FILE)
        except OSError:
            pass

    # 2. Reload .env so the new process picks up fresh values
    dotenv.load_dotenv(ENV_PATH, override=True)

    # 3. Start new tracker process
    log_file = os.path.join(LOGS_DIR, "tracker.log")
    try:
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=PROJECT_ROOT,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        # Wait a moment to check it didn't crash immediately
        time.sleep(2)
        if proc.poll() is not None:
            return False, f"Tracker process exited immediately (code {proc.returncode})."

        return True, f"Tracker restarted successfully (PID {proc.pid})."

    except Exception as exc:
        return False, f"Failed to start tracker: {exc}"


def get_tracker_status() -> str:
    """Return a human-readable status of the tracker process."""
    pid = _read_tracker_pid()
    if pid is None:
        return "⚫ Tracker: No PID file found (not running or started externally)"
    if _is_process_running(pid):
        return f"🟢 Tracker: Running (PID {pid})"
    return f"🔴 Tracker: Not running (stale PID {pid})"
