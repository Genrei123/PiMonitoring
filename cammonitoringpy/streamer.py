import os
import platform
import re
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
camera_status: Dict[int, Dict[str, object]] = {}
configured_camera_indexes = []
camera_slot_map: Dict[int, int] = {}


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
        return sorted(set(node_indexes))

    if video_nodes:
        fallback_indexes = []
        for node in video_nodes:
            match = re.search(r"video(\d+)$", node.name)
            if match:
                fallback_indexes.append(int(match.group(1)))
        if fallback_indexes:
            return sorted(set(fallback_indexes))

    return list(range(max_scan + 1))


def _linux_video_nodes():
    if platform.system().lower() != "linux":
        return []
    return sorted(str(node) for node in Path("/dev").glob("video*"))


def detect_available_cameras(max_scan: int = 64):
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

    if platform.system().lower() == "linux":
        linux_candidates = _linux_candidate_indexes(64)
        if linux_candidates:
            fallback = [linux_candidates[0]]
            print(
                "No cameras passed frame-read detection; "
                f"falling back to first Linux video node index: {fallback}"
            )
            return fallback

    print("No cameras auto-detected; defaulting to [0]")
    return [0]


def stream_camera(slot: int, physical_index: int):
    camera_status[slot] = {
        "state": "opening",
        "frames": 0,
        "last_error": None,
        "physical_index": physical_index,
    }

    cap = open_capture(physical_index)
    if not cap.isOpened():
        camera_status[slot]["state"] = "open_failed"
        camera_status[slot]["last_error"] = "could_not_open"
        print(f"[slot{slot}/cam{physical_index}] Failed to open camera")
        return

    camera_status[slot]["state"] = "running"
    print(f"[slot{slot}/cam{physical_index}] Capture loop started")
    while True:
        ret, frame = cap.read()
        if not ret:
            camera_status[slot]["state"] = "read_failed"
            camera_status[slot]["last_error"] = "read_returned_false"
            time.sleep(0.2)
            continue

        resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        ok, buffer = cv2.imencode(
            ".jpg",
            resized,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
        )
        if not ok:
            camera_status[slot]["state"] = "encode_failed"
            camera_status[slot]["last_error"] = "jpeg_encode_failed"
            continue

        with frame_lock:
            frame_store[slot] = buffer.tobytes()

        camera_status[slot]["state"] = "running"
        camera_status[slot]["frames"] = int(camera_status[slot].get("frames", 0)) + 1
        camera_status[slot]["last_error"] = None

        time.sleep(FRAME_INTERVAL_SECONDS)


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "cameras": list(frame_store.keys()),
            "configured": configured_camera_indexes,
            "slot_map": camera_slot_map,
            "status": camera_status,
            "linux_video_nodes": _linux_video_nodes(),
        }
    )


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
    if cam_index not in camera_slot_map:
        return Response(
            f"Unknown camera slot {cam_index}. Available slots: {sorted(camera_slot_map.keys())}",
            status=404,
            mimetype="text/plain",
        )

    if cam_index not in frame_store:
        state = camera_status.get(cam_index, {})
        return Response(
            f"Camera slot {cam_index} is not ready yet. State: {state}",
            status=503,
            mimetype="text/plain",
        )

    return Response(
        mjpeg_generator(cam_index),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    camera_indexes = resolve_camera_indexes()
    configured_camera_indexes = camera_indexes
    camera_slot_map = {slot: idx for slot, idx in enumerate(camera_indexes)}
    print(f"Serving physical camera indexes: {camera_indexes}")
    print(f"Camera slot map: {camera_slot_map}")

    for slot, idx in camera_slot_map.items():
        t = threading.Thread(target=stream_camera, args=(slot, idx), daemon=True)
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
