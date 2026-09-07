"""Generate centered, polished Sovereign Studio Seal assets.

Palette: black, white, red only.
Backgrounds: transparent, black, white.
Variants: logo only + logo with "LAMKA LABS STUDIO" in 6 professional fonts.
Layout: seal and wordmark are centered as a single group, with a tight gap.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
OUT_DIR = BASE / "07-sovereign-centered"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Palette
BLACK = (10, 10, 10)
WHITE = (245, 245, 240)
RED = (200, 16, 46)

# Professional font files (all repo-local or Windows system)
FONT_PATHS = {
    "fraunces": str(BASE / "fonts" / "Fraunces-Regular.ttf"),
    "montserrat": str(BASE / "fonts" / "montserrat.ttf"),
    "playfair": str(BASE / "fonts" / "playfair.ttf"),
    "cormorant": str(BASE / "fonts" / "cormorant.ttf"),
    "inter": str(BASE / "fonts" / "inter.ttf"),
    "bodoni": str(BASE / "fonts" / "bodoni.ttf"),
}


def draw_seal(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    size: int,
    ring1: tuple,
    ring2: tuple,
    stem: tuple,
    accent: tuple,
) -> None:
    """Draw the sovereign seal mark centered at (cx, cy) with diameter ~size."""
    r = int(size * 0.30)
    sw_ring = max(2, int(size * 0.014))
    sw_stem = max(6, int(size * 0.034))
    sw_accent = max(2, int(sw_ring * 1.5))

    # Double ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring1, width=sw_ring)
    draw.ellipse(
        [cx - r + size * 0.045, cy - r + size * 0.045, cx + r - size * 0.045, cy + r - size * 0.045],
        outline=ring2,
        width=sw_ring,
    )

    # Shared vertical stem (L + L)
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
    points = []
    for t in range(0, 101):
        t_ = t / 100
        x = int((1 - t_) ** 2 * left_x + 2 * (1 - t_) * t_ * cx + t_**2 * right_x)
        y = int((1 - t_) ** 2 * curve_y + 2 * (1 - t_) * t_ * cp_y + t_**2 * curve_y)
        points.append((x, y))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=accent, width=sw_accent)


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_PATHS[font_name]
    if not Path(path).exists():
        raise FileNotFoundError(f"Font not found: {path}")
    font = ImageFont.truetype(path, size)

    # Normalize variable fonts to a standard Regular (wght=400) weight so we don't
    # accidentally render Thin or Light defaults.
    try:
        axes = font.get_variation_axes()
    except Exception:
        axes = []
    if axes:
        values = []
        for axis in axes:
            name = axis.get("name", b"").decode("ascii", errors="ignore")
            if name == "Weight":
                values.append(400)
            else:
                values.append(axis["default"])
        font.set_variation_by_axes(values)

    # Sanity check against silent default-font fallback
    bbox = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), "LAMKA", font=font)
    height = bbox[3] - bbox[1]
    if height < size * 0.4:
        raise RuntimeError(f"Font {font_name!r} rendered too small ({height}px); check the file.")
    return font


def make_image(
    width: int,
    height: int,
    bg: str,
    logo_color: tuple,
    text_color: tuple | None,
    font_name: str | None,
) -> Image.Image:
    """Create one composition with the seal and wordmark centered as a group."""
    if bg == "transparent":
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    elif bg == "black":
        img = Image.new("RGBA", (width, height), (*BLACK, 255))
    else:  # white
        img = Image.new("RGBA", (width, height), (*WHITE, 255))

    draw = ImageDraw.Draw(img)

    if text_color is None:
        # Logo only: center in frame
        seal_size = int(min(width, height) * 0.46)
        cx = width // 2
        cy = height // 2
    else:
        # Logo + wordmark: center the group
        seal_size = int(height * 0.44)
        font_size = int(height * 0.20)
        font = load_font(font_name, font_size)

        text = "LAMKA LABS STUDIO"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        gap = int(height * 0.055)  # tight, balanced gap
        group_w = seal_size + gap + text_w
        group_left = (width - group_w) // 2

        cx = group_left + seal_size // 2
        cy = height // 2

        text_x = group_left + seal_size + gap
        text_y = cy - text_h // 2 - bbox[1]
        draw.text((text_x, text_y), text, font=font, fill=text_color)

    draw_seal(
        draw,
        cx,
        cy,
        seal_size,
        ring1=logo_color,
        ring2=RED if logo_color == WHITE else logo_color,
        stem=logo_color,
        accent=RED if logo_color == WHITE else logo_color,
    )

    return img


def save(img: Image.Image, name: str) -> None:
    img.save(OUT_DIR / f"{name}.png", "PNG")
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
    width, height = 1920, 720
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
