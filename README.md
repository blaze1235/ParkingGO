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
| Camera input | RTSP / IP camera URLs (forced over TCP for reliability), HTTP/MJPEG URLs, local webcam, or an uploaded test video — auto-reconnects with backoff if a stream drops |
| Zone calibration | Draw rectangles or free polygons over the camera snapshot; name, re-side, rename, delete; zones saved per camera |
| Car detection | Two independent signals: YOLOv8 vehicle detection (side/angled cameras) **plus** a per-zone occupancy classifier that works at any angle — including top-down/aerial views, where COCO detectors don't recognize cars at all. No plate recognition. |
| Occupancy | Either signal marks a zone occupied → free / occupied / unknown, with anti-flicker hysteresis |
| Dashboard | Free/occupied/unknown counts, per-camera live thumbnail with a LIVE/OFFLINE badge, and a simplified road illustration view |
| Monitor | Dedicated grid page showing every enabled camera's live stream at once, with a low/medium/high quality selector and per-tile fullscreen |
| Live camera view | Full-size MJPEG stream per camera with overlay toggle, quality selector, fullscreen, and snapshot download; admin can edit a camera's source URL in place |
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
| `PARKINGGO_DETECTOR` | `auto` | `auto` (YOLO if installed, else mock), `yolo`, `mock`, or `none` (zone classifier only — the right choice for top-down/aerial cameras) |
| `PARKINGGO_YOLO_MODEL` | `yolov8n.pt` | Any ultralytics model (`yolov8s.pt`/`yolov8m.pt` are more accurate, slower — verify with `check_detection_quality.py` before trusting a switch, since a corrupted download of a larger model fails silently) |
| `PARKINGGO_DETECT_INTERVAL` | `1.0` | Seconds between detection runs per camera |
| `PARKINGGO_OVERLAP_THRESHOLD` | `0.6` | Fallback-only: box/zone overlap ratio that counts as occupied when the box's center falls outside every zone (e.g. clipped at the frame edge) |
| `PARKINGGO_CONF_OCCUPIED` / `PARKINGGO_CONF_UNKNOWN` | `0.45` / `0.25` | Confidence bands: above → occupied, between → unknown |
| `PARKINGGO_MIN_BRIGHTNESS` | `25` | Mean frame brightness (0–255) below which zones go unknown |
| `PARKINGGO_RTSP_TRANSPORT` | `tcp` | FFmpeg RTSP transport. TCP avoids the frame corruption/hangs UDP suffers on real networks; set to `udp` only if you need lower latency on a solid network |
| `PARKINGGO_ZONE_CLASSIFIER` | `1` | Per-zone occupancy classifier on/off (`0` to rely on the detector alone) |
| `PARKINGGO_ZONE_EDGE_OCCUPIED` / `PARKINGGO_ZONE_EDGE_FREE` | `0.13` / `0.11` | Zone structure-score bands: at/above → occupied, below free → free, between → unknown |
| `PARKINGGO_STABLE_TICKS` | `3` | Consecutive identical readings required before a status commits |
| `PARKINGGO_SAMPLE_INTERVAL` | `60` | Seconds between occupancy samples stored for daily stats |
| `PARKINGGO_DATA_DIR` | `./data` | SQLite database + uploaded videos |

## Live camera streaming

**Ingestion.** A camera's `source` can be any URL OpenCV's FFmpeg backend can
open — `rtsp://`, `http://` MJPEG, etc. — a local webcam index, or an
uploaded file. RTSP specifically is forced over **TCP** transport by default
(`PARKINGGO_RTSP_TRANSPORT`), because FFmpeg's default UDP transport drops
and corrupts frames on real networks (WiFi, NAT, packet loss). If a stream
drops, the capture thread reconnects automatically with exponential backoff
(1s → 30s cap) — no restart needed.

**Delivery to the browser** is plain MJPEG (`multipart/x-mixed-replace`),
served from `GET /api/cameras/{id}/stream` and rendered with a plain
`<img>` tag. This was a deliberate choice over HLS/WebRTC: it needs no
extra infrastructure (no RTSPtoWeb/go2rtc/ffmpeg-to-HLS process to run
and keep alive), works in every browser with zero client-side JS library,
and is low-latency enough for an operator dashboard watching a handful of
cameras. Both `/stream` and `/snapshot` take `quality=high|medium|low`
(scale + JPEG quality trade-off) — the **Monitor** page (`#/monitor`, all
enabled cameras in a grid) defaults to `low` so N simultaneous tiles don't
each demand full-resolution bandwidth; the per-camera **Live camera** tab
defaults to `high`.

**Credentials never reach the frontend.** A camera's `source` commonly
embeds `user:pass@` for RTSP auth. Every API response masks this
(`rtsp://***:***@host:554/path`) before it leaves the backend — the real
value only ever lives in the database and inside the capture worker. The
Cameras page's "Edit source" control never round-trips the masked display
value either: its input starts blank ("leave blank to keep current"), and
the backend rejects any update that contains the masked placeholder, so a
UI bug can't accidentally overwrite real credentials with `***`.

**What's intentionally not built:**
- *A public city-CCTV directory.* There's no honest public data source to
  wire up here without fabricating one — any camera (private or public) is
  added the same way, by pasting its URL into the Cameras page.
- *Motion-detection-based alarms.* The per-zone occupancy classifier
  already gives a purpose-built, more accurate occupied/free signal per
  spot than generic frame-differencing motion detection would, and every
  committed status change is already recorded in the History tab — adding
  a second, cruder detection path on top would be redundant.

## How occupancy is decided

1. Each camera runs a capture thread (only the newest frame is kept, so RTSP
   never lags) and a detection thread on a fixed interval.
2. **Signal 1 — vehicle detector (YOLO)**: a vehicle counts as "in" a zone
   primarily when its detection box's center point falls inside the zone
   polygon — robust in dense lots, where a neighboring car's box (especially
   one widened by a cast shadow) can overlap the next stall without its
   center ever leaving its own stall. Heavy area overlap (Sutherland–Hodgman
   polygon clipping) is used only as a fallback for boxes clipped at the
   frame edge. This signal carries side/angled cameras — the views COCO
   models are trained on.
3. **Signal 2 — per-zone occupancy classifier**: each zone's own pixels are
   scored for car-like internal structure (edge density on scale-normalized
   crops). This is what carries **top-down/aerial cameras**: COCO-trained
   detectors (YOLO included) do not recognize cars viewed straight from
   above — verified on real footage, where both YOLOv8 and EfficientDet see
   nadir-view cars as "cell phones" or nothing. The classifier was
   calibrated and verified on real 1080p aerial parking footage (23 stalls
   hand-checked across the whole clip, 100% correct). Reliable from ~720p
   up; tiny or near-black zones read "unknown" rather than guessing.
4. Either signal marks the zone **occupied**; ambiguous zone scores or
   weak-confidence detections read **unknown**; **free** requires the zone
   to actually look empty. Stale/offline cameras and very dark frames force
   **unknown**.
5. A status must repeat for `STABLE_TICKS` consecutive runs before it commits,
   which suppresses flicker; every committed change is written to history.
   A looping test video resets this smoothing at the loop point.

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
    zone_classifier.py  angle-independent per-zone occupancy scoring
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
GET    /api/cameras                        list (+ live connection state; source credentials masked)
POST   /api/cameras                        {name, source_type, source}
POST   /api/cameras/upload                 multipart: name + video file
PATCH  /api/cameras/{id}                   rename / change source / enable
DELETE /api/cameras/{id}
GET    /api/cameras/{id}/snapshot?overlay=1&quality=high|medium|low
GET    /api/cameras/{id}/stream?overlay=1&quality=high|medium|low   MJPEG live stream
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
