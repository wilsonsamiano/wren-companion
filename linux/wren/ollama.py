"""Find, start, and install a local Ollama. All writes stay under $HOME unless the user already has a system binary."""

from __future__ import annotations

import io
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

USER_BIN = Path.home() / ".local" / "bin" / "ollama"
USER_LIB = Path.home() / ".local" / "lib" / "ollama"
LOG = Path.home() / ".local" / "share" / "wren" / "ollama.log"


def _arch() -> str:
    machine = os.uname().machine
    return {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, "amd64")


def tarball_urls() -> list[str]:
    arch = _arch()
    return [
        f"https://github.com/ollama/ollama/releases/latest/download/ollama-linux-{arch}.tar.zst",
        f"https://ollama.com/download/ollama-linux-{arch}.tar.zst",
        f"https://github.com/ollama/ollama/releases/latest/download/ollama-linux-{arch}.tgz",
        f"https://ollama.com/download/ollama-linux-{arch}.tgz",
    ]


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


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    curl = shutil.which("curl")
    if curl:
        result = subprocess.run(
            [curl, "-fL", "--retry", "3", "--retry-delay", "2", "-A", f"Wren/{__version__}", "-o", str(dest), url],
            capture_output=True,
            timeout=300,
        )
        return result.returncode == 0 and dest.is_file() and dest.stat().st_size > 1000
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"Wren/{__version__}"})
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        return dest.is_file() and dest.stat().st_size > 1000
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tar = shutil.which("tar")
    if tar:
        for extra in (["--zstd"], ["-z"], ["-a"], []):
            result = subprocess.run(
                [tar, *extra, "-xf", str(archive), "-C", str(dest)],
                capture_output=True,
            )
            if result.returncode == 0 and any(dest.rglob("ollama")):
                return
    try:
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:
                tf.extractall(dest)
        if any(dest.rglob("ollama")):
            return
    except tarfile.TarError:
        pass
    try:
        from compression import zstd

        data = zstd.decompress(archive.read_bytes())
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:
                tf.extractall(dest)
        return
    except Exception as exc:
        raise RuntimeError(f"cannot extract {archive.name}: {exc}") from exc


def _install_via_brew() -> str | None:
    brew = shutil.which("brew")
    if not brew:
        return None
    subprocess.run([brew, "install", "ollama"], check=False, timeout=600)
    return binary()


def install_userspace() -> str:
    """Download the official Linux tarball into ~/.local. No sudo. Never raises."""
    existing = binary()
    if existing:
        return existing
    try:
        via_brew = _install_via_brew()
        if via_brew:
            return via_brew
    except (subprocess.SubprocessError, OSError):
        pass

    USER_BIN.parent.mkdir(parents=True, exist_ok=True)
    USER_LIB.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "ollama.archive"
            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir()
            used = None
            for url in tarball_urls():
                if _download(url, archive):
                    used = url
                    break
            if used is None:
                return "download-failed: ollama tarball 404 (try: brew install ollama)"
            try:
                _extract(archive, extract_dir)
            except RuntimeError as exc:
                return f"extract-failed: {exc}"
            extracted = None
            for path in extract_dir.rglob("ollama"):
                if path.is_file() and path.name == "ollama":
                    extracted = path
                    break
            if extracted is None:
                return "download-failed: no ollama binary in archive"
            shutil.copy2(extracted, USER_BIN)
            USER_BIN.chmod(0o755)
            libsrc = extracted.parent.parent / "lib" / "ollama"
            if not libsrc.is_dir():
                libsrc = extracted.parent / "lib" / "ollama"
            if libsrc.is_dir():
                shutil.copytree(libsrc, USER_LIB, dirs_exist_ok=True)
        return str(USER_BIN)
    except Exception as exc:
        return f"download-failed: {exc}"


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
        f"pet size:{cfg.pet_size} px",
        f"source:  {cfg.source_dir or 'unknown'}",
    ]
    pet = Path(__file__).resolve().parent / "assets" / "hero.png"
    share = Path.home() / ".local/share/wren/hero.png"
    lines.append(f"sprite:  {pet if pet.exists() else share if share.exists() else 'MISSING'}")
    return "\n".join(lines)
