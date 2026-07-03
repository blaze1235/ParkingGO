#!/usr/bin/env python3
"""Check how well the active vehicle detector performs on real footage.

Runs whichever detector is currently active (real YOLO if installed,
otherwise the mock fallback) against a video file, camera URL, or webcam,
and produces:

  - an annotated output video with detection boxes + confidence, so you can
    watch it and visually judge accuracy (missed cars, false boxes, etc.)
  - confidence and per-frame detection-count statistics

This turns "I'm not sure if it can tell a car from a shadow" into actual
evidence instead of a guess.

On first run this creates/uses a local .venv and installs everything needed
automatically -- including requirements-yolo.txt (PyTorch + ultralytics),
since without it there's no real detector to check. That download is a few
hundred MB to ~2GB depending on platform and takes a few minutes.

Usage:
    python3 scripts/check_detection_quality.py path/to/video.mp4
    python3 scripts/check_detection_quality.py rtsp://user:pass@host/stream --frames 60
    python3 scripts/check_detection_quality.py 0 --frames 30      # webcam
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts._bootstrap import ensure_deps_and_reexec  # noqa: E402

if __name__ == "__main__":
    os.chdir(ROOT)
    ensure_deps_and_reexec(
        script_file=__file__,
        probe_modules=["cv2", "numpy", "ultralytics"],
        requirement_files=["requirements.txt", "requirements-yolo.txt"],
        bootstrap_env_var="PARKINGGO_CHECK_BOOTSTRAPPED",
    )

import argparse

import cv2
import numpy as np

from backend.vision.annotate import annotate_frame
from backend.vision.detector import create_detector


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="video file path, RTSP/HTTP URL, or webcam index (e.g. 0)")
    parser.add_argument("--frames", type=int, default=40, help="frames to sample (default 40)")
    parser.add_argument("--out", default="data/detection_check.mp4", help="annotated output video path")
    args = parser.parse_args()

    is_webcam = args.source.isdigit() and len(args.source) <= 2
    is_url = "://" in args.source
    if is_webcam:
        source = int(args.source)
    elif is_url:
        source = args.source
    else:
        # Expand ~ ourselves: a quoted "~/..." arg reaches us literally,
        # since the shell only expands ~ when it's unquoted.
        source = str(Path(args.source).expanduser())
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        sys.exit(f"Could not open source: {source}"
                 + (f"  (from argument: {args.source})" if str(source) != args.source else ""))

    detector = create_detector()
    print(f"Detector backend: {detector.name}")
    if detector.name == "mock":
        print("WARNING: mock detector active (YOLO not installed) -- these results are")
        print("meaningless for judging real car detection. Install requirements-yolo.txt first.\n")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    is_live = total_frames <= 0  # webcam/RTSP report no known frame count
    frame_indices = None
    if not is_live:
        n = min(args.frames, total_frames)
        frame_indices = np.linspace(0, total_frames - 1, n, dtype=int)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    confidences: list[float] = []
    counts: list[int] = []
    sampled = 0

    def process(frame: np.ndarray) -> None:
        nonlocal writer, sampled
        detections = detector.detect(frame)
        counts.append(len(detections))
        confidences.extend(d.confidence for d in detections)
        annotated = annotate_frame(frame, [], detections)
        if writer is None:
            h, w = annotated.shape[:2]
            writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), 5, (w, h))
        writer.write(annotated)
        sampled += 1
        conf_range = (f", confidence {min(d.confidence for d in detections):.2f}"
                      f"-{max(d.confidence for d in detections):.2f}") if detections else ""
        print(f"  frame {sampled}/{args.frames}: {len(detections)} detection(s){conf_range}")

    print(f"Sampling {args.frames} frames from: {args.source}\n")
    if is_live:
        for _ in range(args.frames):
            ok, frame = cap.read()
            if not ok:
                break
            process(frame)
    else:
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if ok:
                process(frame)

    cap.release()
    if writer:
        writer.release()

    print(f"\n{'=' * 60}")
    print(f"Sampled {sampled} frames, {len(confidences)} total detections")
    if confidences:
        arr = np.array(confidences)
        print(f"Confidence: min={arr.min():.2f}  mean={arr.mean():.2f}  "
              f"median={np.median(arr):.2f}  max={arr.max():.2f}")
        low_conf = int((arr < 0.5).sum())
        if low_conf:
            print(f"  {low_conf}/{len(arr)} detections below 0.50 confidence "
                  f"-- borderline calls worth a closer look in the output video")
    else:
        print("No detections across sampled frames. For TOP-DOWN/AERIAL footage this is")
        print("EXPECTED: COCO-trained detectors (YOLO included) don't recognize cars viewed")
        print("straight from above. ParkingGo handles that case with its per-zone occupancy")
        print("classifier instead (enabled by default) -- draw your zones in the app and the")
        print("dashboard will classify them from each zone's own pixels. For side/angled")
        print("cameras, zero detections on footage that clearly has cars WOULD be a problem.")
    if counts:
        counts_arr = np.array(counts)
        print(f"Detections per frame: min={counts_arr.min()} "
              f"mean={counts_arr.mean():.1f} max={counts_arr.max()}")

    print(f"\nAnnotated output video: {out_path}")
    print("Watch it and check: are real cars boxed? Is anything missed?"
          " Any false boxes on shadows, pavement markings, or other clutter?")


if __name__ == "__main__":
    main()
