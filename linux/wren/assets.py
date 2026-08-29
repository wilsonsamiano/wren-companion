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


def bundled_icon() -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / "icon.png"
    return p if p.is_file() else bundled_hero()


def linux_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_hicolor_index() -> None:
    index = HICOLOR / "index.theme"
    if index.is_file():
        return
    HICOLOR.mkdir(parents=True, exist_ok=True)
    dirs = ",".join(f"{s}x{s}/apps" for s in ICON_SIZES)
    blocks = [f"[Icon Theme]", "Name=Hicolor", f"Directories={dirs}", ""]
    for s in ICON_SIZES:
        blocks += [f"[{s}x{s}/apps]", f"Size={s}", "Context=Applications", "Type=Fixed", ""]
    index.write_text("\n".join(blocks), encoding="utf-8")


def install_icons(src: Path | None = None) -> Path | None:
    icon = bundled_icon()
    if src is not None and src.is_file() and src.name == "icon.png":
        icon = src
    if icon is None:
        return None
    _ensure_hicolor_index()
    for size in ICON_SIZES:
        dest_dir = HICOLOR / f"{size}x{size}" / "apps"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, dest_dir / f"{ICON_NAME}.png")
    PIXMAPS.mkdir(parents=True, exist_ok=True)
    pixmap = PIXMAPS / f"{ICON_NAME}.png"
    shutil.copy2(icon, pixmap)
    subprocess.run(["gtk4-update-icon-cache", "-f", "-t", str(HICOLOR)], capture_output=True, check=False)
    subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(HICOLOR)], capture_output=True, check=False)
    return pixmap


def write_desktop() -> Path:
    APPS.mkdir(parents=True, exist_ok=True)
    old = APPS / "wren.desktop"
    if old.exists():
        old.unlink()
    pixmap = PIXMAPS / f"{ICON_NAME}.png"
    icon_value = str(pixmap) if pixmap.is_file() else ICON_NAME
    path = APPS / f"{ICON_NAME}.desktop"
    home = Path.home()
    path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Name=Wren",
                "Comment=Desktop companion",
                f"Exec=env PATH={home}/.local/bin:/usr/bin:/home/linuxbrew/.linuxbrew/bin wren",
                f"Icon={icon_value}",
                "Terminal=false",
                "Type=Application",
                "StartupWMClass=dev.wren.companion",
                "StartupNotify=true",
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
    icon_src = None
    if root:
        ic = Path(root) / "wren" / "assets" / "icon.png"
        if ic.is_file():
            icon_src = ic
    install_icons(icon_src)
    write_desktop()
    return dest


def pet_path() -> Path | None:
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
            install_icons()
            write_desktop()
        return dest
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    return None
