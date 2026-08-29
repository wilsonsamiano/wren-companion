from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .actions import run_action
from .assets import ICON_NAME, pet_path, pose_files
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
window.wren-window windowcontrols {
  background-color: transparent;
  min-height: 0;
  padding: 0;
  margin: 0;
  opacity: 0;
}
.wren-root, windowhandle, picture {
  background-color: transparent;
  background-image: none;
}
popover.wren-pop,
popover.wren-pop > contents,
popover.wren-speech,
popover.wren-speech > contents {
  background-color: #16181d;
  color: #f6f1ea;
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.14);
  box-shadow: 0 18px 50px -18px rgba(0,0,0,0.55);
  padding: 10px;
}
box.wren-chat {
  background-color: #16181d;
  color: #f6f1ea;
  min-width: 280px;
  min-height: 240px;
}
box.wren-chat label,
box.wren-perm label,
popover.wren-pop label,
popover.wren-speech label {
  color: #f6f1ea;
  background-color: transparent;
}
label.wren-title {
  font-size: 15px;
  font-weight: 600;
  color: #f6f1ea;
}
label.wren-sub {
  font-size: 12px;
  color: #c8c2b8;
}
label.wren-msg-user {
  background-color: #e8e2d8;
  color: #141414;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 500;
}
label.wren-msg-wren {
  background-color: #111318;
  color: #f6f1ea;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
}
box.wren-perm {
  background-color: #1c1f26;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.12);
  padding: 10px 12px;
}
popover.wren-speech label {
  color: #f6f1ea;
  font-size: 14px;
  font-weight: 500;
}
.wren-chat entry {
  background-color: #0f1115;
  color: #f6f1ea;
  caret-color: #f6f1ea;
  border-radius: 8px;
  min-height: 36px;
  padding: 6px 10px;
  border: 1px solid rgba(255,255,255,0.14);
}
.wren-chat button, .wren-perm button {
  background-color: #2a2e38;
  color: #f6f1ea;
  border-radius: 8px;
  min-height: 32px;
  padding: 4px 10px;
}
button.wren-yes {
  background-color: #e8e2d8;
  color: #141414;
  font-weight: 600;
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
            self._pending = None
            self._pending_after = None
            self._messages: list[tuple[str, str]] = []

            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_USER,
            )

            self.picture = Gtk.Picture()
            self.picture.set_can_shrink(False)
            self.picture.set_keep_aspect_ratio(True)
            self.picture.set_halign(Gtk.Align.CENTER)
            self.picture.set_valign(Gtk.Align.CENTER)
            handle = Gtk.WindowHandle()
            handle.set_child(self.picture)
            self.set_child(handle)

            self.chat = self._build_chat(Gtk)
            self.chat_pop = Gtk.Popover()
            self.chat_pop.add_css_class("wren-pop")
            self.chat_pop.set_autohide(False)
            self.chat_pop.set_has_arrow(True)
            self.chat_pop.set_position(Gtk.PositionType.LEFT)
            self.chat_pop.set_child(self.chat)
            self.chat_pop.set_parent(self.picture)

            self.bubble = Gtk.Label(
                label="",
                wrap=True,
                justify=Gtk.Justification.LEFT,
                xalign=0,
                max_width_chars=28,
            )
            self.speech_pop = Gtk.Popover()
            self.speech_pop.add_css_class("wren-speech")
            self.speech_pop.set_autohide(False)
            self.speech_pop.set_has_arrow(True)
            self.speech_pop.set_position(Gtk.PositionType.TOP)
            self.speech_pop.set_child(self.bubble)
            self.speech_pop.set_parent(self.picture)

            self._pose = "idle"
            self._frame_i = 0
            self._bob = 0
            self._bob_dir = 1
            self._anim_id = 0
            self._bob_id = 0
            self._poses: dict = {}
            for pose in ("idle", "think", "point", "talk"):
                pixs = []
                for path in pose_files(pose):
                    try:
                        pixs.append(GdkPixbuf.Pixbuf.new_from_file(str(path)))
                    except Exception:
                        pass
                if pixs:
                    self._poses[pose] = pixs
            if "idle" not in self._poses:
                pet = pet_path()
                try:
                    if pet:
                        self._poses["idle"] = [GdkPixbuf.Pixbuf.new_from_file(str(pet))]
                    else:
                        self._poses["idle"] = [_fallback_pixbuf(GdkPixbuf, 128)]
                except Exception:
                    self._poses["idle"] = [_fallback_pixbuf(GdkPixbuf, 128)]
            self._src_pix = self._poses["idle"][0]
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

            if cfg.permissions.watch:
                GLib.timeout_add_seconds(max(16, int(cfg.watch_seconds)), self.on_watch)

            if cfg.always_on_top:
                self._layer = attach_layer_shell(self, cfg)

            GLib.timeout_add(200, self.boot_brain)
            GLib.timeout_add(700, self._first_pin)

        def _build_chat(self, Gtk):
            chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            chat.add_css_class("wren-chat")
            chat.set_size_request(280, 260)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            name = Gtk.Label(label="Wren", xalign=0)
            name.add_css_class("wren-title")
            sub = Gtk.Label(label="Ask, or let her watch", xalign=0)
            sub.add_css_class("wren-sub")
            titles.append(name)
            titles.append(sub)
            titles.set_hexpand(True)
            close = Gtk.Button(label="✕")
            close.connect("clicked", lambda *_: self.close_chat())
            header.append(titles)
            header.append(close)
            chat.append(header)

            self.perm_box = self._build_perm(Gtk)
            self.perm_box.set_visible(False)
            chat.append(self.perm_box)

            self.msg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_min_content_height(140)
            scroll.set_vexpand(True)
            scroll.set_child(self.msg_box)
            chat.append(scroll)
            self._hints = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for hint in (
                "What am I doing?",
                "Help with the terminal error",
                "Set up Ollama for this machine",
            ):
                btn = Gtk.Button(label=hint)
                btn.set_halign(Gtk.Align.FILL)
                btn.connect("clicked", lambda _b, h=hint: self.send_text(h))
                self._hints.append(btn)
            self.msg_box.append(self._hints)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            look = Gtk.Button(label="Look")
            look.connect("clicked", lambda *_: self.ask_user())
            self.entry = Gtk.Entry()
            self.entry.set_placeholder_text("Ask Wren…")
            self.entry.set_hexpand(True)
            self.entry.connect("activate", lambda *_: self.send_text())
            send = Gtk.Button(label="Send")
            send.connect("clicked", lambda *_: self.send_text())
            row.append(look)
            row.append(self.entry)
            row.append(send)
            chat.append(row)
            return chat

        def _build_perm(self, Gtk):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.add_css_class("wren-perm")
            box.set_halign(Gtk.Align.CENTER)
            self.perm_title = Gtk.Label(label="", wrap=True, xalign=0)
            self.perm_title.add_css_class("wren-title")
            self.perm_detail = Gtk.Label(label="", wrap=True, xalign=0, max_width_chars=32)
            self.perm_detail.add_css_class("wren-sub")
            box.append(self.perm_title)
            box.append(self.perm_detail)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            yes = Gtk.Button(label="Yes")
            yes.add_css_class("wren-yes")
            yes.set_hexpand(True)
            no = Gtk.Button(label="No")
            no.set_hexpand(True)
            yes.connect("clicked", lambda *_: self._answer_perm(True))
            no.connect("clicked", lambda *_: self._answer_perm(False))
            row.append(yes)
            row.append(no)
            box.append(row)
            return box

        def set_pose(self, pose: str) -> None:
            if pose not in self._poses:
                pose = "idle"
            self._pose = pose
            self._frame_i = 0
            if pose == "idle":
                self._stop_anim()
                self._bob = 0
                self.picture.set_margin_bottom(0)
            else:
                self._start_anim()
            self._show_frame()

        def _start_anim(self) -> None:
            if not self._anim_id:
                self._anim_id = GLib.timeout_add(280, self.tick_anim)

        def _stop_anim(self) -> None:
            if self._anim_id:
                GLib.source_remove(self._anim_id)
                self._anim_id = 0
            if self._bob_id:
                GLib.source_remove(self._bob_id)
                self._bob_id = 0
            self._bob = 0
            self.picture.set_margin_bottom(0)

        def _show_frame(self) -> None:
            frames = self._poses.get(self._pose) or self._poses["idle"]
            self._src_pix = frames[self._frame_i % len(frames)]
            size = max(MIN_PET, min(MAX_PET, int(cfg.pet_size)))
            scaled = self._src_pix.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
            self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(scaled))

        def tick_anim(self) -> bool:
            if self._pose == "idle":
                self._anim_id = 0
                return False
            frames = self._poses.get(self._pose) or self._poses["idle"]
            self._frame_i = (self._frame_i + 1) % len(frames)
            self._show_frame()
            return True

        def tick_bob(self) -> bool:
            if self._pose == "idle":
                self._bob = 0
                self.picture.set_margin_bottom(0)
                self._bob_id = 0
                return False
            self._bob += self._bob_dir
            if self._bob >= 4:
                self._bob_dir = -1
            elif self._bob <= 0:
                self._bob_dir = 1
            self.picture.set_margin_bottom(self._bob)
            return True

        def apply_size(self) -> None:
            self._applying = True
            size = max(MIN_PET, min(MAX_PET, int(cfg.pet_size)))
            cfg.pet_size = size
            self.picture.set_size_request(size, size)
            self._show_frame()
            self.set_default_size(size, size)
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

        def open_chat(self) -> None:
            self.chat_pop.popup()
            self.entry.grab_focus()

        def close_chat(self) -> None:
            self.chat_pop.popdown()

        def add_message(self, role: str, text: str) -> None:
            if self._hints.get_parent() is self.msg_box:
                self.msg_box.remove(self._hints)
            lab = Gtk.Label(label=text, wrap=True, xalign=0 if role != "user" else 1, max_width_chars=28)
            lab.add_css_class("wren-msg-user" if role == "user" else "wren-msg-wren")
            lab.set_halign(Gtk.Align.END if role == "user" else Gtk.Align.START)
            lab.set_selectable(True)
            self.msg_box.append(lab)
            self._messages.append((role, text))

        def send_text(self, text: str | None = None) -> None:
            msg = (text if text is not None else self.entry.get_text()).strip()
            if not msg or self._busy:
                return
            self.entry.set_text("")
            self.add_message("user", msg)
            self.ask_user(msg)

        def say(self, text: str, *, animate: bool = False) -> None:
            if animate:
                self.set_pose("talk")
            self.bubble.set_text(text)
            self.speech_pop.popup()
            if self._hide_id:
                GLib.source_remove(self._hide_id)
                self._hide_id = 0
            self._hide_id = GLib.timeout_add_seconds(12, self._hide_bubble)

        def _hide_bubble(self) -> bool:
            self.speech_pop.popdown()
            self.set_pose("idle")
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
            if self.chat_pop.get_visible():
                return
            self.open_chat()

        def ask_user(self, prompt: str | None = None) -> None:
            if self._busy:
                return
            self._busy = True
            self.set_pose("think")
            self.say("Looking…", animate=True)
            user_prompt = prompt or "The user tapped Wren. Help with whatever they are doing."

            def work():
                if not ollama_ping(cfg):
                    return ("need-brain", ollama_binary())
                title = active_window_title() or "the desktop"
                speech, action = ask_ollama(
                    cfg,
                    user_prompt,
                    f"Active window: {title}",
                )
                return ("ok", speech, action)

            def done(result) -> None:
                self._busy = False
                if isinstance(result, Exception):
                    self.say("That thought stalled. Try again.")
                    self.add_message("wren", "That thought stalled. Try again.")
                    return
                kind = result[0]
                if kind == "need-brain":
                    binary = result[1]
                    if binary is None:
                        self.say("Install Ollama so I can think offline.")
                        self.add_message("wren", "Install Ollama so I can think offline.")
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
                    self.add_message("wren", "Start my local brain?")
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
                line = speech or "I'm here."
                self.say(line, animate=True)
                self.add_message("wren", line)
                if action and cfg.permissions.actions:
                    self.prompt_action(action)

            self._bg(work, done)

        def show_menu(self, *_args) -> None:
            pop = Gtk.Popover()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            items = [
                ("Chat", self.open_chat),
                ("Look around", self.ask_user),
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
                    self.add_message("wren", speech)
                if action and cfg.permissions.actions:
                    self.prompt_action(action)

            self._bg(work, done)
            return True

        def prompt_action(self, action: ProposedAction, after=None) -> None:
            self._pending = action
            self._pending_after = after
            extra = action.command or action.url or ""
            self.perm_title.set_text(action.title)
            self.perm_detail.set_text(f"{action.detail}\n{extra}\nrisk: {action.risk}")
            self.perm_box.set_visible(True)
            self.open_chat()

        def _answer_perm(self, yes: bool) -> None:
            action = self._pending
            after = self._pending_after
            self._pending = None
            self._pending_after = None
            self.perm_box.set_visible(False)
            if not yes or action is None:
                self.say("Okay. I won't.")
                return

            def work():
                return run_action(action, ask=False)

            def finished(result) -> None:
                if "install-ollama" in (action.command or ""):
                    line = "Installing Ollama… this can take a minute."
                else:
                    line = result if result not in {"started", "nothing-to-run"} else "Okay."
                self.say(line)
                self.add_message("wren", line)
                if after:
                    GLib.timeout_add(1800, after)

            self._bg(work, finished)

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
