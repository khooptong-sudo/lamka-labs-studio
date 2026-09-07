"""Generate refined Sovereign Studio Seal assets.

Palette: black, white, red only.
Backgrounds: transparent, black, white.
Variants: logo only + logo with "LAMKA LABS STUDIO" in 6 fonts.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
OUT_DIR = BASE / "06-sovereign-refined"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Palette
BLACK = (10, 10, 10)
WHITE = (245, 245, 240)
RED = (200, 16, 46)

# Font files (Windows Python cannot resolve Git-Bash /tmp or /c/... paths)
FONT_PATHS = {
    "fraunces": str(BASE / "fonts" / "Fraunces-Regular.ttf"),
    "georgia": "C:/Windows/Fonts/georgia.ttf",
    "times": "C:/Windows/Fonts/times.ttf",
    "arial": "C:/Windows/Fonts/arial.ttf",
    "century": "C:/Windows/Fonts/CENTURY.TTF",
    "calibri": "C:/Windows/Fonts/calibri.ttf",
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def draw_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, ring1: tuple, ring2: tuple, stem: tuple, accent: tuple) -> None:
    """Draw the sovereign seal mark centered at (cx, cy) with diameter ~size."""
    r = int(size * 0.30)
    sw_ring = max(2, int(size * 0.016))
    sw_stem = max(6, int(size * 0.038))
    sw_accent = max(2, int(sw_ring * 1.4))

    # Double ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring1, width=sw_ring)
    draw.ellipse([cx - r + size * 0.045, cy - r + size * 0.045, cx + r - size * 0.045, cy + r - size * 0.045], outline=ring2, width=sw_ring)

    # Shared stem LL
    stem_h = int(r * 1.15)
    top = cy - stem_h // 2
    bottom = top + stem_h
    draw.line([(cx, top), (cx, bottom)], fill=stem, width=sw_stem)

    # Left L arm
    y1 = cy + int(r * 0.05)
    x_left = cx - int(r * 0.55)
    draw.line([(cx, y1), (x_left, y1)], fill=stem, width=sw_stem)

    # Right L arm
    y2 = cy + int(r * 0.35)
    x_right = cx + int(r * 0.55)
    draw.line([(cx, y2), (x_right, y2)], fill=stem, width=sw_stem)

    # S curve at bottom
    curve_y = cy + int(r * 0.58)
    cp_y = cy + int(r * 0.78)
    left_x = cx - int(r * 0.22)
    right_x = cx + int(r * 0.22)
    # Draw curve as a series of points
    points = []
    for t in range(0, 101):
        t_ = t / 100
        # Quadratic bezier from left to right via control point below
        x = int((1 - t_) ** 2 * left_x + 2 * (1 - t_) * t_ * cx + t_**2 * right_x)
        y = int((1 - t_) ** 2 * curve_y + 2 * (1 - t_) * t_ * cp_y + t_**2 * curve_y)
        points.append((x, y))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=accent, width=sw_accent)


def make_image(width: int, height: int, bg: str, logo_color: tuple, text_color: tuple | None, font_name: str | None) -> Image.Image:
    """Create one composition."""
    if bg == "transparent":
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    elif bg == "black":
        img = Image.new("RGBA", (width, height), (*BLACK, 255))
    else:  # white
        img = Image.new("RGBA", (width, height), (*WHITE, 255))

    draw = ImageDraw.Draw(img)

    seal_size = min(width, height) * (0.55 if text_color is None else 0.42)
    if text_color is None:
        # Logo only, center
        cx = width // 2
        cy = height // 2
    else:
        # Logo left, text right
        cx = int(width * 0.22)
        cy = height // 2

    draw_seal(
        draw,
        cx,
        cy,
        int(seal_size),
        ring1=logo_color,
        ring2=RED if logo_color == WHITE else logo_color,
        stem=logo_color,
        accent=RED if logo_color == WHITE else logo_color,
    )

    if text_color is not None and font_name is not None:
        text = "LAMKA LABS STUDIO"
        font_path = FONT_PATHS[font_name]
        font_size = int(height * 0.13)
        if not Path(font_path).exists():
            raise FileNotFoundError(f"Font not found: {font_path}")
        font = ImageFont.truetype(font_path, font_size)

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        # Sanity check: default font falls back to ~10 px regardless of requested size
        if text_h < font_size * 0.5:
            raise RuntimeError(
                f"Font {font_name!r} rendered at unexpected height {text_h}px "
                f"(requested {font_size}px); check the font file."
            )
        text_x = int(width * 0.42)
        text_y = cy - text_h // 2
        draw.text((text_x, text_y), text, font=font, fill=text_color)

    return img


def save(img: Image.Image, name: str) -> None:
    # PNG preserves alpha
    img.save(OUT_DIR / f"{name}.png", "PNG")
    # JPEG needs a solid background; composite onto white if transparent
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (*WHITE, 255))
        composite = Image.alpha_composite(bg, img).convert("RGB")
    else:
        composite = img.convert("RGB")
    composite.save(OUT_DIR / f"{name}.jpg", "JPEG", quality=95)


def build_logo_only() -> None:
    size = 1080
    combos = [
        ("transparent", "black", BLACK),
        ("transparent", "red", RED),
        ("black-bg", "white", WHITE),
        ("black-bg", "red", RED),
        ("white-bg", "black", BLACK),
        ("white-bg", "red", RED),
    ]

    for bg, color_name, color in combos:
        img = make_image(size, size, bg.replace("-bg", ""), color, None, None)
        save(img, f"logo-only_{bg}_{color_name}")
        print(f"OK logo-only {bg} {color_name}")


def build_logo_with_text() -> None:
    width, height = 1600, 640
    combos = [
        ("transparent", "black", BLACK),
        ("transparent", "red", RED),
        ("black-bg", "white", WHITE),
        ("black-bg", "red", RED),
        ("white-bg", "black", BLACK),
        ("white-bg", "red", RED),
    ]

    for bg, color_name, color in combos:
        for font_name in FONT_PATHS:
            img = make_image(width, height, bg.replace("-bg", ""), color, color, font_name)
            save(img, f"logo-text_{bg}_{color_name}_{font_name}")
            print(f"OK logo-text {bg} {color_name} {font_name}")


if __name__ == "__main__":
    build_logo_only()
    build_logo_with_text()
    print(f"\nAssets written to {OUT_DIR}")
