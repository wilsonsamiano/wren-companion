from __future__ import annotations

import shutil
from pathlib import Path

SHARE = Path.home() / ".local" / "share" / "wren"
ICON_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "128x128" / "apps"


def bundled_hero() -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / "hero.png"
    return p if p.is_file() else None


def pet_path() -> Path | None:
    """Ensure the bird PNG lives in a stable user path, then return it."""
    dest = SHARE / "hero.png"
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    src = bundled_hero()
    if src is None:
        for alt in (
            Path.home() / ".local/share/wren/hero.png",
            Path(__file__).resolve().parents[2] / "public" / "pet" / "hero.png",
        ):
            if alt.is_file():
                src = alt
                break
    if src is None:
        return None
    SHARE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, ICON_DIR / "dev.wren.companion.png")
    return dest
