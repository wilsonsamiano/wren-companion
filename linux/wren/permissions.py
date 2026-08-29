from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProposedAction:
    title: str
    detail: str
    risk: str
    kind: str
    command: str = ""
    url: str = ""
    background: bool = False


def confirm(action: ProposedAction) -> bool:
    """CLI fallback when the GTK dialog is unavailable."""
    print()
    print(f"Wren wants to: {action.title}")
    print(f"  {action.detail}")
    print(f"  risk: {action.risk}   kind: {action.kind}")
    if action.command:
        print(f"  cmd: {action.command}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer in {"y", "yes", "ok", "sure"}
