"""Vehicle detectors.

- YoloDetector: ultralytics YOLOv8, filtered to vehicle classes. Requires the
  optional `ultralytics` package (see requirements-yolo.txt).
- MockDetector: dependency-free fallback that finds car-sized dark blobs.
  It exists so the full pipeline (zones, occupancy, dashboard, history) can be
  exercised with the bundled synthetic demo video before installing YOLO.
"""
import logging
from dataclasses import dataclass

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


class YoloDetector(BaseDetector):
    name = "yolo"

    def __init__(self, model_path: str = None):
        from ultralytics import YOLO  # deferred: optional heavy dependency
        self.model = YOLO(model_path or config.YOLO_MODEL)

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
    """Detects car-sized dark blobs on a light background (demo video)."""
    name = "mock"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY_INV)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        min_area, max_area = (w * h) * 0.002, (w * h) * 0.25
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cw * ch
            if not (min_area <= area <= max_area):
                continue
            detections.append(Detection(
                box=(float(x), float(y), float(x + cw), float(y + ch)),
                confidence=0.9,
                label="vehicle",
            ))
        return detections


def create_detector() -> BaseDetector:
    backend = config.DETECTOR_BACKEND
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
