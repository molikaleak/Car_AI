import sys
import os

# Path resolving
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src import timezone_helper

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

# Test mapping resolves correctly
print("\n🔍 Testing mapping helper:")
test_countries = ["Cambodia", "TH", "US", "Vietnam", "Singapore"]
for c in test_countries:
    os.environ["COUNTRY"] = c
    if "TIMEZONE" in os.environ:
        del os.environ["TIMEZONE"]
    resolved = timezone_helper.resolve_timezone_name()
    print(f"   • Country: {c:10} -> Timezone: {resolved}")
    
# Restore env
os.environ["COUNTRY"] = "Cambodia"
os.environ["TIMEZONE"] = "Asia/Phnom_Penh"

print("=============================================")
print("✅ Timezone resolution test completed successfully!")
