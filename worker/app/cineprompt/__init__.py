"""CinePrompt engine: structured field-state to cinematography prompt.

Public surface:
    build_prompt(state)      -> list[str]
    resolve_state(state)     -> list[dict]
    fill_from_scene(...)     -> dict   (added in Task 6)
"""
from .resolve import build_prompt, resolve_state, strip_ms

__all__ = ["build_prompt", "resolve_state", "strip_ms"]
