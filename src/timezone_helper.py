"""
timezone_helper.py — Timezone Resolution and Local Time Utilities

Provides timezone-aware datetime operations for the warehouse tracking
system. Supports configuration via TIMEZONE or COUNTRY environment
variables, with a fallback to Asia/Phnom_Penh (GMT+7).
"""

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

# ---------------------------------------------------------------------------
# Country-to-IANA timezone mapping
# ---------------------------------------------------------------------------

COUNTRY_MAP: dict[str, str] = {
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
MANUAL_OFFSETS: dict[str, int] = {
    "Asia/Phnom_Penh": 7,
    "Asia/Bangkok": 7,
    "Asia/Ho_Chi_Minh": 7,
    "Asia/Jakarta": 7,
    "Asia/Singapore": 8,
    "Asia/Kuala_Lumpur": 8,
    "America/New_York": -5,
    "Europe/London": 0,
}

# Default timezone when nothing is configured
_DEFAULT_TIMEZONE = "Asia/Phnom_Penh"
_DEFAULT_OFFSET_HOURS = 7


# ---------------------------------------------------------------------------
# Timezone Resolution
# ---------------------------------------------------------------------------

def resolve_timezone_name() -> str:
    """Resolve the configured timezone name from environment variables.

    Checks ``TIMEZONE`` first, then ``COUNTRY`` (mapped via ``COUNTRY_MAP``),
    and defaults to ``Asia/Phnom_Penh`` if neither is set.
    """
    # Explicit timezone override
    tz_env = os.environ.get("TIMEZONE", "").strip()
    if tz_env:
        return tz_env

    # Country-based lookup
    country_env = os.environ.get("COUNTRY", "").strip().lower()
    if country_env and country_env in COUNTRY_MAP:
        return COUNTRY_MAP[country_env]

    return _DEFAULT_TIMEZONE


def get_timezone_object() -> datetime.timezone:
    """Return a timezone object for the configured locale.

    Uses ``zoneinfo.ZoneInfo`` when available, falling back to a fixed
    UTC offset derived from ``MANUAL_OFFSETS``.
    """
    tz_name = resolve_timezone_name()
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    # Fallback to fixed offset timezone
    offset_hours = MANUAL_OFFSETS.get(tz_name, _DEFAULT_OFFSET_HOURS)
    return datetime.timezone(timedelta(hours=offset_hours))


# ---------------------------------------------------------------------------
# Public Datetime Helpers
# ---------------------------------------------------------------------------

def get_local_now() -> datetime.datetime:
    """Return the current datetime in the configured local timezone."""
    tz_obj = get_timezone_object()
    return datetime.datetime.now(tz_obj)


def get_today_date_str() -> str:
    """Return today's date as ``YYYY-MM-DD`` in the configured timezone.

    This is the single source of truth for date-string generation,
    used by ``recorder.py`` and ``cleanup.py``.
    """
    return get_local_now().strftime("%Y-%m-%d")


def to_local_datetime(dt: datetime.datetime) -> datetime.datetime:
    """Convert a naive or aware datetime to the configured local timezone.

    Naive datetimes are assumed to be UTC (Supabase convention).
    """
    tz_obj = get_timezone_object()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(tz_obj)


def get_timezone_offset_seconds() -> int:
    """Return the UTC offset in seconds for the configured timezone."""
    now = datetime.datetime.now()
    tz_obj = get_timezone_object()
    if isinstance(tz_obj, datetime.timezone):
        return int(tz_obj.utcoffset(now).total_seconds())

    local_now = now.astimezone(tz_obj)
    return int(local_now.utcoffset().total_seconds())


def get_timezone_offset_hours() -> float:
    """Return the UTC offset in hours (e.g. ``7.0`` for GMT+7)."""
    return get_timezone_offset_seconds() / 3600.0
