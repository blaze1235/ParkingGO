#!/usr/bin/env python3
"""Unit tests for zone/vehicle geometry and occupancy classification.

No server or video required — pure logic tests. Run directly:
    python scripts/test_occupancy_logic.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.vision.geometry import box_center_in_zone, box_zone_overlap_ratio
from backend.vision.worker import CameraWorker

checks = {"passed": 0, "failed": 0}


def check(name: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    checks["passed" if condition else "failed"] += 1
    print(f"  [{status}] {name}")


class FakeDetection:
    def __init__(self, box, confidence=0.9):
        self.box = box
        self.confidence = confidence


def test_dense_lot_adjacent_zone_bleed():
    """Regression test: a car parked in one stall, with its detection box
    widened by a cast shadow so it spills into the next stall over, must not
    mark the empty neighboring stall as occupied. This was a real false
    positive seen on dense real-world parking-lot footage (adjacent stalls
    with tightly packed cars and long shadows falsely flagged as occupied)."""
    zone_a = [[0, 0], [100, 0], [100, 100], [0, 100]]
    zone_b = [[100, 0], [200, 0], [200, 100], [100, 100]]  # empty, adjacent
    # Car genuinely in Spot A; box shadow-widened 30px (30%) into Spot B.
    car_box = (10, 10, 130, 90)

    overlap_into_b = box_zone_overlap_ratio(car_box, zone_b)
    check("neighbor zone sees >=25% box overlap (the old false-positive trigger)",
          overlap_into_b >= 0.25)
    check("neighbor zone's box-center check correctly says 'not in this zone'",
          not box_center_in_zone(car_box, zone_b))

    result_a = CameraWorker._classify_zone({"polygon": zone_a}, [FakeDetection(car_box)])
    result_b = CameraWorker._classify_zone({"polygon": zone_b}, [FakeDetection(car_box)])
    check("Spot A (the actual car) classified occupied", result_a == "occupied")
    check("Spot B (empty neighbor) NOT falsely classified occupied", result_b == "free")


def test_car_fully_inside_its_own_zone():
    zone = [[0, 0], [100, 0], [100, 100], [0, 100]]
    car_box = (20, 20, 80, 80)
    result = CameraWorker._classify_zone({"polygon": zone}, [FakeDetection(car_box)])
    check("car centered in its own zone -> occupied", result == "occupied")


def test_empty_zone_no_detections():
    zone = [[0, 0], [100, 0], [100, 100], [0, 100]]
    result = CameraWorker._classify_zone({"polygon": zone}, [])
    check("no detections at all -> free", result == "free")


def test_low_confidence_detection_is_unknown():
    zone = [[0, 0], [100, 0], [100, 100], [0, 100]]
    car_box = (20, 20, 80, 80)
    result = CameraWorker._classify_zone({"polygon": zone}, [FakeDetection(car_box, confidence=0.30)])
    check("low-confidence detection centered in zone -> unknown, not occupied", result == "unknown")


def test_frame_edge_clipped_box_falls_back_to_overlap():
    """A box clipped at the frame boundary can have its true center outside
    the zone even though the vehicle is genuinely parked in it -- heavy area
    overlap (>=OVERLAP_THRESHOLD) should still catch this case."""
    zone = [[0, 0], [100, 0], [100, 100], [0, 100]]
    # Box extends far past the zone on one side (as if clipped/mis-detected
    # at a frame edge), pulling its center outside zone -- but it still
    # covers the zone almost completely.
    clipped_box = (-150, 0, 100, 100)
    center_outside = not box_center_in_zone(clipped_box, zone)
    check("clipped box's center falls outside the zone (sets up the fallback case)",
          center_outside)
    result = CameraWorker._classify_zone({"polygon": zone}, [FakeDetection(clipped_box)])
    check("heavy overlap fallback still classifies it occupied", result == "occupied")


def test_zone_classifier_structure_scoring():
    """The per-zone classifier must score a car-like textured zone high and
    flat pavement low — this is what carries top-down/aerial cameras, where
    COCO detectors don't recognize cars at all."""
    import cv2
    import numpy as np
    from backend.vision.zone_classifier import zone_edge_density

    frame = np.full((400, 800, 3), 150, dtype=np.uint8)  # flat pavement
    # "car" in the right half, top-down: white body with black windshield,
    # rear window, sunroof, panel seams and wheels — the high-contrast
    # internal structure every real car has and flat pavement lacks
    cv2.rectangle(frame, (450, 80), (720, 320), (230, 228, 225), -1)   # body
    cv2.rectangle(frame, (480, 110), (560, 290), (25, 25, 30), -1)     # windshield
    cv2.rectangle(frame, (640, 120), (700, 280), (30, 30, 35), -1)     # rear window
    cv2.rectangle(frame, (580, 150), (625, 250), (40, 40, 45), -1)     # sunroof
    for seam_x in (575, 635):                                          # panel seams
        cv2.line(frame, (seam_x, 85), (seam_x, 315), (60, 60, 60), 3)
    for hood_x in (455, 465):                                          # hood creases
        cv2.line(frame, (hood_x, 90), (hood_x, 310), (100, 100, 100), 2)
    for trim_y in (95, 305):                                           # side trim
        cv2.line(frame, (455, trim_y), (715, trim_y), (80, 80, 80), 3)
    cv2.rectangle(frame, (505, 70), (535, 82), (35, 35, 40), -1)       # mirrors
    cv2.rectangle(frame, (505, 318), (535, 330), (35, 35, 40), -1)
    for lx in (452, 716):                                              # light clusters
        for ly in (100, 200, 300):
            cv2.circle(frame, (lx, ly), 7, (255, 240, 200), -1)
    for wx, wy in ((470, 90), (700, 90), (470, 310), (700, 310)):      # wheels
        cv2.circle(frame, (wx, wy), 16, (20, 20, 20), -1)
    cv2.line(frame, (455, 200), (715, 200), (120, 120, 120), 2)        # roof crease
    for hx in (595, 615):                                              # door handles
        for hy in (105, 295):
            cv2.rectangle(frame, (hx, hy), (hx + 12, hy + 6), (70, 70, 70), -1)

    empty_zone = [[40, 40], [360, 40], [360, 360], [40, 360]]
    # zone drawn stall-tight around the car, the way real stall markings sit
    car_zone = [[440, 65], [730, 65], [730, 335], [440, 335]]
    s_empty = zone_edge_density(frame, empty_zone)
    s_car = zone_edge_density(frame, car_zone)
    check("flat pavement zone scores low", s_empty is not None and s_empty < 0.05)
    check("car-structured zone scores high", s_car is not None and s_car > 0.13)

    tiny_zone = [[0, 0], [10, 0], [10, 10], [0, 10]]
    check("tiny zone crop is unscoreable (None)", zone_edge_density(frame, tiny_zone) is None)
    dark = np.full((400, 400, 3), 5, dtype=np.uint8)
    night_zone = [[50, 50], [350, 50], [350, 350], [50, 350]]
    check("near-black zone is unscoreable (None)", zone_edge_density(dark, night_zone) is None)


def test_combine_statuses():
    from backend import config
    from backend.vision.zone_classifier import combine_statuses

    occ, free = config.ZONE_EDGE_OCCUPIED, config.ZONE_EDGE_FREE
    check("detector occupied wins regardless of zone score",
          combine_statuses("occupied", 0.01) == "occupied")
    check("high zone score alone -> occupied (aerial case, detector blind)",
          combine_statuses("free", occ + 0.05) == "occupied")
    check("low zone score + detector free -> free",
          combine_statuses("free", free - 0.05) == "free")
    check("ambiguous zone score -> unknown, not a guess",
          combine_statuses("free", (occ + free) / 2) == "unknown")
    check("unscoreable zone falls back to detector verdict",
          combine_statuses("free", None) == "free")
    check("detector unknown is not overridden to free by a low score",
          combine_statuses("unknown", free - 0.05) == "unknown")


def test_redact_source():
    """RTSP/IP camera URLs may carry credentials (rtsp://user:pass@host/..);
    these must never reach the frontend. Only source_type == "url" entries
    with embedded userinfo get masked -- file paths, webcam device indices,
    and credential-free URLs pass through unchanged."""
    from backend.api.routes_cameras import redact_source

    check("rtsp with credentials -> host/path kept, credentials masked",
          redact_source("url", "rtsp://admin:s3cret@192.168.1.10:554/stream1")
          == "rtsp://***:***@192.168.1.10:554/stream1")
    check("http with credentials -> masked too",
          redact_source("url", "http://user:pw@cam.example.com/video")
          == "http://***:***@cam.example.com/video")
    check("url with no credentials -> unchanged",
          redact_source("url", "rtsp://192.168.1.10:554/stream1")
          == "rtsp://192.168.1.10:554/stream1")
    check("file path source -> untouched (not a url source_type)",
          redact_source("file", "/data/uploads/upload_123.mp4")
          == "/data/uploads/upload_123.mp4")
    check("webcam device index -> untouched",
          redact_source("webcam", "0") == "0")
    check("no '://' at all -> untouched (short-circuits before parsing)",
          redact_source("url", "not a url at all") == "not a url at all")
    check("unparseable url (urlsplit raises ValueError) -> falls back to original",
          redact_source("url", "rtsp://[::1/broken") == "rtsp://[::1/broken")


def main() -> None:
    print("Dense-lot adjacent-zone bleed (the real-world bug this fixes)")
    test_dense_lot_adjacent_zone_bleed()
    print("Baseline occupancy cases")
    test_car_fully_inside_its_own_zone()
    test_empty_zone_no_detections()
    test_low_confidence_detection_is_unknown()
    test_frame_edge_clipped_box_falls_back_to_overlap()
    print("Per-zone occupancy classifier (aerial/top-down support)")
    test_zone_classifier_structure_scoring()
    test_combine_statuses()
    print("Camera source credential redaction")
    test_redact_source()

    print(f"\n{checks['passed']} passed, {checks['failed']} failed")
    sys.exit(1 if checks["failed"] else 0)


if __name__ == "__main__":
    main()
