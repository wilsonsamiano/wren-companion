from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "wren" / "config.json"


def detect_ram_gb() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return max(1, kb // (1024 * 1024))
    except OSError:
        return 8
    return 8


def pick_model(ram_gb: int) -> str:
    # Surface Go 2 class (~8 GB, often reported as 7) must stay on a 1B model.
    if ram_gb >= 48:
        return "qwen2.5:14b-instruct-q4_K_M"
    if ram_gb >= 16:
        return "llama3.1:8b-instruct-q4_K_M"
    if ram_gb >= 10:
        return "phi3:mini"
    return "llama3.2:1b"


@dataclass
class Permissions:
    watch: bool = False
    voice: bool = False
    actions: bool = True
    internet: bool = False


@dataclass
class WrenConfig:
    model: str = field(default_factory=lambda: pick_model(detect_ram_gb()))
    ollama_url: str = "http://127.0.0.1:11434"
    grok_api_key: str = ""
    watch_seconds: float = 16.0
    permissions: Permissions = field(default_factory=Permissions)
    pet_size: int = 96
    source_dir: str = ""
    always_on_top: bool = True
    margin_right: int = 24
    margin_bottom: int = 24

    def save(self) -> Path:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls) -> "WrenConfig":
        path = _config_path()
        if not path.exists():
            cfg = cls()
            cfg.save()
            return cfg
        raw = json.loads(path.read_text(encoding="utf-8"))
        perm = Permissions(**raw.pop("permissions", {}))
        raw.pop("pet_scale", None)
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        cfg = cls(permissions=perm, **known)
        cfg.pet_size = max(64, min(240, int(cfg.pet_size or 96)))
        return cfg
