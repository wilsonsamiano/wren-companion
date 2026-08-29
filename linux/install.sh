#!/usr/bin/env bash
# Wren installer for CachyOS (Arch) and Bazzite (Fedora Atomic).
# The overlay is installed first. Ollama is best-effort and must not block the bird.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RAM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"

echo "Wren installer"
echo "Detected RAM: ${RAM_GB} GB"

if [[ ! -f "$ROOT/wren/assets/hero.png" ]]; then
  echo "This checkout is missing the bird sprite (linux/wren/assets/hero.png)."
  echo "You are on the old 0.1.0 tree. From the repo root run:"
  echo "  git pull"
  echo "  git log -1 --oneline   # should mention 0.1.3"
  echo "Then run this installer again."
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

echo "Installing the overlay…"
python3 -m pip install --user -e "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
hash -r 2>/dev/null || true
echo "Installed Wren $(python3 -c 'import wren; print(wren.__version__)')"

mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/wren" \
         "$HOME/.local/share/icons/hicolor/128x128/apps"
cp "$ROOT/wren/assets/hero.png" "$HOME/.local/share/wren/hero.png"
cp "$ROOT/wren/assets/hero.png" "$HOME/.local/share/icons/hicolor/128x128/apps/dev.wren.companion.png"

cat > "$HOME/.local/share/applications/wren.desktop" <<EOF
[Desktop Entry]
Name=Wren
Comment=Desktop companion
Exec=env PATH=$HOME/.local/bin:/usr/bin:/home/linuxbrew/.linuxbrew/bin wren
Icon=$HOME/.local/share/wren/hero.png
Terminal=false
Type=Application
StartupWMClass=wren
Categories=Utility;
X-GNOME-UsesNotifications=true
EOF

# Brain is optional. A 404 here used to abort before pip ran.
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

echo
echo "Launch with:  wren     (or search Wren in the app grid)"
echo "Version:      wren --version    (must print 0.1.3)"
echo "Status:       wren --doctor"
echo "Config:       ~/.config/wren/config.json"
echo "Wren will not click, type, or go online unless you allow it."
echo
echo "If the bird appears but stays quiet:  wren --ensure-brain"
echo "If Ollama is still missing and you have Homebrew:  brew install ollama"
