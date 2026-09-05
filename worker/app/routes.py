"""HTTP routes (Part II §3.9, §4.7).

Three endpoints:
  - GET  /health          : liveness probe for Railway (process + scheduler + DB)
  - GET  /stats           : the P1 "is it alive" surface
  - POST /ingest/trigger  : manual one-source poll (used by acceptance step 6)

The dashboard (P3) will add the rest; in P1 there is no GUI, so these are the
only surfaces. The scheduler is injected via FastAPI's app.state so /health can
report whether it's running.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db import ping as db_ping, stats as db_stats

router = APIRouter()

# Background generation tasks are held here for their lifetime. asyncio keeps
# only a weak reference to a bare create_task(), so without this a long render
# can be garbage-collected mid-run.
_RUNNING_JOBS: dict = {}


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Process + scheduler_running + db_reachable. NOT sources (§4.7): a dead
    feed is a /stats concern, not a liveness one. Returns 503 if any check fails
    so Railway restarts the container."""
    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_running = scheduler.running if scheduler is not False else False
    db_reachable = await db_ping()
    checks = {
        "process": "up",
        "scheduler_running": bool(scheduler_running),
        "db_reachable": db_reachable,
    }
    ok = all(checks.values())
    return JSONResponse(content=checks, status_code=200 if ok else 503)


@router.get("/stats")
async def stats() -> dict:
    """The /stats payload (Part II §3.9)."""
    return await db_stats()


@router.post("/ingest/trigger")
async def ingest_trigger(source_id: str) -> dict:
    """Manually trigger a poll for one source. Used by the soak checklist (§5.7
    step 6) to verify production idempotency."""
    from app.ingest import trigger_source

    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid source_id (must be a uuid)")
    summary = await trigger_source(sid)
    if summary is None:
        raise HTTPException(status_code=404, detail="source not found")
    return summary


@router.post("/x/publish")
async def x_publish(req: XPublishRequest) -> dict:
    """Publish a text post to X for a given story."""
    import traceback

    from app.x.publish import StoryNotFoundError, XComplianceError, publish_post

    try:
        sid = uuid.UUID(req.story_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")

    try:
        return await publish_post(story_id=sid, text=req.text)
    except HTTPException:
        raise
    except XComplianceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        print(f"Error in x_publish: {exc}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class XPublishRequest(BaseModel):
    story_id: str
    text: str = Field(min_length=1, max_length=280)


class XRewriteRequest(BaseModel):
    story_id: str
    tone: str | None = Field(default=None, max_length=200)
    length: str = Field(default="short", max_length=10)


class XReplyRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    post_context: str | None = Field(default=None, max_length=1000)
    tone: str | None = Field(default=None, max_length=200)


class PosterFromStoryRequest(BaseModel):
    story_id: str
    style: str | None = Field(default=None, max_length=40)


class PosterFromTextRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    bullets: list[str] = Field(default_factory=list)
    style: str | None = Field(default=None, max_length=40)


class YouTubeGenerateRequest(BaseModel):
    story_id: str
    channel_id: str = Field(min_length=1)
    upload_preference: str = "manual"
    voice_key: str | None = Field(default=None, max_length=40)


class CinematicControls(BaseModel):
    """Operator-owned visual direction added to the storyboard continuity bible."""

    shot_scale: str = Field(max_length=80)
    camera_angle: str = Field(max_length=80)
    camera_movement: str = Field(max_length=80)
    lens: str = Field(max_length=80)
    lighting: str = Field(max_length=80)
    color_treatment: str = Field(max_length=80)
    pacing: str = Field(max_length=80)
    motion_intent: str = Field(max_length=80)


class YouTubeJobRequest(BaseModel):
    story_id: str
    channel_id: str = Field(min_length=1)
    upload_preference: str = "manual"
    mode: str | None = None
    storyboard: str | None = Field(default=None, max_length=50000)
    image_provider: str | None = Field(default=None, max_length=20)
    voice_key: str | None = Field(default=None, max_length=40)
    cinematic_controls: CinematicControls | None = None
    brief: str | None = Field(default=None, max_length=2000)


# Shorts are the portrait image-led 3D format. Story Films keep the separate
# low-poly Three.js landscape route; `cinematic` remains a compatible API alias.
MODE_BACKENDS: dict[str, str | None] = {
    "short": "cinematic",
    "film": "three",
    "cinematic": "cinematic",
    "documentary": "cinematic",
}


def backend_for_mode(mode: str | None) -> str | None:
    """Map the GUI's format toggle to a frame backend.

    `None` means "use the FRAME_BACKEND default", which is what a Short wants.
    An unrecognised mode raises rather than defaulting, so a typo cannot
    quietly publish a portrait 2D video under a film's headline.
    """
    if mode is None:
        return None
    if mode not in MODE_BACKENDS:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODE_BACKENDS)}")
    return MODE_BACKENDS[mode]



@router.post("/youtube/generate")
async def youtube_generate(req: YouTubeGenerateRequest) -> dict:
    """Trigger YouTube video generation for a given story."""
    import traceback
    from app.channels import ChannelConfigError
    from app.youtube import generate_youtube_video
    try:
        try:
            sid = uuid.UUID(req.story_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")

        draft_id = await generate_youtube_video(
            story_id=sid,
            channel_id=req.channel_id,
            upload_preference=req.upload_preference,
            backend="cinematic",
            voice_key=req.voice_key,
        )
        if draft_id is None:
            raise HTTPException(status_code=404, detail="story not found")

        return {"draft_id": str(draft_id)}
    except HTTPException:
        raise
    except ChannelConfigError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        print(f"Error in youtube_generate: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/youtube/jobs")
async def youtube_job_start(req: YouTubeJobRequest) -> dict:
    """Start a generation run in the background and return its job id.

    Separate from POST /youtube/generate, which blocks until the render
    finishes and is what the existing Drafts button relies on. Adding a second
    surface leaves that path exactly as it is.
    """
    import asyncio

    from app import channels
    from app.channels import ChannelConfigError
    from app.jobs import create_job, fail_job, finish_job
    from app.youtube import generate_youtube_video

    try:
        try:
            sid = uuid.UUID(req.story_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")

        try:
            backend = backend_for_mode(req.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if backend == "cinematic":
            from app.scene3d.backend import require_cinematic_image_provider

            try:
                require_cinematic_image_provider(req.image_provider)
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Resolved synchronously, same as /youtube/generate: a bad channel_id
        # must fail the request, never a background task that already returned 202.
        await channels.resolve(req.channel_id)
        if req.voice_key:
            from app.youtube import VOICE_MAP

            if req.voice_key not in VOICE_MAP:
                raise HTTPException(status_code=400, detail=f"unknown voice key {req.voice_key!r}")

        job_id = await create_job(kind=req.mode or "short", story_id=sid)
    except HTTPException:
        raise
    except ChannelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def run() -> None:
        try:
            draft_id = await generate_youtube_video(
                story_id=sid,
                channel_id=req.channel_id,
                upload_preference=req.upload_preference,
                backend=backend,
                job_id=job_id,
                storyboard_override=req.storyboard,
                image_provider=req.image_provider,
                voice_key=req.voice_key,
                cinematic_controls=(
                    req.cinematic_controls.model_dump() if req.cinematic_controls else None
                ),
                documentary=(req.mode == "documentary"),
                brief=req.brief,
            )
            if draft_id is None:
                # A guard refused the video. That is a completed decision, not a
                # crash, and the reason is already in the worker log.
                await fail_job(job_id, "generation aborted by a quality guard; see worker logs")
            else:
                await finish_job(job_id, draft_id)
        except Exception as exc:  # noqa: BLE001
            await fail_job(job_id, str(exc))

    # Held so the task is not garbage-collected mid-render.
    task = asyncio.create_task(run())
    _RUNNING_JOBS[job_id] = task
    task.add_done_callback(lambda _t: _RUNNING_JOBS.pop(job_id, None))

    return {"job_id": str(job_id)}


@router.post("/youtube/jobs/with-voice")
async def youtube_job_with_voice(
    story_id: str = Form(...),
    channel_id: str = Form(...),
    upload_preference: str = Form("manual"),
    mode: str | None = Form(None),
    storyboard: str | None = Form(None),
    image_provider: str | None = Form(None),
    voice_key: str | None = Form(None),
    clips: list[UploadFile] | None = File(None),
    brief: str | None = Form(default=None, max_length=2000),
) -> dict:
    """Voice-to-video: owner narration in, everything else like /youtube/jobs.

    Clips match scenes by upload order. Validation is synchronous (a bad
    request fails here, never as a dead background job); files are staged to
    disk before the job starts so run() holds paths, not request memory.
    """
    import asyncio

    from app import channels
    from app.channels import ChannelConfigError
    from app.jobs import create_job, fail_job, finish_job
    from app.youtube import MAX_VOICE_CLIP_BYTES, MAX_VOICE_CLIPS, VIDEOS_DIR, generate_youtube_video

    try:
        try:
            sid = uuid.UUID(story_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")

        try:
            backend = backend_for_mode(mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if backend == "cinematic":
            from app.scene3d.backend import require_cinematic_image_provider

            try:
                require_cinematic_image_provider(image_provider)
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        await channels.resolve(channel_id)
        if voice_key:
            from app.youtube import VOICE_MAP

            if voice_key not in VOICE_MAP:
                raise HTTPException(status_code=400, detail=f"unknown voice key {voice_key!r}")

        if not clips:
            raise HTTPException(status_code=400, detail="at least one voice clip is required")
        if len(clips) > MAX_VOICE_CLIPS:
            raise HTTPException(status_code=400, detail=f"at most {MAX_VOICE_CLIPS} clips")

        payloads: list[tuple[str, bytes]] = []
        for upload in clips:
            raw = await upload.read(MAX_VOICE_CLIP_BYTES + 1)
            if len(raw) > MAX_VOICE_CLIP_BYTES:
                raise HTTPException(status_code=400, detail=f"clip {upload.filename!r} exceeds the size cap")
            if not raw:
                raise HTTPException(status_code=400, detail=f"clip {upload.filename!r} is empty")
            suffix = Path(upload.filename or "").suffix.lower()
            if not suffix or not re.match(r"^\.[a-z0-9]{1,5}$", suffix):
                suffix = ".audio"
            payloads.append((suffix, raw))

        job_id = await create_job(kind=(mode or "short"), story_id=sid)
        staging = VIDEOS_DIR / f"voice-upload-{job_id}"
        staging.mkdir(parents=True, exist_ok=True)
        clip_paths = []
        for index, (suffix, raw) in enumerate(payloads, start=1):
            path = staging / f"clip-{index:02d}{suffix}"
            path.write_bytes(raw)
            clip_paths.append(path)
    except HTTPException:
        raise
    except ChannelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def run() -> None:
        try:
            draft_id = await generate_youtube_video(
                story_id=sid,
                channel_id=channel_id,
                upload_preference=upload_preference,
                backend=backend,
                job_id=job_id,
                storyboard_override=storyboard,
                image_provider=image_provider,
                voice_clip_paths=clip_paths,
                documentary=(mode == "documentary"),
                brief=brief,
            )
            if draft_id is None:
                await fail_job(job_id, "generation aborted by a quality guard; see worker logs")
            else:
                await finish_job(job_id, draft_id)
        except Exception as exc:  # noqa: BLE001
            await fail_job(job_id, str(exc))

    task = asyncio.create_task(run())
    _RUNNING_JOBS[job_id] = task
    task.add_done_callback(lambda _t: _RUNNING_JOBS.pop(job_id, None))

    return {"job_id": str(job_id)}


@router.get("/youtube/image-providers")
async def youtube_image_providers() -> dict:
    """Safe provider readiness for the 3D Short dashboard selector."""
    from app.scene3d.backend import cinematic_image_provider_statuses

    return {"providers": cinematic_image_provider_statuses()}


@router.get("/youtube/jobs/{job_id}")
async def youtube_job_status(job_id: str) -> dict:
    """Current stage of a run. Polled by the GUI."""
    from app.jobs import get_job

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job_id (must be a uuid)")

    job = await get_job(jid)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        key: (str(value) if isinstance(value, uuid.UUID) else value)
        for key, value in job.items()
    }


@router.delete("/youtube/jobs/{job_id}")
async def youtube_job_cancel(job_id: str) -> dict:
    """Cancel a live run. A finished/unknown id is 404, never a silent no-op."""
    from app.jobs import fail_job

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job_id (must be a uuid)")

    task = _RUNNING_JOBS.get(jid)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="job not found or already finished")
    task.cancel()
    await fail_job(jid, "cancelled by owner")
    return {"cancelled": True}


_VIDEOS_DIR = Path(os.environ.get("VIDEOS_DIR", "../videos")).resolve()


@router.get("/youtube/jobs/{job_id}/shots")
async def youtube_job_shots(job_id: str) -> list[dict]:
    """Per-shot verification reports for the GUI's shot inspector."""
    from app.jobs import get_job

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job_id (must be a uuid)")

    job = await get_job(jid)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    path = _VIDEOS_DIR / f"story-{job['story_id']}" / "renders" / "shots.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/youtube/image-providers")
async def youtube_image_providers() -> dict:
    """Fetch available image providers for cinematic mode."""
    from app.scene3d.backend import cinematic_image_provider_statuses

    return {"providers": cinematic_image_provider_statuses()}


@router.get("/stories")
async def get_stories(order: str = "recent") -> list[dict]:
    """Fetch current, source-dated stories for the Inbox.

    `order=score` returns the P2a ranked view; the default is unchanged so the
    films page keeps its existing queue order.
    """
    from app.config import get_ingest_config
    from app.db import get_pending_stories

    cfg = await get_ingest_config()
    try:
        return await get_pending_stories(fresh_hours=cfg.fresh_news_hours, order=order)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ManualStoryRequest(BaseModel):
    headline: str
    channel_id: str = Field(min_length=1)


@router.post("/stories/manual")
async def create_manual_story_endpoint(req: ManualStoryRequest) -> dict:
    """Create a manual story idea."""
    from app.db import create_manual_story
    story_id = await create_manual_story(req.headline, req.channel_id)
    return {"id": str(story_id)}


@router.get("/drafts")
async def get_drafts() -> list[dict]:
    """Fetch all drafts."""
    from app.db import get_drafts
    return await get_drafts()


class DraftThumbnailRequest(BaseModel):
    picked: Literal["a", "b"] | None = None


@router.patch("/drafts/{draft_id}/thumbnail")
async def set_draft_thumbnail(draft_id: str, req: DraftThumbnailRequest) -> dict:
    """Record which rendered thumbnail was uploaded for a draft.

    Persists `thumbnail_picked` ("a", "b", or null) into the draft body
    jsonb. Read back via GET /drafts; the drafts GUI picker calls this.
    An unknown value is a 422 (pydantic), an unknown draft is a 404.
    """
    from app.db import set_draft_thumbnail_picked

    try:
        did = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid draft_id (must be a uuid)")

    updated = await set_draft_thumbnail_picked(did, req.picked)
    if not updated:
        raise HTTPException(status_code=404, detail="draft not found")
    return {"id": str(did), "thumbnail_picked": req.picked}


@router.get("/youtube/analytics")
async def youtube_analytics_endpoint() -> dict:
    """Fetch analytics for all published videos."""
    from app.db import get_drafts
    from app.youtube import get_youtube_analytics
    
    drafts = await get_drafts()
    video_ids = []
    for d in drafts:
        if d.get("status") == "published" and d.get("published_ids") and isinstance(d["published_ids"], dict):
            yt_id = d["published_ids"].get("youtube")
            if yt_id:
                video_ids.append(yt_id)
                
    if not video_ids:
        return {}
        
    return await get_youtube_analytics(video_ids)


@router.get("/config/{key}")
async def get_config_endpoint(key: str) -> dict:
    """Fetch a configuration object by key."""
    from app.db import get_config
    val = await get_config(key)
    if val is None:
        raise HTTPException(status_code=404, detail="config key not found")
    return val


@router.put("/config/{key}")
async def set_config_endpoint(key: str, request: Request) -> dict:
    """Update a configuration object by key."""
    from app.db import set_config
    try:
        val = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    await set_config(key, val)
    return {"status": "ok"}


class CinepromptFillRequest(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    mode: str = "single"
    level: str = "complex"
    locked: dict | None = None


@router.post("/cineprompt/fill")
async def cineprompt_fill(req: CinepromptFillRequest) -> dict:
    """Scene description -> snapped field-state, via the CinePrompt engine."""
    from app.cineprompt import FillError, fill_from_scene

    try:
        fields = await fill_from_scene(
            req.description, mode=req.mode, level=req.level, locked=req.locked,
        )
    except FillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"fields": fields}


class CinepromptBuildRequest(BaseModel):
    mode: str = "single"
    model: str = "universal"
    fields: dict


@router.post("/cineprompt/build")
async def cineprompt_build(req: CinepromptBuildRequest) -> dict:
    """Field-state -> assembled cinematography prompt text(s).

    `build_prompt` returns one string per resolved shot: exactly one for
    `single`, exactly two for `frame_motion` (still-frame, then motion).
    Returning the full list means neither mode silently drops a prompt.
    """
    from app.cineprompt import build_prompt

    try:
        prompts = build_prompt({"mode": req.mode, "model": req.model, "fields": req.fields})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"prompts": prompts}


class CinepromptSaveRequest(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    mode: str = "single"
    model: str = "universal"
    fields: dict
    prompt: str = Field(min_length=1)
    video_url: str = Field(min_length=1)


@router.post("/cineprompt/save")
async def cineprompt_save(req: CinepromptSaveRequest) -> dict:
    """Download the fal.run result and persist it.

    Write-then-insert, in that order: a DB row must never point at a file
    that doesn't exist. Any download failure cleans up the partial file
    and leaves no row at all, rather than a half-saved generation.
    """
    from app.db import save_cineprompt_generation

    file_id = uuid.uuid4()
    dest_dir = _VIDEOS_DIR / "cineprompt"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{file_id}.mp4"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(req.video_url)
            response.raise_for_status()
        dest_path.write_bytes(response.content)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"could not download video: {exc}") from exc

    gen_id = await save_cineprompt_generation(
        description=req.description,
        mode=req.mode,
        model=req.model,
        fields=req.fields,
        prompt=req.prompt,
        video_url=req.video_url,
        local_path=str(dest_path.relative_to(_VIDEOS_DIR).as_posix()),
    )
    return {"id": str(gen_id), "local_path": str(dest_path.relative_to(_VIDEOS_DIR).as_posix())}


@router.get("/cineprompt/history")
async def cineprompt_history() -> list[dict]:
    """Most recent saved Cinema generations, newest first. No pagination in v1."""
    from app.db import get_cineprompt_history

    rows = await get_cineprompt_history()
    return [
        {**row, "id": str(row["id"]) if isinstance(row["id"], uuid.UUID) else row["id"]}
        for row in rows
    ]


@router.get("/cineprompt/vocab")
async def cineprompt_vocab(mode: str = "single", level: str = "complex") -> dict:
    """Section -> field -> {values, free_text}, filtered to what's in scope
    for (mode, level) — the same filter Fill's system prompt catalogue uses,
    so the manual picker and the AI-fill shortcut always agree on what's
    pickable. A section with nothing in scope is omitted, not emitted empty.
    """
    from app.cineprompt import assemble, prompts, vocab

    in_scope = set(prompts.fields_in_scope(mode, level))
    result: dict[str, dict] = {}
    for section, section_fields in assemble.SECTIONS.items():
        fields_here = [f for f in section_fields if f in in_scope]
        if not fields_here:
            continue
        result[section] = {
            field: {"values": vocab.values_for(field), "free_text": vocab.is_free_text(field)}
            for field in fields_here
        }
    return result


@router.get("/x/stories")
async def x_stories() -> list[dict]:
    """Recent inbox stories for the manual X assistant."""
    from app.config import get_ingest_config
    from app.db import get_pending_stories

    cfg = await get_ingest_config()
    stories = await get_pending_stories(fresh_hours=cfg.fresh_news_hours, order="recent")
    for story in stories:
        story["id"] = str(story["id"])
        for item in story.get("items", []):
            item["id"] = str(item["id"])
    return stories


@router.post("/x/rewrite")
async def x_rewrite(req: XRewriteRequest) -> dict:
    """Rewrite a story into a manual X post using Kimi."""
    from app.x.rewrite import RewriteError, rewrite_story_to_post

    try:
        sid = uuid.UUID(req.story_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)") from exc

    try:
        post = await rewrite_story_to_post(story_id=sid, tone=req.tone, length=req.length)
    except RewriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"post": post}


@router.post("/x/reply")
async def x_reply(req: XReplyRequest) -> dict:
    """Suggest a reply to a comment using Kimi."""
    from app.x.rewrite import RewriteError, suggest_reply

    try:
        reply = await suggest_reply(
            comment_text=req.comment,
            post_context=req.post_context,
            tone=req.tone,
        )
    except RewriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"reply": reply}


@router.post("/x/poster/story")
async def x_poster_from_story(req: PosterFromStoryRequest) -> dict:
    """Generate an educational poster structure from a story."""
    from app.x.poster import PosterError, generate_poster_from_story

    try:
        sid = uuid.UUID(req.story_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)") from exc

    try:
        return await generate_poster_from_story(story_id=sid, style=req.style)
    except PosterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/x/poster/text")
async def x_poster_from_text(req: PosterFromTextRequest) -> dict:
    """Generate an educational poster structure from a topic + bullet points."""
    from app.x.poster import PosterError, generate_poster_from_text

    try:
        return await generate_poster_from_text(
            topic=req.topic,
            bullets=req.bullets,
            style=req.style,
        )
    except PosterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
