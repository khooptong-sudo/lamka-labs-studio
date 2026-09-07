"""Lamka Labs Studio — identity program. Generates 5 logo iteration SVGs."""
import math
import os

OUT = os.path.join(os.path.dirname(__file__), "svg")
os.makedirs(OUT, exist_ok=True)

INK = "#15130E"
IVORY = "#F2EEE3"
GOLD = "#B99463"

NAMES = {
    1: "aperture",
    2: "meridian-key",
    3: "crucible",
    4: "strata",
    5: "north-star-seal",
}

def wordmark(y1=852):
    return f'''
  <text x="507" y="{y1}" font-family="Georgia, 'Times New Roman', serif" font-size="54"
        letter-spacing="14" fill="{IVORY}" text-anchor="middle">LAMKA LABS</text>
  <text x="510" y="{y1+54}" font-family="Georgia, 'Times New Roman', serif" font-size="25"
        letter-spacing="20" fill="{GOLD}" text-anchor="middle">STUDIO</text>'''

def svg(inner, note=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">
  <!-- Lamka Labs Studio identity - {note} -->
  <rect width="1000" height="1000" fill="{INK}"/>{inner}
</svg>
'''

marks = {}

# ---- 01 APERTURE -----------------------------------------------------------
# A lens ring frames a chamfered L; a gold period closes the statement.
aperture = f'''
  <circle cx="500" cy="468" r="330" fill="none" stroke="{IVORY}" stroke-width="9"/>
  <path d="M436 300 h74 v266 h154 v74 h-228 Z" fill="{IVORY}"/>
  <circle cx="718" cy="603" r="17" fill="{GOLD}"/>{wordmark()}'''
marks[1] = svg(aperture, "Aperture")

# ---- 02 MERIDIAN KEY -------------------------------------------------------
# One continuous squared spiral: the Greek meander reborn as a lab key.
key_pts = " ".join(f"{x},{y}" for x, y in [
    (690,310),(310,310),(310,690),(610,690),(610,410),(410,410),(410,590)
])
meridian = f'''
  <polyline points="{key_pts}" fill="none" stroke="{GOLD}" stroke-width="46"
            stroke-miterlimit="8"/>{wordmark()}'''
marks[2] = svg(meridian, "Meridian Key")

# ---- 03 CRUCIBLE -----------------------------------------------------------
# The vessel of the lab, reduced to six strokes; the gold meniscus marks the fill line.
crucible = f'''
  <path d="M452 330 V420 L392 470 L500 672 L608 470 L548 420 V330"
        fill="none" stroke="{IVORY}" stroke-width="14" stroke-linejoin="miter"/>
  <polygon points="450,566 550,566 500,650" fill="{GOLD}"/>{wordmark()}'''
marks[3] = svg(crucible, "Crucible")

# ---- 04 STRATA -------------------------------------------------------------
# Three foundation courses; the last one is gold. Craft built in layers.
strata = f'''
  <rect x="320" y="330" width="360" height="64" fill="{IVORY}"/>
  <rect x="320" y="458" width="250" height="64" fill="{IVORY}"/>
  <rect x="320" y="586" width="140" height="64" fill="{GOLD}"/>{wordmark()}'''
marks[4] = svg(strata, "Strata")

# ---- 05 NORTH STAR SEAL ----------------------------------------------------
# An eight-point compass star set in a fine ring: direction, craft, permanence.
pts = []
for i in range(16):
    ang = math.radians(i * 22.5 - 90)
    if i % 4 == 0:
        rad = 264
    elif i % 2 == 0:
        rad = 132
    else:
        rad = 84
    pts.append((500 + rad * math.cos(ang), 458 + rad * math.sin(ang)))
star = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
seal = f'''
  <circle cx="500" cy="458" r="314" fill="none" stroke="{IVORY}" stroke-width="7"/>
  <polygon points="{star}" fill="{GOLD}"/>{wordmark()}'''
marks[5] = svg(seal, "North Star Seal")

for n, content in marks.items():
    path = os.path.join(OUT, f"lamka-labs-{n:02d}-{NAMES[n]}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("wrote", path)
