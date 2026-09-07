"""Convert logo PNGs to JPG + subtle animated GIF (fade + settle, loops)."""
import glob
import math
import os

from PIL import Image, ImageEnhance

HERE = os.path.dirname(__file__)
PNG_DIR = os.path.join(HERE, "png")
JPG_DIR = os.path.join(HERE, "jpg")
GIF_DIR = os.path.join(HERE, "gif")
os.makedirs(JPG_DIR, exist_ok=True)
os.makedirs(GIF_DIR, exist_ok=True)

INK = (21, 19, 14)

for png in sorted(glob.glob(os.path.join(PNG_DIR, "*.png"))):
    base = os.path.splitext(os.path.basename(png))[0]
    img = Image.open(png).convert("RGB")

    jpg_path = os.path.join(JPG_DIR, base + ".jpg")
    img.save(jpg_path, "JPEG", quality=95, optimize=True)

    # Animated GIF: fade up from ink, gentle settle from 94% -> 100%, then hold.
    size = img.size[0]
    frames = []
    n = 22
    hold = 14
    for i in range(n + hold):
        t = min(i / (n - 1), 1.0)
        ease = 1 - (1 - t) ** 3
        scale = 0.94 + 0.06 * ease
        new = int(size * scale)
        frame = img.resize((new, new), Image.LANCZOS)
        canvas = Image.new("RGB", (size, size), INK)
        off = (size - new) // 2
        canvas.paste(frame, (off, off))
        if t < 1.0:
            canvas = Image.blend(Image.new("RGB", (size, size), INK), canvas, ease)
        canvas = canvas.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        frames.append(canvas)

    gif_path = os.path.join(GIF_DIR, base + ".gif")
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=[70] * n + [900] * hold, loop=0, optimize=False)
    print("ok", base)
