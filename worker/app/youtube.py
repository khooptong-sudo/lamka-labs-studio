"""YouTube video automation pipeline (Path B)."""
import html
import os
import re
import subprocess
import uuid
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import structlog

from app import db, gpu
from app.audit import audit_log
from app.channels import Channel
from app.reddit_rights import credit_suffix, split_usable
from app.scene3d.backend import (
    MIN_VERIFIED_FRAMES,
    build_3d_frames,
    build_cinematic_frames,
)
from app.script_quality import (
    MAX_ACT_SCENES,
    MAX_DOC_SCENES,
    MIN_ACT_SCENES,
    MIN_DOC_SCENES,
    fact_check_script,
    validate_script_structure,
)
from app.settings import get_settings
from app.storyboard import (
    Frame,
    Storyboard,
    assign_timing,
    attach_audio,
    parse_storyboard,
    prune_stale_assets,
    render_index_html,
)

log = structlog.get_logger()
settings = get_settings()

VIDEOS_DIR = Path(os.environ.get("VIDEOS_DIR", "../videos")).resolve()

# Above this share of fallback title cards the video no longer represents the
# story, so generation aborts instead of producing something publishable.
MAX_PLACEHOLDER_RATIO = float(os.environ.get("MAX_PLACEHOLDER_RATIO", "0.25"))

# Narration carries the explainer, so the bar is stricter than for visuals: a
# quarter of a video can survive fallback cards, but not a quarter in silence.
MAX_SILENT_RATIO = float(os.environ.get("MAX_SILENT_RATIO", "0.2"))

# A real explainer opens, develops and closes. Anything shorter than this is a
# truncated script rather than a video, and the ratio guards below cannot catch
# it: one good frame out of one is a perfect score.
MIN_SCRIPT_FRAMES = int(os.environ.get("MIN_SCRIPT_FRAMES", "3"))

# 503 UNAVAILABLE from Gemini is routine and clears in seconds.
SCRIPT_MAX_ATTEMPTS = int(os.environ.get("SCRIPT_MAX_ATTEMPTS", "4"))

# An unbounded HyperFrames render wedges the GPU slot forever. Bound the wait
# and fail the job loud on expiry (default 20 minutes).
HYPERFRAMES_TIMEOUT_SECONDS = float(os.environ.get("HYPERFRAMES_TIMEOUT_SECONDS", "1200"))

# A bare `npx hyperframes` re-resolves the newest release on every render and
# downloads it if the cache is cold, so a fresh publish (or a failed download)
# breaks rendering with no code change. Pin the version and let npx take the
# install prompt non-interactively.
HYPERFRAMES_VERSION = os.environ.get("HYPERFRAMES_VERSION", "0.8.30")

MAX_VOICE_CLIP_BYTES = 8 * 1024 * 1024
MAX_VOICE_CLIPS = 40


def is_mp3_bytes(data: bytes) -> bool:
    """True when bytes are already MP3: ID3 header or frame-sync word."""
    if data[:3] == b"ID3":
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


async def _ingest_voice_clips(board, video_dir: Path, clip_paths: list[Path]) -> None:
    """Stage owner narration onto each frame's voice path. Raises, never substitutes.

    Clips match scenes by order. MP3 bytes land directly; anything else is
    normalized through ffmpeg (extension never trusted). Probing happens later
    in the shared attach_audio step.
    """
    if len(clip_paths) != len(board.frames):
        raise ValueError(f"expected {len(board.frames)} voice clips, got {len(clip_paths)}")
    voice_dir = video_dir / "assets" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    for frame, source in zip(board.frames, clip_paths):
        size = source.stat().st_size
        if size == 0:
            raise ValueError(f"voice clip for scene {frame.index} is empty")
        if size > MAX_VOICE_CLIP_BYTES:
            raise ValueError(
                f"voice clip for scene {frame.index} exceeds {MAX_VOICE_CLIP_BYTES} bytes"
            )
        destination = video_dir / frame.voice_filename
        raw = source.read_bytes()
        if is_mp3_bytes(raw):
            destination.write_bytes(raw)
            continue
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source), str(destination)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _get_youtube_credentials(scopes: list[str]) -> Any:
    """
    Load and refresh OAuth credentials for the YouTube Data API.
    Looks for an existing token at FCE_YOUTUBE_TOKEN_PATH. If the token is
    expired but has a refresh token, it refreshes and rewrites the file.
    Raises a clear RuntimeError if no credentials are available.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = settings.youtube_token_path
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")

    if not creds or not creds.valid:
        raise RuntimeError(
            "YouTube OAuth credentials are missing or invalid. "
            f"Run the OAuth flow to create {token_path} "
            f"(e.g., `python worker/test_youtube_upload.py`)."
        )

    return creds


async def _stage(job_id, stage: str, done: int = 0, total: int = 0) -> None:
    """Report progress when a job is tracking this run, otherwise do nothing.

    Progress is optional so the original synchronous entrypoint — and every
    test that drives it — keeps working untouched.
    """
    if job_id is None:
        return
    from app.jobs import set_stage

    try:
        await set_stage(job_id, stage, done, total)
    except Exception as exc:  # noqa: BLE001
        # Losing a progress update must never abort a render that is otherwise fine.
        log.warning("stage_update_failed", stage=stage, error=str(exc))


async def generate_youtube_video(
    story_id: uuid.UUID,
    channel_id: str,
    upload_preference: str = "manual",
    backend: str | None = None,
    job_id: uuid.UUID | None = None,
    storyboard_override: str | None = None,
    image_provider: str | None = None,
    motion: str | None = None,
    voice_key: str | None = None,
    cinematic_controls: dict[str, str] | None = None,
    voice_clip_paths: list[Path] | None = None,
    *,
    documentary: bool = False,
    brief: str | None = None,
) -> uuid.UUID | None:
    """
    Main entrypoint for generating a YouTube video from a story.
    Triggered via GUI dashboard.

    `backend` selects the frame backend for this run only, so one worker can
    produce both formats without an env change or a restart; `FRAME_BACKEND`
    supplies the default. `job_id`, when given, receives stage progress.

    `upload_preference` is recorded on the draft row for provenance only. It
    once chose between "review first" and "upload now"; the publish path is
    gone, so every generated draft is now recorded as pending regardless.
    """
    log.info("youtube_generation_started", story_id=str(story_id), channel_id=channel_id)

    from app import channels
    channel = await channels.resolve(channel_id)
    if voice_key:
        if voice_key not in VOICE_MAP:
            raise ValueError(f"unknown voice key {voice_key!r}; expected one of {sorted(VOICE_MAP)}")
        channel = replace(channel, voice_key=voice_key)

    # 1. Fetch story details
    story = await _fetch_story_details(story_id)
    if not story:
        log.error("story_not_found", story_id=str(story_id))
        return None
        
    slug = f"story-{story_id}"
    video_dir = VIDEOS_DIR / slug
    video_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Scripting & Storyboard Generation
    await _stage(job_id, "script")
    if documentary:
        from app import documentary as doc

        if storyboard_override and storyboard_override.strip():
            script_content = _ensure_storyboard_metadata(
                storyboard_override,
                fallback_title=str(story.get("headline") or "Manual storyboard"),
            )
            violations = validate_script_structure(
                script_content, min_scenes=MIN_DOC_SCENES, max_scenes=MAX_DOC_SCENES,
            )
            if violations:
                log.error(
                    "youtube_generation_aborted",
                    reason="documentary_contract_failed",
                    story_id=str(story_id),
                    violations=violations,
                )
                return None
        else:
            if not (story.get("items") or (brief or "").strip()):
                log.error(
                    "youtube_generation_aborted",
                    reason="documentary_needs_evidence",
                    story_id=str(story_id),
                )
                return None
            try:
                items = _research_items(story, max_sources=12)
                drafter = doc.drafter_provider()
                outline = await doc.plan_outline(
                    headline=str(story.get("headline") or "Untitled"),
                    packet=_render_packet(items),
                    provider=drafter,
                    n_sources=len(items),
                )
                dealt = doc.deal_sources(items, len(outline.acts))
                act_markdowns = []
                first_scene = 1
                recap = ""
                for index, act in enumerate(outline.acts):
                    bundle = _render_packet(dealt[index])
                    if brief and brief.strip():
                        bundle = (
                            "OWNER BRIEF (context, not sourced fact — "
                            "dispute claims are FLAG, not BLOCK):\n"
                            f"{brief.strip()}\n\n{bundle}"
                        )
                    text = await doc.generate_act(
                        act=act, act_index=index, n_acts=len(outline.acts),
                        first_scene=first_scene, recap=recap, bundle_text=bundle,
                        channel_prompt=channel.script_prompt, provider=drafter,
                        want_hook=index == 0,
                        want_closing=index == len(outline.acts) - 1,
                    )
                    violations = validate_script_structure(
                        text, min_scenes=MIN_ACT_SCENES, max_scenes=MAX_ACT_SCENES,
                        require_hook=index == 0,
                        require_closing=index == len(outline.acts) - 1,
                    )
                    if violations:
                        raise ValueError(
                            f"act {index + 1} failed contract: {'; '.join(violations)}"
                        )
                    verdict = await fact_check_script(
                        script=text, evidence_packet=bundle, exclude=(drafter,),
                    )
                    if verdict.get("verdict") == "BLOCK":
                        await audit_log(
                            actor="worker", action="script_fact_check_blocked",
                            entity=str(story_id), entity_type="story",
                            after={"violations": verdict.get("violations", []),
                                   "act": index + 1},
                        )
                        log.error(
                            "youtube_generation_aborted", reason="fact_check_blocked",
                            story_id=str(story_id), act=index + 1,
                            violations=verdict.get("violations", []),
                        )
                        return None
                    if verdict.get("verdict") == "FLAG":
                        log.warning(
                            "script_fact_check_flagged",
                            story_id=str(story_id), act=index + 1,
                        )
                    recap = doc.last_voiceover(text)[-doc.RECAP_CHARS:]
                    act_markdowns.append(text)
                    first_scene += len(parse_storyboard(text).frames)
                script_content = doc.merge_acts(act_markdowns)
                script_content = _append_research_sources(script_content, story)
                violations = validate_script_structure(
                    script_content, min_scenes=MIN_DOC_SCENES, max_scenes=MAX_DOC_SCENES,
                )
                if violations:
                    raise ValueError(
                        f"merged board failed contract: {'; '.join(violations)}"
                    )
            except Exception as e:
                log.error(
                    "youtube_generation_aborted", reason="documentary_act_failed",
                    story_id=str(story_id), error=str(e)[:200],
                )
                return None
    elif storyboard_override and storyboard_override.strip():
        # A valid editor board stays byte-for-byte intact. If it was pasted in
        # a human-friendly outline form, add only the required upload metadata
        # so title/description validation cannot reject its scenes or narration.
        script_content = _ensure_storyboard_metadata(
            storyboard_override,
            fallback_title=str(story.get("headline") or "Manual storyboard"),
        )
        log.info("youtube_storyboard_override_used", story_id=str(story_id))
    else:
        try:
            script_content = await _generate_script_for_story(
                story, channel, cinematic=(backend == "cinematic")
            )
            # Generated boards retain the exact links that constrained the
            # model. A pasted, editor-reviewed board is intentionally left
            # untouched, just as before.
            script_content = _append_research_sources(script_content, story)
            structure_violations = validate_script_structure(script_content)
            if structure_violations:
                log.error(
                    "youtube_generation_aborted",
                    reason="script_contract_failed",
                    story_id=str(story_id),
                    violations=structure_violations,
                )
                return None
            await _stage(job_id, "fact_check")
            drafter = os.environ.get("SCENE_MODEL_PROVIDER", "gemini").lower()
            evidence_packet = _research_packet(story)
            try:
                verdict = await fact_check_script(
                    script=script_content,
                    evidence_packet=evidence_packet,
                    exclude=(drafter,),
                )
            except Exception as e:
                log.error(
                    "youtube_generation_aborted",
                    reason="fact_check_failed",
                    story_id=str(story_id),
                    error=str(e),
                )
                return None
            if verdict.get("verdict") == "BLOCK":
                await audit_log(
                    actor="worker",
                    action="script_fact_check_blocked",
                    entity=str(story_id),
                    entity_type="story",
                    after={"violations": verdict.get("violations", [])},
                )
                log.error("youtube_generation_aborted", reason="fact_check_blocked", story_id=str(story_id), violations=verdict.get("violations", []))
                return None
            if verdict.get("verdict") == "FLAG":
                await audit_log(
                    actor="worker",
                    action="script_fact_check_flagged",
                    entity=str(story_id),
                    entity_type="story",
                    after={"violations": verdict.get("violations", [])},
                )
                log.warning("script_fact_check_flagged", story_id=str(story_id))
        except Exception as e:
            log.error("youtube_generation_aborted", reason="script_generation_failed", error=str(e))
            return None

    script_content = _apply_cinematic_controls(script_content, cinematic_controls)

    storyboard_path = video_dir / "STORYBOARD.md"
    storyboard_path.write_text(script_content, encoding="utf-8")

    # Validate upload metadata before any frame building or rendering. A script
    # with a missing/empty title or description must abort here, not after
    # burning the entire HyperFrames/ffmpeg render.
    frontmatter = _parse_storyboard_frontmatter(storyboard_path)
    title, description, tags = _require_metadata(frontmatter, channel.effective_blocklist)

    # 3. Storyboard compilation (voice first, visuals second)
    #
    # Narration is generated per frame so each frame's on-screen duration can be
    # derived from its own measured audio. A single concatenated mp3 leaves no
    # per-frame timing to key visuals off, which is why this pipeline used to
    # fall back to a static placeholder card.
    board = parse_storyboard(script_content)
    if len(board.frames) < MIN_SCRIPT_FRAMES:
        # Too short to be the story, and every later guard is a ratio: they read
        # a one-frame script as a flawless video.
        log.error(
            "youtube_generation_aborted",
            reason="script_too_short",
            story_id=str(story_id),
            frames=len(board.frames),
            minimum=MIN_SCRIPT_FRAMES,
        )
        return None

    using_owner_voice = voice_clip_paths is not None
    if using_owner_voice:
        if len(voice_clip_paths) > MAX_VOICE_CLIPS:
            log.error(
                "youtube_generation_aborted",
                reason="too_many_voice_clips",
                story_id=str(story_id),
                clips=len(voice_clip_paths),
                maximum=MAX_VOICE_CLIPS,
            )
            return None
        if voice_key:
            log.info("youtube_owner_voice_ignores_voice_key", story_id=str(story_id))
        log.info("youtube_audio_owner_voice", video_dir=str(video_dir), frames=len(board.frames))
        await _stage(job_id, "narration", 0, len(board.frames))
        try:
            await _ingest_voice_clips(board, video_dir, voice_clip_paths)
        except Exception as e:
            log.error(
                "youtube_generation_aborted",
                reason="voice_clip_rejected",
                story_id=str(story_id),
                error=str(e)[:200],
            )
            return None
    else:
        log.info("youtube_audio_generation_started", video_dir=str(video_dir), frames=len(board.frames))
        await _stage(job_id, "narration", 0, len(board.frames))
        silenced = await _generate_frame_audio(
            board,
            video_dir,
            script_content,
            voice_key=channel.voice_key,
        )
        if silenced:
            # Silence renders and validates exactly like narration, so nothing
            # downstream notices. A mostly-mute explainer is not the video the story
            # asked for; refuse it here rather than publish it.
            ratio = len(silenced) / len(board.frames)
            log.error(
                "narration_degraded",
                story_id=str(story_id),
                silenced=len(silenced),
                frames=len(board.frames),
                slugs=silenced,
            )
            if ratio > MAX_SILENT_RATIO:
                log.error("youtube_generation_aborted", reason="too_many_silent_frames")
                return None

    prune_stale_assets(board, video_dir)
    attach_audio(board, video_dir)
    if using_owner_voice:
        unprobed = [frame.slug for frame in board.frames if not frame.audio_duration]
        if unprobed:
            log.error(
                "youtube_generation_aborted",
                reason="voice_clip_unprobed",
                story_id=str(story_id),
                slugs=unprobed,
            )
            return None
    assign_timing(board, board.meta.get("pacing"))

    index_html_path = video_dir / "index.html"
    index_html_path.write_text(
        render_index_html(board, with_bgm=(video_dir / "bgm.mp3").exists()),
        encoding="utf-8",
    )
    duration = board.total_duration
    log.info("storyboard_compiled", frames=len(board.frames), duration=duration)

    await _stage(job_id, "shots", 0, len(board.frames))

    async def report_frame_progress(done: int, total: int) -> None:
        await _stage(job_id, "shots", done, total)

    placeholders = await _build_frames(
        board,
        video_dir,
        backend=backend,
        image_provider=image_provider,
        motion=motion,
        on_frame_complete=report_frame_progress if job_id else None,
    )
    if placeholders:
        # A placeholder renders fine and passes validation, so nothing downstream
        # would notice that most of the video is fallback title cards. Refuse to
        # continue rather than publish that under the story's headline.
        ratio = len(placeholders) / len(board.frames)
        log.error(
            "frame_generation_degraded",
            story_id=str(story_id),
            placeholders=len(placeholders),
            frames=len(board.frames),
            slugs=placeholders,
        )
        if ratio > MAX_PLACEHOLDER_RATIO:
            log.error("youtube_generation_aborted", reason="too_many_placeholder_frames")
            return None

    verified = len(board.frames) - len(placeholders)
    if verified < MIN_VERIFIED_FRAMES:
        # Absolute, not proportional. Every ratio above reads a two-frame film
        # with one good shot as a healthy 50%, and a one-frame film as flawless.
        log.error(
            "youtube_generation_aborted",
            reason="too_few_verified_frames",
            story_id=str(story_id),
            verified=verified,
            minimum=MIN_VERIFIED_FRAMES,
        )
        return None

    package_json_path = video_dir / "package.json"
    if not package_json_path.exists():
        package_json_path.write_text(
            '{ "name": "generated-video", "private": true, "type": "module" }',
            encoding="utf-8",
        )
    
    await _stage(job_id, "render")

    motion_assembly = (
        (backend or FRAME_BACKEND).lower() == "cinematic"
        and motion not in (None, "off")
    )
    if motion_assembly:
        # Motion scenes are already normalized per-scene MP4s of exactly
        # frame.duration; one ffmpeg pass replaces the ~25-40 min
        # headless-Chrome capture and writes the same renders/video.mp4.
        from app.scene3d.assemble import assemble_motion_video

        try:
            await assemble_motion_video(
                board, video_dir, with_bgm=(video_dir / "bgm.mp3").exists()
            )
        except Exception as e:
            log.error("youtube_motion_assembly_failed", error=str(e))
            raise
        log.info("youtube_rendering_complete", renderer="ffmpeg-assemble")
    else:

        import sys
        import subprocess
        from starlette.concurrency import run_in_threadpool
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        try:
            def run_hyperframes():
                return subprocess.run(
                    [
                        npx_cmd,
                        "--yes",
                        f"hyperframes@{HYPERFRAMES_VERSION}",
                        "render",
                        "--output",
                        "renders/video.mp4",
                    ],
                    cwd=str(video_dir),
                    capture_output=True,
                    check=True,
                    timeout=HYPERFRAMES_TIMEOUT_SECONDS,
                )

            async with gpu.slot:
                proc = await asyncio.to_thread(run_hyperframes)
            log.info("youtube_rendering_complete")
        except subprocess.TimeoutExpired as e:
            log.error("youtube_rendering_failed", reason="timeout", timeout_seconds=e.timeout)
            raise Exception("youtube rendering timed out")
        except subprocess.CalledProcessError as e:
            raw = e.stderr or e.stdout or b""
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            tail = "\n".join(text.strip().splitlines()[-20:])
            log.error("youtube_rendering_failed", returncode=e.returncode, stderr=tail)
            detail = f"youtube rendering failed (exit {e.returncode})"
            if tail:
                detail = f"{detail}: {tail}"
            raise Exception(detail)
        except Exception as e:
            log.error("youtube_rendering_error", error=str(e))
            raise

    mp4_path = video_dir / "renders" / "video.mp4"

    _write_upload_txt(video_dir, channel, title, description, tags=tags)

    await _stage(job_id, "thumbnails")
    await build_thumbnail_variants(
        title=title,
        hook=(board.frames[0].voiceover if board.frames else title),
        bible=board.direction,
        video_dir=video_dir,
    )

    # 4. Local Draft Registration
    # User requested all output videos to be stored locally and NOT pushed to VPS/Cloud.
    # Nothing in this system publishes any more — uploads are performed by hand
    # from the drafts page — so a newly generated draft is always "pending".
    # `upload_preference` is still recorded on the draft row, but it no longer
    # selects a publish behaviour; there is no publish path left for it to pick.
    status = "pending"
    external_id = None

    draft_id = await _record_youtube_draft(
        story_id=story_id,
        channel_id=channel_id,
        upload_preference=upload_preference,
        file_path=str(mp4_path),
        status=status,
        external_id=external_id,
        title=title,
        description=description,
        tags=tags,
    )
    
    log.info("youtube_generation_finished", draft_id=str(draft_id))
    return draft_id

MAX_RESEARCH_SOURCES = 4
MAX_RESEARCH_EXCERPT_CHARS = 4_000


async def _reddit_rights_by_url(cur, urls: list[str]) -> dict[str, dict]:
    """Load reddit rights for story urls in one query (Task 2 gate)."""
    if not urls:
        return {}
    await cur.execute(
        "SELECT post_url, state, author, subreddit FROM reddit_rights WHERE post_url = ANY(%s)",
        (urls,),
    )
    return {r["post_url"]: r for r in await cur.fetchall()}


async def _apply_reddit_rights_gate(cur, rows: list[dict]) -> list[dict]:
    """Drop ungranted reddit items from story evidence (granted-only rule).

    Non-reddit rows always pass. Reddit rows pass only with a `granted`
    right; anything else (candidate, sent, denied, expired, review, or no
    rights row at all) is held out of the script with a log line. Surviving
    reddit rows carry their author/subreddit for credit downstream.
    """
    reddit_urls = [
        r.get("url") for r in rows
        if r.get("source_kind") == "reddit" and r.get("url")
    ]
    if not reddit_urls:
        return rows
    rights = await _reddit_rights_by_url(cur, reddit_urls)
    probes = [
        {"kind": ("reddit" if r.get("source_kind") == "reddit" else "other"),
         "url": r.get("url")}
        for r in rows
    ]
    _, held = split_usable(probes, {u: rights.get(u, {}).get("state") for u in reddit_urls})
    if held:
        held_urls = sorted({h["url"] for h in held})
        log.info("reddit_items_held", held_urls=held_urls, held_count=len(held_urls))
        rows = [r for r in rows if r.get("url") not in set(held_urls)]
    for r in rows:
        if r.get("source_kind") == "reddit":
            right = rights.get(r.get("url")) or {}
            if str(right.get("author") or "").strip():
                r["author"] = right["author"]
            if str(right.get("subreddit") or "").strip():
                r["subreddit"] = right["subreddit"]
    return rows


async def _fetch_story_details(story_id: uuid.UUID) -> dict | None:
    """Load the selected story with the source material that formed it.

    The inbox is an editorial decision point, not a permission slip for a
    headline-only model call.  A generated finance script therefore receives
    the same linked articles the editor reviewed.  Manual ideas deliberately
    return an empty item list; the generation guard below asks for a reviewed
    storyboard or source-backed story instead of inventing timely facts.
    """
    pool = await db.get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, headline, channel_id, created_at FROM stories WHERE id = %s",
                (story_id,),
            )
            row = await cur.fetchone()
            if row:
                await cur.execute(
                    """
                    SELECT i.title, i.url, i.published_at, i.full_text, s.name AS source_name,
                           s.kind AS source_kind
                    FROM items i
                    JOIN story_items si ON si.item_id = i.id
                    JOIN sources s ON s.id = i.source_id
                    WHERE si.story_id = %s
                    ORDER BY i.published_at DESC
                    """,
                    (story_id,),
                )
                row["items"] = await _apply_reddit_rights_gate(cur, await cur.fetchall())
                return row
    return None


def _research_items(story: dict, max_sources: int = MAX_RESEARCH_SOURCES) -> list[dict]:
    """Return a small, clean, bounded evidence set for one selected story."""
    items: list[dict] = []
    seen_urls: set[str] = set()
    for raw in story.get("items") or []:
        url = str(raw.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        text = " ".join(str(raw.get("full_text") or "").split())
        item = {
            "title": str(raw.get("title") or "Untitled source").strip(),
            "url": url,
            "source_name": str(raw.get("source_name") or "Source").strip(),
            "published_at": raw.get("published_at"),
            "excerpt": text[:MAX_RESEARCH_EXCERPT_CHARS],
        }
        # Reddit credit rides along only when the caller already resolved it
        # (granted rights lookup); never invented here.
        if str(raw.get("author") or "").strip():
            item["author"] = str(raw["author"]).strip()
        if str(raw.get("subreddit") or "").strip():
            item["subreddit"] = str(raw["subreddit"]).strip()
        items.append(item)
        if len(items) >= max_sources:
            break
    return items


def _render_packet(items: list[dict]) -> str:
    """Serialize evidence items as SOURCE blocks, never as unbounded web context."""
    blocks: list[str] = []
    for number, item in enumerate(items, start=1):
        published = item["published_at"]
        date = published.isoformat() if hasattr(published, "isoformat") else str(published or "Unknown date")
        excerpt = item["excerpt"] or "No article text was captured; use only the title and source attribution."
        credit = credit_suffix(str(item.get("author") or ""), str(item.get("subreddit") or ""))
        blocks.append(
            f"SOURCE {number}\n"
            f"Publisher: {item['source_name']}\n"
            f"Published: {date}\n"
            f"Title: {item['title']}{credit}\n"
            f"URL: {item['url']}\n"
            f"Article excerpt: {excerpt}"
        )
    return "\n\n".join(blocks)


def _research_packet(story: dict) -> str:
    """Serialize linked articles as evidence, never as unbounded web context."""
    entries = _research_items(story)
    if not entries:
        raise RuntimeError(
            "This story has no linked research sources. Select a sourced inbox story "
            "or paste a reviewed storyboard before generating a finance video."
        )
    return _render_packet(entries)


def _append_research_sources(storyboard: str, story: dict) -> str:
    """Keep the exact evidence links beside the generated asset for audit/review."""
    citations = [
        f"- {item['source_name']}: {item['title']}"
        f"{credit_suffix(str(item.get('author') or ''), str(item.get('subreddit') or ''))}"
        f" — {item['url']}"
        for item in _research_items(story)
    ]
    if not citations:
        return storyboard
    return storyboard.rstrip() + "\n\n# Research sources\n" + "\n".join(citations) + "\n"


_CINEMATIC_CONTROL_LABELS = (
    ("shot_scale", "Shot scale"),
    ("camera_angle", "Camera angle"),
    ("camera_movement", "Camera movement"),
    ("lens", "Lens language"),
    ("lighting", "Lighting"),
    ("color_treatment", "Color treatment"),
    ("pacing", "Pacing"),
    ("motion_intent", "Frame-to-motion intent"),
)


def _apply_cinematic_controls(
    storyboard: str, controls: dict[str, str] | None
) -> str:
    """Insert explicit operator direction before the first scene.

    The renderer already treats ``# Video direction`` as its continuity bible.
    Keeping the controls there makes the same choices reach scripting review,
    image generation, and the saved audit artifact without provider-specific
    prompt logic in the GUI.
    """
    if not controls:
        return storyboard

    directives = [
        f"- {label}: {str(controls[key]).strip()}"
        for key, label in _CINEMATIC_CONTROL_LABELS
        if str(controls.get(key, "")).strip()
    ]
    if not directives:
        return storyboard

    block = "## Cinematography controls\n" + "\n".join(directives)
    first_scene = re.search(r"(?m)^# Scene\s+\d+", storyboard)
    if first_scene:
        before = storyboard[: first_scene.start()].rstrip()
        after = storyboard[first_scene.start() :].lstrip()
        return f"{before}\n\n{block}\n\n{after}"
    return storyboard.rstrip() + f"\n\n# Video direction\n\n{block}\n"


async def _generate_script_for_story(
    story: dict, channel: Channel, cinematic: bool = False
) -> str:
    """
    Call the LLM to generate the storyboard markdown for one channel.

    The channel supplies voice and prompt.
    """
    headline = story.get("headline", "Default Headline")
    evidence_packet = _research_packet(story)

    import os
    from google import genai
    from google.genai import types

    cinematic_direction = """
For this run, write an image-led cinematic 3D short in 1080x1920 portrait.
The `# Video direction` section is a visual continuity bible: establish the original recurring character
(appearance, clothing, age-appropriate mannerisms), world, material palette, lighting, and camera language.
Every `Scene:` line must be a specific 3D film-frame prompt that preserves that bible. Use 4–8 scenes;
each scene must represent a new visual beat, never a title card or generic stock chart. For stocks and
investing, use tangible educational metaphors such as a miniature exchange floor, an unlabeled candlestick
city, a diversified garden, a risk umbrella, or a long road through changing weather.
""" if cinematic else ""

    system_instruction = f"""You are generating a script for a faceless YouTube explainer video.
Your Voice & Personality: {channel.script_prompt}

RESEARCH RULES (CRITICAL):
- Use only the factual claims supported by the EVIDENCE PACKET below. Do not fill gaps with general web knowledge,
  guesses, current prices, forecasts, dates, tax thresholds, legal conclusions, or company facts not present there.
- Explain what the sourced development means in plain educational language. If the evidence is thin, keep the video narrowly descriptive.
- Keep separate sources separate: never combine two claims into a new claim. Do not name a source in narration unless
  needed for clarity, but write a source-aware description. The system will preserve the exact links for review.

FORMAT:
You must output a valid markdown document that starts with YAML frontmatter.
Example format:
---
title: "The video title"
description: "A highly detailed, SEO-optimized description of the video. Write this as a human expert. NEVER mention or allude to AI, ChatGPT, or automated generation."
tags: "comma, separated, search, tags (at most 12)"
preset: {channel.voice_key}
music: soft upbeat playful
---

# Video direction
A clean, minimal, yet highly descriptive cartoonized explainer video.

# Scene 1
Voiceover: "Welcome to today's topic..."
Scene: "A bright, clear visual metaphor for the idea..."
{cinematic_direction}
STRUCTURE CONTRACT (the validator enforces this; a board that breaks it is discarded):
- 4-8 scenes, each a new visual beat. Heading form: `# Scene N — <chapter>` with a
  unique, non-empty chapter title per scene.
- Scene 1 Voiceover opens with the hook as its first sentence: at most 25 words,
  naming the concrete stake. Never open with "What if I told you…".
- Restate the stake for the viewer roughly every third scene.
- The final scene closes the story (a takeaway or verdict), never a trailing fact.
"""

    user_prompt = f"""Write a video script for this selected story.

STORY HEADLINE:
{headline}

EVIDENCE PACKET:
{evidence_packet}
"""

    provider = os.environ.get("SCENE_MODEL_PROVIDER", "gemini").lower()
    if provider == "deepseek":
        return await _generate_script_deepseek(system_instruction, user_prompt)
    return await _generate_script_gemini(system_instruction, user_prompt, channel)


async def _generate_script_gemini(
    system_instruction: str, user_prompt: str, channel: Channel
) -> str:
    import os
    from google import genai
    from google.genai import types

    log.info("gemini_generation_started", channel_id=channel.id, preset=channel.voice_key)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)

    def call_gemini():
        return client.models.generate_content(
            model="gemini-flash-latest",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            ),
        )

    last_error: Exception | None = None
    for attempt in range(1, SCRIPT_MAX_ATTEMPTS + 1):
        try:
            response = await asyncio.to_thread(call_gemini)
            log.info("gemini_generation_completed", attempt=attempt)
            return response.text
        except Exception as e:
            last_error = e
            if attempt == SCRIPT_MAX_ATTEMPTS or not _is_retryable(e):
                break
            delay = 2**attempt
            log.warning(
                "gemini_generation_retry",
                attempt=attempt,
                delay=delay,
                error=str(e)[:160],
            )
            await asyncio.sleep(delay)

    log.error("gemini_generation_failed", attempts=attempt, error=str(last_error))
    raise RuntimeError(
        f"script generation failed after {attempt} attempts: {last_error}"
    )


async def _generate_script_deepseek(
    system_instruction: str, user_prompt: str
) -> str:
    import os

    import httpx

    api_key = os.environ["DEEPSEEK_API_KEY"]
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("SCENE_MODEL", "deepseek-chat")

    log.info("deepseek_generation_started", model=model)

    last_error: Exception | None = None
    for attempt in range(1, SCRIPT_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.7,
                    },
                )
                if response.status_code in (429, 503, 500):
                    raise httpx.HTTPStatusError(
                        f"{response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"] or ""
                log.info("deepseek_generation_completed", attempt=attempt)
                return text
        except Exception as e:
            last_error = e
            if attempt == SCRIPT_MAX_ATTEMPTS or not _is_retryable(e):
                break
            delay = 2**attempt
            log.warning(
                "deepseek_generation_retry",
                attempt=attempt,
                delay=delay,
                error=str(e)[:160],
            )
            await asyncio.sleep(delay)

    log.error("deepseek_generation_failed", attempts=attempt, error=str(last_error))
    raise RuntimeError(
        f"script generation failed after {attempt} attempts: {last_error}"
    )

async def _record_youtube_draft(
    story_id: uuid.UUID,
    channel_id: str,
    upload_preference: str,
    file_path: str,
    status: str,
    external_id: str | None,
    title: str,
    description: str,
    *,
    tags: tuple[str, ...] | list[str] = (),
) -> uuid.UUID | None:
    pool = await db.get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                # channel_id and upload_preference are written twice on purpose.
                # Readers go through body->>'...' (see db.py), but migration 006
                # added real columns, and leaving them NULL/default means any SQL
                # that trusts the schema silently reads every draft as 'manual'.
                """
                INSERT INTO drafts
                (story_id, platform, format, body, status, published_ids,
                 channel_id, upload_preference)
                VALUES (%s, 'youtube', 'video', %s::jsonb, %s, %s::jsonb, %s, %s)
                RETURNING id
                """,
                (
                    story_id,
                    db._dumps({
                        "file_path": file_path,
                        "channel_id": channel_id,
                        "upload_preference": upload_preference,
                        "title": title,
                        "description": description,
                        "tags": list(tags),
                    }),
                    status,
                    db._dumps({"youtube": external_id}) if external_id else None,
                    channel_id,
                    upload_preference,
                )
            )
            row = await cur.fetchone()
            return row["id"] if row else None

# Free Microsoft Edge neural voices keyed by the channel/storyboard preset.
# The dashboard's Jenny/Aria control passes a deliberate run-level override so
# an editor's selected narrator always wins over an old pasted-board preset.
VOICE_MAP = {
    "teenage_boy": "en-US-EricNeural",         # Young male
    "teenage_girl": "en-US-AriaNeural",        # Warm expressive female
    "adult_male": "en-US-GuyNeural",           # Smooth male
    "adult_female": "en-US-JennyNeural",       # Friendly female
    "news": "en-US-DavisNeural",               # Steady male narrator
    "baby": "en-US-AnaNeural",                 # Child voice — actually sounds like a kid
}
DEFAULT_VOICE = "adult_male"

# Free plan allows 2 parallel TTS requests; anything more is rejected with 429.
TTS_MAX_CONCURRENCY = int(os.environ.get("TTS_MAX_CONCURRENCY", "2"))
TTS_MAX_ATTEMPTS = 4


def _extract_preset(script_content: str) -> str:
    import re

    match = re.search(r"^preset:\s*(.+)$", script_content, re.MULTILINE)
    return match.group(1).strip() if match else "default"


async def _synthesize_line(client: Any, text: str, voice_id: str, output_path: Path) -> None:
    """Render one narration line to its own mp3 via Edge TTS (free, no API key)."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(str(output_path))


def _write_silence(output_path: Path, seconds: float = 4.0) -> None:
    """Emit a silent placeholder so a failed line can't break the whole render."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(seconds), "-q:a", "9", "-acodec", "libmp3lame", str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _generate_frame_audio(
    board: Storyboard,
    video_dir: Path,
    script_content: str,
    voice_key: str | None = None,
) -> list[str]:
    """Render one voice clip per frame into assets/voice/NN.mp3.

    Per-frame rather than one concatenated track: the compiler measures each clip
    to place its frame on the timeline, so a single blob would leave every frame
    without a duration of its own.

    Returns the slugs that fell back to silence.
    """
    voice_dir = video_dir / "assets" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    preset = voice_key or _extract_preset(script_content)
    voice_id = VOICE_MAP.get(preset, VOICE_MAP[DEFAULT_VOICE])

    # Edge TTS is free with no API key, no rate limits, and decent quality.
    # Concurrency gate is kept light — 4 parallel renders is plenty.
    gate = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
    silenced: list[str] = []

    async def render(frame: Frame) -> None:
        destination = video_dir / frame.voice_filename
        if not frame.voiceover:
            _write_silence(destination, seconds=2.0)
            return
        for attempt in range(TTS_MAX_ATTEMPTS):
            try:
                async with gate:
                    await _synthesize_line(None, frame.voiceover, voice_id, destination)
                return
            except Exception as exc:
                # A concurrency 429 clears on its own, so it is worth waiting out.
                # Anything else (402, bad voice id) will not, so stop immediately.
                retryable = "429" in str(exc) or "concurrent_limit" in str(exc)
                if not retryable or attempt == TTS_MAX_ATTEMPTS - 1:
                    log.error("frame_tts_failed", frame=frame.slug, error=str(exc)[:200])
                    break
                await asyncio.sleep(2 * (attempt + 1))
        # One failed line must not cost the whole video; the frame still occupies
        # time and the storyboard stays intact. The caller decides if too many did.
        silenced.append(frame.slug)
        _write_silence(destination)

    await asyncio.gather(*(render(frame) for frame in board.frames))
    log.info(
        "frame_audio_generated",
        frames=len(board.frames),
        preset=preset,
        silenced=len(silenced),
    )
    return silenced


_FRAME_SYSTEM_PROMPT = """You write a single HyperFrames sub-composition: one HTML file that renders one scene of a vertical finance explainer.

AUDIENCE: teenagers and curious adults at once. Bold, clean, confident. Never babyish, never a corporate slide deck.

HARD CONTRACT — a violation means the frame fails to render:
1. Output ONLY one <template> element. No <!doctype>, <html>, <head>, or markdown fences.
2. Put <style> and <script> INSIDE the <template>. Anything outside it is discarded.
3. The root element inside the template must be exactly:
   <div id="{slug}-root" data-composition-id="{slug}" data-width="1080" data-height="1920" data-duration="{duration}">
4. Register exactly one timeline, built synchronously:
   window.__timelines["{slug}"] = gsap.timeline({{ paused: true }});
5. Prefix EVERY id with "{slug}-". Ids must be unique across the whole assembled page.
   Select with attribute selectors: '[id="{slug}-card"]'.
6. The scene background goes on a full-bleed child (position:absolute; inset:0), NEVER on the root element itself — a fill on the root renders black in the final video.
7. Give the root `container-type: size` and size children in cqw/cqh units so the layout scales.

DETERMINISM — frames are rendered out of order by parallel workers, so identical timestamps must produce identical pixels:
- No Date, no performance.now(), no unseeded Math.random(), no network requests, no repeat:-1 (use a finite repeat count).
- Animate only transform, opacity, filter, color, background-color, and stroke/fill.
- Never animate display or visibility.
- Every tween needs an explicit position parameter so the timeline is reproducible.
- NEVER use relative values such as "+=60" or "-=5". Relative tweens capture their base when the tween initialises, so a worker starting mid-timeline resolves a different base and renders the same frame differently. Always use fromTo() with explicit from and to values.
- Never let two tweens write the same property of the same element at overlapping times. Sequence them so they do not overlap, or pass overwrite: "auto".

FONTS — never declare a family you have not loaded, and never load one:
- The ONLY permitted font-family declaration is:
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
- No <link> and no @import from fonts.googleapis.com. External font requests add latency and can fail mid-render.
- If the global direction names a typeface (Fredoka, Quicksand, Poppins, anything), IGNORE the name and use the stack above. Declaring an unloaded family makes the renderer silently substitute a fallback, so the rendered typography stops matching the design.
- Express personality through weight, size, letter-spacing, and colour instead of typeface choice.

PALETTE — use these exact values, nothing else:
  ground   #0B1220   surface  #1B2A4A   surface-alt #24365C
  text     #F8FAFC   muted    #CBD5E1
  accent   #38BDF8   positive #34D399   warning #FBBF24   negative #F87171

CONTRAST — the render is rejected below 4.5:1 on text:
- Text on ground/surface/surface-alt is #F8FAFC, or #CBD5E1 for secondary text only.
- Text on an accent, positive, warning or negative fill is ALWAYS #0B1220.
- Never colour text with an accent on top of a coloured surface, and never place a light accent on a light fill.
- Accents belong to shapes, bars, borders, and glows, not to body copy.

LAYOUT — overlapping text is rejected:
- Lay the frame out as a single vertical column: `display:flex; flex-direction:column` with gap. Every text block gets its own row.
- Never absolutely position one text block on top of another, and never put SVG <text> over an HTML text block.
- Decorative absolutely-positioned elements must contain no text.
- Keep content inside the middle 80% of the height; the top and bottom are covered by platform UI.

3D STYLE: the parent composition sets `perspective: 1400px` and this scene inherits `transform-style: preserve-3d`. Use translateZ, rotateY and rotateX on cards so elements have real depth, with soft shadows to sell it. Animate with GSAP eases such as power3.out and back.out(1.5).

Text must be legible at a glance: display type at least 7cqw, body at least 4.5cqw, weight 600+. No <br> in body text."""


# "local" builds frames from archetypes planned by Ollama (free, no rate limit);
# "gemini" has the cloud model author raw HTML per frame.
FRAME_BACKEND = os.environ.get("FRAME_BACKEND", "local").lower()


async def _build_frames(
    board: Storyboard,
    video_dir: Path,
    backend: str | None = None,
    image_provider: str | None = None,
    motion: str | None = None,
    on_frame_complete=None,
) -> list[str]:
    """Dispatch frame generation to the requested backend.

    Backend is per request so a single running worker can produce both a
    portrait 2D Short and a landscape 3D film without an env change or a
    restart; FRAME_BACKEND only supplies the default.
    """
    chosen = (backend or FRAME_BACKEND).lower()
    if motion and motion != "off" and chosen != "cinematic":
        log.info("motion_ignored", backend=chosen, motion=motion)
    if chosen == "three":
        return await build_3d_frames(board, video_dir)
    if chosen == "cinematic":
        if on_frame_complete is None:
            return await build_cinematic_frames(board, video_dir, provider=image_provider, motion=motion)
        return await build_cinematic_frames(
            board,
            video_dir,
            provider=image_provider,
            motion=motion,
            on_frame_complete=on_frame_complete,
        )
    if chosen == "gemini":
        return await _generate_frame_compositions(board, video_dir)
    return await _generate_frame_compositions_local(board, video_dir)


def _is_retryable(exc: BaseException) -> bool:
    """Rate limits and transient server errors are worth another attempt."""
    text = str(exc)
    return any(
        marker in text
        for marker in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500")
    )


async def _generate_frame_compositions_local(board: Storyboard, video_dir: Path) -> list[str]:
    """Build every frame from pre-validated archetypes, planned by the local LLM.

    Returns the slugs that fell back to the heuristic planner. Unlike the
    HTML-authoring path this cannot produce an invalid composition: the model
    only chooses a shape and fills slots, and the templates were validated once.
    """
    import httpx

    from app.archetypes import render_archetype
    from app.localllm import OLLAMA_TIMEOUT, plan_frame

    frames_dir = video_dir / "compositions" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    degraded: list[str] = []

    # One GPU serves one planning request at a time (see app/gpu.py).
    async with gpu.slot:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:

            # Each frame is planned in isolation, so without this the model reaches
            # for the same shape every time and the video reads as one slide repeated.
            used_archetypes: list[str] = []

            async def build(frame: Frame) -> None:
                plan, used_fallback = await plan_frame(
                    voiceover=frame.voiceover,
                    scene=frame.scene,
                    title=frame.title,
                    direction=board.direction,
                    client=client,
                    used_archetypes=used_archetypes,
                )
                if used_fallback:
                    degraded.append(frame.slug)
                used_archetypes.append(plan.get("archetype", ""))
                (frames_dir / f"{frame.slug}.html").write_text(
                    render_archetype(frame.slug, frame.duration, plan), encoding="utf-8"
                )

            # Sequential: one local GPU serves one request at a time, so fanning out
            # only adds queueing latency.
            for frame in board.frames:
                await build(frame)

    log.info(
        "frame_compositions_generated",
        backend="local",
        frames=len(board.frames),
        heuristic=len(degraded),
    )
    return degraded


async def _generate_frame_compositions(board: Storyboard, video_dir: Path) -> list[str]:
    """Generate one sub-composition per frame. Returns the slugs that fell back.

    The caller must inspect the return value. A placeholder keeps the render
    alive, but a video mostly made of placeholders is not the video that was
    asked for and must never be published as though it were.
    """
    from google import genai
    from google.genai import types
    from tenacity import (
        AsyncRetrying,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential,
    )

    frames_dir = video_dir / "compositions" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.warning("gemini_api_key_missing", fallback="placeholder_frames")
        for frame in board.frames:
            (frames_dir / f"{frame.slug}.html").write_text(
                _placeholder_frame(frame), encoding="utf-8"
            )
        return [frame.slug for frame in board.frames]

    client = genai.Client(api_key=api_key)

    async def build(frame: Frame) -> None:
        destination = frames_dir / f"{frame.slug}.html"
        system_instruction = _FRAME_SYSTEM_PROMPT.format(
            slug=frame.slug, duration=frame.duration
        )
        shots = "\n".join(frame.shots) or "(no shot sequence given)"
        user_prompt = (
            f"GLOBAL DIRECTION: {board.direction or 'Clean, bold, 3D finance explainer.'}\n\n"
            f"SCENE: {frame.scene or frame.title}\n"
            f"NARRATION SPOKEN OVER THIS FRAME: \"{frame.voiceover}\"\n"
            f"ON SCREEN FOR: {frame.duration} seconds\n"
            f"SHOT SEQUENCE:\n{shots}\n\n"
            "Write the sub-composition."
        )
        try:
            # Rate limits are the common failure when generating a whole board at
            # once, and they clear on their own; retry before giving up a frame.
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model="gemini-flash-latest",
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction, temperature=0.6
                        ),
                    )
            html = _strip_code_fence(response.text or "")
            if "<template" not in html:
                raise ValueError("response did not contain a <template> element")
            destination.write_text(html, encoding="utf-8")
        except Exception as exc:
            # A frame that fails to generate still has to occupy its slot, or the
            # narration plays over nothing.
            log.error("frame_composition_failed", frame=frame.slug, error=str(exc)[:200])
            destination.write_text(_placeholder_frame(frame), encoding="utf-8")
            failed.append(frame.slug)

    await asyncio.gather(*(build(frame) for frame in board.frames))
    log.info(
        "frame_compositions_generated",
        frames=len(board.frames),
        placeholders=len(failed),
    )
    return failed


def _strip_code_fence(text: str) -> str:
    """Remove ```html fences the model sometimes wraps its output in."""
    import re

    stripped = text.strip()
    fence = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", stripped, re.DOTALL)
    return fence.group(1).strip() if fence else stripped


def _placeholder_frame(frame: Frame) -> str:
    """Minimal valid sub-composition: the narration as a legible title card."""
    text = (frame.voiceover or frame.title).replace("<", "&lt;").replace(">", "&gt;")
    return f"""<template>
  <style>
    [id="{frame.slug}-root"] {{
      width: 100%; height: 100%; position: relative;
      container-type: size; overflow: hidden;
    }}
    [id="{frame.slug}-bg"] {{ position: absolute; inset: 0; background: #0B1220; }}
    [id="{frame.slug}-text"] {{
      position: absolute; inset: 0;
      display: flex; align-items: center; justify-content: center;
      padding: 10cqw;
      font-family: 'Inter', system-ui, sans-serif;
      font-size: 7cqw; font-weight: 700; line-height: 1.3;
      color: #F8FAFC; text-align: center;
    }}
  </style>

  <div id="{frame.slug}-root" data-composition-id="{frame.slug}"
       data-width="1080" data-height="1920" data-duration="{frame.duration}">
    <div class="clip" id="{frame.slug}-bg" data-start="0"
         data-duration="{frame.duration}" data-track-index="0"></div>
    <div id="{frame.slug}-text">{text}</div>
  </div>

  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["{frame.slug}"] = tl;
      tl.fromTo('[id="{frame.slug}-text"]',
        {{ opacity: 0, y: 40 }},
        {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }},
        0
      );
    }})();
  </script>
</template>
"""


async def _generate_audio_for_script(script_content: str, output_path: Path):
    """
    Parses the generated script for 'Voiceover:' lines, concatenates them,
    and calls the ElevenLabs API to generate TTS audio.
    """
    import re
    import os
    from elevenlabs.client import AsyncElevenLabs
    
    # 1. Parse preset from YAML frontmatter
    preset = "default"
    preset_match = re.search(r"^preset:\s*(.+)$", script_content, re.MULTILINE)
    if preset_match:
        preset = preset_match.group(1).strip()
    
    # 2. Extract Voiceover lines
    # We look for lines starting with 'Voiceover:' or 'Voiceover: "'
    # It might be in bold `**Voiceover:**` so we handle that too.
    voiceover_lines = []
    for line in script_content.splitlines():
        line = line.strip()
        # Regex to match Voiceover: <text> with optional markdown formatting
        match = re.match(r"^(?:\*\*)?Voiceover:(?:\*\*)?\s*\"?(.+?)\"?$", line, re.IGNORECASE)
        if match:
            voiceover_lines.append(match.group(1).strip())
            
    if not voiceover_lines:
        log.warning("no_voiceover_lines_found", preset=preset)
        voiceover_text = "No voiceover text found."
    else:
        voiceover_text = " ".join(voiceover_lines)
        
    log.info("parsed_voiceover_text", length=len(voiceover_text), preset=preset)
    
    # 3. Map preset to ElevenLabs Voice ID
    # These are default ElevenLabs voices mapped to our personas
    voice_map = {
        "teenage_boy": "ErXwobaYiN019PkySvjV",  # Antoni
        "teenage_girl": "21m00Tcm4TlvDq8ikWAM", # Rachel
        "adult_male": "TxGEqnHWrfWFTfGW9XjX",   # Josh
        "adult_female": "MF3mGyEYCl7XYWbV9V6O", # Elli
        "baby": "jBpfuIE2acCO8z3wKNLl",         # Gigi (child)
    }
    
    voice_id = voice_map.get(preset, voice_map["adult_male"]) # default to adult_male if not found
    
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        log.warning("elevenlabs_api_key_missing", fallback="dummy_audio")
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "30", "-q:a", "9", "-acodec", "libmp3lame", str(output_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
        
    # 4. Generate audio via ElevenLabs
    try:
        client = AsyncElevenLabs(api_key=api_key)
        audio_generator = await client.generate(
            text=voiceover_text,
            voice=voice_id,
            model="eleven_multilingual_v2"
        )
        
        # Write bytes to output_path
        with open(output_path, "wb") as f:
            async for chunk in audio_generator:
                f.write(chunk)
                
        log.info("youtube_audio_generation_completed", path=str(output_path))
    except Exception as e:
        log.error("youtube_audio_generation_failed", error=str(e))
        # Write dummy file on failure so rendering doesn't crash entirely if it depends on the file
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "30", "-q:a", "9", "-acodec", "libmp3lame", str(output_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def build_thumbnail_art_prompt(*, title: str, hook: str, bible: str, mood: str) -> str:
    """Background-art prompt for one thumbnail variant. Never any text."""
    return f"""Create one original 16:9 landscape YouTube thumbnail background for a finance education video.

VIDEO TITLE: {title}
HOOK: {hook}
WORLD BIBLE: {bible or "Warm stylized 3D animated-feature look, miniature-scale finance world."}
MOOD: {mood}

One decisive cinematic moment, premium stylized 3D render, strong readable silhouette, uncluttered
negative space across the full upper third for a title band. Absolutely no words, letters, numbers,
tickers, logos, watermarks, UI, or subtitles anywhere in the image."""


def _thumbnail_html(*, layout: str, title: str, background: Path | None) -> str:
    """Render one 1280x720 thumbnail template with the title overlaid."""
    safe_title = html.escape(title)
    if background is not None:
        bg_layer = (
            f'<img src="file:///{background.as_posix()}" '
            'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;">'
        )
    else:
        bg_layer = ""
    if layout == "top-band":
        return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                width: 1280px;
                height: 720px;
                background: linear-gradient(135deg, #1e1e2f, #2a2a40);
                position: relative;
                overflow: hidden;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #ffffff;
            }}
            .band {{
                position: absolute;
                top: 0; left: 0; right: 0;
                padding: 48px 60px;
                background: rgba(11, 18, 32, 0.82);
                text-align: center;
            }}
            h1 {{
                font-size: 72px;
                font-weight: 900;
                text-transform: uppercase;
                text-shadow: 0 10px 30px rgba(0,0,0,0.8);
                line-height: 1.15;
                margin: 0;
            }}
        </style>
    </head>
    <body>
        {bg_layer}
        <div class="band"><h1>{safe_title}</h1></div>
    </body>
    </html>
    """
    if layout == "bottom-band":
        return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                width: 1280px;
                height: 720px;
                background: linear-gradient(135deg, #2a2a40, #1e1e2f);
                position: relative;
                overflow: hidden;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #ffffff;
            }}
            .badge {{
                position: absolute;
                top: 40px;
                left: 40px;
                background: #ff4a5a;
                color: white;
                padding: 10px 30px;
                font-size: 30px;
                font-weight: bold;
                border-radius: 50px;
                text-transform: uppercase;
                box-shadow: 0 4px 15px rgba(255, 74, 90, 0.4);
            }}
            .low {{
                position: absolute;
                bottom: 0; left: 0; right: 0;
                padding: 40px 60px;
                background: rgba(11, 18, 32, 0.82);
                text-align: left;
            }}
            h1 {{
                font-size: 64px;
                font-weight: 900;
                text-shadow: 0 10px 30px rgba(0,0,0,0.8);
                line-height: 1.15;
                margin: 0;
            }}
        </style>
    </head>
    <body>
        {bg_layer}
        <div class="badge">Trending</div>
        <div class="low"><h1>{safe_title}</h1></div>
    </body>
    </html>
    """
    raise ValueError(f"unknown thumbnail layout {layout!r}")


async def _generate_gemini_thumbnail_art(*, prompt: str, destination: Path) -> None:
    """Paint one thumbnail background with the keyframe image model."""
    from google import genai
    from google.genai import types

    from app.scene3d.backend import GEMINI_IMAGE_MODEL, extract_gemini_image_bytes

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def call():
        return client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

    response = await asyncio.to_thread(call)
    destination.write_bytes(extract_gemini_image_bytes(response))


async def _compose_thumbnail(*, layout: str, title: str, background: Path | None, output: Path) -> None:
    """Screenshot one thumbnail template to `output` via the Playwright CLI."""
    from starlette.concurrency import run_in_threadpool
    import subprocess
    import tempfile
    import sys

    page = _thumbnail_html(layout=layout, title=title, background=background)

    def _run():
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
            f.write(page)
            temp_html = f.name

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        try:
            # We use playwright cli to snapshot it
            subprocess.run(
                [npx_cmd, "playwright", "screenshot", f"file:///{temp_html.replace(chr(92), '/')}", str(output)],
                check=True,
                capture_output=True
            )
        finally:
            import os
            try:
                os.unlink(temp_html)
            except:
                pass

    await run_in_threadpool(_run)


_THUMBNAIL_VARIANTS = (
    ("a", "top-band", "calm daylight"),
    ("b", "bottom-band", "dramatic dusk"),
)


async def build_thumbnail_variants(*, title: str, hook: str, bible: str, video_dir: Path) -> dict[str, Path]:
    """Build thumbnail-a/b.jpg. Best-effort per variant: art failure falls back
    to the legacy card, and a variant that still fails is skipped. Never raises."""
    built: dict[str, Path] = {}
    for suffix, layout, mood in _THUMBNAIL_VARIANTS:
        output = video_dir / f"thumbnail-{suffix}.jpg"
        try:
            try:
                art = video_dir / f"thumbnail-{suffix}-art.png"
                await _generate_gemini_thumbnail_art(
                    prompt=build_thumbnail_art_prompt(title=title, hook=hook, bible=bible, mood=mood),
                    destination=art,
                )
                background: Path | None = art
            except Exception as exc:  # noqa: BLE001 — one bad variant must not kill the other
                log.warning("thumbnail_art_failed", variant=suffix, error=str(exc))
                background = None
            await _compose_thumbnail(layout=layout, title=title, background=background, output=output)
            built[suffix] = output
        except Exception as exc:  # noqa: BLE001 — thumbnails never block the draft
            log.warning("thumbnail_variant_failed", variant=suffix, error=str(exc))
    if not built:
        log.warning("thumbnail_generation_failed", reason="no variant built")
    return built

async def get_youtube_analytics(video_ids: list[str]) -> dict:
    """
    Fetches view count, like count, and comment count for the given video IDs.
    Returns a dictionary mapping videoId to stats.
    """
    if not video_ids:
        return {}
        
    from starlette.concurrency import run_in_threadpool
    from googleapiclient.discovery import build
    
    def _do_fetch():
        # Read-only: this path only lists statistics. The upload scope it used
        # to request was a leftover from when this module published videos.
        creds = _get_youtube_credentials(
            ["https://www.googleapis.com/auth/youtube.readonly"]
        )
        youtube = build("youtube", "v3", credentials=creds)
        
        # YouTube API allows up to 50 IDs per request
        results = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            request = youtube.videos().list(
                part="statistics,snippet",
                id=",".join(batch)
            )
            response = request.execute()
            
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                results[item["id"]] = {
                    "views": stats.get("viewCount", "0"),
                    "likes": stats.get("likeCount", "0"),
                    "comments": stats.get("commentCount", "0"),
                    "title": item.get("snippet", {}).get("title", "")
                }
        return results
        
    try:
        return await run_in_threadpool(_do_fetch)
    except Exception as e:
        log.error("youtube_analytics_fetch_failed", error=str(e))
        return {}


MAX_TAGS = 12
MAX_TAG_LENGTH = 60


def parse_tags(frontmatter: dict[str, str]) -> list[str]:
    """Split the frontmatter `tags:` line into clean tags. Absent means []."""
    raw = (frontmatter.get("tags") or "")
    seen: set[str] = set()
    tags: list[str] = []
    for chunk in raw.split(","):
        tag = " ".join(chunk.split())
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags


def validate_tags(tags: list[str], blocklist: tuple[str, ...]) -> list[str]:
    """Return violations for a tag list. Empty means shippable."""
    violations: list[str] = []
    if len(tags) > MAX_TAGS:
        violations.append(f"expected at most {MAX_TAGS} tags, found {len(tags)}")
    lowered = [t.lower() for t in tags]
    if len(set(lowered)) != len(tags):
        violations.append("duplicate tags")
    for tag in tags:
        if len(tag) > MAX_TAG_LENGTH:
            violations.append(f"tag {tag!r} exceeds {MAX_TAG_LENGTH} characters")
        blocked = [
            term
            for term in blocklist
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", tag, re.IGNORECASE)
        ]
        if blocked:
            violations.append(f"tag {tag!r} contains blocked term(s): {', '.join(blocked)}")
    return violations


def _require_metadata(
    frontmatter: dict[str, str], blocklist: tuple[str, ...] = ()
) -> tuple[str, str, list[str]]:
    """Return (title, description, tags) or raise.

    The old publish path read `frontmatter.get("description") or title`, so a
    generation that produced no description silently yielded a one-line title in
    the description box. That fallback is gone: an empty field is a generation
    failure and should be visible.
    """
    title = (frontmatter.get("title") or "").strip()
    description = (frontmatter.get("description") or "").strip()

    missing = [n for n, v in (("title", title), ("description", description)) if not v]
    if missing:
        raise ValueError(
            f"storyboard frontmatter is missing: {', '.join(missing)}"
        )

    tags = parse_tags(frontmatter)
    tag_violations = validate_tags(tags, blocklist)
    if tag_violations:
        raise ValueError(f"storyboard tags invalid: {'; '.join(tag_violations)}")
    return title, description, tags


_FRONTMATTER_BLOCK = re.compile(
    r"^\s*---\s*\r?\n(?P<frontmatter>.*?)\r?\n---(?:\s*\r?\n|$)",
    re.DOTALL,
)

_TIMELINE_BEAT = re.compile(
    r"^\s*(?P<start>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"
    r"(?P<end>\d+(?:\.\d+)?)\s*(?:sec(?:ond)?s?|s)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_OUTLINE_FIELD = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,40})\s*:\s*(?P<value>.+?)\s*$")
_NON_SPOKEN_OUTLINE_FIELDS = {
    "visual",
    "scene",
    "on-screen text",
    "style",
    "title",
    "length",
    "target audience",
    "vibe",
    "duration",
    "sound",
    "sound effects",
    "music",
}


def _frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def _yaml_scalar(value: str) -> str:
    """Return a compact, safe single-line value for our flat YAML-ish header."""
    return " ".join(value.split()).replace('"', "'")


def _normalize_timestamped_storyboard_outline(body: str) -> str:
    """Translate readable ``0–5 sec`` story beats into renderable scenes.

    The Storyboard field is deliberately editor-friendly: children-channel
    scripts commonly identify scenes by a time range and use character labels
    instead of a strict Markdown ``# Scene`` heading.  Preserve every spoken
    line, turn the beat duration into explicit timing, and leave ordinary
    Markdown boards untouched.
    """
    beats = list(_TIMELINE_BEAT.finditer(body))
    if not beats:
        return body

    normalized: list[str] = [body[: beats[0].start()].strip()]
    for index, beat in enumerate(beats, start=1):
        next_start = beats[index].start() if index < len(beats) else len(body)
        block = body[beat.end() : next_start]
        duration = max(float(beat.group("end")) - float(beat.group("start")), 0.1)
        visual = ""
        spoken: list[str] = []

        for raw_line in block.splitlines():
            field = _OUTLINE_FIELD.match(raw_line)
            if not field:
                continue
            label = field.group("label").strip()
            value = field.group("value").strip()
            normalized_label = label.lower()
            if normalized_label in {"visual", "scene"}:
                visual = visual or value
            elif normalized_label not in _NON_SPOKEN_OUTLINE_FIELDS:
                spoken.append(value if normalized_label in {"narrator", "voiceover"} else f"{label} says, {value}")

        lines = [f"# Scene {index}", f"Duration: {duration:g} seconds"]
        if visual:
            lines.append(f"Visual: {visual}")
        if spoken:
            lines.append(f"Voiceover: {' '.join(spoken)}")
        normalized.append("\n".join(lines))

    return "\n\n".join(part for part in normalized if part).strip()


def _ensure_storyboard_metadata(storyboard: str, *, fallback_title: str) -> str:
    """Add missing title/description frontmatter without touching a valid board.

    Editors commonly paste a readable outline beginning with ``Title:`` rather
    than a YAML block. The rendering pipeline needs title and description for
    the draft's upload metadata, but rejecting otherwise complete scenes is an
    unnecessary dead end. Existing complete frontmatter is deliberately
    returned unchanged.
    """
    text = storyboard.strip()
    match = _FRONTMATTER_BLOCK.match(text)
    existing_frontmatter = match.group("frontmatter").strip() if match else ""
    body = text[match.end():].strip() if match else text
    normalized_body = _normalize_timestamped_storyboard_outline(body)
    body_changed = normalized_body != body
    body = normalized_body

    title = _frontmatter_value(existing_frontmatter, "title") or _frontmatter_value(body, "title")
    title = _yaml_scalar(title or fallback_title or "Manual storyboard")
    description = _frontmatter_value(existing_frontmatter, "description") or _frontmatter_value(body, "description")
    description = _yaml_scalar(description)
    if not description:
        description = f"A 3D animated short based on {title}."

    if (
        match
        and _frontmatter_value(existing_frontmatter, "title")
        and _frontmatter_value(existing_frontmatter, "description")
        and not body_changed
    ):
        return storyboard

    frontmatter_lines = existing_frontmatter.splitlines() if existing_frontmatter else []
    if not _frontmatter_value(existing_frontmatter, "title"):
        frontmatter_lines.append(f'title: "{title}"')
    if not _frontmatter_value(existing_frontmatter, "description"):
        frontmatter_lines.append(f'description: "{description}"')
    frontmatter = "\n".join(frontmatter_lines)
    return f"---\n{frontmatter}\n---\n\n{body}\n"


def _write_upload_txt(
    video_dir: Path, channel: Channel, title: str, description: str,
    *, tags: tuple[str, ...] | list[str] = ()
) -> Path:
    """Write the paste-ready metadata beside the storyboard.

    Uploads are manual, so this file is how the metadata reaches YouTube. It also
    means the metadata survives a database reset and travels with the folder.
    """
    lines = [
        f"CHANNEL: {channel.display_name}",
        "",
        "TITLE",
        "-----",
        title,
        "",
        "DESCRIPTION",
        "-----------",
        description,
        "",
    ]

    if tags:
        lines += [
            "TAGS",
            "----",
            ", ".join(tags),
            "",
        ]

    if channel.id == "kids":
        lines += [
            "REMINDER",
            "--------",
            "Tick \"Made for kids\" in YouTube Studio before publishing. This is a",
            "COPPA requirement and nothing in this pipeline sets it for you.",
            "",
        ]

    path = video_dir / "upload.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _parse_storyboard_frontmatter(storyboard_path: Path) -> dict[str, str]:
    """
    Parse a simple YAML frontmatter block from the storyboard markdown.
    Returns a dict with at least 'title' and 'description' keys.
    """
    text = storyboard_path.read_text(encoding="utf-8") if storyboard_path.exists() else ""
    frontmatter: dict[str, str] = {"title": "", "description": ""}
    if text.startswith("---"):
        try:
            _, fm, _ = text.split("---", 2)
            for line in fm.strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            pass
    return frontmatter
