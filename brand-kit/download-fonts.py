"""Download professional Google Fonts (variable TTFs) from google/fonts."""
from __future__ import annotations

import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "fonts"
OUT.mkdir(parents=True, exist_ok=True)

# short-name: github/fonts filename
FONTS = {
    "montserrat": "ofl/montserrat/Montserrat[wght].ttf",
    "playfair": "ofl/playfairdisplay/PlayfairDisplay[wght].ttf",
    "cormorant": "ofl/cormorantgaramond/CormorantGaramond[wght].ttf",
    "inter": "ofl/inter/Inter[opsz,wght].ttf",
    "bodoni": "ofl/bodonimoda/BodoniModa[opsz,wght].ttf",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://raw.githubusercontent.com/google/fonts/main/"


if __name__ == "__main__":
    for short, path in FONTS.items():
        dest = OUT / f"{short}.ttf"
        url = BASE + path
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            print(f"OK {short}: {len(data)} bytes")
        except Exception as e:
            print(f"FAILED {short}: {e}")
    print("\nDone.")
