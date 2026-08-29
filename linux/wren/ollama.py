"""Find, start, and install a local Ollama. All writes stay under $HOME unless the user already has a system binary."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import WrenConfig, pick_model, detect_ram_gb
from . import __version__

OLLAMA_TGZ = "https://ollama.com/download/ollama-linux-amd64.tgz"
USER_BIN = Path.home() / ".local" / "bin" / "ollama"
USER_LIB = Path.home() / ".local" / "lib" / "ollama"
LOG = Path.home() / ".local" / "share" / "wren" / "ollama.log"


def ping(cfg: WrenConfig, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"{cfg.ollama_url}/api/tags", timeout=timeout)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def binary() -> str | None:
    candidates = [
        shutil.which("ollama"),
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        str(USER_BIN),
        str(Path.home() / ".linuxbrew/bin/ollama"),
        "/home/linuxbrew/.linuxbrew/bin/ollama",
    ]
    seen: set[str] = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def has_distrobox_wren() -> bool:
    if not shutil.which("distrobox"):
        return False
    try:
        out = subprocess.check_output(["distrobox", "list"], text=True, timeout=8)
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return any(line.split()[0:2] and "wren" in line.split() for line in out.splitlines())


def start(cfg: WrenConfig) -> str:
    """Best-effort start. Returns a short status string."""
    if ping(cfg):
        return "already-up"
    log = LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    path = env.get("PATH", "")
    extra = str(Path.home() / ".local" / "bin")
    if extra not in path.split(":"):
        env["PATH"] = extra + ":" + path

    bin_path = binary()
    if bin_path:
        with log.open("ab") as fh:
            subprocess.Popen(
                [bin_path, "serve"],
                start_new_session=True,
                stdout=fh,
                stderr=subprocess.STDOUT,
                env=env,
            )
        return "started-host"
    if shutil.which("distrobox"):
        with log.open("ab") as fh:
            subprocess.Popen(
                ["distrobox", "enter", "-n", "wren", "--", "ollama", "serve"],
                start_new_session=True,
                stdout=fh,
                stderr=subprocess.STDOUT,
                env=env,
            )
        return "started-distrobox"
    return "missing"


def wait_up(cfg: WrenConfig, seconds: float = 8.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if ping(cfg):
            return True
        time.sleep(0.4)
    return ping(cfg)


def install_userspace() -> str:
    """Download the official Linux tarball into ~/.local. No sudo."""
    USER_BIN.parent.mkdir(parents=True, exist_ok=True)
    USER_LIB.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tgz = Path(tmp) / "ollama.tgz"
        urllib.request.urlretrieve(OLLAMA_TGZ, tgz)
        with tarfile.open(tgz, "r:gz") as tf:
            try:
                tf.extractall(tmp, filter="data")
            except TypeError:
                tf.extractall(tmp)
        extracted = None
        for p in Path(tmp).rglob("ollama"):
            if p.is_file() and os.access(p, os.X_OK) and p.name == "ollama":
                extracted = p
                break
        if extracted is None:
            return "download-failed"
        shutil.copy2(extracted, USER_BIN)
        USER_BIN.chmod(0o755)
        libsrc = extracted.parent.parent / "lib" / "ollama"
        if libsrc.is_dir():
            if USER_LIB.exists():
                shutil.copytree(libsrc, USER_LIB, dirs_exist_ok=True)
    return str(USER_BIN)


def pull_model(cfg: WrenConfig) -> str:
    bin_path = binary()
    if not bin_path:
        return "no-binary"
    model = cfg.model or pick_model(detect_ram_gb())
    try:
        subprocess.run(
            [bin_path, "pull", model],
            check=False,
            timeout=60 * 30,
        )
    except subprocess.SubprocessError as exc:
        return f"pull-failed:{exc}"
    return model


def doctor(cfg: WrenConfig) -> str:
    lines = [
        f"version: {__version__}",
        f"ram:     {detect_ram_gb()} GB",
        f"model:   {cfg.model}",
        f"url:     {cfg.ollama_url}",
        f"binary:  {binary() or 'not found'}",
        f"reachable:{' yes' if ping(cfg) else ' no'}",
        f"distrobox wren: {'yes' if has_distrobox_wren() else 'no'}",
    ]
    pet = Path(__file__).resolve().parent / "assets" / "hero.png"
    share = Path.home() / ".local/share/wren/hero.png"
    lines.append(f"sprite:  {pet if pet.exists() else share if share.exists() else 'MISSING'}")
    return "\n".join(lines)
