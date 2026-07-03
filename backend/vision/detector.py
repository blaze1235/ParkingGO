"""Vehicle detectors.

- YoloDetector: ultralytics YOLOv8, filtered to vehicle classes. Requires the
  optional `ultralytics` package (see requirements-yolo.txt).
- MockDetector: dependency-free fallback that finds car-sized dark blobs.
  It exists so the full pipeline (zones, occupancy, dashboard, history) can be
  exercised with the bundled synthetic demo video before installing YOLO.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .. import config

log = logging.getLogger("parkinggo.detector")

# COCO ids for vehicle-ish classes: car, motorcycle, bus, truck
VEHICLE_CLASS_IDS = {2, 3, 5, 7}


@dataclass
class Detection:
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    label: str


class BaseDetector:
    name = "base"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        raise NotImplementedError


# Below this, a downloaded .pt weights file is almost certainly a truncated
# or otherwise corrupted partial download, not a real model -- the smallest
# real YOLOv8 checkpoint (nano) is several MB. Loading a corrupted file
# doesn't raise an error; it silently produces a "model" that finds nothing
# in any image, which looks identical to "no cars in frame" with no signal
# that anything is wrong.
MIN_SANE_WEIGHTS_BYTES = 1_000_000


class YoloDetector(BaseDetector):
    name = "yolo"

    def __init__(self, model_path: str = None):
        from ultralytics import YOLO  # deferred: optional heavy dependency
        self.model = YOLO(model_path or config.YOLO_MODEL)
        ckpt_path = getattr(self.model, "ckpt_path", None)
        if ckpt_path:
            size = Path(ckpt_path).stat().st_size
            if size < MIN_SANE_WEIGHTS_BYTES:
                raise RuntimeError(
                    f"YOLO weights file {ckpt_path} is only {size} bytes -- almost certainly "
                    f"a corrupted/truncated download, not a real model. Delete it and let it "
                    f"re-download: rm {ckpt_path}"
                )

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(frame, verbose=False, conf=config.CONF_UNKNOWN)
        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in VEHICLE_CLASS_IDS:
                    continue
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                detections.append(Detection(
                    box=(x1, y1, x2, y2),
                    confidence=float(box.conf[0]),
                    label=self.model.names.get(cls_id, "vehicle"),
                ))
        return detections


class MockDetector(BaseDetector):
    """Detects car-sized dark blobs on a light background (demo video).

    This is a coarse, dependency-free stand-in for testing without YOLO — it
    has no learned features, so it cannot recognize a car by shape. To avoid
    flagging shadows/glare as vehicles, every dark blob candidate is screened
    with two classic shadow-rejection heuristics before being reported:

    - Edge density: real cars have panel seams, windows, mirrors, wheels —
      shadows are smooth gradients with almost no internal edges.
    - Texture (intensity) variance: catches soft-edged shadows that Canny
      misses, since shadow interiors are much flatter than a car's body.

    For real footage, install requirements-yolo.txt: YOLO distinguishes cars
    from shadows via learned visual features, not thresholding, and doesn't
    need this filter.
    """
    name = "mock"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY_INV)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        edges = cv2.Canny(gray, 40, 120)

        detections: list[Detection] = []
        min_area, max_area = (w * h) * 0.002, (w * h) * 0.25
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cw * ch
            if not (min_area <= area <= max_area):
                continue

            roi_gray = gray[y:y + ch, x:x + cw]
            roi_edges = edges[y:y + ch, x:x + cw]
            edge_density = float(np.count_nonzero(roi_edges)) / roi_edges.size
            texture_std = float(roi_gray.std())
            structure_score = edge_density * 3 + texture_std / 100
            if structure_score < config.MOCK_SHADOW_SCORE_MIN:
                continue  # smooth, low-detail dark region -> likely a shadow, not a vehicle

            # More internal structure -> higher confidence it's really a vehicle.
            confidence = min(0.95, 0.5 + structure_score - config.MOCK_SHADOW_SCORE_MIN)
            detections.append(Detection(
                box=(float(x), float(y), float(x + cw), float(y + ch)),
                confidence=confidence,
                label="vehicle",
            ))
        return detections


class NoneDetector(BaseDetector):
    """No whole-frame detection at all — occupancy comes purely from the
    per-zone classifier (backend/vision/zone_classifier.py). The right
    choice for top-down/aerial cameras, where COCO-trained detectors do not
    recognize cars and their output is pure noise."""
    name = "none"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        return []


def create_detector() -> BaseDetector:
    backend = config.DETECTOR_BACKEND
    if backend == "none":
        log.info("Detector disabled; using per-zone occupancy classifier only")
        return NoneDetector()
    if backend in ("auto", "yolo"):
        try:
            detector = YoloDetector()
            log.info("Using YOLO detector (%s)", config.YOLO_MODEL)
            return detector
        except Exception as exc:  # ImportError or model load failure
            if backend == "yolo":
                raise
            log.warning("YOLO unavailable (%s); falling back to mock detector. "
                        "Install requirements-yolo.txt for real detection.", exc)
    log.info("Using mock detector")
    return MockDetector()
