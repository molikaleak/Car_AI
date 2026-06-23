"""
tracking_pipeline.py — YOLO/ByteTrack Vehicle Tracking Pipeline

Encapsulates the core detection-and-counting loop used by ``main.py``
(live camera / local video).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

import cv2
import numpy as np

from src.geometry import check_crossing
from src.visuals import draw_bounding_box, draw_gate_line, draw_hud
from src.recorder import EventRecorder


# ---------------------------------------------------------------------------
# Constants (replacing magic numbers)
# ---------------------------------------------------------------------------

FALLBACK_FPS: int = 30
MAX_FPS: int = 100
INACTIVE_TRACK_HISTORY_THRESHOLD: int = 30
MIN_FILE_SIZE_BYTES: int = 1024


# ---------------------------------------------------------------------------
# Data classes for pipeline configuration and state
# ---------------------------------------------------------------------------

@dataclass
class GateConfig:
    """Parameters defining the counting gate line."""
    A: float
    B: float
    C: float
    x0: int
    y0: int
    line_pt1: tuple[int, int]
    line_pt2: tuple[int, int]
    is_vertical_ish: bool
    in_dir: str


@dataclass
class VideoProperties:
    """Video source metadata."""
    width: int
    height: int
    fps: int
    total_frames: int


@dataclass
class TrackingState:
    """Mutable state maintained across frames during tracking."""
    track_history: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    counted_in: set[int] = field(default_factory=set)
    counted_out: set[int] = field(default_factory=set)
    counts_in: dict[str, int] = field(default_factory=lambda: {"Car": 0})
    counts_out: dict[str, int] = field(default_factory=lambda: {"Car": 0})
    last_boxes: list[tuple[Any, int, str]] = field(default_factory=list)
    last_car_count: int = 0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TrackingPipeline:
    """Reusable YOLO/ByteTrack vehicle tracking pipeline.

    Processes a single video frame at a time, handling detection,
    tracking, line-crossing logic, annotation drawing, and event
    recording.

    Args:
        model: Loaded YOLO model instance.
        track_class_ids: List of COCO class IDs to track.
        class_id_to_name: Mapping from class ID to display name.
        gate: Gate line configuration.
        video_props: Video source properties.
        device: Inference device string (``'cpu'``, ``'mps'``, ``'cuda'``).
        recorder: EventRecorder for clip capture.
        conf: Detection confidence threshold.
        detect_every: Run detection every N frames.
        is_night: Whether the scene is in night/security mode.
        on_crossing: Optional callback ``(track_id, class_name, direction)``
            invoked when a vehicle crosses the gate line.
    """

    def __init__(
        self,
        model: Any,
        track_class_ids: list[int],
        class_id_to_name: dict[int, str],
        gate: GateConfig,
        video_props: VideoProperties,
        device: str,
        recorder: EventRecorder,
        conf: float = 0.25,
        detect_every: int = 1,
        is_night: bool = False,
        on_crossing: Callable[[int, str, str], None] | None = None,
    ) -> None:
        self.model = model
        self.track_class_ids = track_class_ids
        self.class_id_to_name = class_id_to_name
        self.gate = gate
        self.video_props = video_props
        self.device = device
        self.recorder = recorder
        self.conf = conf
        self.detect_every = detect_every
        self.is_night = is_night
        self.on_crossing = on_crossing

        self.time_label = "NIGHT (Security Mode)" if is_night else "DAY (Logistics Mode)"
        self.state = TrackingState()
        self.frame_idx: int = 0

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Process a single video frame through the tracking pipeline.

        Runs YOLO detection (if this frame is scheduled for it),
        updates tracking state, checks for line crossings, draws
        annotations, and buffers the frame for event recording.

        Args:
            frame: BGR video frame from OpenCV.

        Returns:
            Annotated copy of the frame with bounding boxes, HUD, and gate line.
        """
        self.frame_idx += 1
        annotated_frame = frame.copy()

        if self.frame_idx % self.detect_every == 0 or self.frame_idx == 1:
            self._run_detection(frame, annotated_frame)
        else:
            self._draw_cached_boxes(annotated_frame)

        # Draw gate line and HUD overlay
        draw_gate_line(
            annotated_frame,
            self.gate.line_pt1,
            self.gate.line_pt2,
            self.gate.x0,
            self.gate.y0,
        )
        draw_hud(
            annotated_frame,
            self.time_label,
            self.state.counts_in,
            self.state.counts_out,
            self.state.last_car_count,
            self.is_night,
        )

        # Buffer frame for event clip recording
        self.recorder.add_frame(annotated_frame)

        return annotated_frame

    def flush(self) -> None:
        """Flush any remaining active recordings at end of stream."""
        self.recorder.flush()

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _run_detection(self, frame: np.ndarray, annotated_frame: np.ndarray) -> None:
        """Run YOLO tracking and process detections for one frame."""
        results = self.model.track(
            frame,
            persist=True,
            classes=self.track_class_ids,
            conf=self.conf,
            tracker="custom_bytetrack.yaml",
            device=self.device,
            verbose=False,
        )

        current_ids: set[int] = set()
        current_car_count = 0
        self.state.last_boxes = []

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()
            classes = results[0].boxes.cls.int().cpu().numpy()

            for box, track_id, cls in zip(boxes, track_ids, classes):
                current_ids.add(track_id)
                x1, y1, x2, y2 = map(int, box)
                class_name = self.class_id_to_name.get(cls, "Object")

                if class_name == "Car":
                    current_car_count += 1

                self.state.last_boxes.append((box, track_id, class_name))

                # Draw bounding box and get center point
                cx, cy = draw_bounding_box(
                    annotated_frame, (x1, y1, x2, y2), track_id, class_name, self.is_night,
                )

                # Check for line crossing
                self._check_crossing(track_id, class_name, cx, cy)

        # Clean memory for old inactive tracks
        self._cleanup_inactive_tracks(current_ids)

        self.state.last_car_count = current_car_count

    def _check_crossing(self, track_id: int, class_name: str, cx: int, cy: int) -> None:
        """Check if a tracked object has crossed the gate line."""
        g = self.gate
        s = self.state

        if track_id in s.track_history:
            prev_cx, prev_cy = s.track_history[track_id][-1]
            crossed_in, crossed_out = check_crossing(
                prev_cx, prev_cy, cx, cy,
                g.A, g.B, g.C, g.is_vertical_ish, g.in_dir,
            )

            if crossed_in and track_id not in s.counted_in:
                s.counts_in[class_name] = s.counts_in.get(class_name, 0) + 1
                s.counted_in.add(track_id)
                self._on_crossing_event(track_id, class_name, "IN")

            elif crossed_out and track_id not in s.counted_out:
                s.counts_out[class_name] = s.counts_out.get(class_name, 0) + 1
                s.counted_out.add(track_id)
                self._on_crossing_event(track_id, class_name, "OUT")

            s.track_history[track_id].append((cx, cy))
        else:
            s.track_history[track_id] = [(cx, cy)]

    def _on_crossing_event(self, track_id: int, class_name: str, direction: str) -> None:
        """Handle a confirmed gate crossing event."""
        w, h = self.video_props.width, self.video_props.height
        self.recorder.trigger_recording(track_id, class_name, direction, w, h)

        if self.on_crossing:
            self.on_crossing(track_id, class_name, direction)

    def _cleanup_inactive_tracks(self, current_ids: set[int]) -> None:
        """Remove tracking history for objects no longer detected."""
        inactive_ids = set(self.state.track_history.keys()) - current_ids
        for inactive_id in list(inactive_ids):
            if len(self.state.track_history[inactive_id]) > INACTIVE_TRACK_HISTORY_THRESHOLD:
                del self.state.track_history[inactive_id]

    def _draw_cached_boxes(self, annotated_frame: np.ndarray) -> None:
        """Redraw last known bounding boxes on frames that skip detection."""
        for box, track_id, class_name in self.state.last_boxes:
            x1, y1, x2, y2 = map(int, box)
            draw_bounding_box(
                annotated_frame, (x1, y1, x2, y2), track_id, class_name, self.is_night,
            )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def read_video_properties(cap: cv2.VideoCapture) -> VideoProperties:
    """Extract video metadata from an OpenCV capture object.

    Args:
        cap: An opened ``cv2.VideoCapture`` instance.

    Returns:
        A ``VideoProperties`` dataclass with width, height, fps, and total frames.
    """
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0 or fps > MAX_FPS:
        fps = FALLBACK_FPS
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    return VideoProperties(width=width, height=height, fps=fps, total_frames=total_frames)
