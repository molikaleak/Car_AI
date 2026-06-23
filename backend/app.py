"""app.py — FastAPI Dashboard API for Warehouse Car Tracking

Endpoints:
    GET  /api/stats      → Today's IN / OUT / Occupancy counts
    GET  /api/events     → Last N crossing events
    GET  /api/chart-data → Hourly traffic breakdown for the chart
    WS   /ws/events      → Real-time WebSocket stream of new events
    /events/*            → Static video clips
    /*                   → Frontend dashboard (static HTML)
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend import database
from backend.websocket_manager import ConnectionManager

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Warehouse Car Tracking Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background Poller — Detects new DB events and pushes to WebSocket clients
# ---------------------------------------------------------------------------

async def poll_new_events() -> None:
    """Polls the database every second for new events.

    When a new event is found, broadcasts it to all WebSocket clients.
    """
    print("⏳ Starting database polling for real-time WebSocket events...")
    last_event_id = 0

    # Seed with the current latest event ID
    try:
        recent = database.get_recent_events(limit=1)
        if recent:
            last_event_id = recent[0]["id"]
    except Exception as e:
        print(f"⚠️  Polling setup warning: {e}")

    while True:
        await asyncio.sleep(1.0)
        try:
            recent = database.get_recent_events(limit=1)
            if not recent:
                continue

            latest = recent[0]
            if latest["id"] > last_event_id:
                last_event_id = latest["id"]
                print(f"🔔 New event: Car #{latest['track_id']} → {latest['direction']}")
                await manager.broadcast({"type": "new_event", "event": latest})
        except Exception:
            pass  # Silently handle transient DB errors during polling


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(poll_new_events())


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    """Today's car stats: total IN, total OUT, and estimated current occupancy."""
    try:
        today_data = database.get_today_report()
    except Exception as e:
        return {"error": str(e), "in": 0, "out": 0, "inside": 0}

    # Extract Car counts from the grouped report
    car_in = 0
    car_out = 0
    for row in today_data:
        if row.get("object_type") == "Car":
            if row.get("direction") == "IN":
                car_in = row.get("count", 0)
            elif row.get("direction") == "OUT":
                car_out = row.get("count", 0)

    return {
        "in": car_in,
        "out": car_out,
        "inside": max(0, car_in - car_out),
        "database_mode": "SQLite (Local)",
    }


@app.get("/api/events")
def get_events(limit: int = 15) -> list[dict[str, Any]] | dict[str, Any]:
    """Last N crossing events (cars only)."""
    try:
        events = database.get_recent_events(limit=limit)
        return [ev for ev in events if ev.get("object_type") == "Car"]
    except Exception as e:
        return {"error": str(e), "events": []}


@app.get("/api/chart-data")
def get_chart_data() -> dict[str, Any]:
    """Hourly car traffic for today, formatted for Chart.js.

    Returns:
        {
            "labels": ["00:00", "01:00", ..., "23:00"],
            "in":     [0, 0, 3, ...],   # count per hour
            "out":    [0, 1, 0, ...]
        }
    """
    rows = database.get_hourly_report()

    # Build 24-slot arrays for IN and OUT
    in_series = [0] * 24
    out_series = [0] * 24

    for row in rows:
        try:
            hour = int(row["hour"])
            count = int(row["count"])
            if 0 <= hour < 24:
                if row["direction"] == "IN":
                    in_series[hour] = count
                else:
                    out_series[hour] = count
        except (ValueError, KeyError, TypeError):
            continue

    return {
        "labels": [f"{h:02d}:00" for h in range(24)],
        "in": in_series,
        "out": out_series,
    }


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/events")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # Keep alive; ignore client messages
    except (WebSocketDisconnect, Exception):
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Static File Serving
# ---------------------------------------------------------------------------

# Serve recorded event video clips
events_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "events")
os.makedirs(events_dir, exist_ok=True)
app.mount("/events", StaticFiles(directory=events_dir), name="events")

# Serve the frontend dashboard HTML/CSS/JS
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"⚠️  Static directory not found: {static_dir}")


# ---------------------------------------------------------------------------
# Dev Server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
