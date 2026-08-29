from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import WrenConfig
from .permissions import ProposedAction

SYSTEM = """You are Wren, a tiny Linux desktop companion.
Speak in 1-3 short calm sentences. Never act — only propose.
If you need a command or a web lookup, put it in the action object.
JSON only:
{"speech":"...","action":null or {"title":"...","detail":"...","risk":"low|medium|high","kind":"command|web","command":"","url":""}}
"""


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def ask_ollama(cfg: WrenConfig, prompt: str, context: str) -> tuple[str, ProposedAction | None]:
    try:
        body = _post_json(
            f"{cfg.ollama_url}/api/chat",
            {
                "model": cfg.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"{context}\n\n{prompt}"},
                ],
            },
        )
        text = body.get("message", {}).get("content", "")
        return _parse(text)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return (
            "Ollama is not reachable. Start it with `ollama serve` or switch to a hosted key in config.",
            None,
        )


def ask_grok(cfg: WrenConfig, prompt: str, context: str, *, allow_internet: bool) -> tuple[str, ProposedAction | None]:
    if not cfg.grok_api_key:
        return ask_ollama(cfg, prompt, context)
    body = _post_json(
        "https://api.x.ai/v1/chat/completions",
        {
            "model": "grok-4.5",
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"allowInternet={allow_internet}\n{context}\n\n{prompt}",
                },
            ],
        },
        headers={"Authorization": f"Bearer {cfg.grok_api_key}"},
    )
    text = body["choices"][0]["message"]["content"]
    return _parse(text)


def _parse(raw: str) -> tuple[str, ProposedAction | None]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return raw.strip(), None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return raw.strip(), None
    action = None
    if data.get("action"):
        a = data["action"]
        action = ProposedAction(
            title=a.get("title", "Action"),
            detail=a.get("detail", ""),
            risk=a.get("risk", "medium"),
            kind=a.get("kind", "command"),
            command=a.get("command", ""),
            url=a.get("url", ""),
        )
    return str(data.get("speech", raw)), action
