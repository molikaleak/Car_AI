"""database.py — Local SQLite Database Layer

Handles all database operations for the car tracking system.
Uses SQLite for reliable local storage on Mac Mini — no network required.

Functions:
    - log_event()          : Insert a new car crossing event
    - get_today_report()   : Aggregate counts for today
    - get_weekly_report()  : Aggregate counts for this week
    - get_monthly_report() : Aggregate counts for this month
    - get_recent_events()  : Fetch last N events
    - get_hourly_report()  : Hourly breakdown for today's chart
"""

import datetime
import os
import sqlite3
import sys
import threading

import dotenv

# Handle imports whether run from project root or backend/
try:
    from src import timezone_helper
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from src import timezone_helper

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

dotenv.load_dotenv()

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH: str = os.path.join(PROJECT_ROOT, "warehouse.db")

# Flag kept for backward compatibility with code that checks this
# (e.g., recorder.py checks is_supabase_configured before uploading)
is_supabase_configured: bool = False

# Thread lock for safe concurrent writes from multiple threads
_db_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Connection Helper
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # enables row["column_name"] access
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent read/write
    conn.execute("PRAGMA busy_timeout=5000")  # wait up to 5s if locked
    return conn


def _init_pool() -> None:
    """Initialize the database and ensure the events table exists.

    Called once at startup. Named _init_pool for backward compatibility
    with main.py which calls database._init_pool().
    """
    try:
        conn = _get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    track_id    INTEGER NOT NULL,
                    direction   TEXT NOT NULL,
                    video_path  TEXT
                )
            """)
            # Index for faster date-based queries (dashboard, reports)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events (timestamp)
            """)
            conn.commit()
        finally:
            conn.close()
        print(f"📁 Database: SQLite ready at {DB_PATH}")
    except Exception as e:
        print(f"❌ Database init failed: {e}")


# ---------------------------------------------------------------------------
# Write Operations
# ---------------------------------------------------------------------------

def log_event(
    object_type: str,
    track_id: int,
    direction: str,
    video_path: str | None = None,
) -> int | None:
    """Insert a new crossing event and return its database ID.

    Args:
        object_type: Always "Car" in our system.
        track_id:    The ByteTrack tracker ID.
        direction:   "IN" or "OUT".
        video_path:  Optional local path to the event clip.

    Returns:
        The new row ID, or None on failure.
    """
    local_now = timezone_helper.get_local_now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with _db_lock:
            conn = _get_connection()
            try:
                cur = conn.execute(
                    """INSERT INTO events (timestamp, object_type, track_id, direction, video_path)
                       VALUES (?, ?, ?, ?, ?)""",
                    (local_now, object_type, track_id, direction, video_path),
                )
                new_id = cur.lastrowid
                conn.commit()
                return new_id
            finally:
                conn.close()
    except Exception as e:
        print(f"❌ log_event error: {e}")
        return None


# ---------------------------------------------------------------------------
# Read Operations — Reports
# ---------------------------------------------------------------------------

def _run_query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return rows as a list of dicts.

    Returns an empty list on any failure.
    """
    try:
        conn = _get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            # Convert sqlite3.Row objects to plain dicts for JSON serialization
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Query error: {e}")
        return []


def get_today_report() -> list[dict]:
    """Aggregate event counts grouped by (object_type, direction) for today."""
    today = timezone_helper.get_local_now().strftime("%Y-%m-%d")
    return _run_query(
        """SELECT object_type, direction, COUNT(*) AS count
           FROM events
           WHERE DATE(timestamp) = ?
           GROUP BY object_type, direction""",
        (today,),
    )


def get_weekly_report() -> list[dict]:
    """Aggregate event counts from Monday 00:00 of the current week."""
    now = timezone_helper.get_local_now()
    monday = (now - datetime.timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    return _run_query(
        """SELECT object_type, direction, COUNT(*) AS count
           FROM events
           WHERE DATE(timestamp) >= ?
           GROUP BY object_type, direction""",
        (monday,),
    )


def get_monthly_report() -> list[dict]:
    """Aggregate event counts from the 1st of the current month."""
    month_start = timezone_helper.get_local_now().strftime("%Y-%m-01")
    return _run_query(
        """SELECT object_type, direction, COUNT(*) AS count
           FROM events
           WHERE DATE(timestamp) >= ?
           GROUP BY object_type, direction""",
        (month_start,),
    )


def get_recent_events(limit: int = 10) -> list[dict]:
    """Return the last N events, newest first."""
    return _run_query(
        """SELECT id,
                  strftime('%Y-%m-%d %H:%M:%S', timestamp) AS timestamp,
                  object_type, track_id, direction, video_path
           FROM events
           ORDER BY id DESC
           LIMIT ?""",
        (limit,),
    )


def get_hourly_report() -> list[dict]:
    """Return today's car events grouped by hour and direction.

    Used by the dashboard chart endpoint.
    """
    today = timezone_helper.get_local_now().strftime("%Y-%m-%d")
    return _run_query(
        """SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour,
                  direction,
                  COUNT(*) AS count
           FROM events
           WHERE DATE(timestamp) = ? AND object_type = 'Car'
           GROUP BY hour, direction
           ORDER BY hour ASC""",
        (today,),
    )


# ---------------------------------------------------------------------------
# Supabase Storage — stub (kept for backward compatibility)
# ---------------------------------------------------------------------------

def upload_to_supabase_storage(local_file_path: str, bucket_name: str = "events") -> str | None:
    """Stub — cloud storage upload is disabled in local SQLite mode.

    Returns None so the caller falls back to local video_path.
    """
    return None


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _init_pool()
    print("\n--- SQLite Database Test ---")
    new_event_id = log_event("Car", 99, "OUT", "events/test.mp4")
    print(f"  Logged event ID: {new_event_id}")
    print(f"  Today report:    {get_today_report()}")
    print(f"  Recent events:   {get_recent_events(3)}")
    print(f"  Hourly report:   {get_hourly_report()}")
