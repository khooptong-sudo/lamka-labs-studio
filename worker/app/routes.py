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

import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db import ping as db_ping, stats as db_stats

router = APIRouter()

# Background generation tasks are held here for their lifetime. asyncio keeps
# only a weak reference to a bare create_task(), so without this a long render
# can be garbage-collected mid-run.
_RUNNING_JOBS: set = set()


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


# Shorts are the portrait image-led 3D format. Story Films keep the separate
# low-poly Three.js landscape route; `cinematic` remains a compatible API alias.
MODE_BACKENDS: dict[str, str | None] = {
    "short": "cinematic",
    "film": "three",
    "cinematic": "cinematic",
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
    _RUNNING_JOBS.add(task)
    task.add_done_callback(_RUNNING_JOBS.discard)

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
async def get_stories() -> list[dict]:
    """Fetch current, source-dated stories for the Inbox."""
    from app.config import get_ingest_config
    from app.db import get_pending_stories

    cfg = await get_ingest_config()
    return await get_pending_stories(fresh_hours=cfg.fresh_news_hours)


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
    except ValueError as exc:
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


__all__ = ["router"]
