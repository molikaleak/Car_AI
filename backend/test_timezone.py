"""test_timezone.py — Timezone Resolution Verification

Tests that the timezone helper correctly resolves timezones for
various country configurations.
"""

import os
import sys

# Path resolving
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src import timezone_helper


def main() -> None:
    """Test timezone resolution for various country configurations."""
    print("=============================================")
    print("🌐 TIMEZONE RESOLUTION TEST")
    print("=============================================")
    tz_name = timezone_helper.resolve_timezone_name()
    print(f"🔹 Configured Country:  {os.environ.get('COUNTRY', 'Not Set')}")
    print(f"🔹 Configured Timezone: {os.environ.get('TIMEZONE', 'Not Set')}")
    print(f"🔹 Resolved Timezone:   {tz_name}")

    local_now = timezone_helper.get_local_now()
    offset_hours = timezone_helper.get_timezone_offset_hours()

    print(f"🔹 Local Time Now:      {local_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔹 UTC Offset:          GMT{'+' if offset_hours >= 0 else ''}{offset_hours} hours")

    # Save original env values for restoration
    original_country = os.environ.get("COUNTRY")
    original_timezone = os.environ.get("TIMEZONE")

    try:
        print("\n🔍 Testing mapping helper:")
        test_countries = ["Cambodia", "TH", "US", "Vietnam", "Singapore"]
        for c in test_countries:
            os.environ["COUNTRY"] = c
            if "TIMEZONE" in os.environ:
                del os.environ["TIMEZONE"]
            resolved = timezone_helper.resolve_timezone_name()
            print(f"   • Country: {c:10} -> Timezone: {resolved}")
    finally:
        # Restore original env values
        if original_country is not None:
            os.environ["COUNTRY"] = original_country
        elif "COUNTRY" in os.environ:
            del os.environ["COUNTRY"]

        if original_timezone is not None:
            os.environ["TIMEZONE"] = original_timezone
        elif "TIMEZONE" in os.environ:
            del os.environ["TIMEZONE"]

    print("=============================================")
    print("✅ Timezone resolution test completed successfully!")


if __name__ == "__main__":
    main()
