from __future__ import annotations

import argparse
import sys

from .config import WrenConfig, detect_ram_gb, pick_model
from .overlay import launch


def main() -> None:
    parser = argparse.ArgumentParser(prog="wren", description="Wren desktop companion")
    parser.add_argument("--setup", action="store_true", help="write default config and exit")
    parser.add_argument("--model", help="override Ollama model")
    parser.add_argument("--doctor", action="store_true", help="print overlay / Ollama status")
    parser.add_argument("--install-ollama", action="store_true", help="download Ollama into ~/.local")
    parser.add_argument("--ensure-brain", action="store_true", help="start Ollama if it is down")
    args = parser.parse_args()

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
        dest = install_userspace()
        print(f"binary: {dest}")
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
