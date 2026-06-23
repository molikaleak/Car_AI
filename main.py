"""main.py — Core Local Video / Live Stream YOLO Tracker

Resolves CLI settings, starts the background services, opens the video source,
instantiates the shared TrackingPipeline, and runs the frame loop.
"""

from __future__ import annotations

import os
import sys
import time

import cv2

from backend import database
from src.config import parse_args
from src.geometry import calculate_line_parameters
from src.tracker import get_device, generate_tracker_config, load_yolo_model
from src.recorder import EventRecorder
from src.visuals import check_is_night
from src.cleanup import start_cleanup_thread
from src.tracking_pipeline import TrackingPipeline, GateConfig, read_video_properties


def main() -> None:
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
        cap: cv2.VideoCapture | ThreadedStreamReader = ThreadedStreamReader(input_source)
    else:
        cap = cv2.VideoCapture(input_source)

    if not cap.isOpened():
        print(f"❌ Error: Could not open video source '{input_source}'")
        return

    if is_live:
        # For ThreadedStreamReader, start the background thread
        cap.start()  # type: ignore[union-attr]

    # Extract video properties
    video_props = read_video_properties(cap)  # type: ignore[arg-type]
    total_frames_str = str(video_props.total_frames) if video_props.total_frames > 0 else "Live Stream"
    print(
        f"📹 Video Resolution: {video_props.width}x{video_props.height} | "
        f"FPS: {video_props.fps} | Total Frames: {total_frames_str}"
    )

    A, B, C, x0, y0, line_pt1, line_pt2, is_vertical_ish = calculate_line_parameters(
        video_props.width, video_props.height, args.line_pos, args.line_angle
    )
    print(
        f"📍 Counting line angle: {args.line_angle}° | Position: {int(args.line_pos * 100)}% | Pivot: ({x0}, {y0})"
    )

    gate = GateConfig(
        A=A,
        B=B,
        C=C,
        x0=x0,
        y0=y0,
        line_pt1=line_pt1,
        line_pt2=line_pt2,
        is_vertical_ish=is_vertical_ish,
        in_dir=args.in_dir,
    )

    try:
        database._init_pool()
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize database: {e}")

    # Start daily cleanup of old event video folders
    start_cleanup_thread()

    clip_before_sec = float(os.environ.get("CLIP_BUFFER_SECONDS", 5))
    clip_after_sec = float(os.environ.get("CLIP_DURATION_SECONDS", 5))
    recorder = EventRecorder(video_props.fps, clip_before_sec, clip_after_sec)

    # Determine day/night mode
    is_night = False
    ret_first, first_frame = cap.read()
    if ret_first and first_frame is not None:
        is_night = check_is_night(first_frame, args.time_mode)
        if not is_live:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # type: ignore[union-attr]

    print(f"⏰ Environment Mode: {'NIGHT (Security Mode)' if is_night else 'DAY (Logistics Mode)'}")

    # Define crossing callback to log to stdout
    def crossing_callback(track_id: int, class_name: str, direction: str) -> None:
        print(f"[LOGISTICS] {class_name} #{track_id} crossed gate heading {direction}.")

    # Initialize tracking pipeline
    pipeline = TrackingPipeline(
        model=model,
        track_class_ids=track_class_ids,
        class_id_to_name=class_id_to_name,
        gate=gate,
        video_props=video_props,
        device=device,
        recorder=recorder,
        conf=args.conf,
        detect_every=args.detect_every,
        is_night=is_night,
        on_crossing=crossing_callback,
    )

    if is_live:
        print("\n🚀 Starting ByteTrack live camera tracking...")
    else:
        print("\n🚀 Starting ByteTrack live warehouse tracking...")

    try:
        frame_queue: list[cv2.Mat] = []
        while True:
            if is_live:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
            else:
                if not frame_queue:
                    ret, frame = cap.read()
                    if not ret or frame is None:
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

            annotated_frame = pipeline.process_frame(frame)

            # Display GUI window if enabled
            if args.show:
                cv2.imshow("Warehouse Gateway Live Tracking (Press 'q' to Quit)", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n👋 Stopped by user.")
                    break

    except KeyboardInterrupt:
        print("\n👋 Process aborted.")

    finally:
        pipeline.flush()
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
        counts_in = pipeline.state.counts_in
        counts_out = pipeline.state.counts_out
        print(f"   🔹 Cars: Entered (IN): {counts_in.get('Car', 0)} | Exited (OUT): {counts_out.get('Car', 0)}")


if __name__ == "__main__":
    main()
