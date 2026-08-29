from __future__ import annotations

import os
import sys
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
"""


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


def _try_layer_shell(gi, win) -> bool:
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell  # type: ignore

        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_anchor(win, LayerShell.Edge.BOTTOM, True)
        LayerShell.set_anchor(win, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(win, LayerShell.Edge.BOTTOM, 28)
        LayerShell.set_margin(win, LayerShell.Edge.RIGHT, 28)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.ON_DEMAND)
        return True
    except Exception:
        return False


def _fallback_pixbuf(GdkPixbuf):
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 192, 192)
    pix.fill(0xC45A2AFF)
    return pix


def launch(cfg: WrenConfig) -> None:
    import gi

    Gtk, Gdk, GdkPixbuf, GLib, Gio = _load_gi()

    class WrenWindow(Gtk.ApplicationWindow):
        def __init__(self, app: Gtk.Application) -> None:
            super().__init__(application=app, title="Wren")
            self.add_css_class("wren-window")
            self.set_decorated(False)
            self.set_resizable(False)
            self.set_default_size(240, 320)
            try:
                self.set_handle_widget(self)
            except Exception:
                pass

            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            root.add_css_class("wren-root")
            root.set_margin_top(8)
            root.set_margin_bottom(8)
            root.set_margin_start(8)
            root.set_margin_end(8)
            self.set_child(root)

            self.bubble = Gtk.Label(
                label="Click me when you want help.",
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

            click = Gtk.GestureClick()
            click.connect("released", self.on_click)
            self.add_controller(click)

            right = Gtk.GestureClick()
            right.set_button(3)
            right.connect("released", self.on_right_click)
            self.add_controller(right)

            if cfg.permissions.watch:
                GLib.timeout_add_seconds(int(cfg.watch_seconds), self.on_watch)

            GLib.timeout_add(400, self.boot_brain)

        def say(self, text: str) -> None:
            self.bubble.set_text(text)

        def boot_brain(self) -> bool:
            if ollama_ping(cfg):
                self.say("Ready. Click me, or keep working — I'll watch if you let me.")
                return False
            status = ollama_start(cfg)
            if status.startswith("started") or status == "already-up":
                self.say("Waking the local brain…")
                GLib.timeout_add(2000, self._after_start)
                return False
            if ollama_binary() is None:
                self.say("I can perch, but I need Ollama to think. Click me to install it (no sudo).")
            else:
                self.say("Ollama is installed but not running. Click me to start it.")
            return False

        def _after_start(self) -> bool:
            if ollama_ping(cfg):
                self.say("There. Click me when you want help.")
            else:
                self.say("Still waiting on Ollama. Click me to retry, or run: ollama serve")
            return False

        def on_click(self, *_args) -> None:
            if not ollama_ping(cfg):
                if ollama_binary() is None:
                    self.say("Install Ollama into ~/.local so I can think offline.")
                    self.prompt_action(
                        ProposedAction(
                            title="Install Ollama (user-space)",
                            detail="Downloads the official Linux binary into ~/.local/bin. No sudo, no system changes.",
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
                        command=f"{ollama_binary()} serve",
                        background=True,
                    ),
                    after=self._after_start,
                )
                return

            title = active_window_title() or "the desktop"
            self.say("Looking…")
            speech, action = ask_ollama(
                cfg,
                "The user clicked Wren. Help with whatever they are doing.",
                f"Active window: {title}",
            )
            self.say(speech or "I'm here.")
            if action and cfg.permissions.actions:
                self.prompt_action(action)

        def on_right_click(self, *_args) -> None:
            pop = Gtk.Popover()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for label, cb in (
                ("Start Ollama", lambda: ollama_start(cfg) and self._after_start()),
                ("Quit Wren", lambda: self.get_application().quit()),
            ):
                btn = Gtk.Button(label=label)
                btn.connect("clicked", lambda _b, fn=cb: (fn(), pop.popdown()))
                box.append(btn)
            pop.set_child(box)
            pop.set_parent(self)
            pop.popup()

        def on_watch(self) -> bool:
            if not cfg.permissions.watch or not ollama_ping(cfg):
                return True
            title = active_window_title()
            if not title:
                return True
            speech, action = ask_ollama(
                cfg,
                "Quietly notice what the user is doing. Only speak if you can actually help.",
                f"Active window: {title}",
            )
            if speech:
                self.say(speech)
            if action and cfg.permissions.actions:
                self.prompt_action(action)
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
                if choice == 1:
                    result = run_action(action, ask=False)
                    if action.command.startswith("wren --install-ollama") or "install-ollama" in action.command:
                        self.say("Installing Ollama… this can take a minute.")
                    else:
                        self.say(result if result not in {"started", "nothing-to-run"} else "Okay.")
                    if after:
                        GLib.timeout_add(1800, after)

            dialog.choose(self, None, done)

    class WrenApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(
                application_id="dev.wren.companion",
                flags=Gio.ApplicationFlags.FLAGS_NONE,
            )

        def do_activate(self) -> None:
            win = WrenWindow(self)
            _try_layer_shell(gi, win)
            win.present()

    # Make ~/.local/bin visible to Yes-card commands like `wren --install-ollama`
    local_bin = str(Path.home() / ".local" / "bin")
    path = os.environ.get("PATH", "")
    if local_bin not in path.split(":"):
        os.environ["PATH"] = local_bin + ":" + path

    app = WrenApp()
    app.run(sys.argv)
