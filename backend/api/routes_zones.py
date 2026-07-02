from fastapi import APIRouter, HTTPException

from .. import db
from ..auth import AuthDep
from ..models import ZoneCreate, ZoneUpdate
from ..vision.manager import manager

router = APIRouter(prefix="/api", tags=["zones"])


@router.get("/cameras/{camera_id}/zones")
def list_zones(camera_id: int, token: str = AuthDep):
    if not db.get_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    return db.list_zones(camera_id)


@router.post("/cameras/{camera_id}/zones", status_code=201)
def create_zone(camera_id: int, body: ZoneCreate, token: str = AuthDep):
    if not db.get_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    zone = db.create_zone(camera_id, body.name, body.polygon, body.side, body.position)
    manager.reload_zones(camera_id)
    return zone


@router.patch("/zones/{zone_id}")
def update_zone(zone_id: int, body: ZoneUpdate, token: str = AuthDep):
    if not db.get_zone(zone_id):
        raise HTTPException(status_code=404, detail="Zone not found")
    zone = db.update_zone(zone_id, **body.model_dump())
    manager.reload_zones(zone["camera_id"])
    return zone


@router.delete("/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: int, token: str = AuthDep):
    zone = db.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete_zone(zone_id)
    manager.reload_zones(zone["camera_id"])
