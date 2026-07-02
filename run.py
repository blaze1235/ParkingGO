#!/usr/bin/env python3
"""Start the ParkingGo server:  python3 run.py [--host 0.0.0.0] [--port 8000]

On first run this creates a local virtual environment in .venv and installs
the dependencies into it automatically (required on macOS/Homebrew and Debian
Python, which block system-wide pip installs per PEP 668). No manual pip
commands needed.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts._bootstrap import ensure_deps_and_reexec  # noqa: E402

if __name__ == "__main__":
    os.chdir(ROOT)  # so backend/, frontend/, data/ resolve regardless of cwd
    ensure_deps_and_reexec(
        script_file=__file__,
        probe_modules=["cv2", "fastapi", "numpy", "uvicorn"],
        requirement_files=["requirements.txt"],
        bootstrap_env_var="PARKINGGO_BOOTSTRAPPED",
    )

    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ParkingGo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(f"ParkingGo running at http://{args.host}:{args.port}  "
          "(default login: admin / admin)")
    uvicorn.run("backend.main:app", host=args.host, port=args.port)
