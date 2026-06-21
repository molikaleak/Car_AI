import os
import cv2
import time
from backend import database
from src.config import parse_args
from src.geometry import calculate_line_parameters, check_crossing
from src.tracker import get_device, generate_tracker_config, load_yolo_model
from src.recorder import EventRecorder
from src.visuals import check_is_night, draw_bounding_box, draw_hud, draw_gate_line
from src.cleanup import start_cleanup_thread

def main():
    args = parse_args()

    # Write PID file so the Telegram bot /restart command can find this process
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tracker.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    
    generate_tracker_config()

    input_source = args.input
    is_live = False
    
    if str(input_source).isdigit():
        input_source = int(input_source)
        is_live = True
    elif str(input_source).startswith(("rtsp://", "rtmp://", "http://", "https://")):
        is_live = True

    if not is_live and not os.path.exists(str(input_source)):
        print(f"❌ Error: Input video file '{input_source}' does not exist.")
        return

    device = get_device(args.device)
    print(f"⚙️ Running on device: {device.upper()}")

    model, track_class_ids, class_id_to_name = load_yolo_model(args.model)

    # Open Video Source
    print(f"📹 Opening video source: {input_source}...")
    if is_live:
        from src.stream_reader import ThreadedStreamReader
        cap = ThreadedStreamReader(input_source)
    else:
        cap = cv2.VideoCapture(input_source)

    if not cap.isOpened():
        print(f"❌ Error: Could not open video source '{input_source}'")
        return

    if is_live:
        cap.start()

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0 or fps > 100:
        fps = 30  # Fallback FPS for live cameras/streams
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames_str = str(total_frames) if total_frames > 0 else "Live Stream"
    print(f"📹 Video Resolution: {width}x{height} | FPS: {fps} | Total Frames: {total_frames_str}")

    A, B, C, x0, y0, line_pt1, line_pt2, is_vertical_ish = calculate_line_parameters(
        width, height, args.line_pos, args.line_angle
    )
    print(f"📍 Counting line angle: {args.line_angle}° | Position: {int(args.line_pos * 100)}% | Pivot: ({x0}, {y0})")

    try:
        database._init_pool()
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize database: {e}")

    # Start daily cleanup of old event video folders
    start_cleanup_thread()

    clip_before_sec = float(os.environ.get("CLIP_BUFFER_SECONDS", 5))
    clip_after_sec = float(os.environ.get("CLIP_DURATION_SECONDS", 5))
    recorder = EventRecorder(fps, clip_before_sec, clip_after_sec)

    track_history = {}
    counted_in = set()
    counted_out = set()
    
    counts_in = {"Car": 0}
    counts_out = {"Car": 0}

    last_boxes = []
    last_car_count = 0

    ret_first, first_frame = cap.read()
    if ret_first and first_frame is not None:
        is_night = check_is_night(first_frame, args.time_mode)
        if not is_live:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    else:
        is_night = False

    time_label = "NIGHT (Security Mode)" if is_night else "DAY (Logistics Mode)"
    print(f"⏰ Environment Mode: {time_label}")
    
    if is_live:
        print("\n🚀 Starting ByteTrack live camera tracking...")
    else:
        print("\n🚀 Starting ByteTrack live warehouse tracking...")

    frame_idx = 0
    try:
        frame_queue = []
        while True:
            if is_live:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
            else:
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
            
            if args.grayscale:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            
            frame_idx += 1
            annotated_frame = frame.copy()

            # Run YOLO Tracking with ByteTrack (strictly Cars only) on matching frames
            if frame_idx % args.detect_every == 0 or frame_idx == 1:
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
                last_boxes = []

                if results[0].boxes is not None and results[0].boxes.id is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy()
                    track_ids = results[0].boxes.id.int().cpu().numpy()
                    classes = results[0].boxes.cls.int().cpu().numpy()

                    for box, track_id, cls in zip(boxes, track_ids, classes):
                        current_ids.add(track_id)
                        x1, y1, x2, y2 = map(int, box)
                        class_name = class_id_to_name.get(cls, "Object")

                        if class_name == "Car":
                            current_car_count += 1

                        # Cache boxes to draw on skipped frames
                        last_boxes.append((box, track_id, class_name))

                        # Draw Box & Label
                        cx, cy = draw_bounding_box(annotated_frame, (x1, y1, x2, y2), track_id, class_name, is_night)

                        # Line crossing logic
                        if track_id in track_history:
                            prev_cx, prev_cy = track_history[track_id][-1]
                            crossed_in, crossed_out = check_crossing(
                                prev_cx, prev_cy, cx, cy, A, B, C, is_vertical_ish, args.in_dir
                            )

                            # Process IN event
                            if crossed_in and track_id not in counted_in:
                                counts_in[class_name] = counts_in.get(class_name, 0) + 1
                                counted_in.add(track_id)
                                print(f"[LOGISTICS] Car #{track_id} entered warehouse.")
                                recorder.trigger_recording(track_id, class_name, "IN", width, height)
                            
                            # Process OUT event
                            elif crossed_out and track_id not in counted_out:
                                counts_out[class_name] = counts_out.get(class_name, 0) + 1
                                counted_out.add(track_id)
                                print(f"[LOGISTICS] Car #{track_id} exited warehouse.")
                                recorder.trigger_recording(track_id, class_name, "OUT", width, height)

                            track_history[track_id].append((cx, cy))
                        else:
                            track_history[track_id] = [(cx, cy)]

                # Clean memory for old inactive tracks
                inactive_ids = set(track_history.keys()) - current_ids
                for inactive_id in list(inactive_ids):
                    if len(track_history[inactive_id]) > 30: 
                        del track_history[inactive_id]

                last_car_count = current_car_count
            else:
                # Draw last known bounding boxes on skipped frames
                for box, track_id, class_name in last_boxes:
                    x1, y1, x2, y2 = map(int, box)
                    draw_bounding_box(annotated_frame, (x1, y1, x2, y2), track_id, class_name, is_night)
                current_car_count = last_car_count

            # Draw counting line
            draw_gate_line(annotated_frame, line_pt1, line_pt2, x0, y0)

            # Draw HUD Background and Text (Cars only)
            draw_hud(annotated_frame, time_label, counts_in, counts_out, current_car_count, is_night)

            # Update active recordings and circular frame buffer
            recorder.add_frame(annotated_frame)

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
        recorder.flush()
        cap.release()
        cv2.destroyAllWindows()

        # Clean up PID file
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except OSError:
                pass
        
        print("\n🏁 ByteTrack Processing Complete!")
        print("📊 Final Counts:")
        print(f"   🔹 Cars: Entered (IN): {counts_in.get('Car', 0)} | Exited (OUT): {counts_out.get('Car', 0)}")

if __name__ == "__main__":
    main()
