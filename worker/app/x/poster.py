"""Manual X/Twitter assistant: generate educational infographic posters."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from app import db
from app.llm import providers

MAX_BULLET_LENGTH = 120
# A summary shorter than this is almost certainly a broken extraction, not a
# stylistic choice. There is deliberately no upper word cap: overlong summaries
# are trimmed to fit the poster instead of failing the whole generation.
MIN_SUMMARY_WORDS = 40
MAX_SUMMARY_CHARS = 900
MAX_SECTIONS = 6
MAX_BULLETS_PER_SECTION = 5

DEFAULT_STYLE = "light"

POSTER_SYSTEM_PROMPT = """You are a finance-education infographic designer.

Your job is to turn the provided source material into a structured educational poster.

Rules:
- Return ONLY a valid JSON object. No markdown, no explanation, no code fences.
- The JSON must match this exact schema:
  {
    "title": "string (max 60 chars)",
    "subtitle": "string (max 90 chars)",
    "summary": "string (one or two short paragraphs, 60 to 120 words total)",
    "sections": [
      {
        "heading": "string (max 40 chars)",
        "bullets": ["string (max 120 chars each)", ...]
      }
    ],
    "footer": "string (max 120 chars)"
  }
- summary is REQUIRED and must never be empty. It is one or two short prose paragraphs (60 to 120 words in total, a short read) that retell the news item itself: what happened, which companies and people, when, the numbers, and the outcome. Write it so a reader who has not seen the article understands the story from the summary alone. It is a summary, not advice, and it is not a list.
- Produce 3 to 5 additional sections after the summary. Each section must have exactly 5 bullets, or 4 if there is genuinely nothing more to say.
- When the input is a news story, base the poster on the article text. Do not replace the story with generic advice.
- Keep one section focused on the advisory/disclaimer, and put it last.
- Keep language clear and educational. Indian finance context is fine.
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
            SELECT i.title, i.full_text, src.name AS source_name
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


def _extract_json(text: str) -> dict[str, Any]:
    """Find the first JSON object in the text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise PosterError("provider did not return JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PosterError(f"provider returned invalid JSON: {exc}") from exc


def _trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """Trim text to at most max_chars, ending at a sentence boundary when one
    is available so the summary never stops mid-word or mid-clause."""
    cut = text[:max_chars]
    boundary = max(cut.rfind(". "), cut.rfind(".\n"))
    if boundary >= max_chars * 0.6:
        return cut[: boundary + 1].strip()
    word_end = cut.rfind(" ")
    return (cut[:word_end] if word_end > 0 else cut).strip()


def _validate_and_trim(poster: dict[str, Any]) -> dict[str, Any]:
    """Validate the poster schema and trim overlong fields."""
    if not isinstance(poster, dict):
        raise PosterError("provider returned non-object JSON")

    title = str(poster.get("title", "")).strip()
    subtitle = str(poster.get("subtitle", "")).strip()
    footer = str(poster.get("footer", "")).strip()
    summary = poster.get("summary", [])
    sections = poster.get("sections", [])

    if not title:
        raise PosterError("poster missing title")

    # Providers drift between a paragraph and a bullet list. Accept either and
    # normalise to the paragraph the poster renders, so a list-shaped response
    # is not silently dropped into an empty "At a Glance" box.
    if isinstance(summary, list):
        summary = "\n\n".join(str(b).strip() for b in summary if str(b).strip())
    # Collapse runs of whitespace inside each paragraph but keep the blank-line
    # breaks between up to two paragraphs, so the poster renders them as
    # separate blocks instead of one run-on wall of text.
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n+", str(summary or ""))]
    clean_summary = "\n\n".join(p for p in paragraphs if p)
    if not clean_summary:
        raise PosterError("poster missing summary")
    if len(clean_summary) > MAX_SUMMARY_CHARS:
        clean_summary = _trim_to_sentence_boundary(clean_summary, MAX_SUMMARY_CHARS)
    word_count = len(clean_summary.split())
    if word_count < MIN_SUMMARY_WORDS:
        raise PosterError(f"summary must contain at least {MIN_SUMMARY_WORDS} words")

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
        "summary": clean_summary,
        "sections": trimmed_sections,
        "footer": footer[:160] or "For educational purposes only. Not financial advice.",
    }


def _render_user_prompt(headline: str, items: list[dict[str, Any]], style: str) -> str:
    def _format_item(item: dict[str, Any]) -> str:
        title = item.get("title") or "(no title)"
        source = item.get("source_name") or "unknown source"
        body = (item.get("full_text") or "").strip()
        if body:
            # Keep the prompt bounded; very long articles are truncated.
            body = body[:2500]
            return f"Source: {title} ({source})\nArticle text:\n{body}"
        return f"Source: {title} ({source})\n(no article text available)"

    items_text = "\n\n---\n\n".join(_format_item(item) for item in items) or "(no linked sources)"

    return f"""Style: {style}

Story headline: {headline}

Linked sources and their article text:
{items_text}

Turn this into an educational infographic poster as JSON. Base the poster on the article text above. Include the key facts, names, numbers, and events from the news. The last section should be the disclaimer/advisory."""


async def generate_poster_from_story(
    story_id: uuid.UUID,
    *,
    style: str | None = None,
) -> dict[str, Any]:
    story = await _fetch_story_with_items(story_id)
    user_prompt = _render_user_prompt(story["headline"], story["items"], style or DEFAULT_STYLE)

    raw = await _llm_call(POSTER_SYSTEM_PROMPT, user_prompt)
    poster = _validate_and_trim(_extract_json(raw))
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
    return {**poster, "style": style or DEFAULT_STYLE}
