"""cleanup.py — Daily Event Video Cleanup

Runs a background thread that automatically removes event video folders
from previous days, keeping only today's folder. Designed for long-running
Mac Mini deployments where disk space must be managed.

Date-based folder structure:
    events/
        2026-06-21/
            event_car_in_16_a6ffcfaf.mp4
            event_car_out_4_389ff795.mp4
        2026-06-22/
            ...
"""

import os
import shutil
import threading
import time
from datetime import datetime

from src.timezone_helper import get_today_date_str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EVENTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "events")

# How often to check for old folders (in seconds) — default 1 hour
_CLEANUP_INTERVAL_SEC: int = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", 3600))


# ---------------------------------------------------------------------------
# Core Cleanup Logic
# ---------------------------------------------------------------------------

def cleanup_old_event_folders() -> int:
    """Remove all date-based subdirectories in the events folder

    except for today's folder.

    Also removes any legacy flat video files (not inside a date folder)
    that may exist from before the date-folder migration.

    Returns:
        Number of items removed.
    """
    if not os.path.isdir(EVENTS_DIR):
        return 0

    today = get_today_date_str()
    removed_count = 0

    for entry in os.listdir(EVENTS_DIR):
        entry_path = os.path.join(EVENTS_DIR, entry)

        # Skip .DS_Store and other hidden files
        if entry.startswith("."):
            continue

        # Handle date-based subdirectories (YYYY-MM-DD format)
        if os.path.isdir(entry_path):
            # Check if it looks like a date folder
            try:
                datetime.strptime(entry, "%Y-%m-%d")
            except ValueError:
                continue  # Not a date folder, skip (e.g., "in", "out" folders)

            if entry != today:
                try:
                    shutil.rmtree(entry_path)
                    print(f"🧹 Cleaned up old event folder: {entry}/")
                    removed_count += 1
                except OSError as exc:
                    print(f"⚠️ Failed to remove {entry_path}: {exc}")

        # Handle legacy flat video files (from before date-folder migration)
        elif os.path.isfile(entry_path) and entry.endswith(".mp4"):
            try:
                os.remove(entry_path)
                print(f"🧹 Cleaned up legacy event file: {entry}")
                removed_count += 1
            except OSError as exc:
                print(f"⚠️ Failed to remove {entry_path}: {exc}")

    return removed_count


# ---------------------------------------------------------------------------
# Background Thread
# ---------------------------------------------------------------------------

def _cleanup_loop() -> None:
    """Background loop that runs cleanup periodically."""
    while True:
        try:
            today = get_today_date_str()
            removed = cleanup_old_event_folders()
            if removed > 0:
                print(f"🧹 Daily cleanup complete: removed {removed} old items. Keeping today ({today}).")
            else:
                print(f"🧹 Daily cleanup check: nothing to remove. Today is {today}.")
        except Exception as exc:
            print(f"❌ Cleanup error: {exc}")

        time.sleep(_CLEANUP_INTERVAL_SEC)


def start_cleanup_thread() -> threading.Thread:
    """Start the daily cleanup background thread.

    Runs an immediate cleanup on startup, then checks periodically.

    Returns:
        The started daemon thread.
    """
    print(f"🧹 Starting daily event cleanup service (interval: {_CLEANUP_INTERVAL_SEC}s)...")

    # Run one immediate cleanup on startup
    try:
        removed = cleanup_old_event_folders()
        today = get_today_date_str()
        if removed > 0:
            print(f"🧹 Startup cleanup: removed {removed} old items. Keeping today ({today}).")
        else:
            print(f"🧹 Startup cleanup: events folder is clean. Today is {today}.")
    except Exception as exc:
        print(f"⚠️ Startup cleanup warning: {exc}")

    thread = threading.Thread(target=_cleanup_loop, daemon=True, name="EventCleanup")
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running manual cleanup...")
    removed_items = cleanup_old_event_folders()
    print(f"Done. Removed {removed_items} items.")
