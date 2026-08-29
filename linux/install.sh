#!/usr/bin/env bash
# Wren installer for CachyOS (Arch) and Bazzite (Fedora Atomic).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RAM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"

echo "Wren installer"
echo "Detected RAM: ${RAM_GB} GB"

if [[ ! -f "$ROOT/wren/assets/hero.png" ]]; then
  echo "This checkout is missing the bird sprite (linux/wren/assets/hero.png)."
  echo "You are on the old 0.1.0 tree. From the repo root run:"
  echo "  git pull"
  echo "  git log -1 --oneline   # should mention 0.1.1 or 'Show the bird'"
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

install_ollama_userspace() {
  if command -v ollama >/dev/null 2>&1; then
    return 0
  fi
  if [[ -x "$HOME/.local/bin/ollama" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    return 0
  fi
  echo "Installing Ollama into ~/.local (no sudo)…"
  python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, ".")
# install.sh cwd is linux/; the editable install happens after, so call the tarball directly
import os, tarfile, tempfile, urllib.request, shutil
url = "https://ollama.com/download/ollama-linux-amd64.tgz"
bindir = Path.home() / ".local" / "bin"
bindir.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    tgz = Path(tmp) / "ollama.tgz"
    urllib.request.urlretrieve(url, tgz)
    with tarfile.open(tgz, "r:gz") as tf:
        try:
            tf.extractall(tmp, filter="data")
        except TypeError:
            tf.extractall(tmp)
    exe = next(p for p in Path(tmp).rglob("ollama") if p.is_file() and p.name == "ollama")
    dest = bindir / "ollama"
    shutil.copy2(exe, dest)
    dest.chmod(0o755)
    print(dest)
PY
  export PATH="$HOME/.local/bin:$PATH"
}

install_bazzite() {
  echo "Bazzite is immutable. Wren itself runs on the host (GTK is already there)."
  echo "Ollama is installed into ~/.local so the overlay can reach it."
  install_ollama_userspace
  if command -v distrobox >/dev/null; then
    distrobox create -n wren -i fedora:41 --yes >/dev/null 2>&1 || true
  fi
}

case "${ID:-}" in
  cachyos|arch) install_cachyos ;;
  bazzite|fedora)
    if command -v rpm-ostree >/dev/null; then
      install_bazzite
    else
      sudo dnf install -y gtk4 python3-gobject python3-pip ollama grim tesseract espeak-ng || true
    fi
    ;;
  *)
    echo "Unknown distro (${ID:-}). Installing Ollama userspace if needed."
    install_ollama_userspace
    ;;
esac

python3 -m pip install --user -e "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
echo "Installed Wren $(python3 -c 'import wren; print(wren.__version__)')"

# Start Ollama, then pull a RAM-sized model.
if command -v ollama >/dev/null; then
  if ! curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    nohup ollama serve >"$HOME/.local/share/wren/ollama.log" 2>&1 &
    echo "Started ollama serve"
    sleep 2
  fi
  if [[ "$RAM_GB" -ge 48 ]]; then
    MODEL="qwen2.5:14b-instruct-q4_K_M"
  elif [[ "$RAM_GB" -ge 16 ]]; then
    MODEL="llama3.1:8b-instruct-q4_K_M"
  elif [[ "$RAM_GB" -ge 10 ]]; then
    MODEL="phi3:mini"
  else
    MODEL="llama3.2:1b"
  fi
  echo "Pulling $MODEL …"
  ollama pull "$MODEL" || true
  python3 -m wren --setup --model "$MODEL" || true
else
  echo "Ollama binary not on PATH yet. After install, run:  wren --install-ollama"
  python3 -m wren --setup || true
fi

mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/wren" \
         "$HOME/.local/share/icons/hicolor/128x128/apps"
if [[ -f "$ROOT/wren/assets/hero.png" ]]; then
  cp "$ROOT/wren/assets/hero.png" "$HOME/.local/share/wren/hero.png"
  cp "$ROOT/wren/assets/hero.png" "$HOME/.local/share/icons/hicolor/128x128/apps/dev.wren.companion.png"
elif [[ -f "$ROOT/../public/pet/hero.png" ]]; then
  cp "$ROOT/../public/pet/hero.png" "$HOME/.local/share/wren/hero.png"
fi

cat > "$HOME/.local/share/applications/wren.desktop" <<EOF
[Desktop Entry]
Name=Wren
Comment=Desktop companion
Exec=env PATH=$HOME/.local/bin:/usr/bin wren
Icon=$HOME/.local/share/wren/hero.png
Terminal=false
Type=Application
StartupWMClass=wren
Categories=Utility;
X-GNOME-UsesNotifications=true
EOF

echo
echo "Launch with:  wren     (or search Wren in the app grid)"
echo "Status:       wren --doctor"
echo "Config:       ~/.config/wren/config.json"
echo "Wren will not click, type, or go online unless you allow it."
echo
echo "If the bird appears but stays quiet:  wren --ensure-brain"
