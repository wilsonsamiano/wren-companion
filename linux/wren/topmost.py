"""Keep Wren above other windows.

GNOME Wayland has no keep-above for regular apps. Prefer gtk4-layer-shell
(overlay layer). If that library is missing, use X11 _NET_WM_STATE_ABOVE
(XWayland), which Bazzite still provides.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from ctypes import Structure, c_char_p, c_int, c_long, c_ulong, c_void_p
from pathlib import Path


def layer_shell_typelib() -> bool:
    names = (
        "Gtk4LayerShell-1.0.typelib",
        "GtkLayerShell-0.1.typelib",
    )
    roots = (
        "/usr/lib64/girepository-1.0",
        "/usr/lib/girepository-1.0",
        "/usr/lib/x86_64-linux-gnu/girepository-1.0",
    )
    return any((Path(root) / name).is_file() for root in roots for name in names)


def maybe_force_x11() -> None:
    """Call before Gtk is imported. GNOME without layer-shell → XWayland."""
    if os.environ.get("GDK_BACKEND"):
        return
    if layer_shell_typelib():
        return
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "GNOME" in desktop or "BUDGIE" in desktop:
        os.environ["GDK_BACKEND"] = "x11"


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


def x11_set_above(win) -> bool:
    try:
        import gi

        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11  # type: ignore
    except (ValueError, ImportError):
        return False
    surface = win.get_surface()
    if surface is None or not hasattr(GdkX11, "X11Surface"):
        return False
    try:
        xid = GdkX11.X11Surface.get_xid(surface)
    except Exception:
        return False
    if shutil.which("wmctrl"):
        r = subprocess.run(
            ["wmctrl", "-i", "-r", str(xid), "-b", "add,above"],
            capture_output=True,
        )
        if r.returncode == 0:
            return True
    return _xsend_above(xid)


def _xsend_above(xid: int) -> bool:
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
    above = lib.XInternAtom(dpy, b"_NET_WM_STATE_ABOVE", 0)
    root = lib.XDefaultRootWindow(dpy)
    event = XClientMessageEvent()
    event.type = 33
    event.window = xid
    event.message_type = state
    event.format = 32
    event.data[0] = 1
    event.data[1] = above
    event.data[2] = 0
    event.data[3] = 1
    event.data[4] = 0
    mask = (1 << 19) | (1 << 20)
    lib.XSendEvent(dpy, root, 0, mask, ctypes.byref(event))
    lib.XFlush(dpy)
    lib.XCloseDisplay(dpy)
    return True
