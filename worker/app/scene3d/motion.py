"""Image-to-video motion for cinematic 3D Shorts.

Every scene already has a generated keyframe (style anchor, thumbnail source).
When a run selects a motion provider, that keyframe is animated by an
image-to-video model — Google Veo 3 via the google-genai SDK, or Kling v2
master via the fal.run queue REST API — and the downloaded clip is
ffmpeg-normalized to the scene's measured ``frame.duration``: model audio is
stripped (narration is the fact-checked TTS, never the model's) and the clip
is trimmed or looped to fit. The off provider keeps the Ken Burns keyframe
renderer and this module is never touched.
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger()

MOTION_PROVIDERS = ("off", "veo", "kling")

GEMINI_VIDEO_MODEL = os.environ.get("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview")

# Clip generation polls cloud APIs for minutes; three in flight is a good
# trade between wall-clock and provider rate limits.
MOTION_MAX_PARALLEL = max(1, int(os.environ.get("MOTION_MAX_PARALLEL", "3")))

FAL_KLING_URL = "https://queue.fal.run/fal-ai/kling-video/v2/master/image-to-video"
KLING_POLL_INTERVAL_SECONDS = 3.0
KLING_MAX_WAIT_SECONDS = 600.0

FFMPEG_TIMEOUT_SECONDS = 300.0

# Veo's concurrent-request quota is small and shared with every running job;
# 429s clear on their own, so back off and retry rather than fail the film.
VEO_MAX_ATTEMPTS = int(os.environ.get("VEO_MAX_ATTEMPTS", "8"))
VEO_RETRY_INITIAL_SECONDS = float(os.environ.get("VEO_RETRY_INITIAL_SECONDS", "20"))


def _is_quota_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


def normalize_motion_provider(provider: str | None = None) -> str:
    """Validate a per-run motion provider without silently downgrading it."""
    selected = (provider or "off").strip().lower()
    if selected not in MOTION_PROVIDERS:
        raise ValueError(f"unknown motion provider {selected!r}; expected one of {MOTION_PROVIDERS}")
    return selected


def motion_provider_statuses() -> list[dict[str, str | bool]]:
    """Return safe dashboard metadata—never keys."""
    return [
        {
            "id": "off",
            "label": "Ken Burns",
            "detail": "2.5D pan & zoom on the keyframe · no video model",
            "configured": True,
        },
        {
            "id": "veo",
            "label": "Veo 3",
            "detail": "Google image-to-video · 1080p 9:16 · uses API credits",
            "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        },
        {
            "id": "kling",
            "label": "Kling 2.0",
            "detail": "fal.run start-frame video · strong keyframe fidelity",
            "configured": bool(os.environ.get("FAL_KEY", "").strip()),
        },
    ]


def require_motion_provider(provider: str | None = None) -> str:
    selected = normalize_motion_provider(provider)
    if selected == "off":
        return selected
    status = next(item for item in motion_provider_statuses() if item["id"] == selected)
    if status["configured"]:
        return selected
    if selected == "veo":
        raise RuntimeError("GEMINI_API_KEY is required for Veo 3 motion; add it to worker/.env")
    raise RuntimeError("FAL_KEY is required for Kling motion; add it to worker/.env")


def _veo_client():
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


async def generate_veo_clip(keyframe: Path, prompt: str, destination: Path) -> None:
    """Animate one keyframe with Veo 3 and write the raw clip to ``destination``.

    Verified against google-genai 2.15.0: image-to-video goes through
    ``client.models.generate_videos(model=..., prompt=..., image=types.Image(...),
    config=types.GenerateVideosConfig(...))`` returning a GenerateVideosOperation;
    poll with ``client.operations.get(operation)`` until ``.done``; the clip URI
    is ``operation.response.generated_videos[0].video.uri`` and
    ``client.files.download(file=uri)`` returns the bytes.

    Quota exhaustion (HTTP 429) is retried with exponential backoff — a shared
    Gemini quota means bursts fail transiently, and a film that already spent
    minutes on earlier clips must not be thrown away over a throttle.
    """
    from google.genai import types

    client = _veo_client()

    def submit():
        return client.models.generate_videos(
            model=GEMINI_VIDEO_MODEL,
            prompt=prompt,
            image=types.Image(image_bytes=keyframe.read_bytes(), mime_type="image/png"),
            config=types.GenerateVideosConfig(
                resolution="1080p",
                aspect_ratio="9:16",
                number_of_videos=1,
            ),
        )

    async def with_retry(coro_factory, what: str):
        last_error: BaseException | None = None
        for attempt in range(1, VEO_MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(coro_factory)
            except Exception as exc:  # noqa: BLE001 — retried only when quota-ish
                if not _is_quota_error(exc):
                    raise
                last_error = exc
                if attempt < VEO_MAX_ATTEMPTS:
                    delay = min(VEO_RETRY_INITIAL_SECONDS * (2 ** (attempt - 1)), 300)
                    log.warning("veo_quota_retry", what=what, attempt=attempt,
                                delay=delay, error=str(exc)[:200])
                    await asyncio.sleep(delay)
        raise RuntimeError(f"Veo {what} failed after {VEO_MAX_ATTEMPTS} attempts: {last_error}")

    operation = await with_retry(submit, "submit")
    while not operation.done:
        await asyncio.sleep(10)
        operation = await with_retry(lambda: client.operations.get(operation), "poll")
    if getattr(operation, "error", None):
        raise RuntimeError(f"Veo generation failed: {operation.error}")
    videos = (operation.response.generated_videos or []) if operation.response else []
    if not videos:
        raise RuntimeError("Veo finished without a generated video")
    uri = videos[0].video.uri
    data = await asyncio.to_thread(client.files.download, file=uri)
    destination.write_bytes(data)


async def generate_kling_clip(keyframe: Path, prompt: str, destination: Path) -> None:
    """Animate one keyframe with Kling v2 master via the fal.run queue API.

    Mirrors the proven GUI flow in gui/src/app/cinema/page.tsx: submit with
    ``Authorization: Key $FAL_KEY`` (the keyframe rides as a base64 data-URI
    ``image_url`` so nothing needs public hosting), poll ``status_url`` until
    COMPLETED, then read ``video.url`` from ``response_url`` and download it.
    """
    import httpx

    key = os.environ.get("FAL_KEY", "").strip()
    if not key:
        raise RuntimeError("FAL_KEY is required for Kling motion; add it to worker/.env")
    image_url = "data:image/png;base64," + base64.b64encode(keyframe.read_bytes()).decode("ascii")
    headers = {"Authorization": f"Key {key}"}
    payload = {
        "image_url": image_url,
        "prompt": prompt,
        "duration": "5",
        "aspect_ratio": "9:16",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        submit = await client.post(FAL_KLING_URL, headers=headers, json=payload)
        if submit.status_code >= 400:
            raise RuntimeError(f"fal.run rejected the Kling job: {submit.status_code} {submit.text[:300]}")
        submit_body = submit.json()
        status_url = submit_body.get("status_url")
        response_url = submit_body.get("response_url")
        if not status_url or not response_url:
            raise RuntimeError(f"fal.run submit response missing queue URLs: {submit_body}")

        deadline = asyncio.get_event_loop().time() + KLING_MAX_WAIT_SECONDS
        while True:
            await asyncio.sleep(KLING_POLL_INTERVAL_SECONDS)
            status = await client.get(f"{status_url}?logs=1", headers=headers)
            if status.status_code >= 400:
                raise RuntimeError(f"fal.run status poll failed: {status.status_code} {status.text[:300]}")
            status_body = status.json()
            state = status_body.get("status")
            if state == "COMPLETED":
                break
            if state == "ERROR":
                raise RuntimeError(f"fal.run generation failed: {status_body.get('error') or status_body}")
            if asyncio.get_event_loop().time() > deadline:
                raise RuntimeError(f"Kling generation timed out after {KLING_MAX_WAIT_SECONDS:g}s")

        result = await client.get(response_url, headers=headers)
        if result.status_code >= 400:
            raise RuntimeError(f"fal.run result fetch failed: {result.status_code} {result.text[:300]}")
        video_url = (result.json().get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(f"fal.run result has no video URL: {result.text[:300]}")
        video = await client.get(video_url)
        if video.status_code >= 400:
            raise RuntimeError(f"Kling clip download failed: {video.status_code}")
        destination.write_bytes(video.content)


async def generate_motion_clip(provider: str, keyframe: Path, prompt: str, destination: Path) -> None:
    """Dispatch one keyframe to the selected image-to-video provider."""
    selected = normalize_motion_provider(provider)
    if selected == "veo":
        await generate_veo_clip(keyframe, prompt, destination)
        return
    if selected == "kling":
        await generate_kling_clip(keyframe, prompt, destination)
        return
    raise ValueError(f"motion provider {selected!r} does not generate clips")


def _clip_duration_seconds(source: Path) -> float | None:
    """Source clip length via ffprobe; None when it cannot be measured."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


async def normalize_clip(source: Path, destination: Path, duration: float) -> None:
    """Re-encode ``source`` to exactly ``duration`` seconds, audio stripped.

    One ffmpeg pass: ``-an`` drops the model's generated audio (narration is
    the fact-checked TTS) and the clip is trimmed or looped to the measured
    scene duration so per-scene timing — and therefore narration sync — is
    untouched. A source at or above the target is cut with ``-t``; a shorter
    source loops via ``-stream_loop``. When the source length cannot be
    probed, looping is the safe default: for a longer source it behaves
    exactly like a trim.

    Every clip is normalized to the identical target geometry so the motion
    assembler can concat without a second encode: 1080x1920 (scaled with
    ``force_original_aspect_ratio=increase`` and center-cropped, matching the
    composition's object-fit: cover), 30fps, square pixels, yuv420p, crf 18
    preset slow — a single clean encode, no MJPEG generation loss.
    """
    source_seconds = await asyncio.to_thread(_clip_duration_seconds, source)
    loop_input = source_seconds is None or source_seconds < duration
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30,"
        "setsar=1"
    )
    command = ["ffmpeg", "-y"]
    if loop_input:
        command += ["-stream_loop", "-1"]
    command += [
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-an",
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        str(destination),
    ]
    result = await asyncio.to_thread(
        subprocess.run, command, capture_output=True, text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg could not normalize {source.name} to {duration:.3f}s: "
            f"{(result.stderr or '')[-400:]}"
        )
    log.info("clip_normalized", source=source.name, destination=destination.name,
             duration=duration, looped=loop_input)
