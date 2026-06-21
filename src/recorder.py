import os
import cv2
import uuid
import threading
import time
from datetime import datetime
from collections import deque

try:
    from src import timezone_helper
except ImportError:
    try:
        import timezone_helper
    except ImportError:
        timezone_helper = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_today_date_str() -> str:
    """Return today's date string (YYYY-MM-DD) in the configured timezone."""
    if timezone_helper:
        return timezone_helper.get_local_now().strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def _get_today_events_dir() -> str:
    """Return the path to today's date-based events subfolder, creating it if needed."""
    date_str = _get_today_date_str()
    date_dir = os.path.join("events", date_str)
    os.makedirs(date_dir, exist_ok=True)
    return date_dir


# ---------------------------------------------------------------------------
# Background clip saver + Telegram sender
# ---------------------------------------------------------------------------

_TELEGRAM_MAX_RETRIES = 3
_TELEGRAM_RETRY_DELAY = 5  # seconds between retries


def save_and_alert_clip(rec):
    """
    Background worker thread that compiles buffered frames into an MP4 clip,
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
        if not os.path.exists(clip_filename) or os.path.getsize(clip_filename) < 1024:
            print(f"⚠️ Clip file is too small or missing — skipping Telegram send: {clip_filename}")
            return

        print(f"🎬 Event clip saved: {clip_filename}")

        # 1. Log event to database (uploading to Supabase Storage first if cloud mode is configured)
        db_video_path = clip_filename
        try:
            from backend import database
            if database.is_supabase_configured:
                print(f"☁️ Uploading {clip_filename} to Supabase Storage bucket 'events'...")
                public_url = database.upload_to_supabase_storage(clip_filename)
                if public_url:
                    db_video_path = public_url

            event_id = database.log_event(obj_type, track_id, direction, db_video_path)
            print(f"💾 Logged event to database with ID: {event_id}")
        except Exception as e:
            print(f"❌ Error logging event to database: {e}")

        # 2. Send Video Alert to Telegram Bot (with retry)
        try:
            alert_delay = int(os.environ.get("TELEGRAM_ALERT_DELAY", 0))
            if alert_delay > 0:
                print(f"⏳ Delaying Telegram alert by {alert_delay}s for track #{track_id}...")
                time.sleep(alert_delay)

            from backend import telegram_bot

            # Build caption with local timestamp
            if timezone_helper:
                timestamp_str = timezone_helper.get_local_now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                success = telegram_bot.send_telegram_video(clip_filename, caption=caption)
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
    def __init__(self, fps, clip_before_sec, clip_after_sec):
        self.fps = fps
        self.clip_after_sec = clip_after_sec
        self.record_clips = os.environ.get("RECORD_CLIPS", "True").lower() in ("true", "1", "yes")
        
        buffer_size = int(clip_before_sec * fps)
        self.frame_buffer = deque(maxlen=buffer_size)
        self.active_recordings = []

    def add_frame(self, frame):
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
                threading.Thread(target=save_and_alert_clip, args=(rec,), daemon=True).start()
        self.frame_buffer.append(frame_to_buffer)

    def trigger_recording(self, track_id, class_name, direction, width, height):
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

    def flush(self):
        if self.record_clips and self.active_recordings:
            print(f"\n🧹 Video stream ended. Flushing {len(self.active_recordings)} final active recordings...")
            for rec in self.active_recordings:
                save_and_alert_clip(rec)
            self.active_recordings.clear()
