#!/usr/bin/env bash
# Wren installer for CachyOS (Arch) and Bazzite (Fedora Atomic).
# Overlay first. Ollama is best-effort. Re-running this (or `wren --update`)
# upgrades in place — do not uninstall first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RAM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
SKIP_OLLAMA=0
if [[ "${1:-}" == "--update" || "${1:-}" == "--skip-ollama" ]]; then
  SKIP_OLLAMA=1
fi

# 0.1.5 wrote a stub ~/.local/share/icons/hicolor/index.theme that hid
# every other app's icon (Brave, etc. became generic gears). Undo that first.
if [[ -f "$HOME/.local/share/icons/hicolor/index.theme" ]]; then
  if grep -q '512x512/apps' "$HOME/.local/share/icons/hicolor/index.theme" 2>/dev/null \
     && ! grep -q 'Inherits=' "$HOME/.local/share/icons/hicolor/index.theme" 2>/dev/null; then
    rm -f "$HOME/.local/share/icons/hicolor/index.theme"
    echo "Removed the stub icon theme that was hiding other apps."
  fi
fi
rm -f "$HOME/.local/share/icons/hicolor/icon-theme.cache" "$HOME/.cache/icon-cache.kcache"

echo "Wren installer"
echo "Detected RAM: ${RAM_GB} GB"

if [[ ! -f "$ROOT/wren/assets/hero.png" ]]; then
  echo "This checkout is missing the bird sprite (linux/wren/assets/hero.png)."
  echo "From the repo root:  git pull"
  exit 1
fi

if [[ -f /usr/lib/os-release ]]; then
  # shellcheck disable=SC1091
  . /usr/lib/os-release
else
  ID=linux
fi

install_cachyos() {
  sudo pacman -S --needed --noconfirm \
    gtk4 python-gobject python-pip ollama \
    grim tesseract espeak-ng gtk4-layer-shell || true
}

if [[ "$SKIP_OLLAMA" -eq 0 ]]; then
  case "${ID:-}" in
    cachyos|arch) install_cachyos ;;
    bazzite|fedora)
      if command -v rpm-ostree >/dev/null; then
        echo "Bazzite is immutable. Wren runs on the host (GTK is already there)."
      else
        sudo dnf install -y gtk4 python3-gobject python3-pip ollama grim tesseract espeak-ng || true
      fi
      ;;
    *)
      echo "Unknown distro (${ID:-}). Overlay will still be installed."
      ;;
  esac
fi

echo "Installing the overlay…"
python3 -m pip install --user -e "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
hash -r 2>/dev/null || true
echo "Installed Wren $(python3 -c 'import wren; print(wren.__version__)')"

python3 - <<PY
from pathlib import Path
from wren.config import WrenConfig
from wren.assets import sync_assets, write_desktop, repair_icons
from wren.topmost import install_gnome_helper
cfg = WrenConfig.load()
cfg.source_dir = r"$ROOT"
cfg.save()
repair_icons()
sync_assets(Path(r"$ROOT"))
write_desktop()
install_gnome_helper(cfg.always_on_top)
print("icons repaired + desktop + GNOME helper refreshed")
PY

if [[ "$SKIP_OLLAMA" -eq 0 ]]; then
  echo "Looking for a local brain (Ollama)…"
  python3 -m wren --setup || true
  python3 -m wren --install-ollama || echo "Ollama skipped. Wren still launches. Later: wren --install-ollama"
  if command -v ollama >/dev/null || [[ -x "$HOME/.local/bin/ollama" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    python3 -m wren --ensure-brain || true
    if [[ "$RAM_GB" -ge 48 ]]; then
      MODEL="qwen2.5:14b-instruct-q4_K_M"
    elif [[ "$RAM_GB" -ge 16 ]]; then
      MODEL="llama3.1:8b-instruct-q4_K_M"
    elif [[ "$RAM_GB" -ge 10 ]]; then
      MODEL="phi3:mini"
    else
      MODEL="llama3.2:1b"
    fi
    python3 -m wren --setup --model "$MODEL" || true
  fi
fi

echo
echo "Launch with:  wren     (or search Wren in the app grid)"
echo "Update with:  wren --update"
echo "Version:      wren --version    (must print 0.1.13)"
echo "Status:       wren --doctor"
echo "Config:       ~/.config/wren/config.json"
echo "Wren will not click, type, or go online unless you allow it."
echo
echo "Resize: pinch, Ctrl+scroll, or long-press → Smaller / Bigger"
echo "If the bird appears but stays quiet:  wren --ensure-brain"
