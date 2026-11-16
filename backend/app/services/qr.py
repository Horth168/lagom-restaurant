"""QR code images and printable LAGOM table cards (A4 PDF)."""
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_Q
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.models import DiningTable

FOREST = "#263D31"
CREAM = "#F3EBDD"
SAND = "#B18B62"
GOLD = "#C58B50"


def table_url(table: DiningTable) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}/t/{table.qr_token}"


def qr_png(data: str, box_size: int = 12) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=FOREST, back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_mark(c: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    """The LAGOM mark: a vessel (circle) filled to 'just the right amount'."""
    c.saveState()
    c.setStrokeColor(HexColor(FOREST))
    c.setLineWidth(r * 0.12)
    c.circle(cx, cy, r, stroke=1, fill=0)
    # fill the lower part of the circle up to the level line
    level = cy - r * 0.18
    p = c.beginPath()
    p.circle(cx, cy, r * 0.78)
    c.clipPath(p, stroke=0, fill=0)
    c.setFillColor(HexColor(GOLD))
    c.rect(cx - r, cy - r, 2 * r, level - (cy - r), stroke=0, fill=1)
    c.restoreState()


def _spaced(c: canvas.Canvas, text: str, x_center: float, y: float, font: str, size: float, spacing: float):
    c.setFont(font, size)
    width = sum(c.stringWidth(ch, font, size) for ch in text) + spacing * (len(text) - 1)
    x = x_center - width / 2
    for ch in text:
        c.drawString(x, y, ch)
        x += c.stringWidth(ch, font, size) + spacing


def _card(c: canvas.Canvas, table: DiningTable, x: float, y: float, w: float, h: float) -> None:
    # background + border
    c.setFillColor(HexColor(CREAM))
    c.setStrokeColor(HexColor(SAND))
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, 3 * mm, stroke=1, fill=1)
    # cut guide
    c.setDash(2, 3)
    c.setStrokeColor(HexColor("#d8ccb8"))
    c.rect(x - 2 * mm, y - 2 * mm, w + 4 * mm, h + 4 * mm, stroke=1, fill=0)
    c.setDash()

    cx = x + w / 2
    top = y + h
    _draw_mark(c, cx, top - 16 * mm, 6.5 * mm)
    c.setFillColor(HexColor(FOREST))
    _spaced(c, "LAGOM", cx, top - 33 * mm, "Times-Roman", 24, 7)
    c.setFillColor(HexColor(SAND))
    _spaced(c, "FOOD · DRINKS · MOMENTS", cx, top - 39.5 * mm, "Helvetica", 6.5, 1.6)

    # Fit between the tagline (top - 45 mm) and the table name area (bottom 32 mm)
    qr_size = min(w - 26 * mm, h - 45 * mm - 33 * mm, 62 * mm)
    c.drawImage(ImageReader(io.BytesIO(qr_png(table_url(table), 10))), cx - qr_size / 2, top - 45 * mm - qr_size,
                qr_size, qr_size)

    c.setFillColor(HexColor(FOREST))
    c.setFont("Times-Roman", 20)
    c.drawCentredString(cx, y + 22 * mm, table.label)
    c.setFont("Helvetica", 8)
    c.drawCentredString(cx, y + 15 * mm, "Scan to order and pay from your phone")
    c.setFillColor(HexColor(GOLD))
    _spaced(c, "JUST THE RIGHT AMOUNT.", cx, y + 8 * mm, "Helvetica-Bold", 6, 1.4)


def table_cards_pdf(tables: list[DiningTable]) -> bytes:
    """Four cards per A4 page (2 × 2), with cut guides."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("LAGOM table QR cards")
    page_w, page_h = A4
    margin, gap = 12 * mm, 10 * mm
    w = (page_w - 2 * margin - gap) / 2
    h = (page_h - 2 * margin - gap) / 2
    positions = [(margin, margin + h + gap), (margin + w + gap, margin + h + gap), (margin, margin),
                 (margin + w + gap, margin)]
    for i, t in enumerate(tables):
        if i and i % 4 == 0:
            c.showPage()
        px, py = positions[i % 4]
        _card(c, t, px, py, w, h)
    c.showPage()
    c.save()
    return buf.getvalue()
