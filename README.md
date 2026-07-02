# ParkingGo

ParkingGo is a web-based AI system that turns a street-facing camera into a
live parking availability monitor. The admin connects a camera, draws the
roadside parking zones by hand on the camera view, and ParkingGo classifies
each zone in real time:

- 🟩 **Green — free**
- 🟥 **Red — occupied**
- ⬜ **Gray — unknown** (camera offline, low confidence, or bad lighting)

This is the MVP: a single-admin web dashboard for internal testing. No mobile
app, no public users, no license plate recognition.

![Live view](docs/screenshots/live.png)

| Zone calibration | Road illustration view |
|---|---|
| ![Calibration](docs/screenshots/calibration.png) | ![Road view](docs/screenshots/road-view.png) |

| Dashboard | History & daily stats |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![History](docs/screenshots/history.png) |

## Features

| Module | What it does |
|---|---|
| Camera input | RTSP / IP camera URLs, local webcam, or an uploaded test video, with live MJPEG preview |
| Zone calibration | Draw rectangles or free polygons over the camera snapshot; name, re-side, rename, delete; zones saved per camera |
| Car detection | YOLOv8 vehicle detection (car/truck/bus/motorcycle), no plate recognition; mock detector fallback for testing without ML dependencies |
| Occupancy | Overlap of detected vehicles with each zone → free / occupied / unknown, with anti-flicker hysteresis |
| Dashboard | Free/occupied/unknown counts, live camera view with colored overlays, and a simplified road illustration view |
| History | Timestamped status change feed ("Spot 1 became occupied at 14:25") plus hourly daily statistics |

## Quickstart

Requires Python 3.10+. No manual pip setup needed:

```bash
git clone -b claude/parkinggo-app-concept-09ou7c https://github.com/blaze1235/ParkingGO.git
cd ParkingGO
python3 run.py           # http://127.0.0.1:8000  (default login: admin / admin)
```

On first run, `run.py` creates a local virtual environment in `.venv` and
installs the dependencies into it automatically — this is the supported path
on macOS (Homebrew) and Debian/Ubuntu, whose system Python blocks `pip
install` with an `externally-managed-environment` error (PEP 668).

Optional but recommended — real car detection with YOLOv8 (downloads PyTorch,
~2 GB; without it a simple mock detector is used):

```bash
.venv/bin/pip install -r requirements-yolo.txt   # macOS/Linux
# .venv\Scripts\pip install -r requirements-yolo.txt   (Windows)
python3 run.py
```

<details>
<summary>Prefer managing the environment yourself?</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```
</details>

Then in the web app:

1. Sign in (default `admin` / `admin` — change via env vars below).
2. **Cameras → Add camera** — paste an RTSP/IP URL, pick a webcam index, or upload a test video.
3. Open **Zones** for the camera and draw a rectangle or polygon over each parking space.
4. Watch the **Dashboard** / camera **Live** and **Road view** tabs update in real time.

### Try it without a camera

A synthetic demo video (cars arriving and leaving in four bays) works with the
built-in mock detector, so the full pipeline runs with zero ML dependencies:

```bash
python scripts/make_demo_video.py data/demo.mp4
python run.py
# upload data/demo.mp4 as a camera in the UI, then draw zones over the four bays
```

An end-to-end API smoke test is included (run it while the server is up):

```bash
python scripts/smoke_test.py
```

Pure-logic unit tests (no server/video needed, runs in under a second):

```bash
python scripts/test_occupancy_logic.py
```

### Checking real detection quality

Don't guess whether YOLO can actually tell your footage's cars apart from
shadows/clutter — measure it. This runs the active detector against a real
video/RTSP/webcam source and writes an annotated output video plus
confidence stats:

```bash
python scripts/check_detection_quality.py path/to/your_footage.mp4
# or: rtsp://user:pass@host/stream   or:  0  (webcam)
```

Watch `data/detection_check.mp4` afterward and check: are real cars boxed?
Anything missed? Any false boxes on shadows or pavement markings?

## Configuration

Everything is tuned via environment variables (defaults in `backend/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `PARKINGGO_ADMIN_USERNAME` / `PARKINGGO_ADMIN_PASSWORD` | `admin` / `admin` | Dashboard login |
| `PARKINGGO_DETECTOR` | `auto` | `auto` (YOLO if installed, else mock), `yolo`, or `mock` |
| `PARKINGGO_YOLO_MODEL` | `yolov8n.pt` | Any ultralytics model (`yolov8s.pt`/`yolov8m.pt` are more accurate, slower — verify with `check_detection_quality.py` before trusting a switch, since a corrupted download of a larger model fails silently) |
| `PARKINGGO_DETECT_INTERVAL` | `1.0` | Seconds between detection runs per camera |
| `PARKINGGO_OVERLAP_THRESHOLD` | `0.6` | Fallback-only: box/zone overlap ratio that counts as occupied when the box's center falls outside every zone (e.g. clipped at the frame edge) |
| `PARKINGGO_CONF_OCCUPIED` / `PARKINGGO_CONF_UNKNOWN` | `0.45` / `0.25` | Confidence bands: above → occupied, between → unknown |
| `PARKINGGO_MIN_BRIGHTNESS` | `25` | Mean frame brightness (0–255) below which zones go unknown |
| `PARKINGGO_STABLE_TICKS` | `3` | Consecutive identical readings required before a status commits |
| `PARKINGGO_SAMPLE_INTERVAL` | `60` | Seconds between occupancy samples stored for daily stats |
| `PARKINGGO_DATA_DIR` | `./data` | SQLite database + uploaded videos |

## How occupancy is decided

1. Each camera runs a capture thread (only the newest frame is kept, so RTSP
   never lags) and a detection thread on a fixed interval.
2. A vehicle counts as "in" a zone primarily when its detection box's center
   point falls inside the zone polygon — robust in dense lots, where a
   neighboring car's box (especially one widened by a cast shadow) can
   overlap the next stall without its center ever leaving its own stall.
   Heavy area overlap (Sutherland–Hodgman polygon clipping) is used only as
   a fallback for boxes clipped at the frame edge.
3. Detection confidence maps to status: strong → **occupied**, weak-but-present
   → **unknown**, none → **free**. Stale/offline cameras and very dark frames
   force **unknown**.
4. A status must repeat for `STABLE_TICKS` consecutive runs before it commits,
   which suppresses flicker; every committed change is written to history.

## Project layout

```
backend/
  main.py            FastAPI app + static hosting
  config.py          env-driven settings
  db.py              SQLite (cameras, zones, status events, samples)
  auth.py            single-admin token sessions
  api/               REST routes (auth, cameras, zones, status/history)
  vision/
    detector.py      YOLOv8 + mock detector
    worker.py        per-camera capture/detect threads, hysteresis
    manager.py       worker lifecycle + stats sampler
    geometry.py      polygon clipping / overlap math
    annotate.py      overlay drawing for the live stream
frontend/            vanilla JS SPA (dashboard, calibration editor, road view)
scripts/
  make_demo_video.py         synthetic test footage generator
  smoke_test.py               end-to-end API test
  test_occupancy_logic.py     zone/vehicle geometry unit tests
  check_detection_quality.py  measure real detector accuracy on your footage
```

## API overview

All endpoints require `Authorization: Bearer <token>` from `POST /api/auth/login`
(image/stream endpoints also accept `?token=`).

```
POST   /api/auth/login                     {username, password} → {token}
GET    /api/cameras                        list (+ live connection state)
POST   /api/cameras                        {name, source_type, source}
POST   /api/cameras/upload                 multipart: name + video file
PATCH  /api/cameras/{id}                   rename / change source / enable
DELETE /api/cameras/{id}
GET    /api/cameras/{id}/snapshot?overlay=1
GET    /api/cameras/{id}/stream?overlay=1  MJPEG live stream
GET    /api/cameras/{id}/zones             POST to create
PATCH  /api/zones/{id}                     DELETE to remove
GET    /api/status                         occupancy summary, all cameras
GET    /api/cameras/{id}/status            zones with live status
GET    /api/cameras/{id}/history           status change events
GET    /api/cameras/{id}/stats?date=YYYY-MM-DD   hourly averages
```

## MVP scope

Deliberately **not** built yet: mobile/public apps, payments, maps/navigation,
license plate recognition, automatic zone discovery, city integrations. The
goal of this version is to prove that one camera plus manually drawn zones can
reliably report free vs. occupied street parking.
