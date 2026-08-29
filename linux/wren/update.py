"""In-place update: git pull + pip install -e. Never uninstalls."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .assets import linux_root, repair_icons, sync_assets, write_desktop
from .config import WrenConfig
from .topmost import install_gnome_helper


def find_linux_root() -> Path | None:
    here = linux_root()
    if (here / "install.sh").is_file():
        return here
    cfg = WrenConfig.load()
    if cfg.source_dir:
        p = Path(cfg.source_dir)
        if (p / "install.sh").is_file():
            return p
        if (p / "linux" / "install.sh").is_file():
            return p / "linux"
    home = Path.home() / "wren-companion" / "linux"
    if (home / "install.sh").is_file():
        return home
    return None


def git_repo(linux: Path) -> Path:
    if (linux.parent / ".git").exists():
        return linux.parent
    if (linux / ".git").exists():
        return linux
    return linux.parent


def run_update() -> int:
    root = find_linux_root()
    if root is None:
        print("Can't find the Wren checkout.")
        print("Clone once:  git clone https://github.com/wilsonsamiano/wren-companion.git")
        print("Then:        cd wren-companion/linux && ./install.sh")
        return 1
    repo = git_repo(root)
    print(f"Updating {repo} …")
    repair_icons()
    pull = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"])
    if pull.returncode != 0:
        print("git pull failed. Your clone may have local edits.")
        return pull.returncode
    pip = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "-e", str(root)],
        check=False,
    )
    if pip.returncode != 0:
        print("pip install failed.")
        return pip.returncode
    cfg = WrenConfig.load()
    cfg.source_dir = str(root)
    cfg.save()
    sync_assets(root)
    write_desktop()
    install_gnome_helper(cfg.always_on_top)
    ver = subprocess.check_output(
        [sys.executable, "-c", "from wren import __version__; print(__version__)"],
        text=True,
    ).strip()
    print(f"Wren {ver} is installed. Close the bird if it's open, then run:  wren")
    return 0
