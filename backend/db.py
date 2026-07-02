"""SQLite persistence layer.

Connections are opened per call: cheap for an MVP-scale workload and safe
across the FastAPI event loop and the camera worker threads.
"""
import json
import sqlite3
import time
from typing import Any, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'url',   -- url | file | webcam
    source      TEXT NOT NULL,                 -- rtsp/http url, file path, or device index
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id  INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    polygon    TEXT NOT NULL,                  -- JSON [[x,y], ...] in source pixels
    side       TEXT NOT NULL DEFAULT 'right',  -- left | right (road illustration)
    position   INTEGER NOT NULL DEFAULT 0,     -- ordering along the road
    created_at REAL NOT NULL
);

-- One row per committed status change: "Spot 1 became occupied at 14:25".
CREATE TABLE IF NOT EXISTS status_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id  INTEGER NOT NULL,
    zone_id    INTEGER NOT NULL,
    zone_name  TEXT NOT NULL,
    status     TEXT NOT NULL,                  -- free | occupied | unknown
    changed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_camera_time ON status_events(camera_id, changed_at);

-- Periodic per-camera occupancy snapshot for daily statistics.
CREATE TABLE IF NOT EXISTS occupancy_samples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id  INTEGER NOT NULL,
    free       INTEGER NOT NULL,
    occupied   INTEGER NOT NULL,
    unknown    INTEGER NOT NULL,
    sampled_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_camera_time ON occupancy_samples(camera_id, sampled_at);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    config.ensure_dirs()
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _rows(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def _row(query: str, params: tuple = ()) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        r = conn.execute(query, params).fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------- cameras

def list_cameras() -> list[dict]:
    return _rows("SELECT * FROM cameras ORDER BY id")


def get_camera(camera_id: int) -> Optional[dict]:
    return _row("SELECT * FROM cameras WHERE id=?", (camera_id,))


def create_camera(name: str, source_type: str, source: str) -> dict:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO cameras(name, source_type, source, enabled, created_at) VALUES (?,?,?,1,?)",
            (name, source_type, source, time.time()),
        )
        camera_id = cur.lastrowid
    return get_camera(camera_id)


def update_camera(camera_id: int, **fields) -> Optional[dict]:
    allowed = {k: v for k, v in fields.items()
               if k in {"name", "source_type", "source", "enabled"} and v is not None}
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        with _connect() as conn:
            conn.execute(f"UPDATE cameras SET {sets} WHERE id=?", (*allowed.values(), camera_id))
    return get_camera(camera_id)


def delete_camera(camera_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        conn.execute("DELETE FROM status_events WHERE camera_id=?", (camera_id,))
        conn.execute("DELETE FROM occupancy_samples WHERE camera_id=?", (camera_id,))


# ------------------------------------------------------------------ zones

def _zone_out(row: dict) -> dict:
    row["polygon"] = json.loads(row["polygon"])
    return row


def list_zones(camera_id: int) -> list[dict]:
    return [_zone_out(r) for r in _rows(
        "SELECT * FROM zones WHERE camera_id=? ORDER BY position, id", (camera_id,))]


def get_zone(zone_id: int) -> Optional[dict]:
    r = _row("SELECT * FROM zones WHERE id=?", (zone_id,))
    return _zone_out(r) if r else None


def create_zone(camera_id: int, name: str, polygon: list, side: str, position: int) -> dict:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO zones(camera_id, name, polygon, side, position, created_at) VALUES (?,?,?,?,?,?)",
            (camera_id, name, json.dumps(polygon), side, position, time.time()),
        )
        zone_id = cur.lastrowid
    return get_zone(zone_id)


def update_zone(zone_id: int, **fields) -> Optional[dict]:
    allowed = {}
    for k, v in fields.items():
        if v is None or k not in {"name", "polygon", "side", "position"}:
            continue
        allowed[k] = json.dumps(v) if k == "polygon" else v
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        with _connect() as conn:
            conn.execute(f"UPDATE zones SET {sets} WHERE id=?", (*allowed.values(), zone_id))
    return get_zone(zone_id)


def delete_zone(zone_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM zones WHERE id=?", (zone_id,))


# ---------------------------------------------------------------- history

def add_status_event(camera_id: int, zone_id: int, zone_name: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO status_events(camera_id, zone_id, zone_name, status, changed_at) VALUES (?,?,?,?,?)",
            (camera_id, zone_id, zone_name, status, time.time()),
        )


def list_status_events(camera_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    if camera_id is None:
        return _rows("SELECT * FROM status_events ORDER BY changed_at DESC LIMIT ?", (limit,))
    return _rows(
        "SELECT * FROM status_events WHERE camera_id=? ORDER BY changed_at DESC LIMIT ?",
        (camera_id, limit),
    )


def add_occupancy_sample(camera_id: int, free: int, occupied: int, unknown: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO occupancy_samples(camera_id, free, occupied, unknown, sampled_at) VALUES (?,?,?,?,?)",
            (camera_id, free, occupied, unknown, time.time()),
        )


def list_occupancy_samples(camera_id: int, since: float, until: float) -> list[dict]:
    return _rows(
        "SELECT free, occupied, unknown, sampled_at FROM occupancy_samples "
        "WHERE camera_id=? AND sampled_at>=? AND sampled_at<=? ORDER BY sampled_at",
        (camera_id, since, until),
    )
