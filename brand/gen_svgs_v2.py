"""Lamka Labs Studio — identity program v2. Black / white / red. 5 new marks."""
import math
import os

OUT = os.path.join(os.path.dirname(__file__), "svg")
os.makedirs(OUT, exist_ok=True)

INK = "#0F0E0C"
WHITE = "#F7F5F0"
RED = "#C8102E"

NAMES = {
    1: "vantage",
    2: "signal-core",
    3: "counter-l",
    4: "orbit-study",
    5: "quarter-turn",
}

def wordmark(y1=852):
    return f'''
  <text x="507" y="{y1}" font-family="Georgia, 'Times New Roman', serif" font-size="54"
        letter-spacing="14" fill="{WHITE}" text-anchor="middle">LAMKA LABS</text>
  <text x="510" y="{y1+54}" font-family="Georgia, 'Times New Roman', serif" font-size="25"
        letter-spacing="20" fill="{RED}" text-anchor="middle">STUDIO</text>'''

def svg(inner, note=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">
  <!-- Lamka Labs Studio identity v2 - {note} -->
  <rect width="1000" height="1000" fill="{INK}"/>{inner}
</svg>
'''

marks = {}

# ---- 01 VANTAGE ------------------------------------------------------------
# The peak, cut by one red line of descent. Ambition with a route down.
vantage = f'''
  <polygon points="500,280 700,700 300,700" fill="{WHITE}"/>
  <line x1="500" y1="280" x2="614" y2="700" stroke="{RED}" stroke-width="14"/>{wordmark()}'''
marks[1] = svg(vantage, "Vantage")

# ---- 02 SIGNAL CORE --------------------------------------------------------
# Three arcs opening rightward from a red core: the lab ping, reduced.
def arc(cx, cy, r, a0, a1, w):
    x0 = cx + r * math.cos(math.radians(a0)); y0 = cy + r * math.sin(math.radians(a0))
    x1 = cx + r * math.cos(math.radians(a1)); y1 = cy + r * math.sin(math.radians(a1))
    return (f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" '
            f'fill="none" stroke="{WHITE}" stroke-width="{w}" stroke-linecap="butt"/>')
signal = (
    arc(430, 500, 100, -62, 62, 18)
    + arc(430, 500, 180, -62, 62, 18)
    + arc(430, 500, 260, -62, 62, 18)
    + f'<circle cx="430" cy="500" r="46" fill="{RED}"/>'
) + wordmark()
marks[2] = svg(signal, "Signal Core")

# ---- 03 COUNTER L ----------------------------------------------------------
# A heavy L with a red counter floating in the notch: the pause inside the work.
counter = f'''
  <path d="M400 300 h100 v280 h180 v100 h-280 Z" fill="{WHITE}"/>
  <rect x="516" y="516" width="56" height="56" fill="{RED}"/>{wordmark()}'''
marks[3] = svg(counter, "Counter L")

# ---- 04 ORBIT STUDY --------------------------------------------------------
# One white orbit, one red body on it, one white body behind: experiment in motion.
orbit = f'''
  <g transform="rotate(-24 500 490)">
    <ellipse cx="500" cy="490" rx="300" ry="118" fill="none" stroke="{WHITE}" stroke-width="12"/>
    <circle cx="800" cy="490" r="46" fill="{RED}"/>
    <circle cx="200" cy="490" r="18" fill="{WHITE}"/>
  </g>{wordmark()}'''
marks[4] = svg(orbit, "Orbit Study")

# ---- 05 QUARTER TURN -------------------------------------------------------
# A white frame, one quadrant filled red: the shutter set a quarter open.
quarter = f'''
  <rect x="310" y="310" width="380" height="380" fill="none" stroke="{WHITE}" stroke-width="14"/>
  <rect x="500" y="310" width="190" height="190" fill="{RED}"/>{wordmark()}'''
marks[5] = svg(quarter, "Quarter Turn")

for n, content in marks.items():
    path = os.path.join(OUT, f"lamka-labs-v2-{n:02d}-{NAMES[n]}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("wrote", path)
