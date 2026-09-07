"""Render Ken Burns scene clips from keyframe PNGs with ffmpeg zoompan.

The cinematic "motion off" composition (``backend.render_cinematic_frame``)
is a static keyframe under a GSAP scale+pan tween plus atmosphere/light-pass/
vignette overlays. ``zoompan`` reproduces the tween deterministically — same
camera paths, same easing, same endpoints — and ``assemble.bake_overlay_png``
already bakes the atmosphere glows and vignette into an overlay, so feeding
the clips through the existing motion assembly writes the same
``renders/video.mp4`` the HyperFrames capture writes, in about a minute
instead of the ~25-40 min headless-Chrome render.

Geometry, mirroring the composition contract:
- The keyframe is cover-fitted to a 2x canvas (2160x3840) so zoompan's
  integer window math stays smooth, then pre-cropped by the hero's minimum
  GSAP scale (1.025). That bake is what lets zoompan's z start exactly at 1
  instead of zooming out past the frame (z < 1 shows black borders).
- The GSAP tween runs scale 1.025 -> camera_scale (+boost) and translation
  0 -> (pan_x, pan_y) in 1080x1920 CSS px; here z = scale / 1.025 and the
  pan is doubled into canvas px, divided by z to track the zooming window.
- Easing: motion_style's power1.inOut/sine.inOut map to a cosine inOut,
  power3.out to cubic out, evaluated per output frame.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import structlog

from app.scene3d.assemble import FPS, HEIGHT, WIDTH, assemble_motion_video
from app.scene3d.backend import motion_intent_of, motion_style

log = structlog.get_logger()

RENDER_TIMEOUT_SECONDS = 300.0
CLIP_TIMEOUT_SECONDS = 300.0
MAX_PARALLEL_CLIPS = 3

CANVAS_SCALE = 2
CANVAS_WIDTH = WIDTH * CANVAS_SCALE
CANVAS_HEIGHT = HEIGHT * CANVAS_SCALE
MIN_SCALE = 1.025  # hero's starting GSAP scale in render_cinematic_frame

# Mirror of render_cinematic_frame's camera_paths (pan_x, pan_y, end scale),
# indexed by 1-based board position. Keep in sync with backend.py.
CAMERA_PATHS = (
    (-18, -14, 1.115),
    (16, -10, 1.13),
    (-12, 15, 1.12),
    (18, 12, 1.125),
    (-10, 16, 1.14),
    (14, 14, 1.11),
    (-16, 8, 1.135),
    (10, -16, 1.12),
)


def _ease(progress: str, ease: str) -> str:
    """Per-frame eased progress expression; ``progress`` is ``on/<d>``."""
    if ease == "power3.out":
        return f"(1-(1-{progress})*(1-{progress})*(1-{progress}))"
    # power1.inOut and sine.inOut are both matched by a cosine inOut.
    return f"((1-cos(PI*{progress}))/2)"


def build_kenburns_filter(duration: float, motion_index: int, ease: str, boost: float) -> str:
    """Filter chain reproducing one frame's GSAP tween with zoompan."""
    pan_x, pan_y, camera_scale = CAMERA_PATHS[(motion_index - 1) % len(CAMERA_PATHS)]
    frames = max(1, int(round(duration * FPS)))
    z1 = (camera_scale + boost) / MIN_SCALE
    progress = f"on/{frames}"
    eased = _ease(progress, ease)
    z = f"1+{z1 - 1:.6f}*{eased}"
    # GSAP moves the content by (pan_x, pan_y); the zoom window moves the
    # opposite way, in canvas px, tracking the current zoom. Inside zoompan
    # expressions the current zoom value is `zoom`, not `z`.
    x = f"(iw-iw/zoom)/2+({-pan_x * CANVAS_SCALE:.3f}*{eased})/zoom"
    y = f"(ih-ih/zoom)/2+({-pan_y * CANVAS_SCALE:.3f}*{eased})/zoom"
    pre_width = round(CANVAS_WIDTH / MIN_SCALE)
    pre_height = round(CANVAS_HEIGHT / MIN_SCALE)
    return (
        f"scale={CANVAS_WIDTH}:{CANVAS_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={CANVAS_WIDTH}:{CANVAS_HEIGHT},"
        f"crop={pre_width}:{pre_height},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )


def build_kenburns_command(
    png_path: Path, destination: Path, duration: float,
    motion_index: int, ease: str, boost: float,
) -> list[str]:
    frames = max(1, int(round(duration * FPS)))
    return [
        "ffmpeg", "-y",
        "-i", str(png_path),
        "-vf", build_kenburns_filter(duration, motion_index, ease, boost),
        "-frames:v", str(frames),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "16",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        str(destination),
    ]


def render_kenburns_clip(
    png_path: Path, destination: Path, duration: float,
    motion_index: int, ease: str, boost: float,
) -> None:
    """Blocking single-scene render; run via asyncio.to_thread."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        build_kenburns_command(png_path, destination, duration, motion_index, ease, boost),
        capture_output=True, text=True, timeout=CLIP_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg ken burns clip failed (exit {result.returncode}): "
            f"{(result.stderr or '')[-500:]}"
        )


async def render_kenburns_clips(board, video_dir: Path, ease: str, boost: float) -> None:
    """Render every scene's clip; concurrent renders bounded for the CPU encoder."""
    semaphore = asyncio.Semaphore(MAX_PARALLEL_CLIPS)

    async def one(motion_index: int, frame) -> None:
        png_path = video_dir / "assets" / "cinematic" / f"{frame.slug}.png"
        destination = video_dir / "assets" / "cinematic" / f"{frame.slug}.mp4"
        if destination.exists():
            # A retried build reuses clips that already rendered, mirroring
            # the motion path's clip reuse.
            log.info("kenburns_clip_reused", slug=frame.slug)
            return
        if not png_path.exists():
            raise FileNotFoundError(f"ken burns keyframe missing: {png_path}")
        async with semaphore:
            await asyncio.to_thread(
                render_kenburns_clip, png_path, destination, frame.duration,
                motion_index, ease, boost,
            )
            log.info("kenburns_clip_rendered", slug=frame.slug, duration=frame.duration)

    await asyncio.gather(*(one(i, frame) for i, frame in enumerate(board.frames, start=1)))


async def assemble_kenburns_video(board, video_dir: Path, with_bgm: bool) -> Path:
    """Render Ken Burns clips from the keyframes, then the usual ffmpeg assembly.

    The easing/boost come from the same motion_style(motion_intent_of(...))
    call the composition builder uses, so the motion matches the HTML
    compositions frame for frame.
    """
    ease, boost = motion_style(motion_intent_of(board.direction))
    await asyncio.wait_for(render_kenburns_clips(board, video_dir, ease, boost), timeout=RENDER_TIMEOUT_SECONDS)
    return await assemble_motion_video(board, video_dir, with_bgm)
