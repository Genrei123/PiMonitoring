import platform
import time
from pathlib import Path

import cv2


def open_capture(index: int):
    system_name = platform.system().lower()

    if system_name == "windows":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap, "CAP_DSHOW"
        cap.release()

        cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
        if cap.isOpened():
            return cap, "CAP_MSMF"
        cap.release()

    elif system_name == "linux":
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if cap.isOpened():
            return cap, "CAP_V4L2"
        cap.release()

    cap = cv2.VideoCapture(index)
    return cap, "DEFAULT"


def list_video_devices_linux():
    if platform.system().lower() != "linux":
        return []

    dev_dir = Path("/dev")
    return sorted(str(p) for p in dev_dir.glob("video*"))


def probe_index(index: int):
    cap, backend = open_capture(index)
    if not cap.isOpened():
        return {
            "index": index,
            "opened": False,
            "read_ok": False,
            "backend": backend,
            "width": None,
            "height": None,
            "fps": None,
        }

    read_ok = False
    frame = None
    for _ in range(5):
        ok, frame = cap.read()
        if ok and frame is not None:
            read_ok = True
            break
        time.sleep(0.1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    cap.release()

    return {
        "index": index,
        "opened": True,
        "read_ok": read_ok,
        "backend": backend,
        "width": width,
        "height": height,
        "fps": fps,
    }


def main():
    print("=== Camera Probe ===")
    print(f"Platform: {platform.platform()}")

    linux_devices = list_video_devices_linux()
    if linux_devices:
        print(f"Linux video devices: {', '.join(linux_devices)}")

    results = [probe_index(i) for i in range(8)]
    detected = [r for r in results if r["opened"] and r["read_ok"]]

    for r in results:
        if r["opened"]:
            print(
                f"Index {r['index']}: opened={r['opened']} read_ok={r['read_ok']} "
                f"backend={r['backend']} size={r['width']}x{r['height']} fps={r['fps']:.2f}"
            )
        else:
            print(f"Index {r['index']}: opened=False backend={r['backend']}")

    print("---")
    print(f"Readable cameras found: {len(detected)}")
    print(f"Readable indexes: {[r['index'] for r in detected]}")

    if len(detected) >= 2:
        print("PASS: At least 2 cameras are readable.")
    else:
        print("FAIL: Fewer than 2 readable cameras were found.")
        print("Tip: On Raspberry Pi, check power, USB bandwidth, and /boot/firmware/config.txt camera settings.")


if __name__ == "__main__":
    main()
