"""Generate designed wordmark lockups for the Sovereign Studio Seal.

Each iteration is a distinct typographic treatment (not just a different font).
Palette: black, white, red only.
Backgrounds: transparent, black, white.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
OUT_DIR = BASE / "08-sovereign-wordmark"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BLACK = (10, 10, 10)
WHITE = (245, 245, 240)
RED = (200, 16, 46)

FONT_PATHS = {
    "fraunces": str(BASE / "fonts" / "Fraunces-Regular.ttf"),
    "montserrat": str(BASE / "fonts" / "montserrat.ttf"),
    "playfair": str(BASE / "fonts" / "playfair.ttf"),
    "cormorant": str(BASE / "fonts" / "cormorant.ttf"),
    "inter": str(BASE / "fonts" / "inter.ttf"),
    "bodoni": str(BASE / "fonts" / "bodoni.ttf"),
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


def draw_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple) -> None:
    """Draw the sovereign seal mark centered at (cx, cy)."""
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


# ---------------------------------------------------------------------------
# Wordmark treatments
# ---------------------------------------------------------------------------


def treatment_tracking(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Wide-tracked all-caps sans with a thin rule above the text."""
    seal_size = int(height * 0.40)
    font_size = int(height * 0.14)
    font = load_font("montserrat", font_size)
    text = "LAMKA LABS STUDIO"
    tracking = int(font_size * 0.14)

    # Measure total width with custom tracking
    total_text_w = sum(int(font.getlength(ch)) for ch in text) + tracking * (len(text) - 1)
    _, text_h = text_size(draw, text, font)
    gap = int(height * 0.06)
    group_w = seal_size + gap + total_text_w
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    text_y = height // 2 - text_h // 2
    x = group_left + seal_size + gap
    for ch in text:
        draw.text((x, text_y), ch, font=font, fill=color)
        x += int(font.getlength(ch)) + tracking

    # Thin rule above text, aligned with cap height
    rule_y = text_y + int(text_h * 0.05)
    rule_x1 = group_left + seal_size + gap
    rule_x2 = rule_x1 + total_text_w
    sw = max(1, int(height * 0.004))
    draw.line([(rule_x1, rule_y), (rule_x2, rule_y)], fill=RED if color == WHITE else color, width=sw)


def treatment_stacked(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Two-line serif stack with a thin rule between the lines."""
    seal_size = int(height * 0.42)
    font_size = int(height * 0.15)
    font = load_font("playfair", font_size)

    line1 = "LAMKA LABS"
    line2 = "STUDIO"
    w1, h1 = text_size(draw, line1, font)
    w2, h2 = text_size(draw, line2, font)
    line_gap = int(height * 0.025)
    rule_margin = int(height * 0.025)
    stack_h = h1 + line_gap + h2

    gap = int(height * 0.06)
    text_block_w = max(w1, w2)
    group_w = seal_size + gap + text_block_w
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    text_x = group_left + seal_size + gap
    base_y = height // 2 - stack_h // 2
    y1 = base_y
    y2 = base_y + h1 + line_gap

    draw.text((text_x, y1), line1, font=font, fill=color)
    draw.text((text_x, y2), line2, font=font, fill=color)

    # Rule between lines, spanning the wider line
    rule_y = base_y + h1 + line_gap // 2
    sw = max(1, int(height * 0.003))
    draw.line([(text_x, rule_y), (text_x + text_block_w, rule_y)], fill=RED if color == WHITE else color, width=sw)


def treatment_underlined(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Single-line wordmark with a long thin underline."""
    seal_size = int(height * 0.40)
    font_size = int(height * 0.16)
    font = load_font("inter", font_size)
    text = "LAMKA LABS STUDIO"
    text_w, text_h = text_size(draw, text, font)
    gap = int(height * 0.06)
    group_w = seal_size + gap + text_w
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    text_x = group_left + seal_size + gap
    text_y = height // 2 - text_h // 2
    draw.text((text_x, text_y), text, font=font, fill=color)

    underline_y = text_y + text_h + int(height * 0.035)
    sw = max(1, int(height * 0.004))
    underline_x1 = group_left + seal_size // 2
    underline_x2 = text_x + text_w
    draw.line([(underline_x1, underline_y), (underline_x2, underline_y)], fill=RED if color == WHITE else color, width=sw)


def treatment_framed(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Logo + wordmark inside a thin rectangular frame."""
    seal_size = int(height * 0.36)
    font_size = int(height * 0.14)
    font = load_font("fraunces", font_size)
    text = "LAMKA LABS STUDIO"
    text_w, text_h = text_size(draw, text, font)
    gap = int(height * 0.05)
    group_w = seal_size + gap + text_w

    frame_pad_x = int(height * 0.08)
    frame_pad_y = int(height * 0.12)
    frame_w = group_w + frame_pad_x * 2
    frame_h = max(seal_size, text_h) + frame_pad_y * 2
    frame_x = (width - frame_w) // 2
    frame_y = (height - frame_h) // 2

    sw = max(1, int(height * 0.003))
    draw.rectangle([frame_x, frame_y, frame_x + frame_w, frame_y + frame_h], outline=color, width=sw)

    seal_cx = frame_x + frame_pad_x + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    text_x = frame_x + frame_pad_x + seal_size + gap
    text_y = height // 2 - text_h // 2
    draw.text((text_x, text_y), text, font=font, fill=color)


def treatment_initials(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Large initials monogram beside the seal, with the full name stacked small."""
    seal_size = int(height * 0.40)
    initial_size = int(height * 0.42)
    name_size = int(height * 0.09)
    initial_font = load_font("bodoni", initial_size)
    name_font = load_font("inter", name_size)

    init_w, init_h = text_size(draw, "LL", initial_font)
    name1 = "LAMKA LABS"
    name2 = "STUDIO"
    n1w, n1h = text_size(draw, name1, name_font)
    n2w, n2h = text_size(draw, name2, name_font)

    gap1 = int(height * 0.04)  # seal -> initials
    gap2 = int(height * 0.02)  # initials -> name
    name_stack_h = n1h + gap2 + n2h
    name_y_offset = (init_h - name_stack_h) // 2

    group_w = seal_size + gap1 + init_w + gap2 + max(n1w, n2w)
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    init_x = group_left + seal_size + gap1
    init_y = height // 2 - init_h // 2
    draw.text((init_x, init_y), "LL", font=initial_font, fill=color)

    name_x = init_x + init_w + gap2
    name_base_y = init_y + name_y_offset
    draw.text((name_x, name_base_y), name1, font=name_font, fill=color)
    draw.text((name_x, name_base_y + n1h + gap2), name2, font=name_font, fill=color)


def treatment_tagline(draw: ImageDraw.ImageDraw, width: int, height: int, color: tuple) -> None:
    """Main wordmark with a small red tagline below."""
    seal_size = int(height * 0.40)
    main_size = int(height * 0.15)
    tag_size = int(height * 0.07)
    main_font = load_font("cormorant", main_size)
    tag_font = load_font("inter", tag_size)

    main = "LAMKA LABS STUDIO"
    tag = "CREATIVE STUDIO"
    main_w, main_h = text_size(draw, main, main_font)
    tag_w, tag_h = text_size(draw, tag, tag_font)
    gap = int(height * 0.04)

    text_block_w = max(main_w, tag_w)
    text_block_h = main_h + gap + tag_h
    seal_gap = int(height * 0.06)
    group_w = seal_size + seal_gap + text_block_w
    group_left = (width - group_w) // 2

    seal_cx = group_left + seal_size // 2
    seal_cy = height // 2
    draw_seal(draw, seal_cx, seal_cy, seal_size, color)

    text_x = group_left + seal_size + seal_gap
    main_y = height // 2 - text_block_h // 2
    draw.text((text_x, main_y), main, font=main_font, fill=color)

    tag_y = main_y + main_h + gap
    draw.text((text_x, tag_y), tag, font=tag_font, fill=RED)


TREATMENTS = {
    "tracking": treatment_tracking,
    "stacked": treatment_stacked,
    "underlined": treatment_underlined,
    "framed": treatment_framed,
    "initials": treatment_initials,
    "tagline": treatment_tagline,
}


def build() -> None:
    width, height = 1920, 720
    combos = [
        ("transparent", "black", BLACK),
        ("transparent", "red", RED),
        ("black-bg", "white", WHITE),
        ("black-bg", "red", RED),
        ("white-bg", "black", BLACK),
        ("white-bg", "red", RED),
    ]

    for treatment_name, treatment_fn in TREATMENTS.items():
        for bg, color_name, color in combos:
            img = new_canvas(width, height, bg.replace("-bg", ""))
            draw = ImageDraw.Draw(img)
            treatment_fn(draw, width, height, color)
            save(img, f"{treatment_name}_{bg}_{color_name}")
            print(f"OK {treatment_name} {bg} {color_name}")


if __name__ == "__main__":
    build()
    print(f"\nAssets written to {OUT_DIR}")
