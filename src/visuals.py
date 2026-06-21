import cv2
import numpy as np

def check_is_night(frame, mode):
    """
    Determines if the frame represents day or night based on average brightness
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
        return avg_brightness < 60


def draw_bounding_box(frame, box, track_id, class_name, is_night):
    """
    Draws box, label, and center point for tracked object on the frame.
    Returns the center coordinates (cx, cy).
    """
    x1, y1, x2, y2 = box
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)

    box_label = f"Car #{track_id}"
    color = (255, 0, 255)  # Purple
        
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    
    (text_w, text_h), _ = cv2.getTextSize(box_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w + 10, y1), color, -1)
    cv2.putText(
        frame, 
        box_label, 
        (x1 + 5, y1 - 5), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.5, 
        (255, 255, 255), 
        1, 
        cv2.LINE_AA
    )
    # Center point
    cv2.circle(frame, (cx, cy), 4, color, -1)
    return cx, cy


def draw_hud(frame, time_label, counts_in, counts_out, current_car_count, is_night):
    """
    Draws the semi-transparent HUD statistics dashboard.
    """
    hud_w, hud_h = 360, 100
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (10 + hud_w, 10 + hud_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    # Draw HUD text
    cv2.putText(frame, f"WAREHOUSE TRACKING | {time_label}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
    
    # Print car counts
    car_in = counts_in.get("Car", 0)
    car_out = counts_out.get("Car", 0)
    cv2.putText(frame, f"Cars: IN: {car_in} | OUT: {car_out} | Active: {current_car_count}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2, cv2.LINE_AA)

    # Inside frame breakdown string
    breakdown_str = f"Cars inside frame: {current_car_count}"
    cv2.putText(frame, f"HUD: {breakdown_str}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)


def draw_gate_line(frame, line_pt1, line_pt2, x0, y0):
    """
    Draws the gate line and label on the frame.
    """
    cv2.line(frame, line_pt1, line_pt2, (255, 0, 0), 3)
    label_y = y0 - 10 if y0 > 20 else y0 + 20
    cv2.putText(frame, "WAREHOUSE GATEWAY", (x0 - 80 if x0 > 80 else 20, label_y), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2, cv2.LINE_AA)
