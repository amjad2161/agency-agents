"""Webcam presence: detect when user is at desk."""
from __future__ import annotations
import threading, time


class WebcamPresence:
    def __init__(self, on_change):
        self.on_change = on_change
        self.cv2 = None
        self._present = False
        self._running = False
        try:
            import cv2
            self.cv2 = cv2
            casc = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._cascade = cv2.CascadeClassifier(casc)
        except Exception:
            self._cascade = None

    def start(self):
        if self._running or not self.cv2: return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        try:
            cap = self.cv2.VideoCapture(0, self.cv2.CAP_DSHOW)
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(2); continue
                gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
                faces = self._cascade.detectMultiScale(gray, 1.3, 5)
                present = len(faces) > 0
                if present != self._present:
                    self._present = present
                    self.on_change(present)
                time.sleep(3)
            cap.release()
        except Exception:
            pass
