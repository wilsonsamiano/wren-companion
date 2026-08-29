from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def active_window_title() -> str:
    for cmd in (
        ["kdotool", "getactivewindow", "getwindowname"],
        ["hyprctl", "activewindow", "-j"],
        ["xdotool", "getactivewindow", "getwindowname"],
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            out = subprocess.check_output(cmd, text=True, timeout=2)
            return out.strip()[:200]
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    return ""


def screenshot(dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("grim"):
        subprocess.run(["grim", str(dest)], check=False, timeout=5)
    elif shutil.which("spectacle"):
        subprocess.run(
            ["spectacle", "-n", "-b", "-o", str(dest)],
            check=False,
            timeout=5,
        )
    elif shutil.which("gnome-screenshot"):
        subprocess.run(["gnome-screenshot", "-f", str(dest)], check=False, timeout=5)
    else:
        return None
    return dest if dest.exists() else None
