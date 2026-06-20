import argparse
import os
import cv2
import torch
import numpy as np
import threading
import uuid
from collections import deque
from datetime import datetime
from ultralytics import YOLO

# Target COCO Class IDs: 0: 'person', 2: 'car'
COCO_CLASSES = {
    0: "Person",
    2: "Car"
}

def parse_args():
    # Load environment variables from .env if available
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Warehouse vehicle & security tracking using ByteTrack with live count HUD")
    parser.add_argument(
        "--input", 
        type=str, 
        default=os.environ.get("INPUT_VIDEO_PATH", "/Users/molika/Desktop/carvid.mov"), 
        help="Path to the input video file"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default=os.environ.get("MODEL_PATH", "yolo11m.pt"), 
        help="Path to YOLO model file"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default=os.environ.get("OUTPUT_VIDEO_PATH", "output_warehouse_advanced.mp4"), 
        help="Path to save the main annotated output video"
    )
    
    # Line Position
    line_pos_val = os.environ.get("LINE_POS")
    line_pos_default = float(line_pos_val) if line_pos_val is not None else 0.5
    parser.add_argument(
        "--line-pos", 
        type=float, 
        default=line_pos_default, 
        help="Relative position of the counting line (0.0 to 1.0)"
    )
    
    parser.add_argument(
        "--line-type", 
        type=str, 
        default=os.environ.get("LINE_TYPE", "vertical"), 
        choices=["horizontal", "vertical"],
        help="Type of counting line: 'horizontal' or 'vertical'"
    )

    # Line Angle (0 to 180 degrees)
    line_angle_val = os.environ.get("LINE_ANGLE")
    line_angle_default = float(line_angle_val) if line_angle_val is not None else None
    parser.add_argument(
        "--line-angle", 
        type=float, 
        default=line_angle_default, 
        help="Angle of the counting line in degrees (0 to 180). Overrides line-type."
    )
    
    # Confidence threshold
    conf_val = os.environ.get("CONFIDENCE_THRESHOLD")
    conf_default = float(conf_val) if conf_val is not None else 0.25
    parser.add_argument(
        "--conf", 
        type=float, 
        default=conf_default, 
        help="Confidence threshold for YOLO detections"
    )
    
    parser.add_argument(
        "--device", 
        type=str, 
        default=os.environ.get("DEVICE", "auto"), 
        help="Device to use ('mps', 'cpu', or 'auto')"
    )
    
    parser.add_argument(
        "--time-mode", 
        type=str, 
        default=os.environ.get("TIME_MODE", "auto"), 
        choices=["auto", "day", "night"],
        help="Day/Night classification mode for human detection. 'auto' uses video frame brightness."
    )
    
    # Slow Speed
    slow_val = os.environ.get("SLOW_SPEED")
    slow_default = float(slow_val) if slow_val is not None else 1.0
    parser.add_argument(
        "--slow", 
        type=float, 
        default=slow_default, 
        choices=[1.0, 0.5],
        help="Video speed multiplier. 0.5 slows the video down to half speed."
    )
    
    # Grayscale (boolean flag with post-parsing resolution from env if not specified)
    parser.add_argument(
        "--grayscale", 
        action="store_true", 
        default=None,
        help="Convert the video frames to grayscale (black and white) before running detection"
    )
    
    # GUI Window Show flag
    parser.add_argument(
        "--show", 
        action="store_true", 
        default=None,
        help="Show the video in a GUI window during processing"
    )
    
    # IN Direction configuration
    parser.add_argument(
        "--in-dir", 
        type=str, 
        default=os.environ.get("IN_DIRECTION", "").strip().lower(),
        choices=["down", "up", "right", "left", ""],
        help="Direction that counts as IN: 'down' or 'up' (horizontal), 'right' or 'left' (vertical)"
    )
    
    args = parser.parse_args()
    
    # Resolve grayscale boolean default from env
    if args.grayscale is None:
        args.grayscale = os.environ.get("GRAYSCALE", "False").lower() in ("true", "1", "yes")
        
    # Resolve show boolean default from env (defaults to False if not in env)
    if args.show is None:
        args.show = os.environ.get("SHOW_GUI", "False").lower() in ("true", "1", "yes")

    # Overwrite input video path with CAMERA_IP if set in env
    camera_ip = os.environ.get("CAMERA_IP", "").strip()
    if camera_ip:
        args.input = camera_ip
        
    # Resolve line angle from line type if not explicitly set in env or CLI
    if args.line_angle is None:
        if args.line_type == "vertical":
            args.line_angle = 90.0
        else:
            args.line_angle = 0.0

    # Determine if line is vertical-ish (45 to 135 degrees)
    is_vertical_ish = 45 <= (args.line_angle % 180) < 135
    
    # Validate and default in-dir value
    if is_vertical_ish:
        if args.in_dir not in ["right", "left"]:
            args.in_dir = "right"
    else:
        if args.in_dir not in ["down", "up"]:
            args.in_dir = "down"
        
    return args

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

def generate_tracker_config():
    """
    Generates custom_bytetrack.yaml dynamically based on environment variables.
    """
    tracker_type = os.environ.get("TRACKER_TYPE", "bytetrack")
    track_high_thresh = float(os.environ.get("TRACK_HIGH_THRESH", 0.25))
    track_low_thresh = float(os.environ.get("TRACK_LOW_THRESH", 0.1))
    new_track_thresh = float(os.environ.get("NEW_TRACK_THRESH", 0.25))
    track_buffer = int(os.environ.get("TRACK_BUFFER", 1800))
    match_thresh = float(os.environ.get("MATCH_THRESH", 0.8))
    fuse_score = os.environ.get("FUSE_SCORE", "True").lower() in ("true", "1", "yes")

    yaml_content = f"""# ByteTrack tracker defaults for mode="track"
tracker_type: {tracker_type}
track_high_thresh: {track_high_thresh}
track_low_thresh: {track_low_thresh}
new_track_thresh: {new_track_thresh}
track_buffer: {track_buffer}
match_thresh: {match_thresh}
fuse_score: {fuse_score}
"""
    tracker_path = "custom_bytetrack.yaml"
    try:
        with open(tracker_path, "w") as f:
            f.write(yaml_content)
        print(f"⚙️ Dynamically generated tracker config '{tracker_path}' from environment variables.")
    except Exception as e:
        print(f"⚠️ Warning: Could not write tracker config to '{tracker_path}': {e}. Using defaults.")
    return tracker_path

def save_and_alert_clip(rec):
    """
    Background worker thread function that compiles the pre/post frames 
    into an MP4 clip, logs the event to SQLite, and sends a Telegram alert.
    """
    track_id = rec["track_id"]
    obj_type = rec["object_type"]
    direction = rec["direction"]
    frames = rec["frames"]
    fps = rec["fps"]
    w, h = rec["width"], rec["height"]
    
    # Create events directory if it doesn't exist
    os.makedirs("events", exist_ok=True)
    
    # Unique clip name
    clip_filename = f"events/event_{obj_type.lower()}_{direction.lower()}_{track_id}_{uuid.uuid4().hex[:8]}.mp4"
    
    try:
        # Write frames to temporary MP4 file
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(clip_filename, fourcc, fps, (w, h))
        for f in frames:
            out.write(f)
        out.release()
        
        print(f"🎬 Event clip generated and saved: {clip_filename}")
        
        # 1. Log event to SQLite database
        try:
            from backend import database
            event_id = database.log_event(obj_type, track_id, direction, clip_filename)
            print(f"💾 Logged event to SQLite database with ID: {event_id}")
        except Exception as e:
            print(f"❌ Error logging event to database: {e}")

        # 2. Send Video Alert to Telegram Bot
        try:
            import time
            alert_delay = int(os.environ.get("TELEGRAM_ALERT_DELAY", 120))
            if alert_delay > 0:
                print(f"⏳ Delaying Telegram alert send by {alert_delay} seconds for track #{track_id}...")
                time.sleep(alert_delay)
                
            from backend import telegram_bot
            # Format clean, professional caption
            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            caption = f"⚠️ *SECURITY GATEWAY ALERT*\n\n"
            caption += f"🔹 *Object:* {obj_type.upper()}\n"
            caption += f"🔹 *Track ID:* #{track_id}\n"
            caption += f"🔹 *Direction:* {direction}\n"
            caption += f"🔹 *Time:* {timestamp_str}"
            
            success = telegram_bot.send_telegram_video(clip_filename, caption=caption)
            if success:
                print(f"✈️ Telegram alert video sent successfully for track #{track_id}.")
            else:
                print(f"⚠️ Failed to send Telegram video alert.")
        except Exception as e:
            print(f"❌ Error sending Telegram video alert: {e}")
            
    except Exception as e:
        print(f"❌ Error during clip generation: {e}")

def main():
    args = parse_args()
    
    # Generate tracker config dynamically from env
    generate_tracker_config()

    input_source = args.input
    is_live = False
    
    # Check if input is a local camera index (e.g., 0, 1)
    if str(input_source).isdigit():
        input_source = int(input_source)
        is_live = True
    # Check if input is an IP camera URL (RTSP or HTTP stream)
    elif str(input_source).startswith(("rtsp://", "rtmp://", "http://", "https://")):
        is_live = True

    if not is_live and not os.path.exists(str(input_source)):
        print(f"❌ Error: Input video file '{input_source}' does not exist.")
        return

    # 1. Determine device
    if args.device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    else:
        device = args.device
    print(f"⚙️ Running on device: {device.upper()}")

    # 2. Load model
    print(f"⏳ Loading model: {args.model}...")
    try:
        model = YOLO(args.model)
        print("✅ Model loaded successfully!")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return

    # Map model class indices strictly to 'Person' (0) and 'Car' (2)
    track_class_ids = []
    class_id_to_name = {}
    
    for cls_id, name in model.names.items():
        name_lower = name.lower()
        if name_lower == "person":
            track_class_ids.append(cls_id)
            class_id_to_name[cls_id] = "Person"
        elif name_lower == "car":
            track_class_ids.append(cls_id)
            class_id_to_name[cls_id] = "Car"

    if not track_class_ids:
        track_class_ids = list(model.names.keys())
        class_id_to_name = model.names
        print("ℹ️ Warning: Target 'Person' and 'Car' classes not found. Tracking all classes.")
    else:
        print(f"ℹ️ Tracking classes: {list(class_id_to_name.values())} (Strictly Car and Person only)")

    # 3. Open Video Source
    print(f"📹 Opening video source: {input_source}...")
    cap = cv2.VideoCapture(input_source)
    if not cap.isOpened():
        print(f"❌ Error: Could not open video source '{input_source}'")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0 or fps > 100:
        fps = 30  # Fallback FPS for live cameras/streams
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames_str = str(total_frames) if total_frames > 0 else "Live Stream"
    print(f"📹 Video Resolution: {width}x{height} | FPS: {fps} | Total Frames: {total_frames_str}")

    # Set up line position based on angle
    is_vertical_ish = 45 <= (args.line_angle % 180) < 135
    if is_vertical_ish:
        x0 = int(width * args.line_pos)
        y0 = int(height / 2)
    else:
        x0 = int(width / 2)
        y0 = int(height * args.line_pos)

    # Line equation parameters: A*x + B*y + C = 0
    theta = np.radians(args.line_angle)
    A = -np.sin(theta)
    B = np.cos(theta)
    C = np.sin(theta) * x0 - np.cos(theta) * y0
    
    # Calculate boundary intersection points to draw the line
    pts = []
    # Left edge (x = 0)
    if abs(B) > 1e-5:
        y = -C / B
        if 0 <= y <= height:
            pts.append((0, int(y)))
    # Right edge (x = width)
    if abs(B) > 1e-5:
        y = -(A * width + C) / B
        if 0 <= y <= height:
            pts.append((width, int(y)))
    # Top edge (y = 0)
    if abs(A) > 1e-5:
        x = -C / A
        if 0 <= x <= width:
            pts.append((int(x), 0))
    # Bottom edge (y = height)
    if abs(A) > 1e-5:
        x = -(B * height + C) / A
        if 0 <= x <= width:
            pts.append((int(x), height))
            
    # Keep unique points
    unique_pts = []
    for pt in pts:
        if pt not in unique_pts:
            unique_pts.append(pt)
            
    if len(unique_pts) >= 2:
        line_pt1 = unique_pts[0]
        line_pt2 = unique_pts[1]
    else:
        if is_vertical_ish:
            line_pt1 = (x0, 0)
            line_pt2 = (x0, height)
        else:
            line_pt1 = (0, y0)
            line_pt2 = (width, y0)
            
    print(f"📍 Counting line angle: {args.line_angle}° | Position: {int(args.line_pos * 100)}% | Pivot: ({x0}, {y0})")

    # Initialize SQLite database
    try:
        from backend import database
        database.init_db()
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize database: {e}")

    # Event recording configuration from environment
    record_clips = os.environ.get("RECORD_CLIPS", "True").lower() in ("true", "1", "yes")
    clip_before_sec = float(os.environ.get("CLIP_BUFFER_SECONDS", 5))
    clip_after_sec = float(os.environ.get("CLIP_DURATION_SECONDS", 5))
    
    buffer_size = int(clip_before_sec * fps)
    frame_buffer = deque(maxlen=buffer_size)
    active_recordings = []

    # State variables
    track_history = {}
    track_class_history = {} # Maps track_id to its detected class name
    
    counted_in = set()
    counted_out = set()
    
    # Counters
    counts_in = {"Person": 0, "Car": 0}
    counts_out = {"Person": 0, "Car": 0}

    # Check Day/Night mode using the first frame
    ret_first, first_frame = cap.read()
    if ret_first:
        is_night = check_is_night(first_frame, args.time_mode)
        if not is_live:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    else:
        is_night = False

    time_label = "NIGHT (Security Mode)" if is_night else "DAY (Logistics Mode)"
    person_label = "Unauthorized" if is_night else "People/Visitors"
    print(f"⏰ Environment Mode: {time_label}")
    
    if is_live:
        print("\n🚀 Starting ByteTrack live camera tracking...")
    else:
        print("\n🚀 Starting ByteTrack live warehouse tracking...")

    frame_idx = 0
    try:
        frame_queue = []
        while True:
            if not frame_queue:
                ret, frame = cap.read()
                if not ret:
                    break
                if args.slow == 0.5:
                    frame_queue.append(frame)
                    frame_queue.append(frame)
                else:
                    frame_queue.append(frame)
            
            frame = frame_queue.pop(0)
            
            # Convert frame to grayscale if enabled (convert back to BGR for model compatibility)
            if args.grayscale:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            
            frame_idx += 1
            annotated_frame = frame.copy()

            # Run YOLO Tracking with ByteTrack (strictly Car and Person)
            results = model.track(
                frame, 
                persist=True, 
                classes=track_class_ids, 
                conf=args.conf, 
                tracker="custom_bytetrack.yaml",
                device=device, 
                verbose=False
            )

            current_ids = set()
            current_car_count = 0
            current_person_count = 0

            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().numpy()
                classes = results[0].boxes.cls.int().cpu().numpy()

                for box, track_id, cls in zip(boxes, track_ids, classes):
                    current_ids.add(track_id)
                    x1, y1, x2, y2 = map(int, box)
                    
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    # Get class name
                    class_name = class_id_to_name.get(cls, "Object")
                    track_class_history[track_id] = class_name

                    if class_name == "Car":
                        current_car_count += 1
                    elif class_name == "Person":
                        current_person_count += 1

                    # Draw Box & Label
                    if class_name == "Person":
                        if is_night:
                            box_label = f"UNAUTHORIZED PERSON #{track_id}"
                            color = (0, 0, 255)  # Red
                        else:
                            box_label = f"Person #{track_id}"
                            color = (0, 255, 0)  # Green
                    else:  # Car
                        box_label = f"Car #{track_id}"
                        color = (255, 0, 255)  # Purple
                        
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                    
                    (text_w, text_h), _ = cv2.getTextSize(box_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(annotated_frame, (x1, y1 - text_h - 10), (x1 + text_w + 10, y1), color, -1)
                    cv2.putText(
                        annotated_frame, 
                        box_label, 
                        (x1 + 5, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (255, 255, 255), 
                        1, 
                        cv2.LINE_AA
                    )

                    # Center point
                    cv2.circle(annotated_frame, (cx, cy), 4, color, -1)

                    # Line crossing logic (Supports horizontal and vertical lines)
                    if track_id in track_history:
                        prev_cx, prev_cy = track_history[track_id][-1]
                        
                        crossed_in = False
                        crossed_out = False

                        prev_d = A * prev_cx + B * prev_cy + C
                        curr_d = A * cx + B * cy + C
                        
                        if prev_d * curr_d < 0:
                            # Crossed the line!
                            # Determine if movement is in direction of normal vector
                            is_forward = curr_d > prev_d
                            
                            # Decide IN vs OUT based on line orientation and configured in-dir
                            if is_vertical_ish:
                                # For vertical-ish: default left-to-right (reverse direction) is IN
                                if args.in_dir in ["right", "forward"]:
                                    if not is_forward:
                                        crossed_in = True
                                    else:
                                        crossed_out = True
                                else: # left / reverse
                                    if is_forward:
                                        crossed_in = True
                                    else:
                                        crossed_out = True
                            else:
                                # For horizontal-ish: default top-to-bottom (forward direction) is IN
                                if args.in_dir in ["down", "forward"]:
                                    if is_forward:
                                        crossed_in = True
                                    else:
                                        crossed_out = True
                                else: # up / reverse
                                    if not is_forward:
                                        crossed_in = True
                                    else:
                                        crossed_out = True

                        # Process IN event
                        if crossed_in and track_id not in counted_in:
                            counts_in[class_name] = counts_in.get(class_name, 0) + 1
                            counted_in.add(track_id)
                            
                            if class_name == "Person":
                                if is_night:
                                    print(f"[SECURITY ALERT] Unauthorized Person #{track_id} ENTERED warehouse!")
                                else:
                                    print(f"[LOGISTICS] Person #{track_id} entered warehouse.")
                            else:
                                print(f"[LOGISTICS] Car #{track_id} entered warehouse.")
                                
                            if record_clips:
                                active_recordings.append({
                                    "track_id": track_id,
                                    "object_type": class_name,
                                    "direction": "IN",
                                    "frames": list(frame_buffer),
                                    "remaining_frames": int(clip_after_sec * fps),
                                    "fps": fps,
                                    "width": width,
                                    "height": height
                                })
                        
                        # Process OUT event
                        elif crossed_out and track_id not in counted_out:
                            counts_out[class_name] = counts_out.get(class_name, 0) + 1
                            counted_out.add(track_id)
                            
                            if class_name == "Person":
                                if is_night:
                                    print(f"[SECURITY ALERT] Unauthorized Person #{track_id} EXITED warehouse.")
                                else:
                                    print(f"[LOGISTICS] Person #{track_id} exited warehouse.")
                            else:
                                print(f"[LOGISTICS] Car #{track_id} exited warehouse.")
                                
                            if record_clips:
                                active_recordings.append({
                                    "track_id": track_id,
                                    "object_type": class_name,
                                    "direction": "OUT",
                                    "frames": list(frame_buffer),
                                    "remaining_frames": int(clip_after_sec * fps),
                                    "fps": fps,
                                    "width": width,
                                    "height": height
                                })

                        track_history[track_id].append((cx, cy))
                    else:
                        track_history[track_id] = [(cx, cy)]

            # Clean memory for old inactive tracks
            inactive_ids = set(track_history.keys()) - current_ids
            for inactive_id in list(inactive_ids):
                if len(track_history[inactive_id]) > 30: 
                    del track_history[inactive_id]

            # Draw counting line (supports any angle)
            cv2.line(annotated_frame, line_pt1, line_pt2, (255, 0, 0), 3)
            
            # Position the label near the center pivot point (x0, y0) offset slightly
            label_y = y0 - 10 if y0 > 20 else y0 + 20
            cv2.putText(annotated_frame, "WAREHOUSE GATEWAY", (x0 - 80 if x0 > 80 else 20, label_y), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2, cv2.LINE_AA)

            # Draw HUD Background
            hud_w, hud_h = 360, 160
            overlay = annotated_frame.copy()
            cv2.rectangle(overlay, (10, 10), (10 + hud_w, 10 + hud_h), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.65, annotated_frame, 0.35, 0, annotated_frame)

            # Draw HUD text
            cv2.putText(annotated_frame, f"WAREHOUSE TRACKING | {time_label}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
            
            # Print car counts (IN, OUT, and CURRENT COUNT inside frame)
            car_in = counts_in.get("Car", 0)
            car_out = counts_out.get("Car", 0)
            cv2.putText(annotated_frame, f"Cars: IN: {car_in} | OUT: {car_out} | Count: {current_car_count}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2, cv2.LINE_AA)
            
            # Print person counts (IN, OUT, and CURRENT COUNT inside frame)
            person_in = counts_in.get("Person", 0)
            person_out = counts_out.get("Person", 0)
            person_label = "Unauthorized" if is_night else "People/Visitors"
            person_color = (0, 0, 255) if is_night else (0, 255, 0)
            cv2.putText(annotated_frame, f"{person_label}: IN: {person_in} | OUT: {person_out} | Count: {current_person_count}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, person_color, 2, cv2.LINE_AA)

            # Inside frame breakdown string (clean without emojis)
            breakdown_str = f"Car: {current_car_count}, {person_label}: {current_person_count}"
            cv2.putText(annotated_frame, f"Inside: {breakdown_str}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

            # Update active recordings and circular frame buffer with annotated frame
            if record_clips:
                frame_to_buffer = annotated_frame.copy()
                for rec in list(active_recordings):
                    if rec["remaining_frames"] > 0:
                        rec["frames"].append(frame_to_buffer)
                        rec["remaining_frames"] -= 1
                    else:
                        active_recordings.remove(rec)
                        # Spawn background thread to compile video, log to DB, and notify Telegram
                        threading.Thread(target=save_and_alert_clip, args=(rec,), daemon=True).start()
                frame_buffer.append(frame_to_buffer)

            # Display GUI window if enabled
            if args.show:
                cv2.imshow("Warehouse Gateway Live Tracking (Press 'q' to Quit)", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n👋 Stopped by user.")
                    break

    except KeyboardInterrupt:
        print("\n👋 Process aborted.")
    
    finally:
        # Flush any remaining active recordings at the end of the stream
        if record_clips and active_recordings:
            print(f"\n🧹 Video stream ended. Flushing {len(active_recordings)} final active recordings...")
            for rec in active_recordings:
                save_and_alert_clip(rec)
                
        cap.release()
        cv2.destroyAllWindows()
        
        print("\n🏁 ByteTrack Processing Complete!")
        print("📊 Final Counts:")
        print(f"   🔹 Cars: Entered (IN): {counts_in['Car']} | Exited (OUT): {counts_out['Car']}")
        print(f"   🔹 Persons (as {person_label}): Entered (IN): {counts_in['Person']} | Exited (OUT): {counts_out['Person']}")

if __name__ == "__main__":
    main()
