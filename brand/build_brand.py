"""Generate the LAGOM logo system as SVG files.

    python brand/build_brand.py

The wordmark is drawn with geometric strokes (no font needed), so it looks the
same on every computer, printer and sign maker. PNG icons for the app are made
from these files by `npm run icons` in the frontend folder.
"""
from pathlib import Path

OUT = Path(__file__).parent
FOREST, CREAM, SAND, GOLD, OLIVE = "#263D31", "#F3EBDD", "#B18B62", "#C58B50", "#7C8860"

# Letters drawn in a 40-unit-tall box. (path, width)
LETTERS = {
    "L": ("M0 0V40H24", 24),
    "A": ("M0 40L15 0L30 40M5.6 26H24.4", 30),
    "G": ("M34.14 5.86A20 20 0 1 0 40 20H22", 40),
    "O": ("M20 0A20 20 0 1 1 20 40A20 20 0 1 1 20 0Z", 40),
    "M": ("M0 40V0L17 26L34 0V40", 34),
}
TRACKING = 14
STROKE = 2.6


def wordmark_group(color: str, x: float, y: float, scale: float) -> tuple[str, float]:
    parts, cx = [], 0.0
    for ch in "LAGOM":
        path, w = LETTERS[ch]
        parts.append(f'<path transform="translate({cx:.2f} 0)" d="{path}"/>')
        cx += w + TRACKING
    width = cx - TRACKING
    g = (f'<g transform="translate({x:.2f} {y:.2f}) scale({scale})" fill="none" stroke="{color}" '
         f'stroke-width="{STROKE}" stroke-linecap="square" stroke-linejoin="miter">{"".join(parts)}</g>')
    return g, width * scale


def mark_group(ring: str, fill: str, cx: float, cy: float, r: float, uid: str) -> str:
    inner = r * 20 / 26
    return (f'<defs><clipPath id="{uid}"><circle cx="{cx}" cy="{cy}" r="{inner:.2f}"/></clipPath></defs>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ring}" stroke-width="{r * 4 / 26:.2f}"/>'
            f'<rect x="{cx - r}" y="{cy + r * 4 / 26:.2f}" width="{2 * r}" height="{r}" fill="{fill}" '
            f'clip-path="url(#{uid})"/>')


def svg(w: float, h: float, body: str, label: str, bg: str | None = None) -> str:
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" role="img" aria-label="{label}">'
            f'{rect}{body}</svg>\n')


def spaced_text(text: str, x: float, y: float, size: float, color: str, spacing: float, weight=500) -> str:
    return (f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Inter, Helvetica, Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" letter-spacing="{spacing}" fill="{color}">{text}</text>')


def build():
    files = {}
    for suffix, ring, word, accent in (("", FOREST, FOREST, SAND), ("-reversed", CREAM, CREAM, SAND)):
        # Icon only
        files[f"lagom-mark{suffix}.svg"] = svg(64, 64, mark_group(ring, GOLD, 32, 32, 26, "m"), "LAGOM")
        # Wordmark only
        g, w = wordmark_group(word, 2, 2, 1)
        files[f"lagom-wordmark{suffix}.svg"] = svg(w + 4, 44, g, "LAGOM")
        # Horizontal: mark + wordmark
        # Mark is kept smaller than the letters, with a clear gap, so it never reads as an "O"
        g, w = wordmark_group(word, 84, 17, 0.75)
        files[f"lagom-logo-horizontal{suffix}.svg"] = svg(
            84 + w + 4, 64, mark_group(ring, GOLD, 26, 32, 20, "h") + g, "LAGOM")
        # Main (stacked) logo with descriptor and slogan
        g, w = wordmark_group(word, 0, 0, 1)
        W = 320
        body = (mark_group(ring, GOLD, W / 2, 46, 30, "s")
                + wordmark_group(word, (W - w) / 2, 98, 1)[0]
                + spaced_text("FOOD · DRINKS · MOMENTS", W / 2, 166, 11, accent, 4.2)
                + spaced_text("JUST THE RIGHT AMOUNT.", W / 2, 192, 9, GOLD, 3.4, 600))
        files[f"lagom-logo-main{suffix}.svg"] = svg(W, 206, body, "LAGOM — Just the right amount.")

    # App icon (PWA / iOS): cream mark on forest square; content inside the 80% safe zone for maskable icons
    files["app-icon.svg"] = svg(512, 512, mark_group(CREAM, GOLD, 256, 256, 150, "a"), "LAGOM", bg=FOREST)
    files["favicon.svg"] = svg(64, 64, '<rect width="64" height="64" rx="14" fill="#263D31"/>'
                               + mark_group(CREAM, GOLD, 32, 32, 21, "f"), "LAGOM")
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
    print("Wrote", ", ".join(sorted(files)))


if __name__ == "__main__":
    build()
