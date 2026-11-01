"""
shared/utils/pdf.py

Ticket PDF generation using ReportLab.
Produces a clean, branded A6-sized ticket with:
  - Event details
  - Attendee name
  - Ticket number
  - QR code
  - Karibu branding

Returns the PDF as bytes — the caller decides where to store it.
"""

import io
import qrcode
from qrcode.image.pil import PilImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# Brand colours
KARIBU_GREEN  = colors.HexColor("#16A34A")
KARIBU_DARK   = colors.HexColor("#111827")
KARIBU_LIGHT  = colors.HexColor("#F9FAFB")
KARIBU_GREY   = colors.HexColor("#6B7280")
KARIBU_BORDER = colors.HexColor("#E5E7EB")


def _build_qr_image(payload: str) -> ImageReader:
    """Generate a QR code and return it as a ReportLab ImageReader."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def generate_ticket_pdf(ticket) -> bytes:
    """
    Build and return a ticket PDF as raw bytes.

    Args:
        ticket: A Ticket model instance with .event and .attendee populated.

    Returns:
        bytes: The complete PDF file content.
    """
    buf = io.BytesIO()
    w, h = A6  # 105mm × 148mm

    c = canvas.Canvas(buf, pagesize=A6)

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------
    c.setFillColor(KARIBU_LIGHT)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # ------------------------------------------------------------------
    # Header bar
    # ------------------------------------------------------------------
    header_h = 28 * mm
    c.setFillColor(KARIBU_GREEN)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 16 * mm, "KARIBU")

    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, h - 22 * mm, "karibu.co.ke")

    # ------------------------------------------------------------------
    # Event title
    # ------------------------------------------------------------------
    c.setFillColor(KARIBU_DARK)
    c.setFont("Helvetica-Bold", 11)
    event_title = ticket.event.title
    # Truncate long titles gracefully
    if len(event_title) > 38:
        event_title = event_title[:35] + "..."
    c.drawCentredString(w / 2, h - 38 * mm, event_title)

    # ------------------------------------------------------------------
    # Divider
    # ------------------------------------------------------------------
    c.setStrokeColor(KARIBU_BORDER)
    c.setLineWidth(0.5)
    c.line(8 * mm, h - 42 * mm, w - 8 * mm, h - 42 * mm)

    # ------------------------------------------------------------------
    # Event details
    # ------------------------------------------------------------------
    c.setFont("Helvetica", 8)
    c.setFillColor(KARIBU_GREY)

    details = [
        ("📅 Date",    ticket.event.start_datetime.strftime("%A, %d %B %Y")),
        ("⏰ Time",    ticket.event.start_datetime.strftime("%H:%M") + " EAT"),
        ("📍 Venue",   ticket.event.venue),
        ("🌆 City",    ticket.event.city),
    ]

    y = h - 50 * mm
    for label, value in details:
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(KARIBU_GREY)
        c.drawString(8 * mm, y, label)
        c.setFont("Helvetica", 8)
        c.setFillColor(KARIBU_DARK)
        # Truncate long values
        val_str = str(value)[:40]
        c.drawString(32 * mm, y, val_str)
        y -= 6 * mm

    # ------------------------------------------------------------------
    # Divider
    # ------------------------------------------------------------------
    c.setStrokeColor(KARIBU_BORDER)
    c.line(8 * mm, y - 1 * mm, w - 8 * mm, y - 1 * mm)
    y -= 6 * mm

    # ------------------------------------------------------------------
    # Attendee + ticket info
    # ------------------------------------------------------------------
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(KARIBU_GREY)
    c.drawString(8 * mm, y, "ATTENDEE")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(KARIBU_DARK)
    c.drawString(8 * mm, y - 5 * mm, ticket.attendee.full_name)

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(KARIBU_GREY)
    c.drawString(8 * mm, y - 11 * mm, "TICKET NO.")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(KARIBU_GREEN)
    c.drawString(8 * mm, y - 16 * mm, ticket.ticket_number)

    # Price
    price_str = "FREE" if ticket.event.is_free else f"{ticket.currency} {ticket.price_paid:,.0f}"
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(KARIBU_GREY)
    c.drawString(8 * mm, y - 22 * mm, "PRICE")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(KARIBU_DARK)
    c.drawString(8 * mm, y - 27 * mm, price_str)

    # ------------------------------------------------------------------
    # QR code — right side
    # ------------------------------------------------------------------
    qr_img    = _build_qr_image(ticket.qr_payload)
    qr_size   = 28 * mm
    qr_x      = w - qr_size - 8 * mm
    qr_y      = y - 30 * mm
    c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)

    c.setFont("Helvetica", 6)
    c.setFillColor(KARIBU_GREY)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 4 * mm, "Scan to validate")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    footer_h = 10 * mm
    c.setFillColor(KARIBU_GREEN)
    c.rect(0, 0, w, footer_h, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica", 6)
    c.drawCentredString(
        w / 2, 4 * mm,
        f"This ticket is non-transferable. Code: {ticket.qr_payload[:16]}..."
    )

    c.save()
    buf.seek(0)
    return buf.read()
