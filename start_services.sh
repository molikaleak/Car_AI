#!/bin/bash

# Create logs directory
mkdir -p logs

# Auto-detect Python command (python3 on macOS, python elsewhere)
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "❌ Error: Python not found. Please install Python 3."
    exit 1
fi

echo "============================================="
echo "🏎️  WAREHOUSE GATEWAY CAR TRACKING SERVICES"
echo "============================================="
echo "🐍 Using Python: $PYTHON ($(${PYTHON} --version 2>&1))"

# 1. Start FastAPI Dashboard
echo "📡 Launching Web Dashboard on http://localhost:8000..."
$PYTHON -u backend/app.py > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!

# 2. Start Telegram Bot Polling
echo "🤖 Launching Telegram Bot Polling Service..."
$PYTHON -u backend/telegram_bot.py > logs/telegram_bot.log 2>&1 &
BOT_PID=$!

# 3. Start YOLO Tracker
echo "📹 Launching ByteTrack Car Tracking Engine..."
$PYTHON -u main.py > logs/tracker.log 2>&1 &
TRACKER_PID=$!

echo "---------------------------------------------"
echo "✅ All services successfully launched!"
echo "   🔹 Dashboard PID:  $DASHBOARD_PID  (Logs: logs/dashboard.log)"
echo "   🔹 Telegram Bot:   $BOT_PID  (Logs: logs/telegram_bot.log)"
echo "   🔹 YOLO Tracker:   $TRACKER_PID  (Logs: logs/tracker.log)"
echo "============================================="
echo "👉 Open http://localhost:8000 in your browser to view the live dashboard."
echo "👉 Press [CTRL+C] to stop all running processes cleanly."

# Handle shutdown signals cleanly
cleanup() {
    echo -e "\n🛑 Received stop signal. Terminating all services..."
    kill $DASHBOARD_PID 2>/dev/null
    kill $BOT_PID 2>/dev/null
    kill $TRACKER_PID 2>/dev/null
    echo "👋 All processes stopped. Exiting."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep the script running to monitor and keep processes alive
while true; do
    # Check if dashboard is still running
    if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
        echo "⚠️ Warning: Dashboard service has stopped!"
    fi
    # Check if tracker is still running
    if ! kill -0 $TRACKER_PID 2>/dev/null; then
        echo "⚠️ Warning: Tracker service has stopped!"
    fi
    sleep 5
done
