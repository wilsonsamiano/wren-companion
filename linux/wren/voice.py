"""Offline speak (TTS) and listen (STT). Nothing runs until the user opts in."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

SHARE = Path.home() / ".local" / "share" / "wren"
MODEL_DIR = SHARE / "vosk-model-small-en-us-0.15"
MODEL_ZIP_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

_speak_proc: subprocess.Popen | None = None

AFFIRM = {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "do it", "go ahead", "please"}
DENY = {"no", "nope", "nah", "don't", "dont", "cancel", "stop", "never"}


def is_affirm(text: str) -> bool:
    t = text.lower().strip().rstrip(".!")
    return t in AFFIRM or t.startswith("yes")


def is_deny(text: str) -> bool:
    t = text.lower().strip().rstrip(".!")
    return t in DENY or t.startswith("no ")


def tts_bin() -> list[str] | None:
    if shutil.which("spd-say"):
        return ["spd-say", "-e", "-t", "female1"]
    if shutil.which("espeak-ng"):
        return ["espeak-ng", "-v", "en-us", "-s", "165"]
    if shutil.which("espeak"):
        return ["espeak", "-v", "en", "-s", "165"]
    if shutil.which("festival"):
        return ["festival", "--tts"]
    return None


def can_speak() -> bool:
    return tts_bin() is not None


def stop_speak() -> None:
    global _speak_proc
    if _speak_proc and _speak_proc.poll() is None:
        _speak_proc.terminate()
    _speak_proc = None


def speak(text: str) -> None:
    """Block until spoken. Call from a worker thread."""
    stop_speak()
    line = " ".join(text.split())
    if not line:
        return
    cmd = tts_bin()
    if cmd is None:
        return
    global _speak_proc
    try:
        if cmd[0].endswith("festival"):
            _speak_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert _speak_proc.stdin
            _speak_proc.stdin.write(line.encode())
            _speak_proc.stdin.close()
        else:
            _speak_proc = subprocess.Popen(cmd + [line], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _speak_proc.wait(timeout=30)
    except Exception:
        stop_speak()


def vosk_ok() -> bool:
    try:
        import vosk  # noqa: F401
    except Exception:
        return False
    return MODEL_DIR.is_dir() and any(MODEL_DIR.rglob("am/final.mdl"))


def can_listen() -> bool:
    return vosk_ok() and _recorder() is not None


def _recorder() -> list[str] | None:
    raw = str(SHARE / "listen.raw")
    SHARE.mkdir(parents=True, exist_ok=True)
    if shutil.which("pw-record"):
        return ["pw-record", "--rate=16000", "--channels=1", "--format=s16", raw]
    if shutil.which("parecord"):
        return ["parecord", "--raw", "--rate=16000", "--channels=1", "--format=s16le", raw]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", raw]
    return None


def listen(seconds: float = 5.0) -> str:
    rec = _recorder()
    if rec is None or not vosk_ok():
        return ""
    raw = SHARE / "listen.raw"
    if raw.exists():
        raw.unlink()
    try:
        subprocess.run(rec, timeout=max(2.0, seconds), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass
    if not raw.is_file() or raw.stat().st_size < 1600:
        return ""
    data = raw.read_bytes()
    try:
        import vosk

        vosk.SetLogLevel(-1)
        model = vosk.Model(str(MODEL_DIR))
        recg = vosk.KaldiRecognizer(model, 16000)
        recg.AcceptWaveform(data)
        out = json.loads(recg.FinalResult())
        return str(out.get("text") or "").strip()
    except Exception:
        return ""


def install_voice() -> str:
    """pip install vosk + download the small English model. Userspace only."""
    import urllib.request

    SHARE.mkdir(parents=True, exist_ok=True)
    pip = subprocess.run(
        [__import__("sys").executable, "-m", "pip", "install", "--user", "vosk"],
        capture_output=True,
        text=True,
    )
    if pip.returncode != 0:
        return f"pip vosk failed: {pip.stderr[-400:]}"
    zpath = SHARE / "vosk-model.zip"
    try:
        urllib.request.urlretrieve(MODEL_ZIP_URL, zpath)
    except Exception as exc:
        return f"model download failed: {exc}"
    dest_parent = SHARE
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest_parent)
    zpath.unlink(missing_ok=True)
    if not vosk_ok():
        return "unpacked the zip but the model files are missing"
    return "ok"


def status() -> str:
    speak_s = tts_bin()
    rec = _recorder()
    lines = [
        f"speak: {speak_s[0] if speak_s else 'none (install espeak-ng or speech-dispatcher)'}",
        f"record: {rec[0] if rec else 'none (need pw-record, parecord, or arecord)'}",
        f"listen: {'vosk ready' if vosk_ok() else 'vosk not installed (wren --install-voice)'}",
    ]
    return "\n".join(lines)
