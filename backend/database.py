import os
import sqlite3
import requests
from datetime import datetime, timedelta
import dotenv

# Load environment variables
dotenv.load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse.db")

# Supabase Configurations
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# Check if Supabase is configured
is_supabase_configured = (
    SUPABASE_URL 
    and SUPABASE_KEY 
    and "your_supabase" not in SUPABASE_URL 
    and "your_supabase" not in SUPABASE_KEY
)

if is_supabase_configured:
    print("☁️ Database Mode: SUPABASE cloud database")
else:
    print("📁 Database Mode: LOCAL SQLite database (Supabase credentials not configured)")

# --- SQLite Local Helper Functions ---
def get_sqlite_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes local SQLite database if in SQLite mode."""
    if not is_supabase_configured:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with get_sqlite_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    object_type TEXT NOT NULL,
                    track_id INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    video_path TEXT
                );
            """)
            conn.commit()

# --- Supabase / SQLite Unified API ---

def log_event(object_type, track_id, direction, video_path=None):
    """Logs a crossing event. Sends to Supabase if configured, otherwise falls back to SQLite."""
    local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if is_supabase_configured:
        # Supabase API Insert
        url = f"{SUPABASE_URL}/rest/v1/events"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        payload = {
            "object_type": object_type,
            "track_id": track_id,
            "direction": direction,
            "video_path": video_path
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code in [200, 201]:
                res = r.json()
                if res:
                    return res[0].get("id")
            print(f"⚠️ Supabase insert failed (HTTP {r.status_code}): {r.text}. Falling back to SQLite.")
        except Exception as e:
            print(f"⚠️ Supabase connection error: {e}. Falling back to SQLite.")
            
    # SQLite Fallback
    init_db()
    with get_sqlite_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (timestamp, object_type, track_id, direction, video_path) VALUES (?, ?, ?, ?, ?)",
            (local_now, object_type, track_id, direction, video_path)
        )
        conn.commit()
        return cursor.lastrowid

def get_today_report():
    """Returns the traffic report for today."""
    if is_supabase_configured:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/events?select=object_type,direction&created_at=gte.{today_start}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return group_and_count_events(r.json())
        except Exception as e:
            print(f"⚠️ Supabase query error: {e}. Trying SQLite.")

    # SQLite
    init_db()
    with get_sqlite_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT object_type, direction, COUNT(*) as count 
            FROM events 
            WHERE date(timestamp) = date('now', 'localtime')
            GROUP BY object_type, direction
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_weekly_report():
    """Returns the traffic report for the current week (Monday-Sunday)."""
    if is_supabase_configured:
        # Start of current week (Monday 00:00:00)
        now = datetime.now()
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/events?select=object_type,direction&created_at=gte.{week_start}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return group_and_count_events(r.json())
        except Exception as e:
            print(f"⚠️ Supabase query error: {e}. Trying SQLite.")

    # SQLite
    init_db()
    with get_sqlite_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT object_type, direction, COUNT(*) as count 
            FROM events 
            WHERE strftime('%Y-%W', timestamp, 'localtime') = strftime('%Y-%W', 'now', 'localtime')
            GROUP BY object_type, direction
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_monthly_report():
    """Returns the traffic report for the current month."""
    if is_supabase_configured:
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/events?select=object_type,direction&created_at=gte.{month_start}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                return group_and_count_events(r.json())
        except Exception as e:
            print(f"⚠️ Supabase query error: {e}. Trying SQLite.")

    # SQLite
    init_db()
    with get_sqlite_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT object_type, direction, COUNT(*) as count 
            FROM events 
            WHERE strftime('%Y-%m', timestamp, 'localtime') = strftime('%Y-%m', 'now', 'localtime')
            GROUP BY object_type, direction
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_recent_events(limit=10):
    """Returns the last N events logged in the database."""
    if is_supabase_configured:
        url = f"{SUPABASE_URL}/rest/v1/events?select=id,created_at,object_type,track_id,direction,video_path&order=id.desc&limit={limit}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                events = r.json()
                # Rename 'created_at' key to 'timestamp' to match SQLite structure
                for ev in events:
                    if "created_at" in ev:
                        # Convert ISO format to readable local time format for Telegram bot
                        try:
                            dt = datetime.fromisoformat(ev["created_at"].replace("Z", "+00:00"))
                            ev["timestamp"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            ev["timestamp"] = ev["created_at"]
                return events
        except Exception as e:
            print(f"⚠️ Supabase query error: {e}. Trying SQLite.")

    # SQLite
    init_db()
    with get_sqlite_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, object_type, track_id, direction, video_path 
            FROM events 
            ORDER BY id DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def group_and_count_events(events_list):
    """Helper function to group and sum counts of items in memory."""
    counts = {}
    for row in events_list:
        obj = row.get("object_type", "Object")
        dir_val = row.get("direction", "IN")
        key = (obj, dir_val)
        counts[key] = counts.get(key, 0) + 1
    return [{"object_type": k[0], "direction": k[1], "count": v} for k, v in counts.items()]

if __name__ == "__main__":
    init_db()
    print("Database connection test:")
    res_id = log_event("Car", 99, "OUT", "events/test_supabase.mp4")
    print(f"Logged event successfully. Return ID: {res_id}")
    print("Today's report:", get_today_report())
    print("Recent events:", get_recent_events(3))
