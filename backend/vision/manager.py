"""Owns one CameraWorker per enabled camera plus the stats sampler thread.

The detector model is shared across workers (YOLO loads once) and guarded by
a lock because ultralytics inference is not thread-safe.
"""
import logging
import threading
import time
from typing import Optional

from .. import config, db
from .detector import BaseDetector, create_detector
from .worker import CameraWorker

log = logging.getLogger("parkinggo.manager")


class WorkerManager:
    def __init__(self):
        self._workers: dict[int, CameraWorker] = {}
        self._lock = threading.Lock()
        self._detector: Optional[BaseDetector] = None
        self._detector_lock = threading.Lock()
        self._stop = threading.Event()
        self._sampler: Optional[threading.Thread] = None

    @property
    def detector(self) -> BaseDetector:
        if self._detector is None:
            self._detector = create_detector()
        return self._detector

    def start(self) -> None:
        for camera in db.list_cameras():
            if camera["enabled"]:
                self.ensure_worker(camera)
        self._sampler = threading.Thread(target=self._sample_loop, daemon=True,
                                         name="occupancy-sampler")
        self._sampler.start()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            workers, self._workers = list(self._workers.values()), {}
        for worker in workers:
            worker.stop()

    def ensure_worker(self, camera: dict) -> CameraWorker:
        """Start (or restart, if the source changed) the worker for a camera."""
        with self._lock:
            existing = self._workers.get(camera["id"])
            if existing:
                same_source = (existing.camera["source"] == camera["source"]
                               and existing.camera["source_type"] == camera["source_type"])
                if same_source and camera["enabled"]:
                    existing.camera = camera
                    return existing
                self._workers.pop(camera["id"])
        if existing:
            existing.stop()
        if not camera["enabled"]:
            return None
        worker = CameraWorker(camera, self.detector, self._detector_lock)
        worker.start()
        with self._lock:
            self._workers[camera["id"]] = worker
        log.info("Started worker for camera %s (%s)", camera["id"], camera["name"])
        return worker

    def stop_worker(self, camera_id: int) -> None:
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop()

    def get(self, camera_id: int) -> Optional[CameraWorker]:
        with self._lock:
            return self._workers.get(camera_id)

    def reload_zones(self, camera_id: int) -> None:
        worker = self.get(camera_id)
        if worker:
            worker.reload_zones()

    def _sample_loop(self) -> None:
        while not self._stop.wait(config.SAMPLE_INTERVAL):
            with self._lock:
                workers = list(self._workers.values())
            for worker in workers:
                try:
                    summary = worker.status_summary()
                    if summary["total"]:
                        db.add_occupancy_sample(
                            worker.camera["id"], summary["free"],
                            summary["occupied"], summary["unknown"],
                        )
                except Exception:
                    log.exception("sampling failed for camera %s", worker.camera["id"])


manager = WorkerManager()
