"""recorder.py — Video Event Recorder

Captures video clips preceding and succeeding crossing events, saves them locally,
logs the event to database, and publishes notifications to Telegram.
"""

from __future__ import annotations

from collections import deque
import os
import threading
import time
from typing import Any
import uuid

import cv2
import numpy as np

from src.timezone_helper import get_local_now, get_today_date_str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_today_events_dir() -> str:
    """Return the path to today's date-based events subfolder, creating it if needed."""
    date_str = get_today_date_str()
    date_dir = os.path.join("events", date_str)
    os.makedirs(date_dir, exist_ok=True)
    return date_dir


# ---------------------------------------------------------------------------
# Background clip saver + Telegram sender
# ---------------------------------------------------------------------------

_TELEGRAM_MAX_RETRIES: int = 3
_TELEGRAM_RETRY_DELAY: int = 5  # seconds between retries
MIN_CLIP_FILE_SIZE: int = 1024


def save_and_alert_clip(rec: dict[str, Any]) -> None:
    """Background worker thread that compiles buffered frames into an MP4 clip,

    logs the event to Supabase Postgres, and sends a Telegram alert.

    Clips are saved into date-based folders: events/YYYY-MM-DD/
    """
    track_id = rec["track_id"]
    obj_type = rec["object_type"]
    direction = rec["direction"]
    frames = rec["frames"]
    fps = rec["fps"]
    w, h = rec["width"], rec["height"]

    # Skip if no frames were captured (prevents empty/corrupt 48-byte files)
    if not frames:
        print(f"⚠️ No frames captured for track #{track_id} — skipping clip generation.")
        return

    # Save clip into today's date folder: events/YYYY-MM-DD/
    date_dir = _get_today_events_dir()
    clip_filename = os.path.join(
        date_dir,
        f"event_{obj_type.lower()}_{direction.lower()}_{track_id}_{uuid.uuid4().hex[:8]}.mp4",
    )

    try:
        # Write frames to MP4 file
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(clip_filename, fourcc, fps, (w, h))
        for f in frames:
            out.write(f)
        out.release()

        # Validate the file was actually written
        if not os.path.exists(clip_filename) or os.path.getsize(clip_filename) < MIN_CLIP_FILE_SIZE:
            print(f"⚠️ Clip file is too small or missing — skipping Telegram send: {clip_filename}")
            return

        print(f"🎬 Event clip saved: {clip_filename}")

        # 1. Log event to database
        try:
            from backend import database
            event_id = database.log_event(obj_type, track_id, direction, clip_filename)
            print(f"💾 Logged event to database with ID: {event_id}")
        except Exception as e:
            print(f"❌ Error logging event to database: {e}")

        # 2. Send Video Alert to Telegram Bot (with retry)
        try:
            alert_delay = int(os.environ.get("TELEGRAM_ALERT_DELAY", 0))
            if alert_delay > 0:
                print(f"⏳ Delaying Telegram alert by {alert_delay}s for track #{track_id}...")
                time.sleep(alert_delay)

            from backend.telegram_client import send_telegram_video

            # Build caption with local timestamp
            timestamp_str = get_local_now().strftime("%Y-%m-%d %H:%M:%S")

            caption = (
                f"🚗 *WAREHOUSE GATEWAY ACTIVITY*\n\n"
                f"🔹 *Vehicle:* {obj_type.upper()}\n"
                f"🔹 *Track ID:* #{track_id}\n"
                f"🔹 *Direction:* {direction}\n"
                f"🔹 *Time:* {timestamp_str}"
            )

            # Retry loop — network issues on Mac Mini can cause transient failures
            success = False
            for attempt in range(1, _TELEGRAM_MAX_RETRIES + 1):
                success = send_telegram_video(clip_filename, caption=caption)
                if success:
                    print(f"✈️ Telegram video sent for track #{track_id} (attempt {attempt}).")
                    break
                else:
                    print(f"⚠️ Telegram send attempt {attempt}/{_TELEGRAM_MAX_RETRIES} failed for track #{track_id}.")
                    if attempt < _TELEGRAM_MAX_RETRIES:
                        time.sleep(_TELEGRAM_RETRY_DELAY)

            if not success:
                print(f"❌ All {_TELEGRAM_MAX_RETRIES} Telegram send attempts failed for track #{track_id}.")

        except Exception as e:
            print(f"❌ Error sending Telegram video alert: {e}")

    except Exception as e:
        print(f"❌ Error during clip generation: {e}")


class EventRecorder:
    """Manages recording of activity clips centered around crossing events."""

    def __init__(self, fps: int, clip_before_sec: float, clip_after_sec: float) -> None:
        self.fps = fps
        self.clip_after_sec = clip_after_sec
        self.record_clips = os.environ.get("RECORD_CLIPS", "True").lower() in ("true", "1", "yes")

        buffer_size = int(clip_before_sec * fps)
        self.frame_buffer: deque[np.ndarray] = deque(maxlen=buffer_size)
        self.active_recordings: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []

    def add_frame(self, frame: np.ndarray) -> None:
        """Buffer a video frame and write it to any active recording clips."""
        if not self.record_clips:
            return
        frame_to_buffer = frame.copy()
        for rec in list(self.active_recordings):
            if rec["remaining_frames"] > 0:
                rec["frames"].append(frame_to_buffer)
                rec["remaining_frames"] -= 1
            else:
                self.active_recordings.remove(rec)
                # Spawn background thread to compile video, log to DB, and notify Telegram
                t = threading.Thread(target=save_and_alert_clip, args=(rec,), daemon=True)
                t.start()
                self.threads.append(t)
        self.frame_buffer.append(frame_to_buffer)

    def trigger_recording(
        self, track_id: int, class_name: str, direction: str, width: int, height: int
    ) -> None:
        """Trigger clip capture for a specific event."""
        if not self.record_clips:
            try:
                from backend import database
                database.log_event(class_name, track_id, direction)
            except Exception as e:
                print(f"❌ Error logging event to database: {e}")
            return
        self.active_recordings.append({
            "track_id": track_id,
            "object_type": class_name,
            "direction": direction,
            "frames": list(self.frame_buffer),
            "remaining_frames": int(self.clip_after_sec * self.fps),
            "fps": self.fps,
            "width": width,
            "height": height
        })

    def flush(self) -> None:
        """Flush and compile any currently active recordings."""
        if self.record_clips and self.active_recordings:
            print(f"\n🧹 Video stream ended. Flushing {len(self.active_recordings)} final active recordings...")
            for rec in self.active_recordings:
                save_and_alert_clip(rec)
            self.active_recordings.clear()

        if self.threads:
            print(f"⏳ Waiting for {len(self.threads)} background upload threads to finish...")
            for t in self.threads:
                if t.is_alive():
                    t.join()
            print("✅ All background upload threads finished.")
