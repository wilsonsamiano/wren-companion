from __future__ import annotations

import shutil
import subprocess


def speak(text: str) -> None:
    """Prefer Piper; fall back to espeak-ng. Never required."""
    if shutil.which("piper"):
        subprocess.run(
            ["piper", "--output-raw"],
            input=text.encode(),
            stdout=subprocess.DEVNULL,
            check=False,
        )
        return
    if shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", text], check=False)
        return
    print(f"Wren: {text}")


def transcribe(wav_path: str) -> str:
    if shutil.which("whisper-cli"):
        out = subprocess.check_output(
            ["whisper-cli", "-f", wav_path, "-nt"],
            text=True,
            timeout=30,
        )
        return out.strip()
    return ""
