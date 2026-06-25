"""stream_reader.py — Threaded Live Video Stream Reader

Provides a non-blocking frame reader for live video sources (RTSP,
webcam, HTTP streams) that keeps only the latest frame to prevent
processing lag.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import cv2
import numpy as np

# Timing constants
INITIAL_FRAME_WAIT_SEC: float = 0.5
RECONNECT_DELAY_SEC: float = 1.0
STOP_JOIN_TIMEOUT_SEC: float = 1.0


class ThreadedStreamReader:
    """A multi-threaded frame reader for live video sources (RTSP, webcam).

    Continuously pulls frames in a background thread, storing only the latest
    frame to avoid buffer accumulation and processing lag.
    """

    def __init__(self, src: str | int) -> None:
        self.src = src
        self.cap = cv2.VideoCapture(src)
        self.ret: bool = False
        self.frame: np.ndarray | None = None
        self.started: bool = False
        self.read_lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.new_frame: bool = False

    def start(self) -> ThreadedStreamReader:
        """Start the background stream reader thread."""
        if self.started:
            return self
        self.started = True
        self.thread = threading.Thread(target=self._update, args=(), daemon=True)
        self.thread.start()
        # Wait briefly for first frame to arrive
        time.sleep(INITIAL_FRAME_WAIT_SEC)
        return self

    def _update(self) -> None:
        """Background thread update loop that pulls frames from capture."""
        while self.started:
            ret, frame = self.cap.read()
            if not ret:
                # Reconnect logic if connection is dropped
                time.sleep(RECONNECT_DELAY_SEC)
                with self.read_lock:
                    self.ret = False
                self.cap.release()
                self.cap = cv2.VideoCapture(self.src)
                continue

            with self.read_lock:
                self.ret = ret
                self.frame = frame
                self.new_frame = True

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Return the latest frame copy only if it is a new frame."""
        with self.read_lock:
            if not self.new_frame:
                return False, None
            # Return copy of the frame to prevent access conflicts
            frame_copy = self.frame.copy() if self.frame is not None else None
            self.new_frame = False
            return self.ret, frame_copy

    def release(self) -> None:
        """Release the capture device and stop background thread."""
        self.started = False
        if self.thread is not None:
            self.thread.join(timeout=STOP_JOIN_TIMEOUT_SEC)
        self.cap.release()

    def get(self, prop_id: int) -> float:
        """Get a video capture property."""
        return self.cap.get(prop_id)

    def set(self, prop_id: int, value: float) -> bool:
        """Set a video capture property (e.g. CAP_PROP_POS_FRAMES)."""
        return self.cap.set(prop_id, value)

    def isOpened(self) -> bool:
        """Check if the video capture device is open."""
        return self.cap.isOpened()
