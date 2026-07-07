import shutil
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from .. import config, db
from ..auth import AuthDep
from ..models import CameraCreate, CameraUpdate
from ..vision.manager import manager

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

ALLOWED_VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
REDACTED_USERINFO = "***:***"


def _get_camera_or_404(camera_id: int) -> dict:
    camera = db.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def redact_source(source_type: str, source: str) -> str:
    """Mask embedded credentials (rtsp://user:pass@host/..) before a camera
    source ever reaches the frontend. Workers always read the real value
    straight from the database, so this only affects API responses."""
    if source_type != "url" or "://" not in source:
        return source
    try:
        parts = urlsplit(source)
    except ValueError:
        return source
    if not parts.username and not parts.password:
        return source
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, f"{REDACTED_USERINFO}@{netloc}", parts.path,
                       parts.query, parts.fragment))


def _with_runtime(camera: dict) -> dict:
    worker = manager.get(camera["id"])
    camera = dict(camera)
    camera["source"] = redact_source(camera["source_type"], camera["source"])
    camera["connected"] = bool(worker and worker.connected)
    camera["runtime_error"] = worker.error if worker else None
    return camera


@router.get("")
def list_cameras(token: str = AuthDep):
    return [_with_runtime(c) for c in db.list_cameras()]


@router.post("", status_code=201)
def create_camera(body: CameraCreate, token: str = AuthDep):
    if body.source_type == "webcam" and not body.source.isdigit():
        raise HTTPException(status_code=422, detail="Webcam source must be a device index, e.g. 0")
    camera = db.create_camera(body.name, body.source_type, body.source)
    manager.ensure_worker(camera)
    return _with_runtime(camera)


@router.post("/upload", status_code=201)
def create_camera_from_upload(name: str = Form(...), file: UploadFile = File(...),
                              token: str = AuthDep):
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(status_code=422,
                            detail=f"Unsupported video type {ext}; use {sorted(ALLOWED_VIDEO_EXT)}")
    config.ensure_dirs()
    dest = config.UPLOAD_DIR / f"upload_{int(time.time())}{ext}"
    written = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > config.MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Video file too large")
            out.write(chunk)
    camera = db.create_camera(name, "file", str(dest))
    manager.ensure_worker(camera)
    return _with_runtime(camera)


@router.get("/{camera_id}")
def get_camera(camera_id: int, token: str = AuthDep):
    return _with_runtime(_get_camera_or_404(camera_id))


@router.patch("/{camera_id}")
def update_camera(camera_id: int, body: CameraUpdate, token: str = AuthDep):
    existing = _get_camera_or_404(camera_id)
    if body.source and REDACTED_USERINFO in body.source:
        # Guards against a client round-tripping the masked value shown in
        # the UI back as a real update, which would overwrite (and lose)
        # the actual stored credentials.
        raise HTTPException(status_code=422,
                            detail="Source looks like a redacted display value, not a real URL")
    effective_type = body.source_type or existing["source_type"]
    effective_source = body.source if body.source is not None else existing["source"]
    if effective_type == "webcam" and not effective_source.isdigit():
        raise HTTPException(status_code=422, detail="Webcam source must be a device index, e.g. 0")
    camera = db.update_camera(camera_id, **body.model_dump())
    if camera["enabled"]:
        manager.ensure_worker(camera)
    else:
        manager.stop_worker(camera_id)
    return _with_runtime(camera)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: int, token: str = AuthDep):
    camera = _get_camera_or_404(camera_id)
    manager.stop_worker(camera_id)
    if camera["source_type"] == "file":
        path = Path(camera["source"])
        if path.is_file() and path.parent == config.UPLOAD_DIR:
            path.unlink(missing_ok=True)
    db.delete_camera(camera_id)


# ------------------------------------------------------------------ frames

def _placeholder_jpeg(text: str) -> bytes:
    frame = np.full((360, 640, 3), 40, dtype=np.uint8)
    cv2.putText(frame, text, (40, 190), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (200, 200, 200), 2, cv2.LINE_AA)
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


Quality = Literal["low", "medium", "high"]
# scale factor, JPEG quality per level. "high" matches pre-existing behavior
# exactly (scale 1.0, config.JPEG_QUALITY) so callers that don't pass
# quality -- notably calibration.js, which places zone polygons in
# source-frame pixels and must never receive a resized snapshot -- are
# unaffected.
_QUALITY_PRESETS: dict[str, tuple[float, int]] = {
    "high": (1.0, config.JPEG_QUALITY),
    "medium": (0.5, min(config.JPEG_QUALITY, 70)),
    "low": (0.33, min(config.JPEG_QUALITY, 55)),
}


def _encode(frame, quality: Quality = "high") -> bytes:
    scale, jpeg_quality = _QUALITY_PRESETS[quality]
    if scale != 1.0:
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    return buf.tobytes()


@router.get("/{camera_id}/snapshot")
def snapshot(camera_id: int, overlay: bool = False, quality: Quality = "high", token: str = AuthDep):
    _get_camera_or_404(camera_id)
    worker = manager.get(camera_id)
    frame = worker.snapshot(overlay=overlay) if worker else None
    data = _encode(frame, quality) if frame is not None else _placeholder_jpeg("No frame available yet")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/stream")
def stream(camera_id: int, overlay: bool = True, quality: Quality = "high", token: str = AuthDep):
    """MJPEG stream (multipart/x-mixed-replace) for use in an <img> tag.

    quality trades resolution/bitrate for bandwidth -- useful when several
    streams run at once (e.g. the Monitor grid), where "low" keeps N
    simultaneous tiles from saturating bandwidth the way N full-res streams
    would.
    """
    _get_camera_or_404(camera_id)
    boundary = b"--parkinggoframe"
    interval = 1.0 / config.STREAM_FPS

    def generate():
        while True:
            worker = manager.get(camera_id)
            if worker is None:
                data = _placeholder_jpeg("Camera disabled")
            else:
                frame = worker.snapshot(overlay=overlay)
                data = _encode(frame, quality) if frame is not None else \
                    _placeholder_jpeg("Connecting to camera...")
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                   + data + b"\r\n")
            time.sleep(interval)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=parkinggoframe",
        headers={"Cache-Control": "no-store"},
    )
