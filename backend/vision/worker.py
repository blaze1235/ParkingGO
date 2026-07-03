"""Per-camera processing: capture thread + detection thread.

The capture thread keeps only the most recent frame (RTSP buffers are drained
so detection never lags behind live video). The detection thread runs the
vehicle detector every DETECT_INTERVAL seconds, converts detections into
per-zone statuses with hysteresis, and records committed changes to history.
"""
import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .. import config, db
from .annotate import annotate_frame
from .detector import BaseDetector
from .geometry import box_center_in_zone, box_zone_overlap_ratio
from .zone_classifier import combine_statuses, zone_edge_density

log = logging.getLogger("parkinggo.worker")


class ZoneState:
    def __init__(self, zone: dict):
        self.zone = zone
        self.status = "unknown"
        self.since = time.time()
        self._pending: Optional[str] = None
        self._pending_ticks = 0
        self._committed_once = False

    def observe(self, status: str, camera_id: int, immediate: bool = False) -> None:
        """Apply hysteresis; commit + record history when stable.

        immediate=True bypasses hysteresis for this observation — used right
        after a scene cut (a looping test video restarting), where the world
        legitimately changed in one frame and smoothing would just show
        several seconds of stale statuses.
        """
        if status == self.status:
            self._pending = None
            self._pending_ticks = 0
            return
        if status != self._pending:
            self._pending = status
            self._pending_ticks = 1
        else:
            self._pending_ticks += 1
        if (immediate or self._pending_ticks >= config.STATUS_STABLE_TICKS
                or not self._committed_once):
            self.status = status
            self.since = time.time()
            self._pending = None
            self._pending_ticks = 0
            self._committed_once = True
            db.add_status_event(camera_id, self.zone["id"], self.zone["name"], status)


class CameraWorker:
    def __init__(self, camera: dict, detector: BaseDetector, detector_lock: threading.Lock):
        self.camera = camera
        self.detector = detector
        self.detector_lock = detector_lock
        self.lock = threading.RLock()
        self.latest_frame: Optional[np.ndarray] = None
        self.frame_time: float = 0.0
        self.last_detections: list = []
        self.zone_states: dict[int, ZoneState] = {}
        self.connected = False
        self.error: Optional[str] = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._scene_cut = False  # set when a looping file restarts
        self.reload_zones()

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        for target, name in ((self._capture_loop, "capture"), (self._detect_loop, "detect")):
            t = threading.Thread(target=target, daemon=True,
                                 name=f"cam{self.camera['id']}-{name}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)

    def reload_zones(self) -> None:
        zones = db.list_zones(self.camera["id"])
        with self.lock:
            old = self.zone_states
            self.zone_states = {
                z["id"]: old.get(z["id"], ZoneState(z)) for z in zones
            }
            for z in zones:  # pick up renamed zones / edited polygons
                self.zone_states[z["id"]].zone = z

    # -------------------------------------------------------------- capture

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        source = self.camera["source"]
        if self.camera["source_type"] == "webcam":
            cap = cv2.VideoCapture(int(source))
        else:
            cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _capture_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            cap = self._open_capture()
            if cap is None:
                self.connected = False
                self.error = f"Cannot open source: {self.camera['source']}"
                log.warning("[cam %s] %s (retry in %.0fs)", self.camera["id"], self.error, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1.0
            self.connected = True
            self.error = None
            is_file = self.camera["source_type"] == "file"
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frame_interval = 1.0 / fps if (is_file and 5 <= fps <= 120) else 0.0
            while not self._stop.is_set():
                started = time.time()
                ok, frame = cap.read()
                if not ok:
                    if is_file:  # loop test videos forever
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self._scene_cut = True  # statuses re-evaluate immediately
                        continue
                    log.warning("[cam %s] stream read failed; reconnecting", self.camera["id"])
                    break
                with self.lock:
                    self.latest_frame = frame
                    self.frame_time = time.time()
                if frame_interval:  # pace file playback to real time
                    delay = frame_interval - (time.time() - started)
                    if delay > 0:
                        self._stop.wait(delay)
            cap.release()
            self.connected = False

    # ------------------------------------------------------------ detection

    def _detect_loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            self._detect_once()
            elapsed = time.time() - started
            self._stop.wait(max(0.05, config.DETECT_INTERVAL - elapsed))

    def _detect_once(self) -> None:
        with self.lock:
            frame = self.latest_frame
            frame_time = self.frame_time
        stale = frame is None or (time.time() - frame_time) > config.FRAME_STALE_SECONDS
        if stale:
            with self.lock:
                self.last_detections = []
                for state in self.zone_states.values():
                    state.observe("unknown", self.camera["id"])
            return

        too_dark = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) < config.MIN_BRIGHTNESS
        detections = []
        if not too_dark:
            try:
                with self.detector_lock:
                    detections = self.detector.detect(frame)
            except Exception:
                log.exception("[cam %s] detection failed", self.camera["id"])
                too_dark = True  # treat as unreliable -> unknown

        immediate = self._scene_cut
        self._scene_cut = False
        with self.lock:
            self.last_detections = detections
            for state in self.zone_states.values():
                if too_dark:
                    state.observe("unknown", self.camera["id"])
                    continue
                state.observe(self._classify_zone(state.zone, detections, frame),
                              self.camera["id"], immediate=immediate)

    @staticmethod
    def _classify_zone(zone: dict, detections: list, frame=None) -> str:
        """Two independent signals, merged by combine_statuses():

        1. Whole-frame detector (YOLO): a vehicle counts as "in" a zone if
           its detection box center falls inside the zone polygon, or
           (fallback, for boxes clipped at the frame edge) if it has very
           heavy area overlap. Center-in-zone is the primary criterion
           because in a dense lot a neighboring car's box often spills 25%+
           into the next stall over — especially with a cast shadow widening
           the box on one side — which used to falsely mark the empty
           neighboring zone as occupied. This signal carries side/angled
           cameras, the views the detector was trained on.
        2. Per-zone structure score: carries top-down/aerial cameras, where
           COCO detectors do not recognize cars at all (verified on real
           footage — see zone_classifier.py).
        """
        best_conf = 0.0
        for det in detections:
            in_zone = box_center_in_zone(det.box, zone["polygon"])
            if not in_zone:
                overlap = box_zone_overlap_ratio(det.box, zone["polygon"])
                in_zone = overlap >= config.OVERLAP_THRESHOLD
            if in_zone:
                best_conf = max(best_conf, det.confidence)
        if best_conf >= config.CONF_OCCUPIED:
            detector_status = "occupied"
        elif best_conf >= config.CONF_UNKNOWN:
            detector_status = "unknown"  # something car-ish but low confidence
        else:
            detector_status = "free"

        if not config.ZONE_CLASSIFIER_ENABLED or frame is None:
            return detector_status
        score = zone_edge_density(frame, zone["polygon"])
        return combine_statuses(detector_status, score)

    # -------------------------------------------------------------- outputs

    def snapshot(self, overlay: bool = False) -> Optional[np.ndarray]:
        with self.lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
            zones = self.zones_with_status()
            detections = list(self.last_detections)
        return annotate_frame(frame, zones, detections) if overlay else frame

    def zones_with_status(self) -> list[dict]:
        with self.lock:
            return [
                {**state.zone, "status": state.status, "since": state.since}
                for state in self.zone_states.values()
            ]

    def status_summary(self) -> dict:
        zones = self.zones_with_status()
        counts = {"free": 0, "occupied": 0, "unknown": 0}
        for z in zones:
            counts[z["status"]] += 1
        return {
            "camera_id": self.camera["id"],
            "connected": self.connected,
            "error": self.error,
            "total": len(zones),
            **counts,
            "zones": zones,
        }
