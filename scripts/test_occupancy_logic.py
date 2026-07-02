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


def main() -> None:
    print("Dense-lot adjacent-zone bleed (the real-world bug this fixes)")
    test_dense_lot_adjacent_zone_bleed()
    print("Baseline occupancy cases")
    test_car_fully_inside_its_own_zone()
    test_empty_zone_no_detections()
    test_low_confidence_detection_is_unknown()
    test_frame_edge_clipped_box_falls_back_to_overlap()

    print(f"\n{checks['passed']} passed, {checks['failed']} failed")
    sys.exit(1 if checks["failed"] else 0)


if __name__ == "__main__":
    main()
