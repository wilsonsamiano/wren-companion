# Wren for Linux

A tiny always-on-top companion for Wayland desktops (KDE on CachyOS, GNOME/KDE on Bazzite).

Wren watches the active window **only if you let her**, talks through a local Ollama model, and **never runs a command or hits the network without a Yes**.

## Why two machines

| Machine | RAM | Model Wren picks | Watch |
|---|---|---|---|
| CachyOS · XPS-class | 64 GB | `qwen2.5:14b` Q4 | ~14s |
| Bazzite · Surface Go 2 | 8 GB | `llama3.2:1b` | ~28s |

The overlay itself is a GTK window. RAM goes to the model, not to Wren.

## Install

```bash
git clone https://github.com/wilsonsamiano/wren-companion.git
cd wren-companion/linux
chmod +x install.sh
./install.sh
wren
```

If you already cloned, update in place (do **not** uninstall):

```bash
wren --update
wren
```

Or:

```bash
cd ~/wren-companion
git pull
cd linux
./install.sh --update
wren
```

### CachyOS

`install.sh` uses pacman for `gtk4`, `python-gobject`, `ollama`, `grim`, `tesseract`.

### Bazzite (GNOME)

The host is immutable. Wren runs **on the host** (GTK 4 is already there). Ollama is dropped into `~/.local/bin` so you don't need sudo or a distrobox just to think.

Then search **Wren** in the app grid, or run `wren`.

If you only see a tiny gray sentence on the wallpaper, you are on 0.1.0. Current is 0.1.8 — still bird while idle, animates only when you talk to him. `wren --repair` restores other app icons if an older build hid them.

```bash
wren --doctor          # sprite / ollama / RAM
wren --ensure-brain    # start ollama if it is down
wren --install-ollama  # download the official binary into ~/.local
```

## Uninstall

```bash
cd wren-companion/linux
./uninstall.sh                 # overlay + app menu
./uninstall.sh --purge         # also config and the wren distrobox
./uninstall.sh --with-ollama   # also the ~/.local Ollama binary
```

## Permissions

Stored in `~/.config/wren/config.json`:

- `watch` — screenshot / active window title
- `voice` — mic in, Piper/espeak out
- `actions` — show Yes/No before any subprocess
- `internet` — optional Grok key, still per-request

There is no hidden telemetry. Read `wren/brain.py` and `wren/actions.py` — they are short on purpose.

## Optional hosted brain

Put an xAI key in config as `grok_api_key` if you want a cloud fallback. Wren still asks before any live lookup.

## Development

```bash
python3 -m wren --setup
python3 -m wren --doctor
python3 -m wren
```

PRs welcome. Keep the contract: **offline first, visible, gated.**
