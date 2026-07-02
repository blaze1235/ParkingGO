#!/usr/bin/env python3
"""Generate a synthetic street-parking test video.

Creates a light-toned curbside scene with four parking bays and dark car
shapes that arrive and leave on a schedule. Designed to work with the mock
detector (dark blobs on a light background), so the whole ParkingGo pipeline
can be tested before installing YOLO or connecting a real camera.

Usage: python scripts/make_demo_video.py [output.mp4] [--seconds 60]
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 640, 360, 15

# Four curbside bays (x, y, w, h) above the road.
BAYS = [(40 + i * 150, 70, 120, 80) for i in range(4)]

# Per-bay occupancy schedule as (start_fraction, end_fraction) of the clip.
SCHEDULE = [
    [(0.00, 0.45), (0.70, 1.00)],  # Spot 1
    [(0.20, 0.80)],                # Spot 2
    [],                            # Spot 3 stays free (but gets a shadow — see SHADOW_SCHEDULE)
    [(0.00, 1.00)],                # Spot 4 always occupied
]

# A cast shadow (no car) sweeps across Spot 3 during this window, to verify
# the detector doesn't mistake a dark, smooth-gradient region for a vehicle.
SHADOW_BAY_INDEX = 2
SHADOW_SCHEDULE = [(0.30, 0.70)]


def draw_scene() -> np.ndarray:
    frame = np.full((H, W, 3), 172, dtype=np.uint8)          # pavement
    cv2.rectangle(frame, (0, 200), (W, H), (120, 120, 120), -1)  # road
    cv2.line(frame, (0, 205), (W, 205), (230, 230, 230), 3)      # curb line
    for x in range(0, W, 60):                                    # lane dashes
        cv2.line(frame, (x, 280), (x + 30, 280), (235, 235, 235), 4)
    for (x, y, w, h) in BAYS:                                    # bay markings
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), 2)
    return frame


def draw_car(frame: np.ndarray, bay: tuple) -> None:
    """A top-down car with enough internal detail (roof, mirrors, lights,
    door seam, wheels) to give it real Canny edge density — unlike a smooth
    shadow, which is a plain gradient with no internal structure."""
    x, y, w, h = bay
    cx1, cy1 = x + 12, y + 14
    cx2, cy2 = x + w - 12, y + h - 14
    cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), (45, 40, 40), -1)      # body
    cv2.rectangle(frame, (cx1 + 14, cy1 + 8), (cx2 - 14, cy2 - 8),
                  (80, 75, 70), -1)                                     # roof
    cv2.line(frame, ((cx1 + cx2) // 2, cy1 + 8), ((cx1 + cx2) // 2, cy2 - 8),
             (30, 28, 26), 1)                                           # door seam
    for wx in (cx1 + 8, cx2 - 8):
        for wy in (cy1 - 2, cy2 + 2):
            cv2.circle(frame, (wx, wy), 5, (25, 25, 25), -1)            # wheels
    for mx in (cx1 - 3, cx2 + 3):                                       # side mirrors
        cv2.rectangle(frame, (mx - 2, cy1 + 12), (mx + 2, cy1 + 18), (30, 28, 26), -1)
    for lx in (cx1 + 6, cx2 - 6):                                       # head/tail lights
        cv2.circle(frame, (lx, cy1 + 3), 2, (210, 210, 190), -1)
        cv2.circle(frame, (lx, cy2 - 3), 2, (60, 40, 40), -1)


def draw_shadow(frame: np.ndarray, bay: tuple) -> None:
    """A soft cast shadow with NO hard edges anywhere — a smooth diagonal
    cosine gradient, not a filled/blurred polygon (blurring a polygon still
    leaves a faint boundary Canny can pick up). This is what should still
    read as "free": dark, but structurally nothing like a car."""
    x, y, w, h = bay
    pad = 20
    rx, ry = max(x - pad, 0), max(y - pad, 0)
    rw = min(w + 2 * pad, frame.shape[1] - rx)
    rh = min(h + 2 * pad, frame.shape[0] - ry)
    yy, xx = np.mgrid[0:rh, 0:rw].astype(np.float32)
    diag = (xx + yy) / (rw + rh)                          # 0..1 across the diagonal
    alpha = (0.5 - 0.5 * np.cos(np.clip(diag, 0, 1) * np.pi)) * 0.6  # smooth falloff, no edges
    region = frame[ry:ry + rh, rx:rx + rw].astype(np.float32)
    frame[ry:ry + rh, rx:rx + rw] = (region * (1 - alpha[..., None])).astype(np.uint8)


def occupied_at(bay_index: int, t: float) -> bool:
    return any(start <= t <= end for start, end in SCHEDULE[bay_index])


def shadow_at(bay_index: int, t: float) -> bool:
    if bay_index != SHADOW_BAY_INDEX:
        return False
    return any(start <= t <= end for start, end in SHADOW_SCHEDULE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="data/demo.mp4")
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    total = args.seconds * FPS
    background = draw_scene()
    for i in range(total):
        frame = background.copy()
        t = i / total
        for bay_index, bay in enumerate(BAYS):
            if occupied_at(bay_index, t):
                draw_car(frame, bay)
            elif shadow_at(bay_index, t):
                draw_shadow(frame, bay)
        writer.write(frame)
    writer.release()

    print(f"Wrote {out_path} ({args.seconds}s @ {FPS}fps, {W}x{H})")
    print("Suggested zone rectangles (draw these in the calibration view):")
    for n, (x, y, w, h) in enumerate(BAYS, start=1):
        print(f"  Spot {n}: ({x},{y}) -> ({x + w},{y + h})")


if __name__ == "__main__":
    main()
