"""Generate subtle animated GIF reveals for each logo concept."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).parent / "assets"
OUT = ASSETS


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def make_fade_gif(png_path: Path, out_path: Path, frames: int = 36, hold: int = 24) -> None:
    base = Image.open(png_path).convert("RGBA")
    bg = Image.new("RGBA", base.size, (10, 10, 10, 255))
    gif_frames = []

    for i in range(frames):
        t = ease(i / (frames - 1))
        overlay = Image.new("RGBA", base.size, (10, 10, 10, int((1 - t) * 255)))
        frame = Image.alpha_composite(base, overlay)
        gif_frames.append(frame.convert("RGB"))

    for _ in range(hold):
        gif_frames.append(base.convert("RGB"))

    # Append reversed fade for seamless loop
    for i in range(frames - 1, -1, -1):
        t = ease(i / (frames - 1))
        overlay = Image.new("RGBA", base.size, (10, 10, 10, int((1 - t) * 255)))
        frame = Image.alpha_composite(base, overlay)
        gif_frames.append(frame.convert("RGB"))

    gif_frames[0].save(
        out_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=60,
        loop=0,
        optimize=True,
    )


def make_shimmer_gif(png_path: Path, out_path: Path, frames: int = 40) -> None:
    base = Image.open(png_path).convert("RGBA")
    w, h = base.size
    gif_frames = []

    for i in range(frames):
        t = i / frames
        sweep = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(sweep)
        # Diagonal white sheen band
        offset = -w + int((w * 2.4) * t)
        pts = [
            (offset, 0),
            (offset + w * 0.18, 0),
            (offset + w * 0.58, h),
            (offset + w * 0.40, h),
        ]
        draw.polygon(pts, fill=(255, 255, 255, 22))
        frame = Image.alpha_composite(base, sweep)
        gif_frames.append(frame.convert("RGB"))

    gif_frames[0].save(
        out_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=70,
        loop=0,
        optimize=True,
    )


for concept in ["01-aperture", "02-frame", "03-prism", "04-node", "05-seal", "06-sovereign"]:
    png = ASSETS / f"{concept}-social.png"
    make_shimmer_gif(png, OUT / f"{concept}-social.gif")
    print(f"OK {concept}-social.gif")

print(f"\nGIFs written to {OUT}")
