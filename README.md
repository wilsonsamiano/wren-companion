# Wren

A tiny open-source Linux desktop companion. She perches on your windows like Clippy, watches only with permission, and never clicks, types, or goes online until you say **Yes**.

This repository is the native overlay (`linux/`). The playground in this app is a full desktop simulation so you can feel the bird before installing anything.

## Contract

- **Offline first.** Local Ollama on your machine. Hosted brain is optional.
- **Visible.** Every proposed command, click, or lookup is a Yes / No card (or a spoken yes).
- **Sized to RAM.** 64 GB CachyOS can run a 14B model. 8 GB Bazzite runs a 1B model and a slower watch interval.
- **Open.** MIT. Read the overlay — `linux/wren/` is small on purpose.

## Try the playground

1. Pick CachyOS (64 GB) or Bazzite (8 GB).
2. Leave **Watch** and **Actions** on, **Internet** off.
3. Click Wren, or open chat and ask *Help with the terminal error*.
4. When she proposes `sudo pacman -S tesseract`, press **Yes** or say yes.
5. Open **Source** in the dock for the file layout.

Voice: enable it in Wren settings, then use the mic. Screen watch of your real display: share a screen, then press Look.

## Install on Linux

```bash
git clone https://github.com/wilsonsamiano/wren-companion.git
cd wren-companion/linux
chmod +x install.sh
./install.sh
wren
```

Already cloned? Don't uninstall.

```bash
cd ~/wren-companion
git pull
cd linux
./install.sh --update
wren
```

After that, later versions are just `wren --update`.

On Bazzite, if you only get a floating sentence and no bird, you are on 0.1.0. 0.1.6 is a small transparent bird, resizable, always-on-top on every workspace, with an app icon.

Details: [linux/README.md](linux/README.md).

## Status

v0.1.13 — playground + GTK overlay + Ollama brain + gated actions. Help wanted: Hyprland window titles, Piper voices, a quieter watch heuristic.

## License

MIT. See [LICENSE](LICENSE).
