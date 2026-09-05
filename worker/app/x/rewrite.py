"""Manual X/Twitter assistant: rewrite stories into posts and suggest replies."""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

from app import db
from app.llm import providers
from app.x import client

log = structlog.get_logger()

MAX_POST_LENGTH = client.MAX_TWEET_LENGTH
MAX_LONG_POST_LENGTH = 4000

DEFAULT_TONE = "analyst-educator: clear, curious, never promotional"

REWRITE_SYSTEM_PROMPT = """You are the voice of a finance education X account.

Rewrite the provided news into a single, compelling X post.

Rules:
- One sentence or two short sentences.
- No hashtags unless they add real value.
- Explain what happened and why it matters.
- Stay under 280 characters.
- Match the requested tone.

Return ONLY the post text. No markdown, no quotes around it, no explanation."""

REWRITE_LONG_SYSTEM_PROMPT = """You are the voice of a finance education X account writing a long-form post.

Rewrite the provided news into an essay-style post for readers who want depth.

Rules:
- Open with a one-line hook.
- Then 3 to 5 short paragraphs: what happened, why it matters, the mechanics underneath, what to watch next.
- Close with one genuine open-ended question.
- Plain text only: no markdown, no headers, no hashtags unless they add real value.
- Match the requested tone.

Return ONLY the post text. No quotes around it, no explanation."""

REPLY_SYSTEM_PROMPT = """You are the same finance education X account replying to a comment.

Rules:
- Keep it under 280 characters.
- Be helpful, concise, and on-brand.
- Match the tone of the original post.

Return ONLY the reply text. No markdown, no quotes, no explanation."""


class RewriteError(ValueError):
    """The story could not be rewritten into a compliant post."""


async def _fetch_story_with_items(story_id: uuid.UUID) -> dict[str, Any]:
    pool = await db.get_pool()
    async with pool.connection() as conn:
        story = await db._fetchone(
            conn,
            "SELECT id, headline FROM stories WHERE id = %s",
            story_id,
        )
        if story is None:
            raise RewriteError(f"story {story_id} not found")
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


async def _llm_call(system: str, user: str) -> str:
    """Call the configured text provider asynchronously."""
    provider_name = os.environ.get("X_REWRITE_PROVIDER", "deepseek").strip().lower()
    provider = providers.PROVIDERS.get(provider_name)
    if provider is None:
        raise RewriteError(f"provider {provider_name!r} is not configured")
    api_key = os.environ.get(provider.env_key, "").strip()
    if not api_key:
        raise RewriteError(f"{provider.env_key} is not set")
    return await provider.call(system, user)


async def rewrite_story_to_post(
    story_id: uuid.UUID,
    *,
    tone: str | None = None,
    length: str = "short",
) -> str:
    if length not in ("short", "long"):
        raise RewriteError(f"unknown post length {length!r}; expected 'short' or 'long'")
    story = await _fetch_story_with_items(story_id)
    items_text = "\n".join(
        f"- {item['title']} ({item['source_name']})" for item in story["items"]
    ) or "(no linked sources)"

    user_prompt = f"""Tone: {tone or DEFAULT_TONE}

Headline: {story['headline']}

Linked sources:
{items_text}

Write the X post."""

    text = await _llm_call(
        REWRITE_LONG_SYSTEM_PROMPT if length == "long" else REWRITE_SYSTEM_PROMPT,
        user_prompt,
    )
    text = text.strip().strip('"').strip("'")

    cap = MAX_LONG_POST_LENGTH if length == "long" else MAX_POST_LENGTH
    if len(text) > cap:
        raise RewriteError(
            f"provider returned {len(text)} characters; max is {cap}"
        )

    return text


async def suggest_reply(
    comment_text: str,
    *,
    post_context: str | None = None,
    tone: str | None = None,
) -> str:
    if not comment_text or not comment_text.strip():
        raise RewriteError("comment text is required")

    context = f"Original post:\n{post_context}\n\n" if post_context else ""
    user_prompt = f"""Tone: {tone or DEFAULT_TONE}

{context}Comment to reply to:
{comment_text}

Write a reply."""

    text = await _llm_call(REPLY_SYSTEM_PROMPT, user_prompt)
    text = text.strip().strip('"').strip("'")

    if len(text) > MAX_POST_LENGTH:
        raise RewriteError(
            f"provider returned {len(text)} characters; max is {MAX_POST_LENGTH}"
        )

    return text
