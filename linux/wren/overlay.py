from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .actions import run_action
from .assets import ICON_NAME, pet_path
from .brain import ask_ollama
from .config import WrenConfig
from .ollama import binary as ollama_binary
from .ollama import ping as ollama_ping
from .permissions import ProposedAction
from .topmost import attach_layer_shell, install_gnome_helper, move_layer, x11_set_above
from .watch import active_window_title

# Old Intel (Surface Go 2 HD 615) hangs on GTK4's ngl renderer.
os.environ.setdefault("GSK_RENDERER", "cairo")

CSS = b"""
window.wren-window,
window.wren-window.background,
window.wren-window.csd,
window.wren-window.solid-csd,
window.wren-window.undecorated {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
  outline: none;
}
window.wren-window decoration,
window.wren-window headerbar,
window.wren-window .titlebar,
window.wren-window windowcontrols,
.wren-grip, .wren-grip > box {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  min-height: 0;
  padding: 0;
  margin: 0;
  opacity: 0;
}
.wren-root, windowhandle, picture {
  background-color: transparent;
  background-image: none;
}
.wren-bubble {
  background-color: rgba(28, 22, 18, 0.92);
  color: #f6eee4;
  padding: 8px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.wren-bubble label, label.wren-bubble {
  color: #f6eee4;
  background-color: transparent;
}
"""

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wren")
MIN_PET = 64
MAX_PET = 240


def _load_gi():
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio  # type: ignore

        return Gtk, Gdk, GdkPixbuf, GLib, Gio
    except (ImportError, ValueError) as exc:
        raise SystemExit(
            "Wren overlay needs GTK 4 (python3-gobject + gtk4).\n"
            "CachyOS: sudo pacman -S gtk4 python-gobject\n"
            "Bazzite: GTK is on the host already; reinstall with linux/install.sh."
        ) from exc


def _fallback_pixbuf(GdkPixbuf, size: int):
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)
    pix.fill(0xC45A2AFF)
    return pix


def launch(cfg: WrenConfig) -> None:
    install_gnome_helper(cfg.always_on_top)
    Gtk, Gdk, GdkPixbuf, GLib, Gio = _load_gi()

    def ui(fn, *args):
        def wrap() -> bool:
            try:
                fn(*args)
            except Exception:
                pass
            return False

        GLib.idle_add(wrap)

    class WrenWindow(Gtk.ApplicationWindow):
        def __init__(self, app: Gtk.Application) -> None:
            super().__init__(application=app, title="Wren")
            self.set_css_classes(["wren-window"])
            self.set_decorated(False)
            self.set_resizable(True)
            self.set_deletable(False)
            self.set_titlebar(None)
            self.set_icon_name(ICON_NAME)
            self._busy = False
            self._did_drag = False
            self._move_armed = False
            self._hide_id = 0
            self._applying = False
            self._src_pix = None
            self._layer = False
            self._drag_origin = (cfg.margin_right, cfg.margin_bottom)

            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10,
            )

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            root.add_css_class("wren-root")
            handle = Gtk.WindowHandle()
            handle.set_child(root)
            self.set_child(handle)

            self.bubble = Gtk.Label(
                label="",
                wrap=True,
                justify=Gtk.Justification.CENTER,
                max_width_chars=22,
            )
            self.bubble.add_css_class("wren-bubble")
            self.bubble.set_halign(Gtk.Align.CENTER)
            self.bubble.set_visible(False)
            root.append(self.bubble)

            self.picture = Gtk.Picture()
            self.picture.set_can_shrink(True)
            self.picture.set_halign(Gtk.Align.CENTER)
            self.picture.set_valign(Gtk.Align.CENTER)
            pet = pet_path()
            try:
                if pet:
                    self._src_pix = GdkPixbuf.Pixbuf.new_from_file(str(pet))
                else:
                    self._src_pix = _fallback_pixbuf(GdkPixbuf, 128)
            except Exception:
                self._src_pix = _fallback_pixbuf(GdkPixbuf, 128)
            root.append(self.picture)
            self.apply_size()

            drag = Gtk.GestureDrag()
            drag.set_button(0)
            drag.connect("drag-begin", self.on_drag_begin)
            drag.connect("drag-update", self.on_drag_update)
            drag.connect("drag-end", lambda *_: cfg.save())
            self.add_controller(drag)

            click = Gtk.GestureClick()
            click.set_button(1)
            click.connect("released", self.on_click)
            self.picture.add_controller(click)

            longp = Gtk.GestureLongPress()
            longp.connect("pressed", lambda *_: self.show_menu())
            self.picture.add_controller(longp)

            right = Gtk.GestureClick()
            right.set_button(3)
            right.connect("released", lambda *_: self.show_menu())
            self.add_controller(right)

            zoom = Gtk.GestureZoom()
            zoom.connect("begin", self.on_zoom_begin)
            zoom.connect("scale-changed", self.on_zoom)
            zoom.connect("end", lambda *_: cfg.save())
            self.add_controller(zoom)
            self._zoom0 = cfg.pet_size

            scroll = Gtk.EventControllerScroll()
            scroll.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
            scroll.connect("scroll", self.on_scroll)
            self.add_controller(scroll)

            self.connect("notify::default-width", self.on_win_size)
            self.connect("notify::default-height", self.on_win_size)

            if cfg.permissions.watch:
                GLib.timeout_add_seconds(max(16, int(cfg.watch_seconds)), self.on_watch)

            if cfg.always_on_top:
                self._layer = attach_layer_shell(self, cfg)

            GLib.timeout_add(200, self.boot_brain)
            GLib.timeout_add(700, self._first_pin)

        def apply_size(self) -> None:
            self._applying = True
            size = max(MIN_PET, min(MAX_PET, int(cfg.pet_size)))
            cfg.pet_size = size
            self.picture.set_size_request(size, size)
            if self._src_pix is not None:
                scaled = self._src_pix.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
                self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(scaled))
            extra_h = 52 if self.bubble.get_visible() else 12
            self.set_default_size(size + 12, size + extra_h)
            self._applying = False

        def bump_size(self, delta: int) -> None:
            cfg.pet_size = max(MIN_PET, min(MAX_PET, int(cfg.pet_size) + delta))
            cfg.save()
            self.apply_size()

        def on_zoom_begin(self, *_args) -> None:
            self._zoom0 = cfg.pet_size

        def on_zoom(self, _g, scale: float) -> None:
            cfg.pet_size = int(max(MIN_PET, min(MAX_PET, self._zoom0 * scale)))
            self.apply_size()

        def on_scroll(self, controller, _dx, dy) -> bool:
            state = controller.get_current_event_state()
            if not (state & Gdk.ModifierType.CONTROL_MASK):
                return False
            self.bump_size(-16 if dy > 0 else 16)
            return True

        def on_win_size(self, *_args) -> None:
            if self._applying:
                return
            w, h = self.get_width(), self.get_height()
            if w < 40 or h < 40:
                return
            size = min(w, h) - (48 if self.bubble.get_visible() else 12)
            size = max(MIN_PET, min(MAX_PET, size))
            if abs(size - cfg.pet_size) < 8:
                return
            cfg.pet_size = size
            cfg.save()
            self.apply_size()

        def say(self, text: str) -> None:
            self.bubble.set_text(text)
            self.bubble.set_visible(True)
            self.apply_size()
            if self._hide_id:
                GLib.source_remove(self._hide_id)
                self._hide_id = 0
            self._hide_id = GLib.timeout_add_seconds(10, self._hide_bubble)

        def _hide_bubble(self) -> bool:
            self.bubble.set_visible(False)
            self.apply_size()
            self._hide_id = 0
            return False

        def _bg(self, fn, then) -> None:
            def work() -> None:
                try:
                    result = fn()
                except Exception as exc:
                    result = exc
                ui(then, result)

            _POOL.submit(work)

        def boot_brain(self) -> bool:
            def work():
                return ollama_ping(cfg), ollama_binary()

            def done(result) -> None:
                if isinstance(result, Exception):
                    self.say("Tap me to set up Ollama.")
                    return
                up, binary = result
                if up:
                    return
                if binary is None:
                    self.say("Tap me to install Ollama.")
                    return
                self.say("Tap me to start Ollama.")

            self._bg(work, done)
            return False

        def _after_start(self) -> bool:
            def work():
                return ollama_ping(cfg)

            def done(up) -> None:
                if up is True:
                    self.say("Ready.")
                else:
                    self.say("Still waiting on Ollama.")

            self._bg(work, done)
            return False

        def on_drag_begin(self, *_args) -> None:
            self._did_drag = False
            self._move_armed = False
            self._drag_origin = (cfg.margin_right, cfg.margin_bottom)

        def on_drag_update(self, gesture, dx, dy) -> None:
            if self._layer:
                self._did_drag = abs(dx) > 6 or abs(dy) > 6
                if self._did_drag:
                    move_layer(self, cfg, dx, dy, self._drag_origin)
                return
            if self._move_armed:
                return
            if abs(dx) < 8 and abs(dy) < 8:
                return
            self._did_drag = True
            self._move_armed = True
            native = self.get_native()
            if native is None:
                return
            surface = native.get_surface()
            if surface is None or not hasattr(surface, "begin_move"):
                return
            device = gesture.get_current_event_device()
            if device is None:
                seat = self.get_display().get_default_seat()
                device = seat.get_pointer() if seat else None
            if device is None:
                return
            try:
                surface.begin_move(device, 1, 0, 0, gesture.get_current_event_time())
            except Exception:
                pass

        def _first_pin(self) -> bool:
            self.pin_above()
            GLib.timeout_add_seconds(4, self.pin_above)
            return False

        def pin_above(self) -> bool:
            if not cfg.always_on_top:
                return False
            if self._layer:
                return False
            x11_set_above(self)
            return True

        def on_click(self, *_args) -> None:
            if self._did_drag:
                self._did_drag = False
                return
            if self._busy:
                return
            self.ask_user()

        def ask_user(self) -> None:
            if self._busy:
                return
            self._busy = True
            self.say("Looking…")

            def work():
                if not ollama_ping(cfg):
                    return ("need-brain", ollama_binary())
                title = active_window_title() or "the desktop"
                speech, action = ask_ollama(
                    cfg,
                    "The user tapped Wren. Help with whatever they are doing.",
                    f"Active window: {title}",
                )
                return ("ok", speech, action)

            def done(result) -> None:
                self._busy = False
                if isinstance(result, Exception):
                    self.say("That thought stalled. Tap to try again.")
                    return
                kind = result[0]
                if kind == "need-brain":
                    binary = result[1]
                    if binary is None:
                        self.say("Install Ollama so I can think offline.")
                        self.prompt_action(
                            ProposedAction(
                                title="Install Ollama (user-space)",
                                detail="Downloads the official Linux binary into ~/.local/bin. No sudo.",
                                risk="medium",
                                kind="command",
                                command="wren --install-ollama",
                                background=True,
                            )
                        )
                        return
                    self.say("Start my local brain?")
                    self.prompt_action(
                        ProposedAction(
                            title="Start Ollama",
                            detail="Run ollama serve in the background so Wren can talk offline.",
                            risk="low",
                            kind="command",
                            command=f"{binary} serve",
                            background=True,
                        ),
                        after=self._after_start,
                    )
                    return
                _, speech, action = result
                self.say(speech or "I'm here.")
                if action and cfg.permissions.actions:
                    self.prompt_action(action)

            self._bg(work, done)

        def show_menu(self, *_args) -> None:
            pop = Gtk.Popover()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            items = [
                ("Ask Wren", self.ask_user),
                ("Smaller", lambda: self.bump_size(-24)),
                ("Bigger", lambda: self.bump_size(24)),
                (
                    "Float on top" if not cfg.always_on_top else "Don't stay on top",
                    self.toggle_top,
                ),
                (
                    "Watch on" if not cfg.permissions.watch else "Watch off",
                    self.toggle_watch,
                ),
                ("Update Wren", self.run_update),
                ("Quit Wren", lambda: self.get_application().quit()),
            ]
            for label, cb in items:
                btn = Gtk.Button(label=label)
                btn.connect("clicked", lambda _b, fn=cb: (fn(), pop.popdown()))
                box.append(btn)
            pop.set_child(box)
            pop.set_parent(self)
            pop.popup()

        def run_update(self) -> None:
            self.say("Updating…")

            def work():
                from .update import run_update

                return run_update()

            def done(code) -> None:
                if code == 0:
                    self.say("Updated. Close me and tap Wren in the app grid.")
                else:
                    self.say("Update failed. In a terminal: wren --update")

            self._bg(work, done)

        def toggle_watch(self) -> None:
            cfg.permissions.watch = not cfg.permissions.watch
            cfg.save()
            self.say("Watching on." if cfg.permissions.watch else "Watching off.")

        def toggle_top(self) -> None:
            cfg.always_on_top = not cfg.always_on_top
            cfg.save()
            install_gnome_helper(cfg.always_on_top)
            if cfg.always_on_top:
                self.pin_above()
                self.say("I'll stay on every screen. Log out once if I still slip behind.")
            else:
                self.say("I won't stay on top.")

        def on_watch(self) -> bool:
            if not cfg.permissions.watch or self._busy:
                return True

            def work():
                if not ollama_ping(cfg):
                    return None
                title = active_window_title()
                if not title:
                    return None
                return ask_ollama(
                    cfg,
                    "Quietly notice what the user is doing. Only speak if you can actually help.",
                    f"Active window: {title}",
                )

            def done(result) -> None:
                if not result or isinstance(result, Exception):
                    return
                speech, action = result
                if speech:
                    self.say(speech)
                if action and cfg.permissions.actions:
                    self.prompt_action(action)

            self._bg(work, done)
            return True

        def prompt_action(self, action: ProposedAction, after=None) -> None:
            dialog = Gtk.AlertDialog()
            dialog.set_message(action.title)
            extra = action.command or action.url
            dialog.set_detail(f"{action.detail}\n\n{extra}\n\nrisk: {action.risk}")
            dialog.set_buttons(["No", "Yes"])
            dialog.set_cancel_button(0)
            dialog.set_default_button(1)

            def done(_d, res) -> None:
                try:
                    choice = dialog.choose_finish(res)
                except Exception:
                    return
                if choice != 1:
                    return

                def work():
                    return run_action(action, ask=False)

                def finished(result) -> None:
                    if "install-ollama" in (action.command or ""):
                        self.say("Installing Ollama… this can take a minute.")
                    else:
                        self.say(result if result not in {"started", "nothing-to-run"} else "Okay.")
                    if after:
                        GLib.timeout_add(1800, after)

                self._bg(work, finished)

            dialog.choose(self, None, done)

    class WrenApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(
                application_id="dev.wren.companion",
                flags=Gio.ApplicationFlags.FLAGS_NONE,
            )

        def do_startup(self) -> None:
            Gtk.Application.do_startup(self)
            Gtk.Window.set_default_icon_name(ICON_NAME)

        def do_activate(self) -> None:
            win = WrenWindow(self)
            win.present()

    local_bin = str(Path.home() / ".local" / "bin")
    path = os.environ.get("PATH", "")
    if local_bin not in path.split(":"):
        os.environ["PATH"] = local_bin + ":" + path

    app = WrenApp()
    app.run(sys.argv)
