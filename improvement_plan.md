# Warehouse Camera Car Detection: Next-Step Improvement Plan

This document outlines the implementation plan to transition your prototype car tracking script into a robust, production-ready warehouse monitoring service.

---

## 📋 Objective
Deploy a real-time, edge-based computer vision system at the warehouse gate to:
* Detect only cars (filtering out other objects).
* Count entries (IN) and exits (OUT) as they cross a calibrated virtual gateway.
* Maintain a live count of cars currently inside the warehouse.
* Trigger security alerts if humans are detected during off-hours (Night Mode).

---

## 🛠️ Action Plan: Next Steps

### Phase 1: Camera Placement & Feed Calibration
To ensure detection accuracy, the camera feed must meet specific hardware and positioning standards:

1. **Mounting Angle (Reduce Occlusions):**
   * Mount the camera high (4+ meters / 13+ feet) pointing downward at a 45-degree angle.
   * This angle prevents cars from blocking each other in the frame (occlusion) and makes tracking trajectories much clearer.
2. **Gateway Line Position Calibration:**
   * **Horizontal Gateway (Vertical Traffic):** If cars drive straight toward or away from the camera, use a **Horizontal Line** placed at **40% to 60%** of the height.
   * **Vertical Gateway (Horizontal Traffic):** If cars cross from left-to-right, use a **Vertical Line** placed at **40% to 60%** of the width.
3. **Optimizing Frame Processing:**
   * Retain the **0.5x frame duplication logic** inside the code. It acts as a stabilizer, keeping the tracking ID locked onto the vehicle even if it moves fast or the camera drops frames.

---

### Phase 2: Production Script & Edge Deployment
Transition the script from running on static `.MP4` files to running on a live, continuous camera stream:

1. **RTSP Stream Integration:**
   * Modify the input source in OpenCV from a file path to the camera's network stream (RTSP URL):
     ```python
     # Example RTSP feed from an IP camera
     rtsp_url = "rtsp://admin:password@192.168.1.100:554/h264Preview_01_main"
     cap = cv2.VideoCapture(rtsp_url)
     ```
2. **Edge Device Hosting (Local Mac/Mini M1):**
   * Keep the code running locally on a dedicated Mac Mini (M1/M2/M3) situated in the warehouse. 
   * The M1's GPU (MPS acceleration) is powerful enough to handle 1080p live streams at 30 FPS.
3. **Background Service (Daemon):**
   * Set up the python script to run as a macOS `launchd` service or a Docker container. This ensures that if the computer restarts or power drops, the camera tracking service starts up automatically.

---

### Phase 3: Data Integration & Reporting
Save the counts and trigger actions rather than just drawing them on the video:

1. **Database Logging:**
   * Log every line crossing to a database (like PostgreSQL or SQLite):
     | Timestamp | Vehicle ID | Direction | Class | Confidence |
     | :--- | :--- | :--- | :--- | :--- |
     | `2026-06-16 22:15:30` | `144` | `IN` | `Car` | `0.92` |
     | `2026-06-16 22:16:12` | `240` | `OUT` | `Car` | `0.89` |
2. **Simple Local Web Dashboard:**
   * Build a lightweight web interface (using Flask, FastAPI, or Node.js) to display:
     * **Current Occupancy:** (Total Cars IN - Total Cars OUT).
     * **Live Gate Feed:** Visualizing the live gateway line.
     * **Logs Table:** Recent entries and exits.
3. **Alert Webhooks:**
   * Connect the `NIGHT (Security Mode)` to an instant alert API. 
   * If an `Unauthorized Person` crosses the gateway at night, send an immediate notification with a snapshot to a Telegram channel, Discord webhook, or your email.
