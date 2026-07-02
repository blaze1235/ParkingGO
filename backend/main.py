"""ParkingGo — web-based AI street parking monitor (FastAPI app)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .api import routes_auth, routes_cameras, routes_status, routes_zones
from .vision.manager import manager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    manager.start()
    yield
    manager.shutdown()


app = FastAPI(title="ParkingGo", version="0.1.0", lifespan=lifespan)

app.include_router(routes_auth.router)
app.include_router(routes_cameras.router)
app.include_router(routes_zones.router)
app.include_router(routes_status.router)


@app.get("/api/info")
def info():
    return {
        "app": "ParkingGo",
        "version": "0.1.0",
        "detector": manager.detector.name,
    }


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
