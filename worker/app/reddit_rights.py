"""Reddit permission state machine (pure logic; persistence lives in the table).

States: candidate → pm_approved → sent → granted | denied | expired | review;
review → granted | denied. granted/denied/expired are terminal. Only granted
items may enter evidence — enforced by split_usable at story-build time.
"""

from __future__ import annotations

EXPIRY_DAYS = 30

_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "candidate": ("pm_approved",),
    "pm_approved": ("sent",),
    "sent": ("granted", "denied", "expired", "review"),
    "review": ("granted", "denied"),
    "granted": (),
    "denied": (),
    "expired": (),
}


class RightsError(ValueError):
    """An illegal rights transition was attempted."""


def transition(state: str, to: str) -> str:
    """Move a post right forward. Raises RightsError on any illegal move."""
    if to not in _TRANSITIONS.get(state, ()):
        raise RightsError(f"cannot move reddit right from {state!r} to {to!r}")
    return to


def is_expired(*, sent_days_ago: int) -> bool:
    return sent_days_ago > EXPIRY_DAYS


def split_usable(
    items: list[dict], rights_by_url: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Partition story items into (usable, held). Non-reddit items always pass;
    reddit items pass only when granted. Pure — callers supply the rows."""
    usable, held = [], []
    for item in items:
        if item.get("kind") != "reddit":
            usable.append(item)
            continue
        (usable if rights_by_url.get(item.get("url")) == "granted" else held).append(item)
    return usable, held


def credit_suffix(author: str, subreddit: str) -> str:
    """Attribution fragment for packets and narration prompts."""
    if not (author or "").strip() or not (subreddit or "").strip():
        return ""
    return f" (u/{author.strip()} on r/{subreddit.strip()})"
