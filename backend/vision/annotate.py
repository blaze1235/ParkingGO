"""Overlay drawing for the live camera view."""
import cv2
import numpy as np

STATUS_COLORS_BGR = {
    "free": (80, 190, 60),      # green
    "occupied": (60, 60, 220),  # red
    "unknown": (150, 150, 150), # gray
}
DETECTION_COLOR = (200, 160, 40)


def annotate_frame(frame: np.ndarray, zones: list[dict], detections: list) -> np.ndarray:
    """zones: [{name, polygon, status}], detections: [Detection]. Returns a copy."""
    out = frame.copy()
    overlay = frame.copy()

    for zone in zones:
        pts = np.array(zone["polygon"], dtype=np.int32)
        color = STATUS_COLORS_BGR.get(zone["status"], STATUS_COLORS_BGR["unknown"])
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(out, [pts], isClosed=True, color=color, thickness=2)

    cv2.addWeighted(overlay, 0.35, out, 0.65, 0, dst=out)

    for zone in zones:
        pts = np.array(zone["polygon"], dtype=np.int32)
        cx, cy = pts.mean(axis=0).astype(int)
        label = f'{zone["name"]}: {zone["status"]}'
        cv2.putText(out, label, (cx - 40, cy), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, label, (cx - 40, cy), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)

    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det.box)
        cv2.rectangle(out, (x1, y1), (x2, y2), DETECTION_COLOR, 2)
        cv2.putText(out, f"{det.label} {det.confidence:.2f}", (x1, max(15, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, DETECTION_COLOR, 1, cv2.LINE_AA)
    return out
