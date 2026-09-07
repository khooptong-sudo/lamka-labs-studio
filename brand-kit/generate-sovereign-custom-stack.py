"""Custom stacked wordmark: Lamka (Prata) + Labs (Prata red) / Studio (Grand Hotel).

Layout: seal left, stacked wordmark right, everything centered as a group.
Studio is scaled so its width matches "Lamka Labs" and aligns with the L.
Also generates logo-only variants in the same folder.
Backgrounds: transparent, black, white.
Palette: black, white, red only.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
OUT_DIR = BASE / "09-sovereign-custom-stack"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BLACK = (10, 10, 10)
WHITE = (245, 245, 240)
RED = (200, 16, 46)

FONT_PATHS = {
    "prata": str(BASE / "fonts" / "prata.ttf"),
    "grandhotel": str(BASE / "fonts" / "grandhotel.ttf"),
}


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_PATHS[font_name]
    if not Path(path).exists():
        raise FileNotFoundError(f"Font not found: {path}")
    font = ImageFont.truetype(path, size)
    try:
        axes = font.get_variation_axes()
    except Exception:
        axes = []
    if axes:
        values = []
        for axis in axes:
            name = axis.get("name", b"").decode("ascii", errors="ignore")
            values.append(400 if name == "Weight" else axis["default"])
        font.set_variation_by_axes(values)
    return font


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_font_width(
    draw: ImageDraw.ImageDraw,
    font_name: str,
    text: str,
    target_width: int,
    min_size: int = 10,
    max_size: int = 600,
) -> ImageFont.FreeTypeFont:
    """Find a font size so the text is close to target_width."""
    best_font = load_font(font_name, min_size)
    best_diff = abs(text_size(draw, text, best_font)[0] - target_width)

    lo, hi = min_size, max_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = load_font(font_name, mid)
        w = text_size(draw, text, font)[0]
        diff = abs(w - target_width)
        if diff < best_diff:
            best_diff = diff
            best_font = font
        if w < target_width:
            lo = mid + 1
        else:
            hi = mid - 1
    return best_font


def draw_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    r = int(size * 0.30)
    sw_ring = max(2, int(size * 0.014))
    sw_stem = max(6, int(size * 0.034))
    sw_accent = max(2, int(sw_ring * 1.5))

    ring2 = RED if color == WHITE else color
    accent = RED if color == WHITE else color

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=sw_ring)
    draw.ellipse(
        [cx - r + size * 0.045, cy - r + size * 0.045, cx + r - size * 0.045, cy + r - size * 0.045],
        outline=ring2,
        width=sw_ring,
    )

    stem_h = int(r * 1.15)
    top = cy - stem_h // 2
    bottom = top + stem_h
    draw.line([(cx, top), (cx, bottom)], fill=color, width=sw_stem)

    y1 = cy + int(r * 0.05)
    x_left = cx - int(r * 0.55)
    draw.line([(cx, y1), (x_left, y1)], fill=color, width=sw_stem)

    y2 = cy + int(r * 0.35)
    x_right = cx + int(r * 0.55)
    draw.line([(cx, y2), (x_right, y2)], fill=color, width=sw_stem)

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


def new_canvas(width: int, height: int, bg: str) -> Image.Image:
    if bg == "transparent":
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if bg == "black":
        return Image.new("RGBA", (width, height), (*BLACK, 255))
    return Image.new("RGBA", (width, height), (*WHITE, 255))


def save(img: Image.Image, name: str) -> None:
    img.save(OUT_DIR / f"{name}.png", "PNG")
    bg = Image.new("RGBA", img.size, (*WHITE, 255))
    composite = Image.alpha_composite(bg, img).convert("RGB")
    composite.save(OUT_DIR / f"{name}.jpg", "JPEG", quality=95)


def draw_custom_stack(draw: ImageDraw.ImageDraw, width: int, height: int, main_color: tuple) -> None:
    seal_size = int(height * 0.42)
    gap = int(height * 0.05)

    prata_size = int(height * 0.17)
    prata = load_font("prata", prata_size)

    lamka_w, lamka_h = text_size(draw, "Lamka", prata)
    labs_w, labs_h = text_size(draw, "Labs", prata)
    space = int(prata_size * 0.18)
    line1_w = lamka_w + space + labs_w
    line1_h = max(lamka_h, labs_h)

    # Scale "Studio" so it spans exactly the width of "Lamka Labs"
    hotel = fit_font_width(draw, "grandhotel", "Studio", line1_w, min_size=20, max_size=600)
    studio_w, studio_h = text_size(draw, "Studio", hotel)

    line_gap = int(height * 0.01)
    text_block_w = max(line1_w, studio_w)
    text_block_h = line1_h + line_gap + studio_h

    group_w = seal_size + gap + text_block_w
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, main_color)

    text_block_top = height // 2 - text_block_h // 2
    text_block_left = group_left + seal_size + gap

    line1_y = text_block_top
    lamka_x = text_block_left
    labs_x = lamka_x + lamka_w + space
    draw.text((lamka_x, line1_y), "Lamka", font=prata, fill=main_color)
    draw.text((labs_x, line1_y), "Labs", font=prata, fill=RED)

    # Studio aligned to start at the L of Lamka and end at the s of Labs
    line2_y = line1_y + line1_h + line_gap
    draw.text((text_block_left, line2_y), "Studio", font=hotel, fill=main_color)


def draw_logo_only(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    seal_size = int(min(width, height) * 0.46)
    cx = width // 2
    cy = height // 2
    draw_seal(draw, cx, cy, seal_size, color)


def build() -> None:
    combos = [
        ("transparent", "black", BLACK),
        ("transparent", "white", WHITE),
        ("transparent", "red", RED),
        ("black-bg", "white", WHITE),
        ("black-bg", "red", RED),
        ("white-bg", "black", BLACK),
        ("white-bg", "red", RED),
    ]

    # Logo-only square assets
    for bg, color_name, color in combos:
        img = new_canvas(1080, 1080, bg.replace("-bg", ""))
        draw = ImageDraw.Draw(img)
        draw_logo_only(draw, 1080, 1080, color)
        save(img, f"logo-only_{bg}_{color_name}")
        print(f"OK logo-only {bg} {color_name}")

    # Custom stacked wordmark assets
    for bg, color_name, color in combos:
        img = new_canvas(1920, 720, bg.replace("-bg", ""))
        draw = ImageDraw.Draw(img)
        draw_custom_stack(draw, 1920, 720, color)
        save(img, f"custom-stack_{bg}_{color_name}")
        print(f"OK custom-stack {bg} {color_name}")


if __name__ == "__main__":
    build()
    print(f"\nAssets written to {OUT_DIR}")
