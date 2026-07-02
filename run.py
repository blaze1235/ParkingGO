#!/usr/bin/env python3
"""Start the ParkingGo server:  python3 run.py [--host 0.0.0.0] [--port 8000]

On first run this creates a local virtual environment in .venv and installs
the dependencies into it automatically (required on macOS/Homebrew and Debian
Python, which block system-wide pip installs per PEP 668). No manual pip
commands needed.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def deps_available() -> bool:
    try:
        import cv2, fastapi, numpy, uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


def bootstrap_and_reexec() -> None:
    """Create .venv, install requirements, and restart inside it."""
    if os.environ.get("PARKINGGO_BOOTSTRAPPED"):
        sys.exit("Dependencies are still missing after setup. Try removing the "
                 ".venv folder and running `python3 run.py` again.")
    if not VENV_PYTHON.exists():
        print("First run: creating virtual environment in .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    print("Installing dependencies into .venv (this can take a few minutes) ...")
    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--quiet",
                           "--disable-pip-version-check",
                           "-r", str(ROOT / "requirements.txt")])
    print("Dependencies ready — starting ParkingGo.\n")
    env = {**os.environ, "PARKINGGO_BOOTSTRAPPED": "1"}
    os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]], env)


if __name__ == "__main__":
    os.chdir(ROOT)  # so backend/, frontend/, data/ resolve regardless of cwd
    if not deps_available():
        bootstrap_and_reexec()

    parser = argparse.ArgumentParser(description="ParkingGo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn
    print(f"ParkingGo running at http://{args.host}:{args.port}  "
          "(default login: admin / admin)")
    uvicorn.run("backend.main:app", host=args.host, port=args.port)
