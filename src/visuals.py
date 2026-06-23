"""visuals.py — Frame Annotation and HUD Rendering

Draws bounding boxes, the gate line, and the heads-up display (HUD)
statistics overlay on video frames.
"""

import cv2
import numpy as np

import os

def _parse_color(val: str | None, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if not val:
        return default
    try:
        parts = [int(p.strip()) for p in val.split(",")]
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
    except Exception:
        pass
    return default

# HUD dimensions and colors (loaded from env with defaults)
HUD_WIDTH: int = int(os.environ.get("HUD_WIDTH", 360))
HUD_HEIGHT: int = int(os.environ.get("HUD_HEIGHT", 100))
HUD_OPACITY: float = float(os.environ.get("HUD_OPACITY", 0.65))
HUD_BACKGROUND_COLOR: tuple[int, int, int] = _parse_color(os.environ.get("HUD_BACKGROUND_COLOR"), (0, 0, 0))
HUD_TEXT_COLOR: tuple[int, int, int] = _parse_color(os.environ.get("HUD_TEXT_COLOR"), (255, 255, 255))

# Bounding box colors (loaded from env with defaults)
BOX_COLOR_DEFAULT: tuple[int, int, int] = _parse_color(os.environ.get("BOX_COLOR_DEFAULT"), (255, 0, 255))  # Purple
GATE_LINE_COLOR: tuple[int, int, int] = _parse_color(os.environ.get("GATE_LINE_COLOR"), (255, 0, 0))  # Blue (BGR)
GATE_LINE_THICKNESS: int = int(os.environ.get("GATE_LINE_THICKNESS", 3))

# Night mode brightness threshold (loaded from env with defaults)
NIGHT_BRIGHTNESS_THRESHOLD: int = int(os.environ.get("NIGHT_BRIGHTNESS_THRESHOLD", 60))


def check_is_night(frame: np.ndarray, mode: str) -> bool:
    """Determines if the frame represents day or night based on average brightness

    if mode is set to 'auto'. Otherwise, returns the explicit mode setting.
    """
    if mode == "night":
        return True
    elif mode == "day":
        return False
    else:
        # Convert frame to grayscale and get average brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)
        return avg_brightness < NIGHT_BRIGHTNESS_THRESHOLD


def draw_bounding_box(
    frame: np.ndarray,
    box: tuple[int, int, int, int],
    track_id: int,
    class_name: str,
    is_night: bool,
) -> tuple[int, int]:
    """Draws box, label, and center point for tracked object on the frame.

    Returns the center coordinates (cx, cy).
    """
    x1, y1, x2, y2 = box
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)

    box_label = f"Car #{track_id}"
    color = BOX_COLOR_DEFAULT

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    (text_w, text_h), _ = cv2.getTextSize(box_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w + 10, y1), color, -1)
    cv2.putText(
        frame,
        box_label,
        (x1 + 5, y1 - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        HUD_TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )
    # Center point
    cv2.circle(frame, (cx, cy), 4, color, -1)
    return cx, cy


def draw_hud(
    frame: np.ndarray,
    time_label: str,
    counts_in: dict[str, int],
    counts_out: dict[str, int],
    current_car_count: int,
    is_night: bool,
) -> None:
    """Draws the semi-transparent HUD statistics dashboard."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (10 + HUD_WIDTH, 10 + HUD_HEIGHT), HUD_BACKGROUND_COLOR, -1)
    cv2.addWeighted(overlay, HUD_OPACITY, frame, 1.0 - HUD_OPACITY, 0, frame)

    # Draw HUD text
    cv2.putText(
        frame,
        f"WAREHOUSE TRACKING | {time_label}",
        (20, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        HUD_TEXT_COLOR,
        2,
        cv2.LINE_AA,
    )

    # Print car counts
    car_in = counts_in.get("Car", 0)
    car_out = counts_out.get("Car", 0)
    cv2.putText(
        frame,
        f"Cars: IN: {car_in} | OUT: {car_out} | Active: {current_car_count}",
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        BOX_COLOR_DEFAULT,
        2,
        cv2.LINE_AA,
    )

    # Inside frame breakdown string
    breakdown_str = f"Cars inside frame: {current_car_count}"
    cv2.putText(
        frame,
        f"HUD: {breakdown_str}",
        (20, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        HUD_TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )


def draw_gate_line(
    frame: np.ndarray,
    line_pt1: tuple[int, int],
    line_pt2: tuple[int, int],
    x0: int,
    y0: int,
) -> None:
    """Draws the gate line and label on the frame."""
    cv2.line(frame, line_pt1, line_pt2, GATE_LINE_COLOR, GATE_LINE_THICKNESS)
    label_y = y0 - 10 if y0 > 20 else y0 + 20
    cv2.putText(
        frame,
        "WAREHOUSE GATEWAY",
        (x0 - 80 if x0 > 80 else 20, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        GATE_LINE_COLOR,
        2,
        cv2.LINE_AA,
    )
