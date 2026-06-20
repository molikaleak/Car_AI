import argparse
import os
import cv2
import torch
from ultralytics import YOLO

def parse_args():
    # Load environment variables from .env if available
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Run YOLO model on an image and count detections (Occupied/Vacant slots)")
    parser.add_argument(
        "--input", 
        type=str, 
        default=os.environ.get("INPUT_IMAGE_PATH"),
        required=not os.environ.get("INPUT_IMAGE_PATH"), 
        help="Path to the input image"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default=os.environ.get("MODEL_PATH", "yolo11m.pt"), 
        help="Path to YOLO model file (e.g., yolo11m.pt or yolo26n.pt)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default=os.environ.get("OUTPUT_IMAGE_PATH", "result.jpg"), 
        help="Path to save the annotated result image"
    )
    
    # Confidence threshold
    conf_val = os.environ.get("CONFIDENCE_THRESHOLD")
    conf_default = float(conf_val) if conf_val is not None else 0.25
    parser.add_argument(
        "--conf", 
        type=float, 
        default=conf_default, 
        help="Confidence threshold for detections"
    )
    
    parser.add_argument(
        "--device", 
        type=str, 
        default=os.environ.get("DEVICE", "auto"), 
        help="Device to use ('mps' for Apple Silicon GPU, 'cpu', or 'auto')"
    )
    parser.add_argument(
        "--show", 
        action="store_true", 
        help="Show the image in a window after processing"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    # 1. Verify input image exists
    if not os.path.exists(args.input):
        print(f"❌ Error: Input image '{args.input}' does not exist.")
        return

    # 2. Determine device
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

    # 3. Load the YOLO model
    print(f"⏳ Loading model: {args.model}...")
    try:
        model = YOLO(args.model)
        print("✅ Model loaded successfully!")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return

    # 4. Load the image
    frame = cv2.imread(args.input)
    if frame is None:
        print(f"❌ Error: Could not read image '{args.input}'.")
        return

    # 5. Run inference
    print(f"🔍 Running detection on '{args.input}'...")
    results = model(frame, conf=args.conf, device=device, verbose=False)

    # Initialize counter dict
    counts = {}
    for name in model.names.values():
        counts[name] = 0

    color_map = {
        "occupied": (0, 0, 255),  # Red in BGR
        "vacant": (0, 255, 0)     # Green in BGR
    }

    # 6. Process and draw detections
    for result in results:
        boxes = result.boxes
        for box in boxes:
            cls_id = int(box.cls[0].item())
            label = model.names[cls_id]
            conf = box.conf[0].item()

            # Increment count
            counts[label] = counts.get(label, 0) + 1

            # Get coordinates
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            # Determine color
            label_lower = label.lower()
            if label_lower in color_map:
                color = color_map[label_lower]
            else:
                color = (int((cls_id * 50) % 255), int((cls_id * 80 + 100) % 255), int((cls_id * 120 + 50) % 255))

            # Draw rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Draw label text
            text = f"{label} {conf:.2f}"
            (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - text_h - 10), (x1 + text_w + 10, y1), color, -1)
            cv2.putText(
                frame, 
                text, 
                (x1 + 5, y1 - 5), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (255, 255, 255), 
                1, 
                cv2.LINE_AA
            )

    # 7. Print summary counts to terminal
    print("\n📊 --- Detection Summary ---")
    for label, count in counts.items():
        print(f"   🔹 {label}: {count}")
    print("----------------------------\n")

    # 8. Overlay summary table on top-left of the image
    overlay_x, overlay_y = 20, 30
    cv2.putText(
        frame, 
        "Detection Summary:", 
        (overlay_x, overlay_y), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.7, 
        (255, 255, 255), 
        2, 
        cv2.LINE_AA
    )
    
    current_y = overlay_y + 25
    for label, count in counts.items():
        label_lower = label.lower()
        text_color = color_map.get(label_lower, (255, 255, 255))
        cv2.putText(
            frame, 
            f"- {label}: {count}", 
            (overlay_x, current_y), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.6, 
            text_color, 
            2, 
            cv2.LINE_AA
        )
        current_y += 20

    # 9. Save output image
    try:
        cv2.imwrite(args.output, frame)
        print(f"💾 Saved annotated image to: {args.output}")
    except Exception as e:
        print(f"❌ Error saving output image: {e}")

    # 10. Display image if requested
    if args.show:
        print("🖥️ Displaying image (Press any key to close the window)...")
        cv2.imshow("Detection Result", frame)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
