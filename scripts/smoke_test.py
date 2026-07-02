#!/usr/bin/env python3
"""End-to-end smoke test against a running ParkingGo server.

Requires the demo video (scripts/make_demo_video.py). Exercises the full
pipeline: login -> add camera -> draw zones -> wait for detection ->
verify occupancy, snapshot, stream, history, and stats endpoints.

Usage:
    python scripts/make_demo_video.py data/demo.mp4
    python run.py &          # in another terminal
    python scripts/smoke_test.py [http://127.0.0.1:8000]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DEMO = Path("data/demo.mp4").resolve()
TOKEN = ""
checks = {"passed": 0, "failed": 0}


def call(method: str, path: str, body=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data=data, timeout=30) as res:
        payload = res.read()
        return payload if raw else (json.loads(payload) if payload else None)


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    checks["passed" if condition else "failed"] += 1
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    global TOKEN
    if not DEMO.is_file():
        sys.exit("Demo video missing — run: python scripts/make_demo_video.py data/demo.mp4")

    print("1. Auth")
    try:
        call("POST", "/api/auth/login", {"username": "admin", "password": "wrong"})
        check("wrong password rejected", False)
    except Exception:
        check("wrong password rejected", True)
    TOKEN = call("POST", "/api/auth/login", {"username": "admin", "password": "admin"})["token"]
    check("login returns token", bool(TOKEN))

    print("2. Camera setup")
    cam = call("POST", "/api/cameras",
               {"name": "Smoke demo", "source_type": "file", "source": str(DEMO)})
    cam_id = cam["id"]
    check("camera created", cam["name"] == "Smoke demo", f"id={cam_id}")

    # Zones matching the demo video bays (Spot 4 is always occupied, Spot 3 always free).
    for n, (x, y, w, h) in enumerate([(40 + i * 150, 70, 120, 80) for i in range(4)], 1):
        poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        side = "left" if n % 2 else "right"
        call("POST", f"/api/cameras/{cam_id}/zones",
             {"name": f"Spot {n}", "polygon": poly, "side": side, "position": n})
    zones = call("GET", f"/api/cameras/{cam_id}/zones")
    check("4 zones saved", len(zones) == 4)

    print("3. Detection (waiting for pipeline to settle)...")
    deadline = time.time() + 40
    status = None
    while time.time() < deadline:
        status = call("GET", f"/api/cameras/{cam_id}/status")
        by_name = {z["name"]: z["status"] for z in status["zones"]}
        if by_name.get("Spot 4") == "occupied" and by_name.get("Spot 3") == "free":
            break
        time.sleep(2)
    by_name = {z["name"]: z["status"] for z in status["zones"]}
    check("camera connected", status["connected"])
    check("Spot 4 detected occupied", by_name.get("Spot 4") == "occupied", str(by_name))
    check("Spot 3 detected free", by_name.get("Spot 3") == "free")
    check("counts add up", status["free"] + status["occupied"] + status["unknown"] == 4)

    print("4. Media endpoints")
    jpeg = call("GET", f"/api/cameras/{cam_id}/snapshot?overlay=1", raw=True)
    check("snapshot is JPEG", jpeg[:2] == b"\xff\xd8", f"{len(jpeg)} bytes")

    req = urllib.request.Request(f"{BASE}/api/cameras/{cam_id}/stream?token={TOKEN}")
    with urllib.request.urlopen(req, timeout=15) as res:
        ctype = res.headers.get("Content-Type", "")
        chunk = res.read(20000)
    check("MJPEG stream serves frames",
          "multipart/x-mixed-replace" in ctype and b"\xff\xd8" in chunk)

    print("5. History & stats")
    events = call("GET", f"/api/cameras/{cam_id}/history")
    check("status events recorded", len(events) >= 4, f"{len(events)} events")
    stats = call("GET", f"/api/cameras/{cam_id}/stats")
    check("stats endpoint responds", "hourly" in stats)

    print("6. Cleanup")
    call("DELETE", f"/api/cameras/{cam_id}")
    check("camera deleted", all(c["id"] != cam_id for c in call("GET", "/api/cameras")))

    print(f"\n{checks['passed']} passed, {checks['failed']} failed")
    sys.exit(1 if checks["failed"] else 0)


if __name__ == "__main__":
    main()
