import argparse
import os

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
    
    # Detection skip interval
    detect_every_val = os.environ.get("DETECT_EVERY")
    detect_every_default = int(detect_every_val) if detect_every_val is not None else 1
    parser.add_argument(
        "--detect-every",
        type=int,
        default=detect_every_default,
        help="Run detection every N frames (e.g. 10 to run 3 times per second on 30fps video)"
    )
    
    # Grayscale
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
