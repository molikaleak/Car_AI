import os
import datetime
from datetime import timedelta

# Try importing zoneinfo (available in Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback to pytz if zoneinfo is not available (older Python versions)
    try:
        from pytz import timezone as ZoneInfo
    except ImportError:
        ZoneInfo = None

# Country to IANA Timezone mapping
COUNTRY_MAP = {
    "cambodia": "Asia/Phnom_Penh",
    "kh": "Asia/Phnom_Penh",
    "khmer": "Asia/Phnom_Penh",
    "thailand": "Asia/Bangkok",
    "th": "Asia/Bangkok",
    "vietnam": "Asia/Ho_Chi_Minh",
    "vn": "Asia/Ho_Chi_Minh",
    "singapore": "Asia/Singapore",
    "sg": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "my": "Asia/Kuala_Lumpur",
    "indonesia": "Asia/Jakarta",
    "id": "Asia/Jakarta",
    "united states": "America/New_York",
    "us": "America/New_York",
    "usa": "America/New_York",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "england": "Europe/London",
}

# Common manual offsets in hours for fallback if zoneinfo/pytz fails
MANUAL_OFFSETS = {
    "Asia/Phnom_Penh": 7,
    "Asia/Bangkok": 7,
    "Asia/Ho_Chi_Minh": 7,
    "Asia/Jakarta": 7,
    "Asia/Singapore": 8,
    "Asia/Kuala_Lumpur": 8,
    "America/New_York": -5,
    "Europe/London": 0
}

def resolve_timezone_name():
    """Resolves the configured timezone name from environment variables."""
    # Load explicit timezone override
    tz_env = os.environ.get("TIMEZONE", "").strip()
    if tz_env:
        return tz_env
        
    # Check country-based lookup
    country_env = os.environ.get("COUNTRY", "").strip().lower()
    if country_env:
        if country_env in COUNTRY_MAP:
            return COUNTRY_MAP[country_env]
            
    # Default to Cambodia Time (GMT+7)
    return "Asia/Phnom_Penh"

def get_timezone_object():
    """Returns a timezone object or datetime.timezone offset fallback."""
    tz_name = resolve_timezone_name()
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
            
    # Fallback to fixed offset timezone if ZoneInfo is not available or fails
    offset_hours = MANUAL_OFFSETS.get(tz_name, 7) # Default to GMT+7 (Cambodia/Thailand)
    return datetime.timezone(timedelta(hours=offset_hours))

def get_local_now():
    """Returns the current datetime in the configured local timezone."""
    tz_obj = get_timezone_object()
    return datetime.datetime.now(tz_obj)

def to_local_datetime(dt):
    """Converts a naive or aware datetime to the configured local timezone."""
    tz_obj = get_timezone_object()
    if dt.tzinfo is None:
        # If naive, assume UTC and localize it (Supabase standard)
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(tz_obj)

def get_timezone_offset_seconds():
    """Returns the offset in seconds from UTC for the local timezone."""
    now = datetime.datetime.now()
    tz_obj = get_timezone_object()
    # If using fixed offset fallback
    if isinstance(tz_obj, datetime.timezone):
        return int(tz_obj.utcoffset(now).total_seconds())
        
    # Otherwise using ZoneInfo/pytz
    local_now = now.astimezone(tz_obj)
    return int(local_now.utcoffset().total_seconds())

def get_timezone_offset_hours():
    """Returns the offset in hours from UTC (e.g. 7.0 for GMT+7)."""
    return get_timezone_offset_seconds() / 3600.0
