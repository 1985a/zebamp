"""Built-in vector skin "Zebamp" (Winamp 5 era look, original artwork).

Every sheet of the classic sprite layout is drawn with antialiased vector
graphics directly at the screen zoom (`res`), so the skin stays sharp at 2x or
3x instead of showing enlarged pixels.  Coordinates below are in classic 1x
pixels; the images carry a device pixel ratio of `res`.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from . import sprites as SP
from .classic import ClassicSkin

# ---------------------------------------------------------------- palette
BODY_TOP = QColor(74, 80, 94)
BODY_MID = QColor(48, 52, 63)
BODY_BOT = QColor(30, 33, 41)
EDGE_HI = QColor(140, 150, 170)
EDGE_LO = QColor(10, 11, 15)
LCD_BG = QColor(4, 12, 26)
LCD_BG2 = QColor(10, 28, 56)
LCD_EDGE = QColor(0, 0, 0)
GLOW = QColor(110, 205, 255)        # LCD text
GLOW_DIM = QColor(24, 52, 86)       # unlit LCD segments
ACCENT = QColor(56, 160, 255)
ACCENT_HI = QColor(150, 215, 255)
BTN_TOP = QColor(118, 126, 144)
BTN_BOT = QColor(52, 57, 70)
BTN_TOP_P = QColor(40, 44, 54)
BTN_BOT_P = QColor(70, 76, 92)
ICON = QColor(228, 234, 245)
LABEL = QColor(170, 182, 205)
TITLE_ON = QColor(235, 242, 255)
TITLE_OFF = QColor(130, 138, 156)

UI_FONT = "DejaVu Sans"
COND_FONT = "DejaVu Sans Condensed"


# ---------------------------------------------------------------- helpers
class Canvas:
    """A sheet image at `res` x resolution painted in 1x coordinates."""

    def __init__(self, res: int, w: int, h: int, fill: QColor | None = None):
        self.res = res
        self.img = QImage(w * res, h * res, QImage.Format.Format_ARGB32_Premultiplied)
        self.img.fill(fill if fill is not None else QColor(0, 0, 0, 0))
        self.img.setDevicePixelRatio(res)
        self.p = QPainter(self.img)
        self.p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    def done(self) -> QImage:
        self.p.end()
        return self.img


def font(size: float, bold=False, family=UI_FONT, spacing=0.0) -> QFont:
    f = QFont(family)
    f.setPointSizeF(size * 0.75)   # px -> pt at 96 dpi; exact enough for QImage
    f.setBold(bold)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def text(p: QPainter, r: QRectF | QRect, s: str, size: float, color: QColor, bold=True,
         align=Qt.AlignmentFlag.AlignCenter, family=UI_FONT, spacing=0.0, glow=False):
    p.save()
    p.setFont(font(size, bold, family, spacing))
    r = QRectF(r)
    if glow:
        g = QColor(color)
        g.setAlpha(70)
        p.setPen(g)
        for dx, dy in ((-0.35, 0), (0.35, 0), (0, -0.35), (0, 0.35)):
            p.drawText(r.translated(dx, dy), int(align), s)
    p.setPen(color)
    p.drawText(r, int(align), s)
    p.restore()


def vgrad(y0, y1, *stops) -> QLinearGradient:
    g = QLinearGradient(0, y0, 0, y1)
    n = len(stops)
    for i, c in enumerate(stops):
        g.setColorAt(i / max(1, n - 1), c)
    return g


def rrect(r, radius) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(r), radius, radius)
    return path


def body(p: QPainter, r: QRect, radius=0.0):
    """Brushed graphite body with a soft top light."""
    rf = QRectF(r)
    p.save()
    path = rrect(rf, radius) if radius else None
    if path is not None:
        p.setClipPath(path)
    p.fillRect(rf, vgrad(rf.top(), rf.bottom(), BODY_TOP, BODY_MID, BODY_BOT))
    # brushed lines
    pen = QPen(QColor(255, 255, 255, 9), 0.5)
    p.setPen(pen)
    y = rf.top() + 0.75
    while y < rf.bottom():
        p.drawLine(QPointF(rf.left(), y), QPointF(rf.right(), y))
        y += 1.5
    # bevel
    p.setPen(QPen(EDGE_HI, 0.75))
    p.drawLine(QPointF(rf.left() + 0.4, rf.top() + 0.4), QPointF(rf.right() - 0.4, rf.top() + 0.4))
    p.drawLine(QPointF(rf.left() + 0.4, rf.top() + 0.4), QPointF(rf.left() + 0.4, rf.bottom() - 0.4))
    p.setPen(QPen(EDGE_LO, 0.75))
    p.drawLine(QPointF(rf.left(), rf.bottom() + 0.6), QPointF(rf.right() + 1, rf.bottom() + 0.6))
    p.drawLine(QPointF(rf.right() + 0.6, rf.top()), QPointF(rf.right() + 0.6, rf.bottom() + 1))
    p.restore()


def lcd(p: QPainter, r, radius=2.0):
    """Recessed blue LCD panel."""
    rf = QRectF(r)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    # outer recess
    p.setBrush(vgrad(rf.top() - 1, rf.bottom() + 1, QColor(8, 9, 12), QColor(110, 118, 136)))
    p.drawPath(rrect(rf.adjusted(-0.8, -0.8, 0.8, 0.8), radius + 0.8))
    g = QLinearGradient(0, rf.top(), 0, rf.bottom())
    g.setColorAt(0, LCD_BG2)
    g.setColorAt(0.55, LCD_BG)
    g.setColorAt(1, QColor(2, 6, 14))
    p.setBrush(g)
    p.drawPath(rrect(rf, radius))
    # glass sheen
    sheen = QLinearGradient(0, rf.top(), 0, rf.top() + rf.height() * 0.5)
    sheen.setColorAt(0, QColor(255, 255, 255, 28))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(sheen)
    p.drawPath(rrect(rf.adjusted(0.6, 0.6, -0.6, -rf.height() * 0.5), max(0.5, radius - 0.6)))
    p.restore()


def button(p: QPainter, r, pressed=False, radius=2.6, lit=False, flat_top=None):
    """Glossy rounded button."""
    rf = QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5)
    p.save()
    p.setPen(QPen(QColor(8, 9, 13), 0.8))
    if pressed:
        p.setBrush(vgrad(rf.top(), rf.bottom(), BTN_TOP_P, BTN_BOT_P))
    else:
        p.setBrush(vgrad(rf.top(), rf.bottom(), BTN_TOP, QColor(84, 91, 107), BTN_BOT))
    p.drawPath(rrect(rf, radius))
    if not pressed:
        gl = QLinearGradient(0, rf.top(), 0, rf.center().y())
        gl.setColorAt(0, QColor(255, 255, 255, 95))
        gl.setColorAt(1, QColor(255, 255, 255, 8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gl)
        p.drawPath(rrect(QRectF(rf.left() + 0.8, rf.top() + 0.7, rf.width() - 1.6,
                                rf.height() * 0.48), max(0.5, radius - 0.8)))
    if lit:
        p.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 200), 0.7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(rrect(rf.adjusted(0.5, 0.5, -0.5, -0.5), max(0.5, radius - 0.5)))
    p.restore()


def led(p: QPainter, cx, cy, on: bool, r=1.3):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    if on:
        g = QRadialGradient(QPointF(cx, cy), r * 2.4)
        g.setColorAt(0, QColor(220, 245, 255))
        g.setColorAt(0.35, ACCENT)
        g.setColorAt(1, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), r * 2.4, r * 2.4)
    p.setBrush(QColor(170, 230, 255) if on else QColor(20, 34, 52))
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.restore()


def icon(p: QPainter, kind: str, r, color: QColor, s=1.0):
    """Transport icons drawn as filled vector shapes centred in r."""
    rf = QRectF(r)
    cx, cy = rf.center().x(), rf.center().y()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    k = s

    def tri(x0, x1, h):
        return QPolygonF([QPointF(x0, cy - h), QPointF(x0, cy + h), QPointF(x1, cy)])
    if kind == "play":
        p.drawPolygon(tri(cx - 3 * k, cx + 4 * k, 4 * k))
    elif kind == "pause":
        p.drawRoundedRect(QRectF(cx - 3.6 * k, cy - 3.8 * k, 2.6 * k, 7.6 * k), 0.4, 0.4)
        p.drawRoundedRect(QRectF(cx + 1.0 * k, cy - 3.8 * k, 2.6 * k, 7.6 * k), 0.4, 0.4)
    elif kind == "stop":
        p.drawRoundedRect(QRectF(cx - 3.5 * k, cy - 3.5 * k, 7 * k, 7 * k), 0.6, 0.6)
    elif kind == "prev":
        p.drawRect(QRectF(cx - 5 * k, cy - 3.5 * k, 1.8 * k, 7 * k))
        p.drawPolygon(tri(cx + 0.3 * k, cx - 3.2 * k, 3.5 * k))
        p.drawPolygon(tri(cx + 4.4 * k, cx + 0.5 * k, 3.5 * k))
    elif kind == "next":
        p.drawPolygon(tri(cx - 4.4 * k, cx - 0.5 * k, 3.5 * k))
        p.drawPolygon(tri(cx - 0.3 * k, cx + 3.2 * k, 3.5 * k))
        p.drawRect(QRectF(cx + 3.2 * k, cy - 3.5 * k, 1.8 * k, 7 * k))
    elif kind == "eject":
        p.drawPolygon(QPolygonF([QPointF(cx - 4.5 * k, cy + 0.8 * k), QPointF(cx + 4.5 * k, cy + 0.8 * k),
                                 QPointF(cx, cy - 4 * k)]))
        p.drawRect(QRectF(cx - 4.5 * k, cy + 2.2 * k, 9 * k, 1.8 * k))
    p.restore()


def small_btn(p: QPainter, x, y, kind, pressed=False):
    r = QRectF(x, y, 9, 9)
    button(p, r, pressed, radius=2.0)
    p.save()
    pen = QPen(ACCENT_HI if pressed else ICON, 1.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    c = r.center()
    if kind == "close":
        p.drawLine(QPointF(c.x() - 2, c.y() - 2), QPointF(c.x() + 2, c.y() + 2))
        p.drawLine(QPointF(c.x() + 2, c.y() - 2), QPointF(c.x() - 2, c.y() + 2))
    elif kind == "min":
        p.drawLine(QPointF(c.x() - 2.2, c.y() + 2), QPointF(c.x() + 2.2, c.y() + 2))
    elif kind == "shade":
        p.drawLine(QPointF(c.x() - 2.2, c.y() - 1.6), QPointF(c.x() + 2.2, c.y() - 1.6))
        p.drawLine(QPointF(c.x() - 2.2, c.y() + 0.6), QPointF(c.x() + 2.2, c.y() + 0.6))
    elif kind == "unshade":
        p.drawRect(QRectF(c.x() - 2, c.y() - 2, 4, 4))
    elif kind == "menu":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ACCENT_HI if pressed else ICON)
        p.drawPolygon(QPolygonF([QPointF(c.x() - 2.5, c.y() - 1.2), QPointF(c.x() + 2.5, c.y() - 1.2),
                                 QPointF(c.x(), c.y() + 1.8)]))
    p.restore()


def title_bar(p: QPainter, r: QRect, caption: str, active: bool, logo=False):
    rf = QRectF(r)
    p.save()
    if active:
        g = vgrad(rf.top(), rf.bottom(), QColor(92, 104, 132), QColor(52, 60, 82), QColor(30, 34, 46))
    else:
        g = vgrad(rf.top(), rf.bottom(), QColor(68, 72, 84), QColor(44, 47, 56), QColor(30, 32, 38))
    p.fillRect(rf, g)
    p.setPen(QPen(QColor(255, 255, 255, 60 if active else 30), 0.6))
    p.drawLine(QPointF(rf.left(), rf.top() + 0.3), QPointF(rf.right() + 1, rf.top() + 0.3))
    p.setPen(QPen(QColor(0, 0, 0, 160), 0.6))
    p.drawLine(QPointF(rf.left(), rf.bottom() + 0.7), QPointF(rf.right() + 1, rf.bottom() + 0.7))
    if caption:
        f = font(7.6, True, UI_FONT, 1.1)
        tw = QFontMetricsF(f).horizontalAdvance(caption)
        cx = rf.center().x() + 0.5
        # grooved grips on both sides
        p.setPen(QPen(QColor(0, 0, 0, 120), 0.7))
        hi = QPen(QColor(255, 255, 255, 45 if active else 22), 0.7)
        for yy in (rf.top() + 4.5, rf.top() + 7.5, rf.top() + 10.5) if rf.height() >= 13 else ():
            for x0, x1 in ((rf.left() + 22, cx - tw / 2 - 7), (cx + tw / 2 + 7, rf.right() - 34)):
                if x1 - x0 > 4:
                    p.setPen(QPen(QColor(0, 0, 0, 120), 0.7))
                    p.drawLine(QPointF(x0, yy), QPointF(x1, yy))
                    p.setPen(hi)
                    p.drawLine(QPointF(x0, yy + 0.8), QPointF(x1, yy + 0.8))
        col = TITLE_ON if active else TITLE_OFF
        text(p, QRectF(rf.left(), rf.top() + 0.3, rf.width() + 1, rf.height()), caption, 7.6, col,
             True, spacing=1.1, glow=active)
    p.restore()


# ---------------------------------------------------------------- sheets
def make_main(res) -> QImage:
    c = Canvas(res, 275, 116)
    p = c.p
    body(p, QRect(0, 0, 275, 116))
    # display bezel holding time + vis, marquee and info
    bez = QRectF(9, 17, 258, 47)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(vgrad(bez.top(), bez.bottom(), QColor(20, 22, 28), QColor(40, 44, 54)))
    p.drawPath(rrect(bez, 4))
    p.setPen(QPen(QColor(255, 255, 255, 40), 0.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(rrect(bez.adjusted(0.3, 0.3, -0.3, -0.3), 4))
    lcd(p, QRectF(22, 20, 82, 41), 3)
    # time colon (digits are drawn at x 48/60 and 78/90, y 26)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for cy in (30.6, 35.4):
        glow = QColor(GLOW)
        glow.setAlpha(70)
        p.setBrush(glow)
        p.drawEllipse(QPointF(73.0, cy), 1.5, 1.5)
        p.setBrush(GLOW)
        p.drawEllipse(QPointF(73.0, cy), 0.95, 0.95)
    p.restore()
    lcd(p, QRectF(109, 22, 158, 13), 2)
    lcd(p, QRectF(109, 41, 19, 10), 1.5)
    text(p, QRectF(129, 41, 24, 10), "kbps", 5.6, LABEL, True, family=COND_FONT)
    lcd(p, QRectF(154, 41, 14, 10), 1.5)
    text(p, QRectF(169, 41, 18, 10), "kHz", 5.6, LABEL, True, family=COND_FONT)
    # groove for the position bar and divider above the transport
    p.setPen(QPen(QColor(0, 0, 0, 150), 0.7))
    p.drawLine(QPointF(10, 85.5), QPointF(265, 85.5))
    p.setPen(QPen(QColor(255, 255, 255, 35), 0.7))
    p.drawLine(QPointF(10, 86.3), QPointF(265, 86.3))
    # logo badge
    lr = QRectF(250, 89, 18, 18)
    button(p, lr, radius=4)
    zp = QPainterPath()
    zp.moveTo(lr.left() + 4.5, lr.top() + 5)
    zp.lineTo(lr.right() - 4.5, lr.top() + 5)
    zp.lineTo(lr.left() + 4.5, lr.bottom() - 5)
    zp.lineTo(lr.right() - 4.5, lr.bottom() - 5)
    pen = QPen(ACCENT_HI, 1.6)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(zp)
    return c.done()


def make_cbuttons(res) -> QImage:
    c = Canvas(res, 136, 36)
    p = c.p
    items = [("prev", 0, 23), ("play", 23, 23), ("pause", 46, 23), ("stop", 69, 23), ("next", 92, 22)]
    for kind, x, w in items:
        for row, pressed in ((0, False), (18, True)):
            r = QRectF(x, row, w, 18).adjusted(0.3, 0.3, -0.3, -0.3)
            button(p, r, pressed, radius=3)
            icon(p, kind, r.translated(0.5, 0.5) if pressed else r, ACCENT_HI if pressed else ICON)
    for row, pressed in ((0, False), (16, True)):
        r = QRectF(114, row, 22, 16).adjusted(0.3, 0.3, -0.3, -0.3)
        button(p, r, pressed, radius=3)
        icon(p, "eject", r, ACCENT_HI if pressed else ICON, 0.9)
    return c.done()


def make_titlebar(res) -> QImage:
    c = Canvas(res, 344, 87)
    p = c.p
    title_bar(p, QRect(27, 0, 275, 14), "ZEBAMP", True)
    title_bar(p, QRect(27, 15, 275, 14), "ZEBAMP", False)
    title_bar(p, QRect(27, 57, 275, 14), "ZEBAMP", True)
    title_bar(p, QRect(27, 72, 275, 14), "ZEBAMP", False)
    for r, active in ((QRect(27, 29, 275, 14), True), (QRect(27, 42, 275, 14), False)):
        title_bar(p, r, "", active)
        lcd(p, QRectF(r.left() + 125, r.top() + 2, 32, 9), 1.5)
        lcd(p, QRectF(r.left() + 77, r.top() + 3, 41, 8), 1.5)
    small_btn(p, 0, 0, "menu")
    small_btn(p, 0, 9, "menu", True)
    small_btn(p, 9, 0, "min")
    small_btn(p, 9, 9, "min", True)
    small_btn(p, 18, 0, "close")
    small_btn(p, 18, 9, "close", True)
    small_btn(p, 0, 18, "shade")
    small_btn(p, 9, 18, "shade", True)
    small_btn(p, 0, 27, "unshade")
    small_btn(p, 9, 27, "unshade", True)
    # windowshade position bar + thumbs
    p.fillRect(QRectF(0, 36, 17, 7), LCD_BG)
    for x in (17, 20, 23):
        p.fillRect(QRectF(x, 36, 3, 7), ACCENT if x == 20 else QColor(40, 110, 190))
    # clutter bar O A I D V
    for x, enabled in ((304, True), (312, False)):
        p.fillRect(QRectF(x, 0, 8, 43), vgrad(0, 43, QColor(36, 40, 50), QColor(22, 24, 30)))
        for i, ch in enumerate("OAIDV"):
            text(p, QRectF(x, 2 + i * 8, 8, 8), ch, 5.6, LABEL if enabled else QColor(80, 86, 100), True,
                 family=COND_FONT)
    pressed = [(304, 47, "O", 8), (312, 55, "A", 7), (320, 62, "I", 7), (328, 69, "D", 8), (336, 77, "V", 7)]
    for x, y, ch, h in pressed:
        p.fillRect(QRectF(x, y, 8, h), QColor(20, 60, 110))
        text(p, QRectF(x, y, 8, h), ch, 5.6, ACCENT_HI, True, family=COND_FONT)
    return c.done()


def make_shufrep(res) -> QImage:
    c = Canvas(res, 92, 85)
    p = c.p
    for x, w, label in ((28, 47, "SHUFFLE"), (0, 28, "REP")):
        for i, (pressed, sel) in enumerate(((False, False), (True, False), (False, True), (True, True))):
            r = QRectF(x, i * 15, w, 15).adjusted(0.3, 0.3, -0.3, -0.3)
            button(p, r, pressed, radius=3, lit=sel)
            text(p, r.adjusted(0, 0.3 + (0.5 if pressed else 0), 0, 0), label, 5.9,
                 ACCENT_HI if sel else LABEL, True, family=COND_FONT, spacing=0.3)
    for x, label in ((0, "EQ"), (23, "PL")):
        for y, sel in ((61, False), (73, True)):
            for dx, pr in ((0, False), (46, True)):
                r = QRectF(x + dx, y, 23, 12).adjusted(0.3, 0.3, -0.3, -0.3)
                button(p, r, pr, radius=2.5, lit=sel)
                text(p, r, label, 5.9, ACCENT_HI if sel else LABEL, True,
                     family=COND_FONT)
    return c.done()


def make_text(res, fg=GLOW) -> QImage:
    """5x6 cells of the classic font, drawn with a crisp condensed face."""
    c = Canvas(res, 155, 18, LCD_BG)
    p = c.p
    f = font(6.4, True, COND_FONT)
    fm = QFontMetricsF(f)
    p.setFont(f)
    p.setPen(fg)
    done = set()
    for ch, (row, col) in SP.FONT_LOOKUP.items():
        key = (row, col)
        if key in done:
            continue
        done.add(key)
        if ch == " ":
            continue
        g = ch.upper()
        if g == "…":
            g = "…"
        cell = QRectF(col * 5, row * 6, 5, 6)
        p.save()
        p.setClipRect(cell)
        w = fm.horizontalAdvance(g)
        sx = min(1.0, 4.6 / max(0.1, w))
        p.translate(cell.left() + 2.5, cell.top())
        p.scale(sx, 1.0)
        p.drawText(QRectF(-4, -0.9, 8, 7.4), int(Qt.AlignmentFlag.AlignCenter), g)
        p.restore()
    return c.done()


SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
            "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": ""}


def _segment_digit(p: QPainter, ch: str, x0: float, on: QColor, off: QColor):
    """Slanted seven-segment digit in a 9x13 cell."""
    lit = SEGMENTS.get(ch, "")
    t = 0.9      # thickness
    sl = 0.9     # slant (x shift at the top)
    left, right = x0 + 1.6, x0 + 7.4
    top, mid, bot = 0.9, 6.5, 12.1

    def sk(x, y):  # slant: shift x by how high the point is
        return QPointF(x + sl * (bot - y) / (bot - top) - sl / 2, y)

    def hseg(y):
        return QPolygonF([sk(left + 0.6, y), sk(left + 1.2, y - t), sk(right - 1.2, y - t),
                          sk(right - 0.6, y), sk(right - 1.2, y + t), sk(left + 1.2, y + t)])

    def vseg(x, y0, y1):
        return QPolygonF([sk(x, y0 + 0.5), sk(x + t, y0 + 1.1), sk(x + t, y1 - 1.1),
                          sk(x, y1 - 0.5), sk(x - t, y1 - 1.1), sk(x - t, y0 + 1.1)])
    shapes = {"a": hseg(top + 0.2), "g": hseg(mid), "d": hseg(bot - 0.2),
              "f": vseg(left, top, mid), "b": vseg(right, top, mid),
              "e": vseg(left, mid, bot), "c": vseg(right, mid, bot)}
    p.setPen(Qt.PenStyle.NoPen)
    for s, poly in shapes.items():
        if s in lit:
            continue
        p.setBrush(off)
        p.drawPolygon(poly)
    for s, poly in shapes.items():
        if s not in lit:
            continue
        glow = QColor(on)
        glow.setAlpha(55)
        p.setPen(QPen(glow, 1.6))
        p.setBrush(on)
        p.drawPolygon(poly)
        p.setPen(Qt.PenStyle.NoPen)


def make_numbers(res, ex: bool) -> QImage:
    c = Canvas(res, 108 if ex else 99, 13, QColor(0, 0, 0, 0))
    p = c.p
    for i in range(10):
        _segment_digit(p, str(i), i * 9, GLOW, GLOW_DIM)
    if ex:
        _segment_digit(p, " ", 90, GLOW, GLOW_DIM)
        _segment_digit(p, "-", 99, GLOW, GLOW_DIM)
    else:
        p.fillRect(QRectF(20, 6, 5, 1), GLOW)
        p.fillRect(QRectF(9, 6, 5, 1), QColor(0, 0, 0, 0))
    return c.done()


def make_playpaus(res) -> QImage:
    c = Canvas(res, 42, 9, QColor(0, 0, 0, 0))
    p = c.p
    icon(p, "play", QRectF(0, 0, 9, 9), GLOW, 0.75)
    icon(p, "pause", QRectF(9, 0, 9, 9), GLOW, 0.75)
    icon(p, "stop", QRectF(18, 0, 9, 9), GLOW, 0.7)
    p.fillRect(QRectF(36, 0, 3, 9), QColor(0, 0, 0, 0))
    # (no "working" LED dot)
    return c.done()


def make_monoster(res) -> QImage:
    c = Canvas(res, 56, 24, QColor(0, 0, 0, 0))
    p = c.p
    for y, lit in ((0, True), (12, False)):
        col = ACCENT_HI if lit else QColor(70, 78, 94)
        text(p, QRectF(0, y, 29, 12), "STEREO", 5.6, col, True, family=COND_FONT, glow=lit)
        text(p, QRectF(29, y, 27, 12), "MONO", 5.6, col, True, family=COND_FONT, glow=lit)
    return c.done()


def _slider_thumb(p: QPainter, r: QRectF, sel: bool):
    button(p, r, False, radius=2.5, lit=sel)
    p.setPen(QPen(QColor(0, 0, 0, 120), 0.6))
    cx = r.center().x()
    for dx in (-1.5, 0, 1.5):
        p.drawLine(QPointF(cx + dx, r.top() + 3), QPointF(cx + dx, r.bottom() - 3))


def make_posbar(res) -> QImage:
    c = Canvas(res, 307, 10, QColor(0, 0, 0, 0))
    p = c.p
    groove = QRectF(0.5, 2.5, 247, 5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(vgrad(groove.top(), groove.bottom(), QColor(5, 6, 9), QColor(46, 50, 60)))
    p.drawPath(rrect(groove, 2.5))
    for x, sel in ((248, False), (278, True)):
        _slider_thumb(p, QRectF(x + 0.3, 0.3, 28.4, 9.4), sel)
    return c.done()


def _slider_strip(res, width: int, frames: int, mode: str) -> QImage:
    total_w = width if mode == "volume" else 47
    c = Canvas(res, total_w, 433, QColor(0, 0, 0, 0))
    p = c.p
    x0 = 0 if mode == "volume" else 9
    w = width
    for i in range(frames):
        y = i * 15
        t = i / (frames - 1)
        groove = QRectF(x0 + 0.5, y + 4, w - 1, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(vgrad(groove.top(), groove.bottom(), QColor(5, 6, 9), QColor(46, 50, 60)))
        p.drawPath(rrect(groove, 2.5))
        if mode == "volume":
            fill = QRectF(groove.left() + 0.8, groove.top() + 0.9, (groove.width() - 1.6) * t, 3.2)
            if fill.width() > 0.3:
                g = QLinearGradient(fill.left(), 0, groove.right(), 0)
                g.setColorAt(0, QColor(30, 90, 170))
                g.setColorAt(1, ACCENT_HI)
                p.setBrush(g)
                p.drawPath(rrect(fill, 1.6))
        else:
            # balance: lights from the centre towards the side
            mid = groove.center().x()
            span = (groove.width() / 2 - 0.8) * t
            if span > 0.3:
                p.setBrush(QColor(80, 170, 255))
                p.drawPath(rrect(QRectF(mid - span, groove.top() + 0.9, span * 2, 3.2), 1.6))
            p.setBrush(QColor(200, 230, 255))
            p.drawRect(QRectF(mid - 0.4, groove.top() + 0.5, 0.8, 4))
    for x, sel in ((15, False), (0, True)):
        _slider_thumb(p, QRectF(x + 0.3, 422.3, 13.4, 10.4), sel)
    return c.done()


EQ_LABELS = ["60", "170", "310", "600", "1K", "3K", "6K", "12K", "14K", "16K"]


def make_eqmain(res) -> QImage:
    c = Canvas(res, 275, 315)
    p = c.p
    body(p, QRect(0, 0, 275, 116))
    title_bar(p, QRect(0, 134, 275, 14), "EQUALIZER", True)
    title_bar(p, QRect(0, 149, 275, 14), "EQUALIZER", False)
    title_bar(p, QRect(0, 0, 275, 14), "EQUALIZER", False)
    p.fillRect(QRectF(0, 116, 275, 18), BODY_BOT)
    small_btn(p, 0, 116, "close")
    small_btn(p, 0, 125, "close", True)
    for top in (134, 149, 0):
        small_btn(p, 264, top + 3, "close")
        small_btn(p, 254, top + 3, "shade")
    lcd(p, QRectF(85, 16, 115, 21), 2.5)
    for lab, y in (("+12 dB", 37), ("0 dB", 65), ("-12 dB", 96)):
        text(p, QRectF(36, y - 2, 30, 9), lab, 5.4, LABEL, True, family=COND_FONT)
    text(p, QRectF(8, 102, 34, 10), "PREAMP", 5.6, LABEL, True, family=COND_FONT)
    for i, lab in enumerate(EQ_LABELS):
        text(p, QRectF(76 + i * 18, 102, 18, 10), lab, 5.6, LABEL, True, family=COND_FONT)
    for x, w, label in ((10, 26, "ON"), (36, 32, "AUTO")):
        for dx, sel, pressed in ((0, False, False), (118, False, True), (59, True, False), (177, True, True)):
            r = QRectF(x + dx, 119, w, 12).adjusted(0.3, 0.3, -0.3, -0.3)
            button(p, r, pressed, radius=2.5, lit=sel)
            text(p, r, label, 5.8, ACCENT_HI if sel else LABEL, True, family=COND_FONT)
    for f in range(28):
        x = 13 + (f % 14) * 15
        y = 164 + (f // 14) * 65
        p.fillRect(QRectF(x, y, 14, 63), BODY_MID)
        groove = QRectF(x + 5, y + 0.5, 4, 62)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QLinearGradient())
        p.setBrush(vgrad(groove.top(), groove.bottom(), QColor(5, 6, 9), QColor(30, 34, 42)))
        p.drawPath(rrect(groove, 2))
        level = 60 * f / 27
        if level > 0.5:
            g = QLinearGradient(0, groove.bottom(), 0, groove.top())
            g.setColorAt(0, QColor(30, 90, 170))
            g.setColorAt(1, ACCENT_HI)
            p.setBrush(g)
            p.drawPath(rrect(QRectF(x + 6, groove.bottom() - level - 0.5, 2, level), 1))
    for y, sel in ((164, False), (176, True)):
        _slider_thumb(p, QRectF(0.3, y + 0.3, 10.4, 10.4), sel)
    for y, pressed in ((164, False), (176, True)):
        r = QRectF(224, y, 44, 12).adjusted(0.3, 0.3, -0.3, -0.3)
        button(p, r, pressed, radius=2.5)
        text(p, r, "PRESETS", 5.8, ACCENT_HI if pressed else LABEL, True, family=COND_FONT)
    # graph background, line colour ramp and preamp line
    p.fillRect(QRectF(0, 294, 113, 19), LCD_BG)
    p.setPen(QPen(QColor(40, 70, 110), 0.5))
    p.drawLine(QPointF(0, 303.5), QPointF(113, 303.5))
    for i in range(19):
        t = abs(i - 9) / 9
        p.fillRect(QRectF(115, 294 + i, 1, 1), QColor(int(110 + 145 * t), int(205 - 60 * t), int(255 - 175 * t)))
    p.fillRect(QRectF(0, 314, 113, 1), QColor(150, 165, 190))
    return c.done()


def make_eq_ex(res) -> QImage:
    c = Canvas(res, 275, 56)
    p = c.p
    for y, active in ((0, True), (15, False)):
        title_bar(p, QRect(0, y, 275, 14), "", active)
        lcd(p, QRectF(60, y + 3, 99, 8), 1.5)
        lcd(p, QRectF(163, y + 3, 45, 8), 1.5)
        small_btn(p, 264, y + 3, "close")
        small_btn(p, 254, y + 3, "unshade")
    for x in (1, 4, 7, 11, 14, 17):
        p.fillRect(QRectF(x, 30, 3, 7), ACCENT)
    small_btn(p, 1, 38, "unshade", True)
    small_btn(p, 1, 47, "shade", True)
    small_btn(p, 11, 38, "close")
    small_btn(p, 11, 47, "close", True)
    return c.done()


def _bar_button(p, r: QRectF, label: str, pressed=False):
    button(p, r.adjusted(0.3, 0.3, -0.3, -0.3), pressed, radius=2.5)
    text(p, r, label, 5.8, ACCENT_HI if pressed else LABEL, True, family=COND_FONT)


def make_pledit(res) -> QImage:
    c = Canvas(res, 280, 186)
    p = c.p
    for y, active in ((0, True), (21, False)):
        for x, w in ((0, 25), (127, 25), (153, 25)):
            title_bar(p, QRect(x, y, w, 20), "", active)
        title_bar(p, QRect(26, y, 100, 20), "PLAYLIST", active)
        small_btn(p, 153 + 14, y + 3, "close")
        small_btn(p, 153 + 4, y + 3, "shade")
    # side tiles: tileable vertically, so no top/bottom edges
    side_tile(p, QRectF(0, 42, 12, 29), left=True)
    side_tile(p, QRectF(31, 42, 20, 29), left=False)
    trough = QLinearGradient(31 + 7, 0, 31 + 15, 0)
    trough.setColorAt(0, QColor(6, 7, 10))
    trough.setColorAt(1, QColor(26, 29, 36))
    p.fillRect(QRectF(31 + 7, 42, 8, 29), trough)
    # scroll handles
    _slider_thumb(p, QRectF(52.3, 53.3, 7.4, 17.4), False)
    _slider_thumb(p, QRectF(61.3, 53.3, 7.4, 17.4), True)
    small_btn(p, 52, 42, "close", True)
    small_btn(p, 62, 42, "shade", True)
    small_btn(p, 150, 42, "unshade", True)
    for x, y, w in ((72, 57, 25), (72, 42, 25)):
        title_bar(p, QRect(x, y, w, 14), "", y == 42)
    for y, active in ((57, False), (42, True)):
        title_bar(p, QRect(99, y, 50, 14), "", active)
        small_btn(p, 99 + 39, y + 3, "close")
        small_btn(p, 99 + 29, y + 3, "unshade")
    # bottom
    body(p, QRect(0, 72, 125, 38))
    body(p, QRect(126, 72, 150, 38))
    body(p, QRect(179, 0, 25, 38))
    body(p, QRect(205, 0, 75, 38))
    lcd(p, QRectF(205 + 2, 12, 72, 16), 2)
    for i, lab in enumerate(["ADD", "REM", "SEL", "MISC"]):
        _bar_button(p, QRectF(14 + i * 29, 72 + 8, 22, 18), lab)
    br = 126
    lcd(p, QRectF(br + 5, 72 + 8, 82, 10), 1.5)
    for i, kind in enumerate(["prev", "play", "pause", "stop", "next", "eject"]):
        icon(p, kind, QRectF(br + 3 + i * 10, 72 + 22, 10, 10), LABEL, 0.55)
    lcd(p, QRectF(br + 62, 72 + 21, 31, 10), 1.5)
    _bar_button(p, QRectF(br + 150 - 44, 72 + 8, 22, 18), "LIST")
    pen = QPen(QColor(150, 160, 180), 0.8)
    p.setPen(pen)
    for i in range(3):
        p.drawLine(QPointF(br + 140 + i * 3, 72 + 36.5), QPointF(br + 148.5, 72 + 28 + i * 3))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(LABEL)
    ax = br + 150 - 12
    p.drawPolygon(QPolygonF([QPointF(ax - 3, 72 + 6), QPointF(ax + 3, 72 + 6), QPointF(ax, 72 + 2.5)]))
    p.drawPolygon(QPolygonF([QPointF(ax - 3, 72 + 9), QPointF(ax + 3, 72 + 9), QPointF(ax, 72 + 12.5)]))
    menu = [(0, 111, ["URL", "DIR", "FILE"]), (54, 111, ["ALL", "CROP", "SEL", "MISC"]),
            (104, 111, ["INV", "NONE", "ALL"]), (154, 111, ["SORT", "INFO", "OPTS"]),
            (204, 111, ["NEW", "SAVE", "LOAD"])]
    for x, y0, labels in menu:
        for i, lab in enumerate(labels):
            for dx, pressed in ((0, False), (23, True)):
                _bar_button(p, QRectF(x + dx, y0 + i * 19, 22, 18), lab, pressed)
    for x, h in ((48, 54), (100, 72), (150, 54), (200, 54), (250, 54)):
        p.fillRect(QRectF(x, 111, 3, h), ACCENT)
    return c.done()


def side_tile(p: QPainter, r: QRectF, left: bool):
    g = QLinearGradient(r.left(), 0, r.right(), 0)
    if left:
        g.setColorAt(0, QColor(92, 100, 118))
        g.setColorAt(0.15, BODY_MID)
        g.setColorAt(1, BODY_BOT)
    else:
        g.setColorAt(0, BODY_BOT)
        g.setColorAt(0.85, BODY_MID)
        g.setColorAt(1, QColor(20, 22, 28))
    p.fillRect(r, g)


def make_gen(res) -> QImage:
    c = Canvas(res, 194, 109)
    p = c.p
    for y, active in ((0, True), (21, False)):
        for x in (0, 26, 52, 78, 104, 130):
            title_bar(p, QRect(x, y, 25, 20), "", active)
        small_btn(p, 130 + 14, y + 4, "close")
    body(p, QRect(0, 42, 125, 14))
    body(p, QRect(0, 57, 125, 14))
    body(p, QRect(127, 72, 25, 14))
    for x, w, left in ((127, 11, True), (158, 11, True), (139, 8, False), (170, 8, False)):
        side_tile(p, QRectF(x, 42, w, 29), left)
    small_btn(p, 148, 42, "close", True)
    return c.done()


GENEX_NAMES = ["item_bg", "item_fg", "window_bg", "button_text", "window_text", "divider",
               "playlist_selection", "list_header_bg", "list_header_text", "list_header_frame_tl",
               "list_header_frame_br", "list_header_frame_pressed", "list_header_dead",
               "scrollbar_one", "scrollbar_two", "pressed_scrollbar_one", "pressed_scrollbar_two",
               "scrollbar_dead", "list_text_highlighted", "list_text_highlighted_bg",
               "list_text_selected", "list_text_selected_bg"]
GENEX_COLORS = [LCD_BG, GLOW, BODY_MID, ICON, ICON, EDGE_HI, QColor(20, 60, 110), BTN_BOT, ICON,
                BTN_TOP, EDGE_LO, EDGE_LO, BODY_MID, BTN_BOT, BTN_TOP, QColor(40, 110, 190), ACCENT,
                BODY_BOT, QColor(255, 255, 255), QColor(30, 80, 150), QColor(255, 255, 255),
                QColor(20, 60, 110)]


def make_genex(res) -> QImage:
    c = Canvas(res, 96, 64, BODY_MID)
    for i, col in enumerate(GENEX_COLORS):
        c.p.fillRect(QRectF(48 + i * 2, 0, 2, 1), col)
    return c.done()


_CACHE: dict[int, ClassicSkin] = {}


def zebamp_skin(res: int = 2) -> ClassicSkin:
    res = max(1, int(res))
    sk = _CACHE.get(res)
    if sk is not None:
        return sk
    sheets = {
        "MAIN": make_main(res), "CBUTTONS": make_cbuttons(res), "TITLEBAR": make_titlebar(res),
        "SHUFREP": make_shufrep(res), "TEXT": make_text(res), "NUMBERS": make_numbers(res, False),
        "NUMS_EX": make_numbers(res, True), "PLAYPAUS": make_playpaus(res),
        "MONOSTER": make_monoster(res), "POSBAR": make_posbar(res),
        "VOLUME": _slider_strip(res, 68, 28, "volume"), "BALANCE": _slider_strip(res, 38, 28, "balance"),
        "EQMAIN": make_eqmain(res), "EQ_EX": make_eq_ex(res), "PLEDIT": make_pledit(res),
        "GEN": make_gen(res), "GENEX": make_genex(res),
    }
    vis = [QColor(3, 9, 20), QColor(3, 9, 20)]   # [1] = grid dots: none
    for i in range(16):        # top (index 2) -> bottom (17): white-blue to deep blue
        t = i / 15
        vis.append(QColor(int(225 - 205 * t), int(245 - 150 * t), 255 - int(60 * t)))
    vis += [QColor(225, 245, 255), QColor(160, 220, 255), QColor(110, 190, 255),
            QColor(70, 150, 240), QColor(40, 110, 210), QColor(235, 245, 255)]
    pledit = {"normal": QColor(130, 205, 255), "current": QColor(255, 255, 255),
              "normalbg": QColor(5, 12, 24), "selectedbg": QColor(24, 70, 140), "font": "DejaVu Sans"}
    sk = ClassicSkin(sheets, name="Zebamp", path=None, fallback=None, viscolors=vis,
                     pledit=pledit, nums_ex=True, res=res, text_colors=(GLOW, LCD_BG))
    sk.genex_colors = {n: GENEX_COLORS[i] for i, n in enumerate(GENEX_NAMES)}
    sk.vector = True
    _CACHE.clear()
    _CACHE[res] = sk
    return sk
