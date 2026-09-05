"""One-time copy of the active voice profile into the channels config.

Values are carried forward, not recreated, so the finance channel keeps the
prompt that has been producing content. Terms already in BASE_BLOCKLIST are not
duplicated into extra_blocklist: the base set is unioned in at read time.

Run once:  ..\\.venv\\Scripts\\python.exe -m scripts.seed_channels
"""

from __future__ import annotations

import asyncio
import sys

from app import db
from app.channels import BASE_BLOCKLIST, CONFIG_KEY


def check_voice_key(voice_key: str) -> str:
    from app.youtube import VOICE_MAP

    if voice_key not in VOICE_MAP:
        valid = ", ".join(sorted(VOICE_MAP))
        raise ValueError(
            f"voice_key {voice_key!r} is not a recognized voice; valid keys: {valid}"
        )
    return voice_key


def build_channels_payload(voice_profiles: dict | None) -> dict:
    if not voice_profiles or not voice_profiles.get("profiles"):
        raise ValueError("no voice_profiles config to migrate from")

    profiles = voice_profiles["profiles"]
    active_id = voice_profiles.get("activeProfileId") or profiles[0]["id"]
    active = next((p for p in profiles if p.get("id") == active_id), profiles[0])
    baby = next((p for p in profiles if p.get("id") == "baby"), None)

    def extras(profile: dict) -> list[str]:
        return [t for t in (profile.get("blocklist") or []) if t not in BASE_BLOCKLIST]

    payload = {
        "finance": {
            "display_name": "Finance",
            "voice_key": check_voice_key(active["id"]),
            "script_prompt": active["prompt"],
            "extra_blocklist": extras(active),
        }
    }

    if baby:
        payload["kids"] = {
            "display_name": "Kids",
            "voice_key": check_voice_key("baby"),
            "script_prompt": baby["prompt"],
            "extra_blocklist": extras(baby),
        }

    return payload


async def main() -> None:
    voice_profiles = await db.get_config("voice_profiles")
    payload = build_channels_payload(voice_profiles)
    await db.set_config(CONFIG_KEY, payload)
    print(f"wrote {CONFIG_KEY}: {', '.join(sorted(payload))}")


BUILT_IN_CHANNELS: dict[str, dict] = {
    "history": {
        "display_name": "History, Explained",
        "voice_key": "news",
        "script_prompt": (
            "You are a measured documentary narrator for a history channel. "
            "Explain what happened, how, and why it mattered, in plain vivid language. "
            "State dates and claims only as supported by the evidence; say plainly "
            "when something is uncertain or disputed instead of smoothing it over. "
            "No present-day moralizing, no extremist glorification, no invented "
            "dialogue presented as fact."
        ),
        "extra_blocklist": [],
    },
    "science": {
        "display_name": "Science & Space",
        "voice_key": "adult_female",
        "script_prompt": (
            "You are a curious, warm explainer of space, physics, and nature for "
            "a general audience. Lead with mechanisms over marvels: how it works, "
            "then why it matters. Never give medical or financial advice, never "
            "promise outcomes, never use miracle language."
        ),
        "extra_blocklist": ["miracle cure", "guaranteed cure", "doctors hate"],
    },
    "mystery": {
        "display_name": "Mysteries & True Crime",
        "voice_key": "adult_male",
        "script_prompt": (
            "You are a sober case-driven narrator for a mystery channel. Lay out "
            "what is known, what is disputed, and what remains unknown. Living "
            "persons are alleged until convicted. Never detail a method an "
            "imitator could use, never glorify a perpetrator, and keep victim "
            "dignity above spectacle in every line."
        ),
        "extra_blocklist": ["how to kill", "graphic autopsy", "glorify the killer"],
    },
}


def ensure_builtin_channels(existing: dict | None) -> dict:
    """Return existing plus every missing built-in channel, validated.

    Present ids are returned untouched (same object values, stable order:
    existing first, additions appended). Raises ValueError on any invalid
    built-in entry — a bad default must fail the seed, never ship.
    """
    merged = dict(existing or {})
    for channel_id, entry in BUILT_IN_CHANNELS.items():
        if channel_id in merged:
            continue
        for field in ("display_name", "voice_key", "script_prompt"):
            if not entry.get(field) or not str(entry[field]).strip():
                raise ValueError(f"built-in channel {channel_id!r} is missing {field!r}")
        merged[channel_id] = {
            "display_name": entry["display_name"],
            "voice_key": check_voice_key(entry["voice_key"]),
            "script_prompt": entry["script_prompt"],
            "extra_blocklist": [t for t in entry.get("extra_blocklist", [])
                                if t not in BASE_BLOCKLIST],
        }
    return merged


async def ensure_main() -> None:
    """Add missing built-in channels to the live row. Writes only on change."""
    from app.channels import CONFIG_KEY

    existing = await db.get_config(CONFIG_KEY) or {}
    merged = ensure_builtin_channels(existing)
    added = [cid for cid in merged if cid not in existing]
    if not added:
        print(f"{CONFIG_KEY}: already complete ({', '.join(sorted(existing))})")
        return
    await db.set_config(CONFIG_KEY, merged)
    print(f"{CONFIG_KEY}: added {', '.join(added)}; existing entries untouched")


if __name__ == "__main__":
    # psycopg's async pool cannot run on the ProactorEventLoop, Python's default
    # on Windows, and times out after 30s with "Psycopg cannot use the
    # 'ProactorEventLoop' to run in async mode". run_worker.py documents the same
    # problem; an explicit loop_factory is what works.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    if len(sys.argv) > 1 and sys.argv[1] == "ensure":
        asyncio.run(ensure_main(), loop_factory=loop_factory)
    else:
        asyncio.run(main(), loop_factory=loop_factory)
