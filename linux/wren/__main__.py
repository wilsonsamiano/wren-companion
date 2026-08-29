from __future__ import annotations

import argparse
import sys

from .config import WrenConfig, detect_ram_gb, pick_model
from .overlay import launch


def main() -> None:
    parser = argparse.ArgumentParser(prog="wren", description="Wren desktop companion")
    parser.add_argument("--setup", action="store_true", help="write default config and exit")
    parser.add_argument("--model", help="override Ollama model")
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
    try:
        launch(cfg)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
