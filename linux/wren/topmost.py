"""Keep Wren above other windows and on every workspace.

CachyOS/KDE: gtk4-layer-shell overlay.
Bazzite/GNOME: a tiny user extension (make_above + stick). X11 hints
are a fallback only when we are actually on XWayland.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
from ctypes import Structure, byref, c_char_p, c_int, c_long, c_ulong, c_void_p
from pathlib import Path

from .assets import linux_root, pin_dash

EXT_UUID = "wren-top@dev.wren.companion"


def attach_layer_shell(win, cfg) -> bool:
    try:
        import gi

        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell  # type: ignore
    except (ValueError, ImportError):
        return False
    try:
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(win, "wren")
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.ON_DEMAND)
        LayerShell.set_exclusive_zone(win, 0)
        LayerShell.set_anchor(win, LayerShell.Edge.BOTTOM, True)
        LayerShell.set_anchor(win, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(win, LayerShell.Edge.RIGHT, int(getattr(cfg, "margin_right", 24)))
        LayerShell.set_margin(win, LayerShell.Edge.BOTTOM, int(getattr(cfg, "margin_bottom", 24)))
        try:
            LayerShell.set_monitor_disabled  # type: ignore[attr-defined]
        except Exception:
            pass
        win._layer_shell = LayerShell
        return True
    except Exception:
        return False


def move_layer(win, cfg, dx: float, dy: float, origin: tuple[int, int]) -> None:
    ls = getattr(win, "_layer_shell", None)
    if ls is None:
        return
    right = max(0, int(origin[0] - dx))
    bottom = max(0, int(origin[1] - dy))
    cfg.margin_right = right
    cfg.margin_bottom = bottom
    ls.set_margin(win, ls.Edge.RIGHT, right)
    ls.set_margin(win, ls.Edge.BOTTOM, bottom)


def install_gnome_helper(enabled: bool = True) -> None:
    src = None
    for candidate in (
        linux_root() / "gnome" / EXT_UUID,
        Path(__file__).resolve().parent / "gnome" / EXT_UUID,
    ):
        if (candidate / "extension.js").is_file():
            src = candidate
            break
    if src is None:
        return
    dest = Path.home() / ".local/share/gnome-shell/extensions" / EXT_UUID
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "extension.js", dest / "extension.js")
    shutil.copy2(src / "metadata.json", dest / "metadata.json")
    subprocess.run(
        ["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"],
        capture_output=True,
        check=False,
    )
    cmd = "enable" if enabled else "disable"
    subprocess.run(["gnome-extensions", cmd, EXT_UUID], capture_output=True, check=False)
    if enabled:
        pin_dash()


def x11_set_above(win) -> bool:
    try:
        import gi

        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11  # type: ignore
    except (ValueError, ImportError):
        return False
    surface = win.get_surface()
    if surface is None:
        return False
    try:
        xid = GdkX11.X11Surface.get_xid(surface)
    except Exception:
        return False
    ok = False
    for extra in (b"_NET_WM_STATE_ABOVE", b"_NET_WM_STATE_STICKY"):
        ok = _xsend_state(xid, extra) or ok
    _xset_type_dock(xid)
    return ok


def _xsend_state(xid: int, atom: bytes) -> bool:
    class XClientMessageEvent(Structure):
        _fields_ = [
            ("type", c_int),
            ("serial", c_ulong),
            ("send_event", c_int),
            ("display", c_void_p),
            ("window", c_ulong),
            ("message_type", c_ulong),
            ("format", c_int),
            ("data", c_long * 5),
        ]

    try:
        lib = ctypes.CDLL("libX11.so.6")
    except OSError:
        return False
    lib.XOpenDisplay.restype = c_void_p
    lib.XOpenDisplay.argtypes = [c_char_p]
    dpy = lib.XOpenDisplay(None)
    if not dpy:
        return False
    lib.XInternAtom.restype = c_ulong
    lib.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
    state = lib.XInternAtom(dpy, b"_NET_WM_STATE", 0)
    value = lib.XInternAtom(dpy, atom, 0)
    root = lib.XDefaultRootWindow(dpy)
    event = XClientMessageEvent()
    event.type = 33
    event.window = xid
    event.message_type = state
    event.format = 32
    event.data[0] = 1
    event.data[1] = value
    event.data[2] = 0
    event.data[3] = 1
    event.data[4] = 0
    mask = (1 << 19) | (1 << 20)
    lib.XSendEvent(dpy, root, 0, mask, byref(event))
    lib.XFlush(dpy)
    lib.XCloseDisplay(dpy)
    return True


def _xset_type_dock(xid: int) -> None:
    try:
        lib = ctypes.CDLL("libX11.so.6")
    except OSError:
        return
    lib.XOpenDisplay.restype = c_void_p
    lib.XOpenDisplay.argtypes = [c_char_p]
    dpy = lib.XOpenDisplay(None)
    if not dpy:
        return
    lib.XInternAtom.restype = c_ulong
    lib.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
    prop = lib.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE", 0)
    dock = lib.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE_UTILITY", 0)
    atom_t = c_ulong
    val = atom_t(dock)
    XA_ATOM = 4
    lib.XChangeProperty(dpy, xid, prop, XA_ATOM, 32, 0, byref(val), 1)
    lib.XFlush(dpy)
    lib.XCloseDisplay(dpy)
