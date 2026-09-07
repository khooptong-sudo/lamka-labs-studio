"""Assemble a motion-mode 3D Short with one ffmpeg pass, bypassing HyperFrames.

Motion scenes are already normalized per-scene MP4s of exactly
``frame.duration`` seconds (see motion.normalize_clip), so the headless-Chrome
HyperFrames capture — MJPEG intermediate, ~25-40 min on the VPS — adds nothing
essential. This module concats the clips in board order, bakes the
composition's atmosphere/vignette look into one overlay PNG, muxes every
frame's narration at the same offsets render_index_html computes, and writes
the same ``renders/video.mp4`` the HyperFrames path writes, so downstream
thumbnails and draft registration are untouched.
"""

from __future__ import annotations

import asyncio
import math
import subprocess
from pathlib import Path

import structlog

from app.storyboard import BGM_VOLUME

log = structlog.get_logger()

ASSEMBLE_TIMEOUT_SECONDS = 600.0
OUTPUT_RELATIVE = Path("renders") / "video.mp4"
OVERLAY_RELATIVE = Path("assets") / "cinematic" / "_motion_overlay.png"
AUDIO_BITRATE = "192k"

# Geometry of every normalized clip and of the final render.
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Overlay look, mirrored from render_cinematic_motion_frame's CSS: warm glow
# rgba(255,230,180,.20) centered at 22%,28%; cool glow rgba(115,190,255,.16)
# at 76%,72%; vignette rgba(0,0,0,.28) from transparent at 45% out to the edges.
_WARM_GLOW = (255, 230, 180, 51)  # alpha .20 * 255
_COOL_GLOW = (115, 190, 255, 41)  # alpha .16 * 255
_VIGNETTE = (0, 0, 0, 71)  # alpha .28 * 255
_VIGNETTE_INNER = 0.45  # transparent inside this fraction of the radius


def _radial_alpha(radius_x: int, radius_y: int, color: tuple[int, int, int, int], *, inverted: bool) -> "object":
    """RGBA blob fading between center and edge, as a Pillow image."""
    from PIL import Image

    mask = Image.radial_gradient("L").resize(
        (max(2, radius_x * 2), max(2, radius_y * 2)), Image.Resampling.BILINEAR
    )
    if inverted:
        mask = mask.point(lambda a: 255 - a)
    mask = mask.point(lambda a: a * color[3] // 255)
    blob = Image.new("RGBA", mask.size, color[:3] + (0,))
    blob.putalpha(mask)
    return blob


def bake_overlay_png(destination: Path) -> None:
    """Bake the atmosphere glows + vignette into one 1080x1920 RGBA PNG."""
    from PIL import Image

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    warm = _radial_alpha(int(0.42 * WIDTH), int(0.42 * WIDTH), _WARM_GLOW, inverted=True)
    canvas.alpha_composite(warm, (int(0.22 * WIDTH) - warm.width // 2, int(0.28 * HEIGHT) - warm.height // 2))
    cool = _radial_alpha(int(0.46 * WIDTH), int(0.46 * WIDTH), _COOL_GLOW, inverted=True)
    canvas.alpha_composite(cool, (int(0.76 * WIDTH) - cool.width // 2, int(0.72 * HEIGHT) - cool.height // 2))

    # Vignette: transparent inside 45% of the radius, ramping to .28 black at
    # the radius, which is sized to reach the farthest corner.
    cx, cy = WIDTH // 2, int(0.42 * HEIGHT)
    radius = int(
        max(math.hypot(x - cx, y - cy) for x in (0, WIDTH) for y in (0, HEIGHT))
    )
    ramp = Image.radial_gradient("L").resize((radius * 2, radius * 2), Image.Resampling.BILINEAR)
    inner = int(_VIGNETTE_INNER * 255)
    span = 255 - inner
    ramp = ramp.point(lambda a: max(0, a - inner) * _VIGNETTE[3] // span)
    vignette = Image.new("RGBA", ramp.size, _VIGNETTE[:3] + (0,))
    vignette.putalpha(ramp)
    canvas.alpha_composite(vignette, (cx - radius, cy - radius))

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG")


def _adelay_ms(frame) -> int:
    """Voice offset exactly as render_index_html computes the audio start."""
    return int(round((frame.start + frame.voice_offset) * 1000))


def build_ffmpeg_command(board, video_dir: Path, with_bgm: bool, overlay_path: Path) -> list[str]:
    """List-form ffmpeg command: concat clips, overlay look, mux narration+bgm."""
    frames = list(board.frames)
    total = board.total_duration

    bgm_path = video_dir / "bgm.mp3"
    if with_bgm and not bgm_path.exists():
        raise FileNotFoundError(f"bgm requested for assembly but missing: {bgm_path}")

    clip_paths = [video_dir / "assets" / "cinematic" / f"{frame.slug}.mp4" for frame in frames]
    voice_paths = [video_dir / frame.voice_filename for frame in frames]
    for clip, voice in zip(clip_paths, voice_paths):
        if not clip.exists():
            raise FileNotFoundError(f"motion clip missing for assembly: {clip}")
        if not voice.exists():
            raise FileNotFoundError(f"narration missing for assembly: {voice}")

    n = len(frames)
    overlay_index = n
    voice_base = n + 1
    bgm_index = voice_base + n

    filters: list[str] = []
    filters.append("".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    filters.append(f"[cat][{overlay_index}:v]overlay=0:0[vout]")
    for i, frame in enumerate(frames):
        filters.append(f"[{voice_base + i}:a]adelay={_adelay_ms(frame)}:all=1[v{i}]")
    filters.append(
        "".join(f"[v{i}]" for i in range(n))
        + f"amix=inputs={n}:normalize=0:dropout_transition=0[vo]"
    )
    if with_bgm:
        filters.append(
            f"[{bgm_index}:a]atrim=0:{total:.3f},volume={BGM_VOLUME},asetpts=PTS-STARTPTS[bg]"
        )
        filters.append("[vo][bg]amix=inputs=2:normalize=0:dropout_transition=0[aout]")
    else:
        filters.append("[vo]anull[aout]")

    command = ["ffmpeg", "-y"]
    for clip in clip_paths:
        command += ["-i", str(clip)]
    command += ["-i", str(overlay_path)]
    for voice in voice_paths:
        command += ["-i", str(voice)]
    if with_bgm:
        command += ["-stream_loop", "-1", "-i", str(video_dir / "bgm.mp3")]
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-movflags", "+faststart",
        str(video_dir / OUTPUT_RELATIVE),
    ]
    return command


async def assemble_motion_video(board, video_dir: Path, with_bgm: bool) -> Path:
    """Assemble the final renders/video.mp4 for a motion build. Returns its path."""
    overlay_path = video_dir / OVERLAY_RELATIVE
    await asyncio.to_thread(bake_overlay_png, overlay_path)
    command = build_ffmpeg_command(board, video_dir, with_bgm, overlay_path)

    output = video_dir / OUTPUT_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    result = await asyncio.to_thread(
        subprocess.run, command, capture_output=True, text=True,
        timeout=ASSEMBLE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg motion assembly failed (exit {result.returncode}): "
            f"{(result.stderr or '')[-500:]}"
        )
    log.info(
        "motion_video_assembled",
        frames=len(board.frames),
        with_bgm=with_bgm,
        output=str(output),
    )
    return output
