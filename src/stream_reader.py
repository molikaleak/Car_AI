import cv2
import threading
import time

class ThreadedStreamReader:
    """
    A multi-threaded frame reader for live video sources (RTSP, webcam).
    Continuously pulls frames in a background thread, storing only the latest
    frame to avoid buffer accumulation and processing lag.
    """
    def __init__(self, src):
        self.src = src
        self.cap = cv2.VideoCapture(src)
        self.ret = False
        self.frame = None
        self.started = False
        self.read_lock = threading.Lock()
        self.thread = None

    def start(self):
        if self.started:
            return self
        self.started = True
        self.thread = threading.Thread(target=self._update, args=(), daemon=True)
        self.thread.start()
        # Wait briefly for first frame to arrive
        time.sleep(0.5)
        return self

    def _update(self):
        while self.started:
            ret, frame = self.cap.read()
            if not ret:
                # Reconnect logic if connection is dropped
                time.sleep(1.0)
                with self.read_lock:
                    self.ret = False
                self.cap.release()
                self.cap = cv2.VideoCapture(self.src)
                continue
            
            with self.read_lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        with self.read_lock:
            # Return copy of the frame to prevent access conflicts
            frame_copy = self.frame.copy() if self.frame is not None else None
            return self.ret, frame_copy

    def release(self):
        self.started = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        self.cap.release()

    def get(self, propId):
        return self.cap.get(propId)

    def isOpened(self):
        return self.cap.isOpened()
