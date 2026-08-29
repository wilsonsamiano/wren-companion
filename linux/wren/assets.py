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
POSES = {
    "idle": ("idle-1.png",),
    "think": ("think-1.png", "think-2.png"),
    "point": ("point-1.png", "point-2.png", "point-3.png"),
    "talk": ("idle-1.png", "idle-2.png", "point-1.png", "point-2.png", "point-1.png", "idle-2.png"),
}


def bundled_hero() -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / "hero.png"
    return p if p.is_file() else None


def bundled_icon() -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / "icon.png"
    return p if p.is_file() else bundled_hero()


def bundled_pose(name: str) -> Path | None:
    p = Path(__file__).resolve().parent / "assets" / name
    return p if p.is_file() else None


def linux_root() -> Path:
    return Path(__file__).resolve().parent.parent


def repair_icons() -> None:
    """Undo the 0.1.5 stub that overwrote user hicolor and blanked other apps."""
    index = HICOLOR / "index.theme"
    if index.is_file():
        text = index.read_text(encoding="utf-8", errors="ignore")
        if "512x512/apps" in text and "Name=Hicolor" in text and "Inherits=" not in text:
            index.unlink()
    cache = HICOLOR / "icon-theme.cache"
    if cache.exists():
        cache.unlink()
    kcache = Path.home() / ".cache" / "icon-cache.kcache"
    if kcache.exists():
        kcache.unlink()


def install_icons(src: Path | None = None) -> Path | None:
    repair_icons()
    icon = bundled_icon()
    if src is not None and src.is_file() and src.name == "icon.png":
        icon = src
    if icon is None:
        return None
    for size in ICON_SIZES:
        dest_dir = HICOLOR / f"{size}x{size}" / "apps"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, dest_dir / f"{ICON_NAME}.png")
    PIXMAPS.mkdir(parents=True, exist_ok=True)
    pixmap = PIXMAPS / f"{ICON_NAME}.png"
    shutil.copy2(icon, pixmap)
    # Do NOT write index.theme or gtk-update-icon-cache on ~/.local hicolor.
    # That stub hid every other app's icon on GNOME.
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
                "Keywords=clippy;bird;assistant;pet;wren;",
                "Categories=Utility;",
                "X-GNOME-UsesNotifications=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["update-desktop-database", str(APPS)], capture_output=True, check=False)
    pin_dash()
    return path


def pin_dash() -> None:
    desktop = f"{ICON_NAME}.desktop"
    r = subprocess.run(
        ["gsettings", "get", "org.gnome.shell", "favorite-apps"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return
    raw = r.stdout.strip()
    if desktop in raw:
        return
    if raw in ("@as []", "[]", ""):
        new = f"['{desktop}']"
    elif raw.endswith("]"):
        new = raw[:-1] + f", '{desktop}']"
    else:
        return
    subprocess.run(
        ["gsettings", "set", "org.gnome.shell", "favorite-apps", new],
        capture_output=True,
        check=False,
    )


def sync_assets(root: Path | None = None) -> Path | None:
    repair_icons()
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
    assets_dir = Path(__file__).resolve().parent / "assets"
    if root:
        alt = Path(root) / "wren" / "assets"
        if alt.is_dir():
            assets_dir = alt
    for names in POSES.values():
        for name in names:
            f = assets_dir / name
            if f.is_file():
                shutil.copy2(f, SHARE / name)
    icon_src = assets_dir / "icon.png"
    install_icons(icon_src if icon_src.is_file() else None)
    write_desktop()
    return dest


def pose_files(pose: str = "idle") -> list[Path]:
    names = POSES.get(pose, POSES["idle"])
    found: list[Path] = []
    for name in names:
        bundled = bundled_pose(name)
        shared = SHARE / name
        if bundled and bundled.is_file():
            found.append(bundled)
        elif shared.is_file():
            found.append(shared)
    if not found:
        hero = pet_path()
        if hero:
            found.append(hero)
    return found


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
        return dest
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    return None
