import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict

import cv2
from flask import Flask, Response, jsonify

try:
    from waitress import serve as waitress_serve
except Exception:
    waitress_serve = None

HOST = os.getenv("STREAM_HOST", "0.0.0.0")
PORT = int(os.getenv("STREAM_PORT", "5000"))
CAMERA_INDEXES_ENV = os.getenv("CAMERA_INDEXES")
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "45"))
FRAME_INTERVAL_SECONDS = float(os.getenv("FRAME_INTERVAL_SECONDS", "0.05"))

app = Flask(__name__)
frame_store: Dict[int, bytes] = {}
frame_lock = threading.Lock()


def open_capture(index: int):
    system_name = platform.system().lower()

    if system_name == "windows":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
        cap.release()

        cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
        if cap.isOpened():
            return cap
        cap.release()

    elif system_name == "linux":
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        return cap

    return cv2.VideoCapture(index)


def _linux_candidate_indexes(max_scan: int):
    video_nodes = sorted(Path("/dev").glob("video*"))
    node_indexes = []

    for node in video_nodes:
        suffix = node.name.replace("video", "")
        if not suffix.isdigit():
            continue

        index = int(suffix)
        if index > max_scan:
            continue

        try:
            details = subprocess.run(
                ["v4l2-ctl", "-d", str(node), "--all"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            out = (details.stdout or "") + (details.stderr or "")
            if "Video Capture" not in out and "Video Capture Multiplanar" not in out:
                continue
        except Exception:
            pass

        node_indexes.append(index)

    if node_indexes:
        return node_indexes

    return list(range(max_scan + 1))


def detect_available_cameras(max_scan: int = 8):
    detected = []
    system_name = platform.system().lower()
    if system_name == "linux":
        probe_indexes = _linux_candidate_indexes(max_scan)
    else:
        probe_indexes = list(range(max_scan + 1))

    for idx in probe_indexes:
        cap = open_capture(idx)
        if cap.isOpened():
            ok_count = 0
            for _ in range(5):
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    ok_count += 1
                time.sleep(0.03)

            if ok_count >= 2:
                detected.append(idx)
        cap.release()
    return detected


def resolve_camera_indexes():
    if CAMERA_INDEXES_ENV:
        configured = [
            int(idx.strip())
            for idx in CAMERA_INDEXES_ENV.split(",")
            if idx.strip()
        ]
        print(f"Using CAMERA_INDEXES from env: {configured}")
        return configured

    detected = detect_available_cameras()
    if detected:
        print(f"Auto-detected cameras: {detected}")
        return detected

    print("No cameras auto-detected; defaulting to [0]")
    return [0]


def stream_camera(cam_index: int):
    cap = open_capture(cam_index)
    if not cap.isOpened():
        print(f"[cam{cam_index}] Failed to open camera")
        return

    print(f"[cam{cam_index}] Capture loop started")
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.2)
            continue

        resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        ok, buffer = cv2.imencode(
            ".jpg",
            resized,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
        )
        if not ok:
            continue

        with frame_lock:
            frame_store[cam_index] = buffer.tobytes()

        time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/health")
def health():
    return jsonify({"ok": True, "cameras": list(frame_store.keys())})


@app.get("/cam/<int:cam_index>/frame.jpg")
def frame_jpg(cam_index: int):
    with frame_lock:
        data = frame_store.get(cam_index)

    if data is None:
        return Response("Camera frame not ready", status=404)

    return Response(data, mimetype="image/jpeg")


def mjpeg_generator(cam_index: int):
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        with frame_lock:
            data = frame_store.get(cam_index)

        if data is not None:
            yield boundary + data + b"\r\n"
        time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/cam/<int:cam_index>/mjpeg")
def mjpeg(cam_index: int):
    return Response(
        mjpeg_generator(cam_index),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    camera_indexes = resolve_camera_indexes()
    print(f"Serving camera indexes: {camera_indexes}")

    for idx in camera_indexes:
        t = threading.Thread(target=stream_camera, args=(idx,), daemon=True)
        t.start()

    print(f"Flask streamer listening on http://{HOST}:{PORT}")
    print("Expose this with ngrok and use that URL in the mobile app Settings page.")

    if waitress_serve is not None:
        threads = int(os.getenv("STREAM_THREADS", "8"))
        print(f"Using waitress with {threads} threads")
        waitress_serve(app, host=HOST, port=PORT, threads=threads)
    else:
        print("waitress not installed; falling back to Flask dev server")
        app.run(host=HOST, port=PORT, threaded=True)
