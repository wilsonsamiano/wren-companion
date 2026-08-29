from __future__ import annotations

import sys
from pathlib import Path

from .brain import ask_ollama
from .config import WrenConfig
from .permissions import ProposedAction
from .watch import active_window_title
from .actions import run_action


PET_CANDIDATES = [
    Path(__file__).resolve().parent / "assets" / "hero.png",
    Path(__file__).resolve().parents[2] / "public" / "pet" / "hero.png",
    Path.home() / ".local/share/wren/hero.png",
]


def _load_gi():
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gdk, GdkPixbuf, GLib  # type: ignore

        return Gtk, Gdk, GdkPixbuf, GLib
    except (ImportError, ValueError) as exc:
        raise SystemExit(
            "Wren overlay needs GTK 4 (python3-gobject + gtk4).\n"
            "CachyOS: sudo pacman -S gtk4 python-gobject\n"
            "Bazzite: run inside a Fedora distrobox with those packages."
        ) from exc


def launch(cfg: WrenConfig) -> None:
    Gtk, Gdk, GdkPixbuf, GLib = _load_gi()

    class WrenWindow(Gtk.ApplicationWindow):
        def __init__(self, app: Gtk.Application) -> None:
            super().__init__(application=app, title="Wren")
            self.set_decorated(False)
            self.set_resizable(False)
            self.set_default_size(140, 160)
            try:
                self.set_handle_widget(self)
            except Exception:
                pass

            overlay = Gtk.Overlay()
            self.set_child(overlay)

            self.picture = Gtk.Picture()
            pet = next((p for p in PET_CANDIDATES if p.exists()), None)
            if pet:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(pet), 128, 128, True)
                tex = Gdk.Texture.new_for_pixbuf(pix)
                self.picture.set_paintable(tex)
            overlay.set_child(self.picture)

            self.bubble = Gtk.Label(label="Click me, or press Ctrl+Shift+W.")
            self.bubble.set_wrap(True)
            self.bubble.add_css_class("bubble")
            overlay.add_overlay(self.bubble)
            self.bubble.set_valign(Gtk.Align.START)

            click = Gtk.GestureClick()
            click.connect("released", self.on_click)
            self.add_controller(click)

            css = Gtk.CssProvider()
            css.load_from_data(
                b"window { background: transparent; } .bubble { padding: 8px; }"
            )
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            if cfg.permissions.watch:
                GLib.timeout_add_seconds(int(cfg.watch_seconds), self.on_watch)

        def on_click(self, *_args) -> None:
            title = active_window_title() or "the desktop"
            speech, action = ask_ollama(
                cfg,
                "The user clicked Wren. Help with whatever they are doing.",
                f"Active window: {title}",
            )
            self.bubble.set_text(speech)
            if action and cfg.permissions.actions:
                self.prompt_action(action)

        def on_watch(self) -> bool:
            if not cfg.permissions.watch:
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
                self.bubble.set_text(speech)
            if action and cfg.permissions.actions:
                self.prompt_action(action)
            return True

        def prompt_action(self, action: ProposedAction) -> None:
            dialog = Gtk.AlertDialog()
            dialog.set_message(action.title)
            dialog.set_detail(f"{action.detail}\n\nrisk: {action.risk}")
            dialog.set_buttons(["No", "Yes"])
            dialog.set_cancel_button(0)
            dialog.set_default_button(1)

            def done(_d, res) -> None:
                try:
                    choice = dialog.choose_finish(res)
                except Exception:
                    return
                if choice == 1:
                    run_action(action, ask=False)

            dialog.choose(self, None, done)

    class WrenApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="dev.wren.companion")

        def do_activate(self) -> None:
            win = WrenWindow(self)
            win.present()

    app = WrenApp()
    app.run(sys.argv)
