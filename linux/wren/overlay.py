from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .actions import run_action
from .assets import pet_path
from .brain import ask_ollama
from .config import WrenConfig
from .ollama import binary as ollama_binary
from .ollama import ping as ollama_ping
from .ollama import start as ollama_start
from .permissions import ProposedAction
from .watch import active_window_title

# Old Intel (Surface Go 2 HD 615) hangs on GTK4's ngl renderer.
os.environ.setdefault("GSK_RENDERER", "cairo")

CSS = b"""
window.wren-window {
  background-color: transparent;
}
.wren-root {
  background-color: transparent;
}
.wren-bubble {
  background-color: #1c1612;
  color: #f6eee4;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
}
.wren-bubble label, label.wren-bubble {
  color: #f6eee4;
  background-color: #1c1612;
}
headerbar.wren-bar {
  min-height: 28px;
  padding: 0 8px;
  background: #1c1612;
  color: #f6eee4;
  border: none;
  box-shadow: none;
}
headerbar.wren-bar label {
  color: #f6eee4;
  font-size: 12px;
}
"""

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wren")


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


def _fallback_pixbuf(GdkPixbuf):
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 192, 192)
    pix.fill(0xC45A2AFF)
    return pix


def launch(cfg: WrenConfig) -> None:
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
            self.add_css_class("wren-window")
            self.set_resizable(False)
            self.set_default_size(260, 360)
            self._busy = False
            self._did_drag = False
            self._move_armed = False

            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            # Real CSD header so GNOME/Wayland will let us drag (undecorated
            # windows cannot be moved on GNOME).
            bar = Gtk.HeaderBar()
            bar.add_css_class("wren-bar")
            bar.set_show_title_buttons(True)
            bar.set_title_widget(Gtk.Label(label="Wren  ·  drag me"))
            self.set_titlebar(bar)

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            root.add_css_class("wren-root")
            root.set_margin_top(8)
            root.set_margin_bottom(8)
            root.set_margin_start(8)
            root.set_margin_end(8)

            handle = Gtk.WindowHandle()
            handle.set_child(root)
            self.set_child(handle)

            self.bubble = Gtk.Label(
                label="Drag me to a corner. Tap when you want help.",
                wrap=True,
                justify=Gtk.Justification.CENTER,
                max_width_chars=28,
            )
            self.bubble.add_css_class("wren-bubble")
            self.bubble.set_halign(Gtk.Align.CENTER)
            root.append(self.bubble)

            self.picture = Gtk.Picture()
            self.picture.set_size_request(192, 192)
            self.picture.set_halign(Gtk.Align.CENTER)
            pet = pet_path()
            try:
                if pet:
                    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(pet), 192, 192, True)
                else:
                    pix = _fallback_pixbuf(GdkPixbuf)
                self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
            except Exception:
                self.picture.set_paintable(
                    Gdk.Texture.new_for_pixbuf(_fallback_pixbuf(GdkPixbuf))
                )
            root.append(self.picture)

            drag = Gtk.GestureDrag()
            drag.set_button(0)
            drag.connect("drag-begin", self.on_drag_begin)
            drag.connect("drag-update", self.on_drag_update)
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

            if cfg.permissions.watch:
                GLib.timeout_add_seconds(max(16, int(cfg.watch_seconds)), self.on_watch)

            GLib.timeout_add(200, self.boot_brain)

        def say(self, text: str) -> None:
            self.bubble.set_text(text)

        def _bg(self, fn, then) -> None:
            def work() -> None:
                try:
                    result = fn()
                except Exception as exc:
                    result = exc
                ui(then, result)

            _POOL.submit(work)

        def boot_brain(self) -> bool:
            self.say("Checking the local brain…")

            def work():
                return ollama_ping(cfg), ollama_binary()

            def done(result) -> None:
                if isinstance(result, Exception):
                    self.say("I can perch. Tap me if you want to set up Ollama.")
                    return
                up, binary = result
                if up:
                    self.say("Ready. Drag me, then tap when you want help.")
                    return
                if binary is None:
                    self.say("I can perch, but I need Ollama to think. Tap me to install it.")
                    return
                self.say("Ollama is installed but not running. Tap me to start it.")

            self._bg(work, done)
            return False

        def _after_start(self) -> bool:
            def work():
                return ollama_ping(cfg)

            def done(up) -> None:
                if up is True:
                    self.say("There. Tap me when you want help.")
                else:
                    self.say("Still waiting on Ollama. Tap me to retry, or run: ollama serve")

            self._bg(work, done)
            return False

        def on_drag_begin(self, *_args) -> None:
            self._did_drag = False
            self._move_armed = False

        def on_drag_update(self, gesture, dx, dy) -> None:
            if self._move_armed:
                return
            if abs(dx) < 10 and abs(dy) < 10:
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
                    self.say("That thought stalled. Tap me to try again.")
                    return
                kind = result[0]
                if kind == "need-brain":
                    binary = result[1]
                    if binary is None:
                        self.say("Install Ollama into ~/.local so I can think offline.")
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
                (
                    "Watch on" if not cfg.permissions.watch else "Watch off",
                    self.toggle_watch,
                ),
                ("Quit Wren", lambda: self.get_application().quit()),
            ]
            for label, cb in items:
                btn = Gtk.Button(label=label)
                btn.connect("clicked", lambda _b, fn=cb: (fn(), pop.popdown()))
                box.append(btn)
            pop.set_child(box)
            pop.set_parent(self)
            pop.popup()

        def toggle_watch(self) -> None:
            cfg.permissions.watch = not cfg.permissions.watch
            cfg.save()
            self.say("Watching on." if cfg.permissions.watch else "Watching off. I only look when you tap.")

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

        def do_activate(self) -> None:
            win = WrenWindow(self)
            # Layer-shell pins the bird and blocks dragging on GNOME. Skip it.
            win.present()

    local_bin = str(Path.home() / ".local" / "bin")
    path = os.environ.get("PATH", "")
    if local_bin not in path.split(":"):
        os.environ["PATH"] = local_bin + ":" + path

    app = WrenApp()
    app.run(sys.argv)
