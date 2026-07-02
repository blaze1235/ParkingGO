"""Central configuration for ParkingGo, driven by environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PARKINGGO_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "parkinggo.db"
FRONTEND_DIR = BASE_DIR / "frontend"

# Admin credentials (single-admin MVP; change via environment)
ADMIN_USERNAME = os.environ.get("PARKINGGO_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("PARKINGGO_ADMIN_PASSWORD", "admin")
SESSION_TTL_SECONDS = int(os.environ.get("PARKINGGO_SESSION_TTL", 12 * 3600))

# Detection backend: "auto" (YOLO if installed, else mock), "yolo", "mock"
DETECTOR_BACKEND = os.environ.get("PARKINGGO_DETECTOR", "auto").lower()
YOLO_MODEL = os.environ.get("PARKINGGO_YOLO_MODEL", "yolov8n.pt")

# How often (seconds) each camera runs detection on its latest frame.
DETECT_INTERVAL = float(os.environ.get("PARKINGGO_DETECT_INTERVAL", 1.0))
# MJPEG stream frame rate served to the browser.
STREAM_FPS = float(os.environ.get("PARKINGGO_STREAM_FPS", 8))
JPEG_QUALITY = int(os.environ.get("PARKINGGO_JPEG_QUALITY", 80))

# Occupancy logic tuning.
# A zone counts as occupied when a vehicle detection overlaps it by at least
# this fraction of min(zone area, vehicle box area).
OVERLAP_THRESHOLD = float(os.environ.get("PARKINGGO_OVERLAP_THRESHOLD", 0.25))
# Detections at or above CONF_OCCUPIED are trusted; detections between
# CONF_UNKNOWN and CONF_OCCUPIED make an overlapping zone "unknown".
CONF_OCCUPIED = float(os.environ.get("PARKINGGO_CONF_OCCUPIED", 0.45))
CONF_UNKNOWN = float(os.environ.get("PARKINGGO_CONF_UNKNOWN", 0.25))
# Mean-brightness floor (0-255); darker frames flip zones to "unknown".
MIN_BRIGHTNESS = float(os.environ.get("PARKINGGO_MIN_BRIGHTNESS", 25))
# A camera with no fresh frame for this long is considered offline.
FRAME_STALE_SECONDS = float(os.environ.get("PARKINGGO_FRAME_STALE", 10))
# A zone status must be observed this many consecutive detection ticks
# before it is committed (anti-flicker hysteresis).
STATUS_STABLE_TICKS = int(os.environ.get("PARKINGGO_STABLE_TICKS", 3))

# Occupancy counts are sampled into history at this interval (seconds).
SAMPLE_INTERVAL = float(os.environ.get("PARKINGGO_SAMPLE_INTERVAL", 60))

MAX_UPLOAD_BYTES = int(os.environ.get("PARKINGGO_MAX_UPLOAD_MB", 500)) * 1024 * 1024


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
