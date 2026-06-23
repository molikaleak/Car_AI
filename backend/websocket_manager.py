"""
websocket_manager.py — WebSocket Connection Manager

Single source of truth for managing active WebSocket connections.
Used by ``app.py`` (live camera mode) for real-time event broadcasting to dashboards.
"""

from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    """Manages active WebSocket connections for real-time event broadcasting.

    Provides thread-safe connection tracking and broadcast capabilities
    for pushing events to all connected dashboard clients.
    """

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection from the active list."""
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected clients.

        Automatically removes clients that fail to receive the message.
        """
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)
