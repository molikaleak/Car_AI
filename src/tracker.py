import os
import torch
from ultralytics import YOLO

def get_device(device_arg="auto"):
    """
    Resolves the execution device.
    """
    if device_arg == "auto":
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
        else:
            return "cpu"
    return device_arg

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

def load_yolo_model(model_path):
    """
    Loads the YOLO model and returns target tracking class IDs and class_id_to_name map.
    """
    print(f"⏳ Loading model: {model_path}...")
    model = YOLO(model_path)
    print("✅ Model loaded successfully!")

    # Map model class indices strictly to 'Car' (2)
    track_class_ids = []
    class_id_to_name = {}
    
    for cls_id, name in model.names.items():
        name_lower = name.lower()
        if name_lower == "car":
            track_class_ids.append(cls_id)
            class_id_to_name[cls_id] = "Car"

    if not track_class_ids:
        track_class_ids = [2]
        class_id_to_name = {2: "Car"}
        print("ℹ️ Warning: Target 'Car' class not found in model names. Forcing COCO Class ID 2 ('Car').")
    else:
        print(f"ℹ️ Tracking classes: {list(class_id_to_name.values())} (Strictly Car only)")

    return model, track_class_ids, class_id_to_name
