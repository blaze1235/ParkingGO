"""Angle-independent per-zone occupancy scoring.

Whole-frame car detectors (YOLO etc.) are trained on ground-level photos and
fail badly on straight-down/aerial parking cameras — verified empirically:
on real nadir parking-lot footage, both YOLOv8 and EfficientDet see the cars
as "cell phones" or nothing at all, full-frame and tiled alike.

This module classifies each marked zone from its own pixels instead: a
parked car fills the zone with strong internal edges (windshield outline,
body panels, wheels, roofline shadows) while an empty stall is compara-
tively flat pavement. Measured on real 1080p aerial footage, Canny(60,160)
edge density on scale-normalized crops separates the classes cleanly:
occupied stalls scored 0.145-0.236 and empty stalls 0.006-0.089, and the
gap holds at half resolution. It is view-angle agnostic, so it also works
for the side/angled cameras where the detector already does well — there
the two signals simply agree.

The zone score is combined with the detector signal in combine_statuses():
either signal saying "occupied" wins; scores in the ambiguous band between
the free and occupied thresholds return "unknown" (rendered gray) rather
than guessing.
"""
from typing import Optional, Sequence

import cv2
import numpy as np

from .. import config

# Canny thresholds chosen by sweep on real footage: low enough to keep the
# edges of dark cars in shade, high enough to suppress faint pavement
# texture and low-contrast clutter (see module docstring).
CANNY_LO, CANNY_HI = 60, 160
# Zone crops are resized so their longest side is this many pixels before
# measuring edge density, making the score resolution-independent.
NORM_SIZE = 128
# Below this many pixels on the longest side (in source resolution), the
# crop carries too little detail to score reliably -> "unknown".
MIN_CROP_PX = 24
# Zones darker than this mean gray value (0-255) are unscoreable (night,
# deep shadow) -> "unknown".
MIN_ZONE_BRIGHTNESS = 15


def zone_edge_density(frame: np.ndarray, polygon: Sequence[Sequence[float]]) -> Optional[float]:
    """Edge density of the polygon's interior, or None if unscoreable.

    Canny runs on the raw bounding-rect crop BEFORE masking (masking first
    would manufacture artificial edges along the polygon boundary); edge
    pixels are then counted only inside the slightly-eroded polygon mask so
    stall paint lines sitting exactly on the zone border don't count.
    """
    h, w = frame.shape[:2]
    pts = np.array(polygon, dtype=np.float64)
    x1 = int(max(0, np.floor(pts[:, 0].min())))
    y1 = int(max(0, np.floor(pts[:, 1].min())))
    x2 = int(min(w, np.ceil(pts[:, 0].max())))
    y2 = int(min(h, np.ceil(pts[:, 1].max())))
    if x2 - x1 < 4 or y2 - y1 < 4 or max(x2 - x1, y2 - y1) < MIN_CROP_PX:
        return None

    crop = frame[y1:y2, x1:x2]
    scale = NORM_SIZE / max(crop.shape[0], crop.shape[1])
    crop = cv2.resize(crop, (max(8, round(crop.shape[1] * scale)),
                             max(8, round(crop.shape[0] * scale))))

    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    local_pts = ((pts - [x1, y1]) * scale).astype(np.int32)
    cv2.fillPoly(mask, [local_pts], 255)
    erode_px = max(1, NORM_SIZE // 32)
    mask = cv2.erode(mask, np.ones((erode_px * 2 + 1, erode_px * 2 + 1), np.uint8))
    area = int(np.count_nonzero(mask))
    if area < 64:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if float(gray[mask > 0].mean()) < MIN_ZONE_BRIGHTNESS:
        return None

    edges = cv2.Canny(gray, CANNY_LO, CANNY_HI)
    return float(np.count_nonzero(edges[mask > 0])) / area


def combine_statuses(detector_status: str, zone_score: Optional[float]) -> str:
    """Merge the whole-frame detector verdict with the per-zone score.

    Either signal alone is enough for "occupied" (the detector carries
    angled cameras it was trained for; the zone score carries aerial views
    the detector is blind to). "free" requires the zone to actually look
    empty; ambiguous zone scores surface as "unknown" instead of a guess.
    """
    if detector_status == "occupied":
        return "occupied"
    if zone_score is None:
        return detector_status
    if zone_score >= config.ZONE_EDGE_OCCUPIED:
        return "occupied"
    if detector_status == "unknown":
        return "unknown"
    if zone_score >= config.ZONE_EDGE_FREE:
        return "unknown"
    return "free"
