from __future__ import annotations

import argparse
import sys

from .config import WrenConfig, detect_ram_gb, pick_model
from .overlay import launch


def main() -> None:
    parser = argparse.ArgumentParser(prog="wren", description="Wren desktop companion")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--setup", action="store_true", help="write default config and exit")
    parser.add_argument("--model", help="override Ollama model")
    parser.add_argument("--doctor", action="store_true", help="print overlay / Ollama status")
    parser.add_argument("--install-ollama", action="store_true", help="download Ollama into ~/.local")
    parser.add_argument("--ensure-brain", action="store_true", help="start Ollama if it is down")
    parser.add_argument("--update", action="store_true", help="git pull + reinstall in place (no uninstall)")
    args = parser.parse_args()

    if args.version:
        from . import __version__

        print(__version__)
        return

    if args.update:
        from .update import run_update

        sys.exit(run_update())

    cfg = WrenConfig.load()
    ram = detect_ram_gb()
    if args.model:
        cfg.model = args.model
    elif args.setup:
        cfg.model = pick_model(ram)
    if args.setup or args.model:
        path = cfg.save()
        print(f"Wren config written to {path}")
        print(f"Detected {ram} GB RAM → model {cfg.model}")
        if args.setup:
            return

    if args.doctor:
        from .ollama import doctor

        print(doctor(cfg))
        return

    if args.install_ollama:
        from .ollama import install_userspace, start, wait_up, pull_model

        print("Installing Ollama into ~/.local …")
        try:
            dest = install_userspace()
        except Exception as exc:
            print(f"Ollama install failed: {exc}")
            print("Wren still works. On Bazzite you can also run:  brew install ollama")
            return
        print(f"binary: {dest}")
        if str(dest).startswith("download-failed") or str(dest).startswith("extract-failed"):
            print("Wren still launches without a brain. Later: brew install ollama")
            print("or retry: wren --install-ollama")
            return
        start(cfg)
        if wait_up(cfg, 12):
            print(f"pulling {cfg.model} …")
            print(pull_model(cfg))
        else:
            print("Ollama installed. Start it with: ollama serve")
        return

    if args.ensure_brain:
        from .ollama import start, wait_up

        print(start(cfg))
        print("up" if wait_up(cfg) else "still-down")
        return

    try:
        launch(cfg)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
