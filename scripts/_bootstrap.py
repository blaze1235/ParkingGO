"""Shared .venv bootstrap for entry-point scripts (run.py and the utility
scripts under scripts/).

macOS Homebrew and Debian/Ubuntu system Python refuse `pip install` outside
a virtual environment (PEP 668's externally-managed-environment error), and
it's easy to accidentally run a script with the wrong Python (system
python3 instead of .venv/bin/python3), which fails with a confusing
ModuleNotFoundError instead of a clear "wrong interpreter" message.

ensure_deps_and_reexec() makes this a non-issue: call it at the very top of
a script's __main__ block, before importing any third-party package. If
everything needed is already importable it's a no-op; otherwise it creates
.venv (if missing), installs the given requirement files into it, and
re-execs the *same* script inside that interpreter with the original CLI
args intact. So `python3 whatever.py args...` always works, no matter which
Python launched it or whether dependencies are installed yet.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _all_importable(modules: list[str]) -> bool:
    for name in modules:
        try:
            importlib.import_module(name)
        except ImportError:
            return False
    return True


def ensure_deps_and_reexec(script_file: str, probe_modules: list[str],
                           requirement_files: list[str], bootstrap_env_var: str) -> None:
    if _all_importable(probe_modules):
        return
    if os.environ.get(bootstrap_env_var):
        sys.exit(f"Dependencies still missing after setup ({', '.join(probe_modules)}). "
                 f"Try removing the .venv folder and running this again.")

    if not VENV_PYTHON.exists():
        print("First run: creating virtual environment in .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])

    for req_file in requirement_files:
        note = " (this can take a few minutes -- it pulls in PyTorch)" if "yolo" in req_file else ""
        print(f"Installing dependencies from {req_file} into .venv{note} ...")
        subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--quiet",
                               "--disable-pip-version-check",
                               "-r", str(ROOT / req_file)])
    print("Dependencies ready.\n")

    env = {**os.environ, bootstrap_env_var: "1"}
    os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), script_file, *sys.argv[1:]], env)
