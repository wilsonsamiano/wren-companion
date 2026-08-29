#!/usr/bin/env bash
# Wren installer for CachyOS (Arch) and Bazzite (Fedora Atomic).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RAM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"

echo "Wren installer"
echo "Detected RAM: ${RAM_GB} GB"

if [[ -f /usr/lib/os-release ]]; then
  # shellcheck disable=SC1091
  . /usr/lib/os-release
else
  ID=linux
fi

install_cachyos() {
  sudo pacman -S --needed --noconfirm \
    gtk4 python-gobject python-pip ollama \
    grim tesseract espeak-ng
}

install_bazzite() {
  echo "Bazzite is immutable. Installing Wren inside a Fedora distrobox."
  if ! command -v distrobox >/dev/null; then
    echo "Install distrobox first (ujust distrobox, or rpm-ostree)."
    exit 1
  fi
  distrobox create -n wren -i fedora:41 --yes || true
  distrobox enter wren -- sudo dnf install -y gtk4 python3-gobject python3-pip ollama espeak-ng || true
}

case "${ID:-}" in
  cachyos|arch) install_cachyos ;;
  bazzite|fedora)
    if command -v rpm-ostree >/dev/null; then
      install_bazzite
    else
      sudo dnf install -y gtk4 python3-gobject python3-pip ollama grim tesseract espeak-ng
    fi
    ;;
  *)
    echo "Unknown distro (${ID:-}). Install gtk4, python-gobject, ollama, then continue."
    ;;
esac

python3 -m pip install --user -e "$ROOT"

if command -v ollama >/dev/null; then
  if [[ "$RAM_GB" -ge 48 ]]; then
    MODEL="qwen2.5:14b-instruct-q4_K_M"
  elif [[ "$RAM_GB" -ge 16 ]]; then
    MODEL="llama3.1:8b-instruct-q4_K_M"
  elif [[ "$RAM_GB" -ge 8 ]]; then
    MODEL="phi3:mini"
  else
    MODEL="llama3.2:1b"
  fi
  echo "Pulling $MODEL …"
  ollama pull "$MODEL" || true
  python3 -m wren --setup --model "$MODEL"
fi

mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/wren"
if [[ -f "$ROOT/wren/assets/hero.png" ]]; then
  cp "$ROOT/wren/assets/hero.png" "$HOME/.local/share/wren/hero.png"
elif [[ -f "$ROOT/../public/pet/hero.png" ]]; then
  cp "$ROOT/../public/pet/hero.png" "$HOME/.local/share/wren/hero.png"
fi

cat > "$HOME/.local/share/applications/wren.desktop" <<EOF
[Desktop Entry]
Name=Wren
Comment=Desktop companion
Exec=wren
Icon=$HOME/.local/share/wren/hero.png
Terminal=false
Type=Application
Categories=Utility;
EOF

echo
echo "Launch with:  wren"
echo "Config:       ~/.config/wren/config.json"
echo "Wren will not click, type, or go online unless you allow it."
