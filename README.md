# Wren

A tiny open-source Linux desktop companion. She perches on your windows like Clippy, watches only with permission, and never clicks, types, or goes online until you say **Yes**.

## Contract

- **Offline first.** Local Ollama on your machine. Hosted brain is optional.
- **Visible.** Every proposed command, click, or lookup is a Yes / No card (or a spoken yes).
- **Sized to RAM.** 64 GB CachyOS can run a 14B model. 8 GB Bazzite runs a 1B–3B model and a slower watch interval.
- **Open.** MIT. Read the overlay — `linux/wren/` is small on purpose.

## Install on Linux

```bash
git clone https://github.com/wilsonsamiano/wren-companion.git
cd wren-companion/linux
chmod +x install.sh
./install.sh
wren
```

Details: [linux/README.md](linux/README.md).

## Status

v0.1 — GTK overlay + Ollama brain + gated actions. Help wanted: Hyprland window titles, Piper voices, a click-through Wayland layer-shell path, and a quieter watch heuristic.

## License

MIT. See [LICENSE](LICENSE).
