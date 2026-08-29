from __future__ import annotations

import shlex
import subprocess

from .permissions import ProposedAction, confirm


def run_action(action: ProposedAction, *, ask: bool = True) -> str:
    if ask and not confirm(action):
        return "declined"
    if action.kind == "command" and action.command:
        result = subprocess.run(
            shlex.split(action.command),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out.strip() or f"exit {result.returncode}"
    if action.kind == "web" and action.url:
        return f"blocked-until-approved:{action.url}"
    return "nothing-to-run"
