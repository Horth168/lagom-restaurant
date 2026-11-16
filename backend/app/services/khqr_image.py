"""Draw the KHQR payment card as a PNG on the server.

Phones inside Telegram (and some in-app browsers) cannot save a picture made by the
web page, but they can download a real file from a web address. This draws the same
card the customer sees: red header with the KHQR mark, name, amount, dashed line and
the QR with the KHQR emblem in the middle.
"""
import io
import math
import re

import qrcode
from PIL import Image, ImageDraw, ImageFont

RED = (204, 0, 0)
EMBLEM_RED = (226, 31, 38)
WHITE = (255, 255, 255)
SCALE = 3  # draw big, then shrink: smooth edges
W, H = 300, 440  # same layout units as the on-screen card (frontend/src/components/KhqrCard.jsx)

# The KHQR letters, in the official badge's 1248 × 514 coordinates (same as KhqrLogo.jsx)
LETTERS = [
    "M95 125 H141 V388 H95 Z",
    "M141 242 L253 125 L307 125 L187 251 L314 388 L258 388 L141 266 Z",
    "M348 125 H393 V388 H348 Z",
    "M521 125 H567 V388 H521 Z",
    "M393 235 H521 V273 H393 Z",
    "M648 125 H821 A40 40 0 0 1 861 165 V356 L821 316 V190 A25 25 0 0 0 796 165 H673 A25 25 0 0 0 648 190 "
    "V319 A25 25 0 0 0 673 344 H795 L835 384 H648 A40 40 0 0 1 608 344 V165 A40 40 0 0 1 648 125 Z",
    "M698 208 H770 A10 10 0 0 1 780 218 V293 A10 10 0 0 1 770 303 H698 A10 10 0 0 1 688 293 V218 A10 10 0 0 1 698 208 Z",
    "M900 250 A124 124 0 0 1 1148 250 V254 H1108 V250 A84 84 0 0 0 940 250 V384 A40 40 0 0 1 900 344 Z",
    "M1012 297 L1066 297 L1152 388 L1096 388 Z",
]
# The emblem, in its 1928 × 1928 grid (same as KhqrEmblem in KhqrCard.jsx)
STAR_OUT = "M964 40 L705 310 H340 V690 L80 964 L340 1240 V1615 H705 L964 1890 L1225 1615 H1590 V1240 L1850 964 L1590 690 V310 H1225 Z"
STAR_IN = "M964 200 L745 420 H445 V740 L228 964 L445 1190 V1510 H745 L964 1735 L1185 1510 H1485 V1200 L1700 964 L1485 740 V420 H1185 Z"
C_OUT = "M630 615 H800 Q964 545 1140 615 H1300 V1315 H1140 Q964 1385 800 1315 H630 V1130 Q560 964 630 800 Z"
C_IN = "M735 725 H830 Q964 655 1100 725 H1195 V1205 H1100 Q964 1275 830 1205 H735 V1130 Q665 964 735 800 Z"


def _path_points(d: str) -> list[tuple[float, float]]:
    """Turn a simple SVG path (M L H V Q A Z, absolute) into polygon points."""
    tokens = re.findall(r"[MLHVQAZ]|-?\d+(?:\.\d+)?", d)
    pts: list[tuple[float, float]] = []
    x = y = 0.0
    i = 0
    cmd = ""
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                continue
        nums = lambda n: [float(t) for t in tokens[i:i + n]]  # noqa: E731
        if cmd in "ML":
            x, y = nums(2)
            i += 2
            pts.append((x, y))
        elif cmd == "H":
            x = nums(1)[0]
            i += 1
            pts.append((x, y))
        elif cmd == "V":
            y = nums(1)[0]
            i += 1
            pts.append((x, y))
        elif cmd == "Q":
            cx, cy, ex, ey = nums(4)
            i += 4
            for k in range(1, 13):
                t = k / 12
                pts.append(((1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t * t * ex,
                            (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t * t * ey))
            x, y = ex, ey
        elif cmd == "A":
            r, _, _, large, sweep, ex, ey = nums(7)
            i += 7
            pts.extend(_arc(x, y, r, int(large), int(sweep), ex, ey))
            x, y = ex, ey
        else:
            i += 1
    return pts


def _arc(x1, y1, r, large, sweep, x2, y2):
    """Points along a circular arc (SVG endpoint form)."""
    mx, my = (x1 - x2) / 2, (y1 - y2) / 2
    d2 = mx * mx + my * my
    r = max(r, math.sqrt(d2))
    f = math.sqrt(max(0.0, (r * r - d2) / d2)) if d2 else 0.0
    if large == sweep:
        f = -f
    cx = (x1 + x2) / 2 + f * my
    cy = (y1 + y2) / 2 - f * mx
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    delta = a2 - a1
    if sweep and delta < 0:
        delta += 2 * math.pi
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    steps = max(4, int(abs(delta) / (math.pi / 24)))
    return [(cx + r * math.cos(a1 + delta * k / steps), cy + r * math.sin(a1 + delta * k / steps))
            for k in range(1, steps + 1)]


def _place(pts, ox, oy, s):
    return [(ox + px * s, oy + py * s) for px, py in pts]


def _font(size: int):
    return ImageFont.load_default(size=size)


def render_card(qr_string: str, *, amount_text: str, currency: str, merchant: str = "LAGOM") -> bytes:
    k = SCALE
    img = Image.new("RGB", (W * k, H * k), WHITE)
    d = ImageDraw.Draw(img)

    # Red header with the flap hanging down on the right
    d.rounded_rectangle((0, 0, W * k, 74 * k), radius=14 * k, fill=RED, corners=(True, True, False, False))
    d.rectangle((0, 40 * k, W * k, 60 * k), fill=RED)
    d.rectangle((0, 60 * k, W * k, 74 * k), fill=WHITE)
    d.polygon([((W - 30) * k, 60 * k), (W * k, 60 * k), (W * k, 88 * k)], fill=RED)

    # KHQR letters, white, centred in the header (84 units wide)
    s = 84 / 1057 * k
    ox, oy = (W - 84) / 2 * k - 95 * s, 20 * k - 125 * s
    for path in LETTERS:
        d.polygon(_place(_path_points(path), ox, oy, s), fill=WHITE)

    # Name, amount, currency
    ink, soft = (34, 34, 34), (51, 51, 51)
    d.text((30 * k, 82 * k), merchant, font=_font(16 * k), fill=ink)
    big = _font(22 * k)
    d.text((30 * k, 112 * k), amount_text, font=big, fill=(17, 17, 17), stroke_width=1, stroke_fill=(17, 17, 17))
    amount_w = d.textlength(amount_text, font=big)
    d.text((30 * k + amount_w + 6 * k, 121 * k), currency, font=_font(11 * k), fill=soft)

    # Dashed line across the card
    for x in range(0, W, 7):
        d.line(((x * k, 152 * k), ((x + 4) * k, 152 * k)), fill=(154, 154, 154), width=k)

    # QR code (high error correction: the emblem in the middle never stops it scanning)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0, box_size=10)
    qr.add_data(qr_string)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((240 * k, 240 * k), Image.NEAREST)
    img.paste(q, (30 * k, 170 * k))

    # KHQR emblem: white ring, red circle, white star band and C, red opening on the right
    cx, cy, r = 150 * k, 290 * k, 21 * k
    d.ellipse((cx - 23 * k, cy - 23 * k, cx + 23 * k, cy + 23 * k), fill=WHITE)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=EMBLEM_RED)
    es = (2 * r) / 1928
    eox, eoy = cx - r, cy - r
    for path, colour in ((STAR_OUT, WHITE), (STAR_IN, EMBLEM_RED), (C_OUT, WHITE), (C_IN, EMBLEM_RED)):
        d.polygon(_place(_path_points(path), eox, eoy, es), fill=colour)
    d.polygon(_place([(1190, 895), (1880, 895), (1880, 1040), (1190, 1040)], eox, eoy, es), fill=EMBLEM_RED)

    # Rounded card corners, then shrink to 2× for a crisp phone picture
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W * k - 1, H * k - 1), radius=14 * k, fill=255)
    out = Image.new("RGB", img.size, WHITE)
    out.paste(img, (0, 0), mask)
    out = out.resize((W * 2, H * 2), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
