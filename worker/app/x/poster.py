"""Manual X/Twitter assistant: generate educational infographic posters."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from app import db
from app.channels import BASE_BLOCKLIST
from app.llm import providers

MAX_BULLET_LENGTH = 120
MAX_SECTIONS = 6
MAX_BULLETS_PER_SECTION = 4

DEFAULT_STYLE = "light"

POSTER_SYSTEM_PROMPT = """You are a finance-education infographic designer.

Your job is to turn the provided source material into a structured educational poster.

Rules:
- Return ONLY a valid JSON object. No markdown, no explanation, no code fences.
- The JSON must match this exact schema:
  {
    "title": "string (max 60 chars)",
    "subtitle": "string (max 90 chars)",
    "sections": [
      {
        "heading": "string (max 40 chars)",
        "bullets": ["string (max 120 chars each)", ...]
      }
    ],
    "footer": "string (max 120 chars)"
  }
- Produce 4 to 6 sections. Each section should have 2 to 4 bullets.
- Focus on explaining the concept, not giving advice. Never say buy, sell, hold, target price, or multibagger.
- Keep language clear and educational. Indian finance context is fine.
- If the input is a news story, extract the educational angle: what happened, why it matters, what to watch.
- If the input is a topic + bullet points, restructure and polish the bullets into the poster format.
- The footer must include a disclaimer like "For educational purposes only. Not financial advice."

Return only the JSON object."""


class PosterError(ValueError):
    """The poster could not be generated."""


async def _llm_call(system: str, user: str) -> str:
    """Call the configured text provider asynchronously."""
    provider_name = os.environ.get("X_REWRITE_PROVIDER", "deepseek").strip().lower()
    provider = providers.PROVIDERS.get(provider_name)
    if provider is None:
        raise PosterError(f"provider {provider_name!r} is not configured")
    api_key = os.environ.get(provider.env_key, "").strip()
    if not api_key:
        raise PosterError(f"{provider.env_key} is not set")
    return await provider.call(system, user)


async def _fetch_story_with_items(story_id: uuid.UUID) -> dict[str, Any]:
    pool = await db.get_pool()
    async with pool.connection() as conn:
        story = await db._fetchone(
            conn,
            "SELECT id, headline FROM stories WHERE id = %s",
            story_id,
        )
        if story is None:
            raise PosterError(f"story {story_id} not found")
        items = await db._fetchall(
            conn,
            """
            SELECT i.title, src.name AS source_name
              FROM items i
              JOIN story_items si ON i.id = si.item_id
              JOIN sources src ON i.source_id = src.id
             WHERE si.story_id = %s
             ORDER BY i.published_at DESC
             LIMIT 5
            """,
            story_id,
        )
    return {"headline": story["headline"], "items": items or []}


def _check_compliance(text: str) -> None:
    lowered = text.lower()
    blocked = [term for term in BASE_BLOCKLIST if term.lower() in lowered]
    if blocked:
        raise PosterError(
            f"generated poster contains blocked term(s): {', '.join(blocked)}"
        )


def _extract_json(text: str) -> dict[str, Any]:
    """Find the first JSON object in the text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise PosterError("provider did not return JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PosterError(f"provider returned invalid JSON: {exc}") from exc


def _validate_and_trim(poster: dict[str, Any]) -> dict[str, Any]:
    """Validate the poster schema and trim overlong fields."""
    if not isinstance(poster, dict):
        raise PosterError("provider returned non-object JSON")

    title = str(poster.get("title", "")).strip()
    subtitle = str(poster.get("subtitle", "")).strip()
    footer = str(poster.get("footer", "")).strip()
    sections = poster.get("sections", [])

    if not title:
        raise PosterError("poster missing title")
    if not isinstance(sections, list) or not sections:
        raise PosterError("poster missing sections")
    if len(sections) > MAX_SECTIONS:
        sections = sections[:MAX_SECTIONS]

    trimmed_sections = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading", "")).strip()
        bullets = section.get("bullets", [])
        if not isinstance(bullets, list):
            bullets = []
        clean_bullets = [
            str(b).strip()[:MAX_BULLET_LENGTH]
            for b in bullets
            if str(b).strip()
        ][:MAX_BULLETS_PER_SECTION]
        if heading and clean_bullets:
            trimmed_sections.append({"heading": heading[:60], "bullets": clean_bullets})

    if not trimmed_sections:
        raise PosterError("poster has no valid sections")

    return {
        "title": title[:80],
        "subtitle": subtitle[:120],
        "sections": trimmed_sections,
        "footer": footer[:160] or "For educational purposes only. Not financial advice.",
    }


def _render_user_prompt(headline: str, items: list[dict[str, Any]], style: str) -> str:
    items_text = "\n".join(
        f"- {item['title']} ({item['source_name']})" for item in items
    ) or "(no linked sources)"

    return f"""Style: {style}

Story headline: {headline}

Linked sources:
{items_text}

Turn this into an educational infographic poster as JSON."""


async def generate_poster_from_story(
    story_id: uuid.UUID,
    *,
    style: str | None = None,
) -> dict[str, Any]:
    story = await _fetch_story_with_items(story_id)
    user_prompt = _render_user_prompt(story["headline"], story["items"], style or DEFAULT_STYLE)

    raw = await _llm_call(POSTER_SYSTEM_PROMPT, user_prompt)
    poster = _validate_and_trim(_extract_json(raw))
    _check_compliance(json.dumps(poster))
    return {**poster, "style": style or DEFAULT_STYLE}


async def generate_poster_from_text(
    topic: str,
    bullets: list[str],
    *,
    style: str | None = None,
) -> dict[str, Any]:
    if not topic or not topic.strip():
        raise PosterError("topic is required")

    bullets_text = "\n".join(f"- {b}" for b in bullets if b.strip()) or "(no bullets provided)"
    user_prompt = f"""Style: {style or DEFAULT_STYLE}

Topic: {topic}

Raw bullet points:
{bullets_text}

Turn this into an educational infographic poster as JSON."""

    raw = await _llm_call(POSTER_SYSTEM_PROMPT, user_prompt)
    poster = _validate_and_trim(_extract_json(raw))
    _check_compliance(json.dumps(poster))
    return {**poster, "style": style or DEFAULT_STYLE}
