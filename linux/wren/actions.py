from __future__ import annotations

import shlex
import subprocess

from .permissions import ProposedAction, confirm


def run_action(action: ProposedAction, *, ask: bool = True) -> str:
    if ask and not confirm(action):
        return "declined"
    if action.kind == "command" and action.command:
        argv = shlex.split(action.command)
        if action.background or (argv and argv[-1] == "serve"):
            subprocess.Popen(
                argv,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "started"
        result = subprocess.run(
            argv,
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
