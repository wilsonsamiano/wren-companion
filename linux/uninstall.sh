#!/usr/bin/env bash
# Remove the Wren overlay. Leaves Ollama unless you pass --with-ollama.
#   ./uninstall.sh              overlay + app menu + pip package
#   ./uninstall.sh --purge      also config, distrobox, icons
#   ./uninstall.sh --with-ollama
set -euo pipefail

PURGE=0
WITH_OLLAMA=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --with-ollama) WITH_OLLAMA=1 ;;
    -h|--help)
      echo "Usage: ./uninstall.sh [--purge] [--with-ollama]"
      exit 0
      ;;
  esac
done

echo "Stopping Wren…"
pkill -f 'application_id=dev.wren.companion' 2>/dev/null || true
pkill -f 'python3 -m wren' 2>/dev/null || true
if command -v wren >/dev/null 2>&1; then
  pkill -f "$HOME/.local/bin/wren" 2>/dev/null || true
fi

echo "Removing the pip package…"
python3 -m pip uninstall -y wren-companion >/dev/null 2>&1 || \
  python3 -m pip uninstall -y --user wren-companion >/dev/null 2>&1 || true
rm -f "$HOME/.local/bin/wren"

echo "Removing the app menu entry…"
rm -f "$HOME/.local/share/applications/wren.desktop"
rm -f "$HOME/.local/share/icons/hicolor/128x128/apps/dev.wren.companion.png"
rm -rf "$HOME/.local/share/wren"

if [[ "$PURGE" -eq 1 ]]; then
  echo "Purging config and distrobox…"
  rm -rf "$HOME/.config/wren"
  if command -v distrobox >/dev/null 2>&1; then
    distrobox stop wren >/dev/null 2>&1 || true
    distrobox rm -f wren >/dev/null 2>&1 || true
  fi
fi

if [[ "$WITH_OLLAMA" -eq 1 ]]; then
  echo "Stopping user-space Ollama (not a system package)…"
  pkill -f 'ollama serve' 2>/dev/null || true
  rm -f "$HOME/.local/bin/ollama"
  rm -rf "$HOME/.local/lib/ollama"
  echo "Models in ~/.ollama were left in place. Delete that folder if you want them gone too."
fi

echo
echo "Old Wren overlay is gone."
echo "Config kept at ~/.config/wren (use --purge to drop it)."
echo "Reinstall:  git pull && ./install.sh && wren"
