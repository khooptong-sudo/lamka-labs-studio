"""Orchestrate one film's 3D frames: world, then shot-verify-retry per frame.

The retry loop is the point. A model writing free-form JavaScript will
occasionally put the camera inside a hill or forget a light, and the gate
catches that — but only if the failure feeds back into the next attempt.
Exhausting the retries reports the slug; it never writes a substitute, because
a substituted shot renders and validates exactly like a real one.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import structlog

from app import gpu
from app.scene3d.author import author_shot, author_world
from app.scene3d.probes import ProbeStats, frames_are_distinct
from app.scene3d.shell import render_3d_frame
from app.scene3d.verify import verify_shot

log = structlog.get_logger()

SHOT_RETRIES = int(os.environ.get("SHOT_RETRIES", "2"))
MIN_VERIFIED_FRAMES = int(os.environ.get("MIN_VERIFIED_FRAMES", "3"))

# Image-led shorts deliberately live beside the code-generated Three.js films:
# both produce the same verified sub-composition artifact, but their visual
# strengths are different. The image path is for character-led, cinematic
# vertical storytelling; the DSL path remains the no-character landscape film.
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
IMAGE_PROVIDERS = ("gemini", "comfyui")

# The image endpoint sometimes answers with an empty or text-only response
# instead of an image. Those clear on their own; retry before failing the film.
GEMINI_IMAGE_MAX_ATTEMPTS = int(os.environ.get("GEMINI_IMAGE_MAX_ATTEMPTS", "4"))


def normalize_cinematic_image_provider(provider: str | None = None) -> str:
    """Validate a per-run image provider without ever silently downgrading it."""
    selected = (provider or os.environ.get("CINEMATIC_IMAGE_PROVIDER", "gemini")).strip().lower()
    if selected not in IMAGE_PROVIDERS:
        raise ValueError(f"unknown cinematic image provider {selected!r}; expected one of {IMAGE_PROVIDERS}")
    return selected


def cinematic_image_provider_statuses() -> list[dict[str, str | bool]]:
    """Return safe dashboard metadata—never keys or workflow contents."""
    comfy_workflow = os.environ.get("COMFYUI_WORKFLOW_PATH", "").strip()
    comfy_checkpoint = os.environ.get("COMFYUI_CHECKPOINT_NAME", "").strip()
    comfy_configured = bool(os.environ.get("COMFYUI_BASE_URL", "").strip()) and bool(
        comfy_checkpoint or (comfy_workflow and Path(comfy_workflow).is_file())
    )
    return [
        {
            "id": "gemini",
            "label": "Gemini Cinematic",
            "detail": "Gemini image keyframes · uses API credits",
            "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        },
        {
            "id": "comfyui",
            "label": "ComfyUI Local",
            "detail": "Your local GPU · requires ComfyUI and a selected checkpoint",
            "configured": comfy_configured,
        },
    ]


def require_cinematic_image_provider(provider: str | None = None) -> str:
    selected = normalize_cinematic_image_provider(provider)
    status = next(item for item in cinematic_image_provider_statuses() if item["id"] == selected)
    if status["configured"]:
        return selected
    if selected == "comfyui":
        raise RuntimeError(
            "ComfyUI is not ready. Set COMFYUI_BASE_URL plus COMFYUI_CHECKPOINT_NAME "
            "(or COMFYUI_WORKFLOW_PATH) in worker/.env, then restart the worker."
        )
    raise RuntimeError("GEMINI_API_KEY is required for Gemini Cinematic Shorts; add it to worker/.env")

ASSETS = Path(__file__).resolve().parent / "assets"


@dataclass
class ShotReport:
    slug: str
    attempts: int = 0
    ok: bool = False
    reason: str = ""
    js: str = ""
    probe_pngs: list[str] = field(default_factory=list)


def _install_assets(video_dir: Path) -> None:
    """Copy the DSL and Three.js into the project so a render needs no network.

    Files land at ``assets/`` (project-root-relative), matching the paths the
    shell emits — ``assets/three.min.js`` and ``assets/primitives.js``.
    Spike Correction 1: ``three.min.js`` (UMD r160.1), NOT ``three.module.js``.
    """
    assets_dir = video_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name in ("three.min.js", "primitives.js"):
        shutil.copyfile(ASSETS / name, assets_dir / name)


async def build_3d_frames(board, video_dir: Path) -> list[str]:
    """Build every frame as a verified 3D shot. Returns slugs that never passed."""
    _install_assets(video_dir)
    frames_dir = video_dir / "compositions" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    probe_dir = video_dir / "renders" / "probes"

    world_code = await author_world(board)
    (video_dir / "compositions" / "world.js").write_text(
        world_code, encoding="utf-8"
    )

    failed: list[str] = []
    reports: list[ShotReport] = []
    prior_shots: list[str] = []
    accepted_probes: list[ProbeStats] = []

    for frame in board.frames:
        report = ShotReport(slug=frame.slug)
        last_error: str | None = None
        frame_path = frames_dir / f"{frame.slug}.html"

        for attempt in range(SHOT_RETRIES + 1):
            report.attempts = attempt + 1
            shot_js = await author_shot(
                board, frame, world_code, prior_shots, last_error=last_error
            )
            frame_path.write_text(
                render_3d_frame(
                    frame.slug,
                    frame.duration,
                    shot_js,
                    frame.voiceover,
                    width=board.width,
                    height=board.height,
                ),
                encoding="utf-8",
            )
            verdict, probes, _errors = await verify_shot(
                frame_path, frame.duration, probe_dir
            )

            if (
                verdict.ok
                and accepted_probes
                and not frames_are_distinct(
                    accepted_probes[-1], probes[len(probes) // 2]
                )
            ):
                verdict = type(verdict)(
                    False, "shot looks identical to the previous one"
                )

            if verdict.ok:
                report.ok = True
                report.js = shot_js
                report.probe_pngs = [
                    f"{frame.slug}-p{i}.png" for i in range(3)
                ]
                prior_shots.append(shot_js)
                accepted_probes.append(probes[len(probes) // 2])
                break

            last_error = verdict.reason
            report.reason = verdict.reason
            log.warning(
                "shot_rejected",
                slug=frame.slug,
                attempt=attempt + 1,
                reason=verdict.reason,
            )

        if not report.ok:
            # Deliberately leave nothing behind. A substituted shot would render
            # and validate exactly like a real one, and ship.
            frame_path.unlink(missing_ok=True)
            failed.append(frame.slug)
        reports.append(report)

    board.meta["shot_reports"] = reports

    # Persist so the shot-inspector API can serve them without a DB round trip.
    # probe_pngs includes the story subdirectory so the GUI can reach them via
    # the already-mounted /videos static mount.
    import json

    story_dir = video_dir.name  # "story-<uuid>"
    (video_dir / "renders").mkdir(parents=True, exist_ok=True)
    (video_dir / "renders" / "shots.json").write_text(
        json.dumps(
            [
                {
                    "slug": r.slug,
                    "ok": r.ok,
                    "attempts": r.attempts,
                    "reason": r.reason,
                    "js": r.js,
                    "probe_pngs": [
                        f"{story_dir}/renders/probes/{png}"
                        for png in r.probe_pngs
                    ],
                }
                for r in reports
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info("3d_frames_built", frames=len(board.frames), failed=len(failed))
    return failed


def cinematic_image_prompt(board, frame) -> str:
    """Turn one board frame into a consistent, image-generation-ready keyframe.

    The storyboard direction is the continuity bible. It is repeated verbatim
    instead of relying on adjacent model calls to remember a character, outfit,
    palette, or world that appeared in an earlier scene.
    """
    direction = board.direction or (
        "Original family-safe finance education short with one warm, expressive "
        "recurring animated guide and a clear visual metaphor."
    )
    return f"""Create one original vertical 9:16 cinematic keyframe for a finance education short.

ART DIRECTION (apply to every scene): premium stylized 3D animated-feature render, expressive original
characters when the scene calls for them, rich miniature-scale environments, physically plausible warm
lighting, readable silhouette, shallow depth of field, polished materials, smooth cinematic framing, and
clear visual storytelling. This must look like a finished film frame, never a presentation slide.

CONTINUITY BIBLE:
{direction}

VIDEO TITLE: {board.title}
SCENE: {frame.scene or frame.title}
NARRATION CONTEXT: {frame.voiceover}

COMPOSITION: choose one decisive visual moment. Leave uncluttered negative space only where captions may
be placed later. Use finance ideas as visual metaphors, not as live market data.

FINANCE VISUAL LANGUAGE: For stock-market scenes, favour original physical worlds: a miniature exchange floor
with glowing abstract price ribbons, a towering candlestick-shaped city with no labels, a balanced scale of
company buildings, or a calm guide observing a market-weather landscape. For investing scenes, favour patient,
long-term metaphors: a diversified garden, sturdy stepping stones, a carefully packed portfolio case, a risk
umbrella, or a growing orchard. Make risk, uncertainty, diversification, and time visible without promising
outcomes. Never depict a "winning" trade, instant wealth, luxury consumption, gambling, panic, or a character
pressing a buy/sell control.

Do not put words, letters, numbers, stock tickers, logos, watermarks, UI panels, or subtitles in the image.
Do not imitate a named studio, franchise, or living artist. The result must be suitable for children, teens,
and young adults."""


_MOTION_INTENT = re.compile(r"^\s*-\s*Frame-to-motion intent:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def motion_intent_of(direction: str) -> str:
    """First `- Frame-to-motion intent:` line in the direction bible, else ""."""
    match = _MOTION_INTENT.search(direction or "")
    return match.group(1).strip() if match else ""


def motion_style(intent: str) -> tuple[str, float]:
    """Map an intent line to (gsap ease, camera-scale boost). Unknown falls back."""
    lowered = (intent or "").lower()
    if "subject" in lowered:
        return ("power1.inOut", 0.0)
    if "energetic" in lowered or "bold" in lowered or "dynamic" in lowered:
        return ("power3.out", 0.01)
    if "gentle" in lowered or "soft" in lowered or "calm" in lowered or "slow" in lowered:
        return ("sine.inOut", -0.01)
    return ("power1.inOut", 0.0)


def render_cinematic_frame(
    slug: str, duration: float, image_src: str, motion_index: int = 1,
    motion_ease: str = "power1.inOut", motion_boost: float = 0.0,
) -> str:
    """Render a generated keyframe with free, deterministic 2.5D motion."""
    camera_paths = (
        (-18, -14, 1.115), (16, -10, 1.13), (-12, 15, 1.12), (18, 12, 1.125),
        (-10, 16, 1.14), (14, 14, 1.11), (-16, 8, 1.135), (10, -16, 1.12),
    )
    pan_x, pan_y, camera_scale = camera_paths[(motion_index - 1) % len(camera_paths)]
    return f"""<!doctype html>
<html lang=\"en\">
  <body>
    <template>
      <style>
        #root {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; background: #08090c; }}
        .stage-fill {{ position: absolute; inset: 0; overflow: hidden; background: #08090c; }}
        .image {{ display: block; width: 100%; height: 100%; object-fit: cover; object-position: center; transform-origin: 50% 50%; will-change: transform; }}
        .depth-backdrop {{ filter: blur(16px) brightness(.72) saturate(.84); transform: scale(1.18); }}
        .hero-image {{ position: absolute; inset: 0; }}
        .atmosphere {{ position: absolute; inset: -12%; pointer-events: none; background: radial-gradient(ellipse at 22% 28%, rgba(255,230,180,.20), transparent 42%), radial-gradient(ellipse at 76% 72%, rgba(115,190,255,.16), transparent 46%); mix-blend-mode: screen; will-change: transform, opacity; }}
        .light-pass {{ position: absolute; inset: -28%; pointer-events: none; background: linear-gradient(112deg, transparent 42%, rgba(255,249,225,.16) 50%, transparent 58%); mix-blend-mode: screen; will-change: transform, opacity; }}
        .vignette {{ position: absolute; inset: 0; pointer-events: none; background: radial-gradient(circle at 50% 42%, transparent 45%, rgba(0,0,0,.28) 100%); }}
      </style>
      <div id=\"root\" data-composition-id=\"{slug}\" data-start=\"0\" data-duration=\"{duration}\" data-width=\"1080\" data-height=\"1920\">
        <div class=\"stage-fill\">
          <img id=\"{slug}-backdrop\" class=\"image depth-backdrop\" src=\"../../{image_src}\" alt=\"\" aria-hidden=\"true\" />
          <img id=\"{slug}-image\" class=\"image hero-image clip\" src=\"../../{image_src}\" alt=\"\" data-start=\"0\" data-duration=\"{duration}\" data-track-index=\"1\" />
          <div id=\"{slug}-atmosphere\" class=\"atmosphere\" aria-hidden=\"true\"></div>
          <div id=\"{slug}-light-pass\" class=\"light-pass\" aria-hidden=\"true\"></div>
          <div class=\"vignette\"></div>
        </div>
      </div>
      <script src=\"https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js\"></script>
      <script>
        window.__timelines = window.__timelines || {{}};
        const tl = gsap.timeline({{ paused: true }});
        tl.fromTo(\"#{slug}-backdrop\", {{ scale: 1.18, x: {pan_x * -0.35}, y: {pan_y * -0.35} }}, {{ scale: 1.28, x: {pan_x * 0.5}, y: {pan_y * 0.5}, duration: {duration}, ease: \"none\" }}, 0);
        tl.fromTo(\"#{slug}-image\", {{ scale: 1.025, x: 0, y: 0 }}, {{ scale: {camera_scale + motion_boost}, x: {pan_x}, y: {pan_y}, duration: {duration}, ease: \"{motion_ease}\" }}, 0);
        tl.fromTo(\"#{slug}-atmosphere\", {{ scale: .96, x: {pan_x * -0.2}, y: {pan_y * -0.15}, opacity: .08 }}, {{ scale: 1.08, x: {pan_x * 0.25}, y: {pan_y * 0.2}, opacity: .38, duration: {duration}, ease: \"sine.inOut\" }}, 0);
        tl.fromTo(\"#{slug}-light-pass\", {{ xPercent: -20, opacity: 0 }}, {{ xPercent: 20, opacity: .42, duration: {duration * 0.72}, ease: \"sine.inOut\" }}, {duration * 0.12});
        window.__timelines[\"{slug}\"] = tl;
      </script>
    </template>
  </body>
</html>
"""


def extract_gemini_image_bytes(response: object) -> bytes:
    """Return the first image part's bytes from a generate_content response."""
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        for part in getattr(candidates[0].content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and str(getattr(inline, "mime_type", "")).startswith("image/"):
                data = inline.data
                return data if isinstance(data, bytes) else base64.b64decode(data)
    finish_reasons = [str(getattr(c, "finish_reason", "")) for c in candidates]
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None) if feedback is not None else None
    raise RuntimeError(
        "cinematic image provider returned no image data "
        f"(finish_reasons={finish_reasons or 'none'}, block_reason={block_reason or 'none'})"
    )


async def _generate_gemini_cinematic_image(prompt: str, destination: Path) -> None:
    """Generate one final-quality keyframe with a Gemini image model."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def call():
        return client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

    last_error: Exception | None = None
    for attempt in range(1, GEMINI_IMAGE_MAX_ATTEMPTS + 1):
        try:
            response = await asyncio.to_thread(call)
            destination.write_bytes(extract_gemini_image_bytes(response))
            return
        except Exception as exc:
            last_error = exc
            log.warning("cinematic_image_retry", attempt=attempt, error=str(exc)[:200])
            if attempt < GEMINI_IMAGE_MAX_ATTEMPTS:
                await asyncio.sleep(min(2 ** attempt, 15))
    raise RuntimeError(
        f"gemini image generation failed after {GEMINI_IMAGE_MAX_ATTEMPTS} attempts: {last_error}"
    )


def _replace_comfy_tokens(value, replacements: dict[str, str | int | float]):
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(f"{{{{{token}}}}}", str(replacement))
        return value
    if isinstance(value, list):
        return [_replace_comfy_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_comfy_tokens(item, replacements) for key, item in value.items()}
    return value


def _comfyui_workflow(prompt: str) -> dict:
    """Create an API-format ComfyUI workflow for a single portrait keyframe.

    A checkpoint workflow is included for the 8 GB RTX 3070 test path. Advanced
    users can export any ComfyUI graph with "Save (API Format)", set its path,
    and use the documented {{PROMPT}}/{{SEED}} token placeholders instead.
    """
    workflow_path = os.environ.get("COMFYUI_WORKFLOW_PATH", "").strip()
    checkpoint = os.environ.get("COMFYUI_CHECKPOINT_NAME", "").strip()
    width = int(os.environ.get("COMFYUI_IMAGE_WIDTH", "768"))
    height = int(os.environ.get("COMFYUI_IMAGE_HEIGHT", "1152"))
    steps = int(os.environ.get("COMFYUI_STEPS", "20"))
    cfg = float(os.environ.get("COMFYUI_CFG", "6.0"))
    seed = int.from_bytes(os.urandom(8), "big") % (2**63 - 1)
    replacements: dict[str, str | int | float] = {
        "PROMPT": prompt,
        "NEGATIVE_PROMPT": "text, letters, numbers, watermark, logo, blurry, distorted anatomy, duplicate subject",
        "SEED": seed,
        "WIDTH": width,
        "HEIGHT": height,
        "CHECKPOINT": checkpoint,
    }
    if workflow_path:
        try:
            custom = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not load COMFYUI_WORKFLOW_PATH: {exc}") from exc
        if not isinstance(custom, dict):
            raise RuntimeError("COMFYUI_WORKFLOW_PATH must contain a ComfyUI API-format JSON object")
        return _replace_comfy_tokens(custom, replacements)
    if not checkpoint:
        raise RuntimeError(
            "COMFYUI_CHECKPOINT_NAME is required for the built-in ComfyUI workflow. "
            "Use the exact filename visible in ComfyUI's checkpoints list."
        )
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": replacements["NEGATIVE_PROMPT"], "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "lamka-cinematic", "images": ["6", 0]}},
    }


async def _generate_comfyui_cinematic_image(prompt: str, destination: Path) -> None:
    """Submit a local ComfyUI workflow, wait for it, then copy its first image."""
    import httpx

    base_url = os.environ["COMFYUI_BASE_URL"].rstrip("/")
    timeout_seconds = float(os.environ.get("COMFYUI_TIMEOUT_SECONDS", "300"))
    workflow = _comfyui_workflow(prompt)
    client_id = f"lamka-{uuid.uuid4().hex}"
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        try:
            response = await client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"ComfyUI could not accept the workflow at {base_url}: {exc}") from exc
        payload = response.json()
        prompt_id = payload.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI rejected the workflow: {payload.get('node_errors') or payload}")

        deadline = time.monotonic() + timeout_seconds
        images: list[dict] = []
        while time.monotonic() < deadline:
            history_response = await client.get(f"/history/{prompt_id}")
            history_response.raise_for_status()
            history = history_response.json().get(prompt_id, {})
            for output in (history.get("outputs") or {}).values():
                images.extend(output.get("images") or [])
            if images:
                break
            if history.get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"ComfyUI workflow failed: {history.get('status')}")
            await asyncio.sleep(1.0)
        if not images:
            raise RuntimeError(f"ComfyUI timed out after {timeout_seconds:g}s without an image")
        image = images[0]
        image_response = await client.get(
            "/view",
            params={"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")},
        )
        image_response.raise_for_status()
        destination.write_bytes(image_response.content)


async def _generate_cinematic_image(prompt: str, destination: Path, provider: str | None = None) -> None:
    """Generate one keyframe through the explicitly selected image provider."""
    selected = require_cinematic_image_provider(provider)
    if selected == "gemini":
        await _generate_gemini_cinematic_image(prompt, destination)
        return
    await _generate_comfyui_cinematic_image(prompt, destination)


async def _build_cinematic_frames_inner(
    board,
    video_dir: Path,
    selected: str,
    on_frame_complete: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[str]:
    frames_dir = video_dir / "compositions" / "frames"
    assets_dir = video_dir / "assets" / "cinematic"
    frames_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    total_frames = len(board.frames)
    ease, boost = motion_style(motion_intent_of(board.direction))
    for completed, frame in enumerate(board.frames, start=1):
        image_src = f"assets/cinematic/{frame.slug}.png"
        image_path = video_dir / image_src
        await _generate_cinematic_image(cinematic_image_prompt(board, frame), image_path, selected)
        (frames_dir / f"{frame.slug}.html").write_text(
            render_cinematic_frame(frame.slug, frame.duration, image_src, completed, ease, boost),
            encoding="utf-8",
        )
        if on_frame_complete:
            await on_frame_complete(completed, total_frames)

    log.info("cinematic_frames_built", frames=len(board.frames), provider=selected, model=GEMINI_IMAGE_MODEL)
    return []


async def build_cinematic_frames(
    board,
    video_dir: Path,
    provider: str | None = None,
    on_frame_complete: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[str]:
    """Build image-led portrait scenes without ever substituting a fallback frame.

    A missing or failed keyframe is a content-quality failure, not a reason to
    send a title card to render. The caller therefore receives an exception and
    the job stops with an actionable error.
    """
    selected = require_cinematic_image_provider(provider)
    if selected == "comfyui":
        async with gpu.slot:
            return await _build_cinematic_frames_inner(board, video_dir, selected, on_frame_complete)
    return await _build_cinematic_frames_inner(board, video_dir, selected, on_frame_complete)
