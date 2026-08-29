# Wren for Linux

A tiny always-on-top companion for Wayland desktops (KDE on CachyOS, KDE/GNOME on Bazzite).

Wren watches the active window **only if you let her**, talks through a local Ollama model, and **never runs a command or hits the network without a Yes**.

## Why two machines

| Machine | RAM | Model Wren picks | Watch |
|---|---|---|---|
| CachyOS · XPS-class | 64 GB | `qwen2.5:14b` Q4 | ~14s |
| Bazzite · Surface Go 2 | 8 GB | `llama3.2:1b` or `phi3:mini` | ~28s |

The overlay itself is a GTK window. RAM goes to the model, not to Wren.

## Install

```bash
git clone https://github.com/wilsonsamiano/wren-companion.git
cd wren-companion/linux
chmod +x install.sh
./install.sh
wren
```

### CachyOS

`install.sh` uses pacman for `gtk4`, `python-gobject`, `ollama`, `grim`, `tesseract`.

### Bazzite

The host is immutable. `install.sh` creates a Fedora distrobox named `wren` and installs there.

## Permissions

Stored in `~/.config/wren/config.json`:

- `watch` — screenshot / active window title
- `voice` — mic in, Piper/espeak out
- `actions` — show Yes/No before any subprocess
- `internet` — optional Grok key, still per-request

There is no hidden telemetry. Read `wren/brain.py` and `wren/actions.py` — they are short on purpose.

PRs welcome. Keep the contract: **offline first, visible, gated.**
