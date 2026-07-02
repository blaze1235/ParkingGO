import datetime as dt

from fastapi import APIRouter, HTTPException

from .. import db
from ..auth import AuthDep
from ..vision.manager import manager

router = APIRouter(prefix="/api", tags=["status"])


def _camera_status(camera: dict) -> dict:
    worker = manager.get(camera["id"])
    if worker:
        summary = worker.status_summary()
    else:
        zones = db.list_zones(camera["id"])
        summary = {
            "camera_id": camera["id"], "connected": False, "error": "Camera disabled",
            "total": len(zones), "free": 0, "occupied": 0, "unknown": len(zones),
            "zones": [{**z, "status": "unknown", "since": None} for z in zones],
        }
    summary["camera_name"] = camera["name"]
    summary["enabled"] = bool(camera["enabled"])
    return summary


@router.get("/status")
def all_status(token: str = AuthDep):
    """Occupancy summary for every camera — powers the dashboard."""
    return [_camera_status(c) for c in db.list_cameras()]


@router.get("/cameras/{camera_id}/status")
def camera_status(camera_id: int, token: str = AuthDep):
    camera = db.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _camera_status(camera)


@router.get("/cameras/{camera_id}/history")
def camera_history(camera_id: int, limit: int = 100, token: str = AuthDep):
    if not db.get_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    return db.list_status_events(camera_id, limit=min(limit, 500))


@router.get("/history")
def history(limit: int = 100, token: str = AuthDep):
    return db.list_status_events(limit=min(limit, 500))


@router.get("/cameras/{camera_id}/stats")
def camera_stats(camera_id: int, date: str = None, token: str = AuthDep):
    """Hourly-average free/occupied/unknown counts for one local day."""
    if not db.get_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    try:
        day = dt.date.fromisoformat(date) if date else dt.date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    start = dt.datetime.combine(day, dt.time.min).timestamp()
    end = dt.datetime.combine(day, dt.time.max).timestamp()
    samples = db.list_occupancy_samples(camera_id, start, end)

    hours: dict[int, dict] = {}
    for s in samples:
        hour = dt.datetime.fromtimestamp(s["sampled_at"]).hour
        bucket = hours.setdefault(hour, {"free": 0, "occupied": 0, "unknown": 0, "n": 0})
        for key in ("free", "occupied", "unknown"):
            bucket[key] += s[key]
        bucket["n"] += 1
    hourly = [
        {"hour": h,
         "free": round(b["free"] / b["n"], 2),
         "occupied": round(b["occupied"] / b["n"], 2),
         "unknown": round(b["unknown"] / b["n"], 2)}
        for h, b in sorted(hours.items())
    ]
    return {"date": day.isoformat(), "samples": len(samples), "hourly": hourly}
