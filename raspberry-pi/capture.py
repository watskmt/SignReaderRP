#!/usr/bin/env python3
"""SignReader Raspberry Pi capture client.

Captures frames from a USB webcam and sends them to the SignReader backend
for OCR processing. Designed to run on Raspberry Pi Zero W.

Environment variables:
  SIGNREADER_API_URL   Backend URL (default: https://api.signreader.amtech-service.com)
  CAPTURE_INTERVAL     Seconds between captures (default: 2.0)
  CAMERA_INDEX         V4L2 device index (default: 0)
  JPEG_QUALITY         JPEG quality 1-100 (default: 70)
  SESSION_TITLE        Session name prefix (default: Pi-YYYYMMDD-HHMM)
  CAPTURE_WIDTH        Frame width (default: 640)
  CAPTURE_HEIGHT       Frame height (default: 480)
"""

import base64
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

import cv2
import requests

API_URL = os.getenv("SIGNREADER_API_URL", "https://api.signreader.amtech-service.com")
CAPTURE_INTERVAL = float(os.getenv("CAPTURE_INTERVAL", "2.0"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "70"))
CAPTURE_WIDTH = int(os.getenv("CAPTURE_WIDTH", "640"))
CAPTURE_HEIGHT = int(os.getenv("CAPTURE_HEIGHT", "480"))
SESSION_TITLE = os.getenv(
    "SESSION_TITLE",
    f"Pi-{datetime.now().strftime('%Y%m%d-%H%M')}",
)
REQUEST_TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def create_session(title: str) -> str:
    resp = requests.post(
        f"{API_URL}/sessions",
        json={"title": title},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    session_id = resp.json()["id"]
    log.info("Session created: %s  id=%s", title, session_id)
    return session_id


def send_frame(session_id: str, frame_b64: str) -> str:
    resp = requests.post(
        f"{API_URL}/ocr/process/async",
        json={"frame": frame_b64, "session_id": session_id},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("task_id", "")


def open_camera() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        log.error("Cannot open camera index %d", CAMERA_INDEX)
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimise latency on Pi Zero W
    return cap


def capture_frame(cap: cv2.VideoCapture) -> Optional[str]:
    ret, frame = cap.read()
    if not ret:
        return None
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return base64.b64encode(buf.tobytes()).decode()


def main() -> None:
    log.info("SignReader Pi Client starting")
    log.info("API=%s  interval=%.1fs  camera=%d  res=%dx%d",
             API_URL, CAPTURE_INTERVAL, CAMERA_INDEX, CAPTURE_WIDTH, CAPTURE_HEIGHT)

    cap = open_camera()
    session_id: Optional[str] = None
    consecutive_errors = 0

    try:
        while True:
            loop_start = time.monotonic()

            if session_id is None:
                try:
                    session_id = create_session(SESSION_TITLE)
                    consecutive_errors = 0
                except Exception as exc:
                    log.error("Session creation failed: %s — retrying in 10s", exc)
                    time.sleep(10)
                    continue

            frame_b64 = capture_frame(cap)
            if frame_b64 is None:
                log.warning("Frame read failed, reopening camera")
                cap.release()
                time.sleep(2)
                cap = open_camera()
                continue

            try:
                task_id = send_frame(session_id, frame_b64)
                consecutive_errors = 0
                log.info("Sent %d B  task_id=%s", len(frame_b64), task_id)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else 0
                if status_code in (404, 410):
                    log.warning("Session gone, creating new one")
                    session_id = None
                else:
                    consecutive_errors += 1
                    log.error("HTTP error %d (%d): %s", status_code, consecutive_errors, exc)
            except Exception as exc:
                consecutive_errors += 1
                log.error("Send error (%d): %s", consecutive_errors, exc)

            if consecutive_errors >= 5:
                log.warning("5 consecutive errors — sleeping 30s")
                time.sleep(30)
                consecutive_errors = 0
                continue

            elapsed = time.monotonic() - loop_start
            sleep_time = max(0.0, CAPTURE_INTERVAL - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        cap.release()
        log.info("Camera released")


if __name__ == "__main__":
    main()
