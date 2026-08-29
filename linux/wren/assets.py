from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SHARE = Path.home() / ".local" / "share" / "wren"
HICOLOR = Path.home() / ".local" / "share" / "icons" / "hicolor"
PIXMAPS = Path.home() / ".local" / "share" / "pixmaps"
APPS = Path.home() / ".local" / "share" / "applications"
ICON_NAME = "dev.wren.companion"
ICON_SIZES = (48, 64, 128, 256, 512)


def bundled_hero() -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / "hero.png"
    return p if p.is_file() else None


def linux_root() -> Path:
    return Path(__file__).resolve().parent.parent


def install_icons(src: Path) -> None:
    if not src.is_file():
        return
    for size in ICON_SIZES:
        dest_dir = HICOLOR / f"{size}x{size}" / "apps"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / f"{ICON_NAME}.png")
    PIXMAPS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, PIXMAPS / f"{ICON_NAME}.png")
    subprocess.run(
        ["gtk4-update-icon-cache", "-f", str(HICOLOR)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["gtk-update-icon-cache", "-f", str(HICOLOR)],
        capture_output=True,
        check=False,
    )


def write_desktop() -> Path:
    APPS.mkdir(parents=True, exist_ok=True)
    path = APPS / "wren.desktop"
    home = Path.home()
    path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Name=Wren",
                "Comment=Desktop companion",
                f"Exec=env PATH={home}/.local/bin:/usr/bin:/home/linuxbrew/.linuxbrew/bin wren",
                f"Icon={ICON_NAME}",
                "Terminal=false",
                "Type=Application",
                "StartupWMClass=dev.wren.companion",
                "Categories=Utility;",
                "X-GNOME-UsesNotifications=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["update-desktop-database", str(APPS)], capture_output=True, check=False)
    subprocess.run(["xdg-desktop-menu", "forceupdate"], capture_output=True, check=False)
    return path


def sync_assets(root: Path | None = None) -> Path | None:
    """Copy the bundled bird into ~/.local/share and refresh icons. Always overwrites."""
    src = None
    if root:
        candidate = Path(root) / "wren" / "assets" / "hero.png"
        if candidate.is_file():
            src = candidate
    if src is None:
        src = bundled_hero()
    if src is None:
        return pet_path()
    SHARE.mkdir(parents=True, exist_ok=True)
    dest = SHARE / "hero.png"
    shutil.copy2(src, dest)
    install_icons(src)
    write_desktop()
    return dest


def pet_path() -> Path | None:
    """Prefer the bundled sprite (so --update replaces an old badge PNG)."""
    dest = SHARE / "hero.png"
    src = bundled_hero()
    if src is not None:
        SHARE.mkdir(parents=True, exist_ok=True)
        if (
            not dest.is_file()
            or dest.stat().st_size != src.stat().st_size
            or src.stat().st_mtime > dest.stat().st_mtime
        ):
            shutil.copy2(src, dest)
            install_icons(src)
        return dest
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    return None
