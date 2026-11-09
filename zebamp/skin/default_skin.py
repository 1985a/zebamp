"""Procedurally drawn default skin ("Zebes").

It is an original design that follows the classic sprite layout, so it also
acts as the fallback for any bitmap a third-party skin does not provide.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPolygon)

from . import sprites as SP
from .classic import ClassicSkin

# ---------------------------------------------------------------- palette
BG = QColor(38, 42, 52)
BG_HI = QColor(70, 77, 94)
BG_LO = QColor(18, 20, 26)
FACE = QColor(54, 60, 74)
FACE_HI = QColor(96, 106, 128)
FACE_LO = QColor(26, 29, 36)
LCD = QColor(6, 10, 12)
LCD_EDGE = QColor(30, 38, 44)
ACCENT = QColor(62, 240, 200)
ACCENT_DIM = QColor(18, 70, 60)
ACCENT_MID = QColor(36, 150, 125)
TEXT_FG = QColor(62, 240, 200)
LABEL = QColor(150, 160, 180)
TITLE_ON = QColor(62, 240, 200)
TITLE_OFF = QColor(110, 118, 135)

# 3x5 / 4x5 pixel font -------------------------------------------------
FONT = {
    "a": ".#.|#.#|###|#.#|#.#", "b": "##.|#.#|##.|#.#|##.",
    "c": ".##|#..|#..|#..|.##", "d": "##.|#.#|#.#|#.#|##.",
    "e": "###|#..|##.|#..|###", "f": "###|#..|##.|#..|#..",
    "g": ".##|#..|#.#|#.#|.##", "h": "#.#|#.#|###|#.#|#.#",
    "i": "###|.#.|.#.|.#.|###", "j": "..#|..#|..#|#.#|.#.",
    "k": "#.#|#.#|##.|#.#|#.#", "l": "#..|#..|#..|#..|###",
    "m": "#...#|##.##|#.#.#|#...#|#...#", "n": "#..#|##.#|#.##|#..#|#..#",
    "o": ".#.|#.#|#.#|#.#|.#.", "p": "##.|#.#|##.|#..|#..",
    "q": ".#.|#.#|#.#|###|.##", "r": "##.|#.#|##.|#.#|#.#",
    "s": ".##|#..|.#.|..#|##.", "t": "###|.#.|.#.|.#.|.#.",
    "u": "#.#|#.#|#.#|#.#|###", "v": "#.#|#.#|#.#|#.#|.#.",
    "w": "#...#|#...#|#.#.#|##.##|#...#", "x": "#.#|#.#|.#.|#.#|#.#",
    "y": "#.#|#.#|.#.|.#.|.#.", "z": "###|..#|.#.|#..|###",
    '"': "#.#|#.#|...|...|...", "@": "###|#.#|###|#..|###",
    " ": "...|...|...|...|...",
    "0": "###|#.#|#.#|#.#|###", "1": ".#.|##.|.#.|.#.|###",
    "2": "##.|..#|.#.|#..|###", "3": "##.|..#|.#.|..#|##.",
    "4": "#.#|#.#|###|..#|..#", "5": "###|#..|##.|..#|##.",
    "6": ".##|#..|###|#.#|###", "7": "###|..#|.#.|.#.|.#.",
    "8": "###|#.#|###|#.#|###", "9": "###|#.#|###|..#|##.",
    "…": "...|...|...|...|#.#", ".": "...|...|...|...|.#.",
    ":": "...|.#.|...|.#.|...", "(": "..#|.#.|.#.|.#.|..#",
    ")": "#..|.#.|.#.|.#.|#..", "-": "...|...|###|...|...",
    "'": ".#.|.#.|...|...|...", "!": ".#.|.#.|.#.|...|.#.",
    "_": "...|...|...|...|###", "+": "...|.#.|###|.#.|...",
    "\\": "#..|#..|.#.|..#|..#", "/": "..#|..#|.#.|#..|#..",
    "[": "##.|#..|#..|#..|##.", "]": ".##|..#|..#|..#|.##",
    "^": ".#.|#.#|...|...|...", "&": ".#.|#.#|.#.|#.#|.##",
    "%": "#.#|..#|.#.|#..|#.#", ",": "...|...|...|.#.|#..",
    "=": "...|###|...|###|...", "$": ".##|##.|.#.|.##|##.",
    "#": "#.#|###|#.#|###|#.#",
    "Å": ".#.|.#.|#.#|###|#.#", "Ö": "#.#|.#.|#.#|#.#|.#.",
    "Ä": "#.#|.#.|#.#|###|#.#", "?": "##.|..#|.#.|...|.#.",
    "*": "...|#.#|.#.|#.#|...",
}


def _img(w, h, color=None) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(color if color is not None else BG)
    return img


def draw_glyph(p: QPainter, ch: str, x: int, y: int, color: QColor):
    rows = FONT.get(ch) or FONT.get(ch.lower())
    if rows is None:
        return 0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for ry, row in enumerate(rows.split("|")):
        for rx, c in enumerate(row):
            if c == "#":
                p.drawRect(x + rx, y + ry, 1, 1)
    return len(rows.split("|")[0])


def draw_label(p: QPainter, text: str, x: int, y: int, color=LABEL, spacing=1):
    for ch in text:
        w = draw_glyph(p, ch, x, y, color)
        x += (w or 3) + spacing
    return x


def label_width(text: str, spacing=1) -> int:
    w = 0
    for ch in text:
        rows = FONT.get(ch) or FONT.get(ch.lower()) or "..."
        w += len(rows.split("|")[0]) + spacing
    return w - spacing if text else 0


def bevel(p: QPainter, r: QRect, face=FACE, hi=FACE_HI, lo=FACE_LO,
          pressed=False):
    p.fillRect(r, face)
    a, b = (lo, hi) if pressed else (hi, lo)
    p.setPen(a)
    p.drawLine(r.left(), r.top(), r.right(), r.top())
    p.drawLine(r.left(), r.top(), r.left(), r.bottom())
    p.setPen(b)
    p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.drawLine(r.right(), r.top(), r.right(), r.bottom())


def sunken(p: QPainter, r: QRect, fill=LCD):
    p.fillRect(r, fill)
    p.setPen(BG_LO)
    p.drawLine(r.left(), r.top(), r.right(), r.top())
    p.drawLine(r.left(), r.top(), r.left(), r.bottom())
    p.setPen(BG_HI)
    p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.drawLine(r.right(), r.top(), r.right(), r.bottom())


def body_texture(p: QPainter, r: QRect):
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(48, 53, 65))
    g.setColorAt(1, QColor(30, 33, 41))
    p.fillRect(r, g)
    p.setPen(QColor(255, 255, 255, 10))
    for yy in range(r.top() + 1, r.bottom(), 3):
        p.drawLine(r.left(), yy, r.right(), yy)


def frame(p: QPainter, r: QRect):
    p.setPen(BG_HI)
    p.drawLine(r.left(), r.top(), r.right(), r.top())
    p.drawLine(r.left(), r.top(), r.left(), r.bottom())
    p.setPen(BG_LO)
    p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.drawLine(r.right(), r.top(), r.right(), r.bottom())


# ---------------------------------------------------------------- sheets
def make_main() -> QImage:
    img = _img(275, 116)
    p = QPainter(img)
    body_texture(p, QRect(0, 0, 275, 116))
    frame(p, QRect(0, 0, 275, 116))
    # LCD block (time + vis)
    sunken(p, QRect(22, 20, 82, 41))
    # marquee
    sunken(p, QRect(109, 22, 158, 13))
    # kbps / khz
    sunken(p, QRect(109, 41, 19, 10))
    draw_label(p, "kbps", 130, 43)
    sunken(p, QRect(154, 41, 14, 10))
    draw_label(p, "khz", 170, 43)
    # bottom deck
    p.setPen(BG_LO)
    p.drawLine(10, 85, 264, 85)
    p.setPen(BG_HI)
    p.drawLine(10, 86, 264, 86)
    # logo
    p.fillRect(QRect(251, 90, 16, 16), FACE_LO)
    p.setPen(ACCENT_MID)
    p.drawLine(254, 93, 263, 93)
    p.drawLine(263, 93, 254, 102)
    p.drawLine(254, 102, 263, 102)
    p.end()
    return img


def _button_icon(p: QPainter, kind: str, r: QRect, color: QColor):
    cx, cy = r.center().x(), r.center().y()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    if kind == "prev":
        p.drawRect(cx - 5, cy - 3, 2, 7)
        p.drawPolygon(QPolygon([QPoint(cx + 4, cy - 3), QPoint(cx + 4, cy + 3),
                                QPoint(cx - 2, cy)]))
    elif kind == "play":
        p.drawPolygon(QPolygon([QPoint(cx - 3, cy - 4), QPoint(cx - 3, cy + 4),
                                QPoint(cx + 4, cy)]))
    elif kind == "pause":
        p.drawRect(cx - 4, cy - 3, 3, 7)
        p.drawRect(cx + 1, cy - 3, 3, 7)
    elif kind == "stop":
        p.drawRect(cx - 3, cy - 3, 7, 7)
    elif kind == "next":
        p.drawPolygon(QPolygon([QPoint(cx - 4, cy - 3), QPoint(cx - 4, cy + 3),
                                QPoint(cx + 2, cy)]))
        p.drawRect(cx + 3, cy - 3, 2, 7)
    elif kind == "eject":
        p.drawPolygon(QPolygon([QPoint(cx - 5, cy + 1), QPoint(cx + 5, cy + 1),
                                QPoint(cx, cy - 4)]))
        p.drawRect(cx - 5, cy + 3, 11, 2)


def make_cbuttons() -> QImage:
    img = _img(136, 36)
    p = QPainter(img)
    items = [("prev", 0, 23), ("play", 23, 23), ("pause", 46, 23),
             ("stop", 69, 23), ("next", 92, 22)]
    for kind, x, w in items:
        for row, pressed in ((0, False), (18, True)):
            r = QRect(x, row, w, 18)
            bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
            ir = r.translated(1, 1) if pressed else r
            _button_icon(p, kind, ir, ACCENT if pressed else QColor(205, 212, 225))
    for row, pressed in ((0, False), (16, True)):
        r = QRect(114, row, 22, 16)
        bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
        _button_icon(p, "eject", r.translated(1, 1) if pressed else r,
                     ACCENT if pressed else QColor(205, 212, 225))
    p.end()
    return img


def _small_btn(p: QPainter, x, y, kind, pressed=False):
    r = QRect(x, y, 9, 9)
    bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
    p.setPen(ACCENT if pressed else QColor(200, 206, 220))
    if kind == "close":
        p.drawLine(x + 2, y + 2, x + 6, y + 6)
        p.drawLine(x + 6, y + 2, x + 2, y + 6)
    elif kind == "min":
        p.drawLine(x + 2, y + 6, x + 6, y + 6)
    elif kind == "shade":
        p.drawLine(x + 2, y + 2, x + 6, y + 2)
        p.drawLine(x + 2, y + 4, x + 6, y + 4)
    elif kind == "unshade":
        p.drawRect(x + 2, y + 2, 4, 4)
    elif kind == "menu":
        p.drawLine(x + 2, y + 3, x + 6, y + 3)
        p.drawLine(x + 3, y + 4, x + 5, y + 4)
        p.drawPoint(x + 4, y + 5)


def _title_bar(p: QPainter, r: QRect, text: str, active: bool):
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    if active:
        g.setColorAt(0, QColor(64, 72, 92))
        g.setColorAt(1, QColor(34, 38, 48))
    else:
        g.setColorAt(0, QColor(48, 52, 62))
        g.setColorAt(1, QColor(32, 34, 40))
    p.fillRect(r, g)
    p.setPen(BG_HI)
    p.drawLine(r.left(), r.top(), r.right(), r.top())
    color = TITLE_ON if active else TITLE_OFF
    tw = label_width(text)
    tx = r.left() + (r.width() - tw) // 2
    # grip lines either side of the title
    p.setPen(QColor(color.red(), color.green(), color.blue(), 90))
    for yy in (r.top() + 5, r.top() + 8):
        p.drawLine(r.left() + 20, yy, tx - 6, yy)
        p.drawLine(tx + tw + 5, yy, r.right() - 36, yy)
    draw_label(p, text, tx, r.top() + 4, color)


def make_titlebar() -> QImage:
    img = _img(344, 87, QColor(0, 0, 0, 0))
    p = QPainter(img)
    _title_bar(p, QRect(27, 0, 275, 14), "zebamp", True)
    _title_bar(p, QRect(27, 15, 275, 14), "zebamp", False)
    _title_bar(p, QRect(27, 57, 275, 14), "zebamp", True)
    _title_bar(p, QRect(27, 72, 275, 14), "zebamp", False)
    for r, active in ((QRect(27, 29, 275, 14), True), (QRect(27, 42, 275, 14), False)):
        _title_bar(p, r, "", active)
        sunken(p, QRect(r.left() + 125, r.top() + 2, 32, 9))
        sunken(p, QRect(r.left() + 77, r.top() + 3, 41, 8))
    # buttons: normal row y=0, pressed row y=9
    _small_btn(p, 0, 0, "menu")
    _small_btn(p, 0, 9, "menu", True)
    _small_btn(p, 9, 0, "min")
    _small_btn(p, 9, 9, "min", True)
    _small_btn(p, 18, 0, "close")
    _small_btn(p, 18, 9, "close", True)
    _small_btn(p, 0, 18, "shade")
    _small_btn(p, 9, 18, "shade", True)
    _small_btn(p, 0, 27, "unshade")
    _small_btn(p, 9, 27, "unshade", True)
    # shade position bar
    p.fillRect(QRect(0, 36, 17, 7), LCD)
    p.fillRect(QRect(17, 36, 9, 7), ACCENT_MID)
    p.fillRect(QRect(20, 36, 3, 7), ACCENT)
    # clutter bar (enabled / disabled) and pressed states
    for x, col in ((304, LABEL), (312, QColor(80, 86, 100))):
        p.fillRect(QRect(x, 0, 8, 43), FACE_LO)
        for i, ch in enumerate("oaidv"):
            draw_glyph(p, ch, x + 2, 4 + i * 8, col)
    pressed = [(304, 47, "o", 8), (312, 55, "a", 7), (320, 62, "i", 7),
               (328, 69, "d", 8), (336, 77, "v", 7)]
    for x, y, ch, h in pressed:
        p.fillRect(QRect(x, y, 8, h), ACCENT_DIM)
        draw_glyph(p, ch, x + 2, y + 1, ACCENT)
    p.end()
    return img


def make_shufrep() -> QImage:
    img = _img(92, 85)
    p = QPainter(img)
    for x, w, text in ((28, 47, "shuffle"), (0, 28, "rep")):
        for i, (pressed, sel) in enumerate(((False, False), (True, False),
                                            (False, True), (True, True))):
            r = QRect(x, i * 15, w, 15)
            bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
            col = ACCENT if sel else QColor(150, 158, 175)
            tw = label_width(text)
            draw_label(p, text, x + (w - tw) // 2 + (1 if pressed else 0),
                       i * 15 + 5 + (1 if pressed else 0), col)
    for x, text in ((0, "eq"), (23, "pl")):
        for y, sel in ((61, False), (73, True)):
            for dx, pr in ((0, False), (46, True)):
                r = QRect(x + dx, y, 23, 12)
                bevel(p, r, face=FACE_LO if pr else FACE, pressed=pr)
                p.fillRect(QRect(x + dx + 3, y + 4, 3, 4),
                           ACCENT if sel else ACCENT_DIM)
                draw_label(p, text, x + dx + 9, y + 4,
                           ACCENT if sel else QColor(150, 158, 175))
    p.end()
    return img


def make_text() -> QImage:
    img = _img(155, 18, LCD)
    p = QPainter(img)
    for ch, (r, c) in SP.FONT_LOOKUP.items():
        if ch in FONT or ch.lower() in FONT:
            if ch.isalpha() and ch.islower() and ch.upper() in FONT:
                continue
            draw_glyph(p, ch, c * 5, r * 6, TEXT_FG)
    p.end()
    return img


SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def _digit(p: QPainter, ch: str, x: int, on: QColor, off: QColor | None):
    segs = {
        "a": [(x + 2, 0, 5, 1)], "d": [(x + 2, 12, 5, 1)],
        "g": [(x + 2, 6, 5, 1)],
        "f": [(x + 1, 1, 1, 5)], "b": [(x + 7, 1, 1, 5)],
        "e": [(x + 1, 7, 1, 5)], "c": [(x + 7, 7, 1, 5)],
    }
    lit = SEGMENTS.get(ch, "")
    for s, rects in segs.items():
        col = on if s in lit else off
        if col is None:
            continue
        for rx, ry, rw, rh in rects:
            p.fillRect(QRect(rx, ry, rw, rh), col)


def make_numbers(ex: bool) -> QImage:
    img = _img(108 if ex else 99, 13, LCD)
    p = QPainter(img)
    for i in range(10):
        _digit(p, str(i), i * 9, ACCENT, ACCENT_DIM)
    if ex:
        p.fillRect(QRect(90, 0, 9, 13), LCD)
        _digit(p, "", 90, ACCENT, ACCENT_DIM)
        _digit(p, "", 99, ACCENT, ACCENT_DIM)
        p.fillRect(QRect(101, 6, 5, 1), ACCENT)
    else:
        p.fillRect(QRect(20, 6, 5, 1), ACCENT)
        p.fillRect(QRect(9, 6, 5, 1), LCD)
    p.end()
    return img


def make_playpaus() -> QImage:
    img = _img(42, 9, LCD)
    p = QPainter(img)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ACCENT)
    p.drawPolygon(QPolygon([QPoint(2, 1), QPoint(2, 7), QPoint(6, 4)]))
    p.fillRect(QRect(11, 1, 2, 7), ACCENT)
    p.fillRect(QRect(14, 1, 2, 7), ACCENT)
    p.fillRect(QRect(20, 2, 5, 5), ACCENT)
    p.fillRect(QRect(36, 0, 3, 9), LCD)
    p.fillRect(QRect(39, 0, 3, 9), LCD)
    p.fillRect(QRect(40, 3, 1, 3), ACCENT)
    p.end()
    return img


def make_monoster() -> QImage:
    img = _img(56, 24)
    p = QPainter(img)
    for y, lit in ((0, True), (12, False)):
        col = ACCENT if lit else QColor(60, 66, 80)
        p.fillRect(QRect(0, y, 29, 12), BG)
        draw_label(p, "stereo", 2, y + 4, col)
        p.fillRect(QRect(29, y, 27, 12), BG)
        draw_label(p, "mono", 33, y + 4, col)
    p.end()
    return img


def make_posbar() -> QImage:
    img = _img(307, 10)
    p = QPainter(img)
    sunken(p, QRect(0, 0, 248, 10), BG_LO)
    p.fillRect(QRect(2, 4, 244, 2), QColor(14, 16, 20))
    for x, sel in ((248, False), (278, True)):
        r = QRect(x, 0, 29, 10)
        bevel(p, r, face=ACCENT_MID if sel else FACE)
        p.setPen(ACCENT if sel else FACE_HI)
        for dx in (11, 14, 17):
            p.drawLine(x + dx, 2, x + dx, 7)
    p.end()
    return img


def _slider_strip(width: int, frames: int, mode: str) -> QImage:
    img = _img(width, 433, QColor(0, 0, 0, 0))
    p = QPainter(img)
    for i in range(frames):
        y = i * 15
        sunken(p, QRect(0, y, width if mode == "volume" else 38, 13), BG_LO)
        t = i / (frames - 1)
        if mode == "volume":
            fill = int((width - 6) * t)
            g = QColor(int(36 + 190 * t), int(150 + 60 * (1 - t)), int(125 * (1 - t) + 40))
            p.fillRect(QRect(3, y + 5, fill, 3), g)
        else:
            c = QColor(int(36 + 190 * t), int(150 + 60 * (1 - t)), 120)
            p.fillRect(QRect(3, y + 5, 32, 3), c)
    for x, sel in ((15, False), (0, True)):
        r = QRect(x, 422, 14, 11)
        bevel(p, r, face=ACCENT_MID if sel else FACE)
        p.setPen(ACCENT if sel else FACE_HI)
        p.drawLine(x + 7, 424, x + 7, 430)
    p.end()
    if mode == "balance":
        # classic balance.bmp has its frames at x=9; shift the whole strip
        out = _img(47, 433, QColor(0, 0, 0, 0))
        q = QPainter(out)
        q.drawImage(9, 0, img.copy(0, 0, 38, 420))
        q.drawImage(0, 422, img.copy(0, 422, 29, 11))
        q.end()
        return out
    return img


def make_eqmain() -> QImage:
    img = _img(275, 315)
    p = QPainter(img)
    body_texture(p, QRect(0, 0, 275, 116))
    frame(p, QRect(0, 0, 275, 116))
    _title_bar(p, QRect(0, 134, 275, 14), "equalizer", True)
    _title_bar(p, QRect(0, 149, 275, 14), "equalizer", False)
    p.fillRect(QRect(0, 116, 275, 18), BG)
    _small_btn(p, 0, 116, "close")
    _small_btn(p, 0, 125, "close", True)
    for r in (QRect(0, 134, 275, 14), QRect(0, 149, 275, 14)):
        _small_btn(p, 264, r.top() + 3, "close")
        _small_btn(p, 254, r.top() + 3, "shade")
    p.drawImage(0, 0, img.copy(0, 149, 275, 14))
    # graph box
    sunken(p, QRect(85, 16, 115, 21))
    # labels
    draw_label(p, "+12", 49, 37)
    draw_label(p, "0", 53, 65)
    draw_label(p, "-12", 49, 96)
    draw_label(p, "preamp", 15, 105)
    for i, lab in enumerate(["60", "170", "310", "600", "1k", "3k", "6k",
                             "12k", "14k", "16k"]):
        x = 78 + i * 18 + (14 - label_width(lab)) // 2
        draw_label(p, lab, x, 105)
    # on / auto
    for x, w, text, _base in ((10, 26, "on", 0), (36, 32, "auto", 0)):
        for dx, sel, pressed in ((0, False, False), (118, False, True),
                                 (59, True, False), (177, True, True)):
            r = QRect(x + dx, 119, w, 12)
            bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
            p.fillRect(QRect(x + dx + 3, 123, 3, 4), ACCENT if sel else ACCENT_DIM)
            draw_label(p, text, x + dx + 9, 123, ACCENT if sel else LABEL)
    # band slider frames 14x63, 28 states
    for f in range(28):
        x = 13 + (f % 14) * 15
        y = 164 + (f // 14) * 65
        p.fillRect(QRect(x, y, 14, 63), BG)
        sunken(p, QRect(x + 5, y, 4, 63), BG_LO)
        level = int(61 * f / 27)
        t = f / 27
        col = QColor(int(40 + 200 * t), int(200 - 90 * t), int(160 - 120 * t))
        p.fillRect(QRect(x + 6, y + 62 - level, 2, level), col)
    for y, sel in ((164, False), (176, True)):
        r = QRect(0, y, 11, 11)
        bevel(p, r, face=ACCENT_MID if sel else FACE)
        p.setPen(ACCENT if sel else FACE_HI)
        p.drawLine(2, y + 5, 8, y + 5)
    # presets button
    for y, pressed in ((164, False), (176, True)):
        r = QRect(224, y, 44, 12)
        bevel(p, r, face=FACE_LO if pressed else FACE, pressed=pressed)
        draw_label(p, "presets", 228 + (1 if pressed else 0), y + 4, LABEL)
    # graph background, line colours and preamp line
    p.fillRect(QRect(0, 294, 113, 19), LCD)
    p.setPen(QColor(20, 40, 36))
    p.drawLine(0, 303, 112, 303)
    for i in range(19):
        t = abs(i - 9) / 9
        p.fillRect(QRect(115, 294 + i, 1, 1),
                   QColor(int(62 + 180 * t), int(240 - 120 * t), int(200 - 160 * t)))
    p.fillRect(QRect(0, 314, 113, 1), QColor(140, 150, 170))
    p.end()
    return img


def make_eq_ex() -> QImage:
    img = _img(275, 56)
    p = QPainter(img)
    for y, active in ((0, True), (15, False)):
        r = QRect(0, y, 275, 14)
        _title_bar(p, r, "", active)
        sunken(p, QRect(60, y + 3, 99, 8), BG_LO)
        sunken(p, QRect(163, y + 3, 45, 8), BG_LO)
        _small_btn(p, 264, y + 3, "close")
        _small_btn(p, 254, y + 3, "unshade")
    for x in (1, 4, 7, 11, 14, 17):
        p.fillRect(QRect(x, 30, 3, 7), ACCENT)
    _small_btn(p, 1, 38, "unshade", True)
    _small_btn(p, 1, 47, "shade", True)
    _small_btn(p, 11, 38, "close")
    _small_btn(p, 11, 47, "close", True)
    p.end()
    return img


def make_pledit() -> QImage:
    img = _img(280, 186)
    p = QPainter(img)
    # top pieces (selected y=0, normal y=21)
    for y, active in ((0, True), (21, False)):
        for x, w in ((0, 25), (127, 25), (153, 25)):
            _title_bar(p, QRect(x, y, w, 20), "", active)
        _title_bar(p, QRect(26, y, 100, 20), "playlist", active)
        _small_btn(p, 153 + 14, y + 3, "close")
        _small_btn(p, 153 + 4, y + 3, "shade")
    # side tiles
    p.fillRect(QRect(0, 42, 12, 29), BG)
    p.setPen(BG_HI)
    p.drawLine(0, 42, 0, 70)
    p.setPen(BG_LO)
    p.drawLine(11, 42, 11, 70)
    p.fillRect(QRect(31, 42, 20, 29), BG)
    p.setPen(BG_LO)
    p.drawLine(31, 42, 31, 70)
    p.fillRect(QRect(31 + 7, 42, 8, 29), BG_LO)
    p.setPen(BG_HI)
    p.drawLine(50, 42, 50, 70)
    # scroll handles
    bevel(p, QRect(52, 53, 8, 18))
    bevel(p, QRect(61, 53, 8, 18), face=ACCENT_MID)
    _small_btn(p, 52, 42, "close", True)
    _small_btn(p, 62, 42, "shade", True)
    _small_btn(p, 150, 42, "unshade", True)
    # shade pieces
    for x, y, w in ((72, 57, 25), (72, 42, 25)):
        _title_bar(p, QRect(x, y, w, 14), "", y == 42)
    for y, active in ((57, False), (42, True)):
        _title_bar(p, QRect(99, y, 50, 14), "", active)
        _small_btn(p, 99 + 39, y + 3, "close")
        _small_btn(p, 99 + 29, y + 3, "unshade")
    # bottom
    body_texture(p, QRect(0, 72, 125, 38))
    body_texture(p, QRect(126, 72, 150, 38))
    body_texture(p, QRect(179, 0, 25, 38))
    p.fillRect(QRect(205, 0, 75, 38), BG)
    sunken(p, QRect(205 + 2, 12, 72, 16))
    for x0 in (0, 126):
        p.setPen(BG_HI)
        p.drawLine(x0, 72, x0 + (124 if x0 == 0 else 149), 72)
    # bottom-left menu buttons placeholders
    for i, lab in enumerate(["add", "rem", "sel", "misc"]):
        r = QRect(14 + i * 29, 72 + 8, 22, 18)
        bevel(p, r)
        draw_label(p, lab, r.left() + (22 - label_width(lab)) // 2, r.top() + 7, LABEL)
    # bottom-right: time box, mini buttons, list button, resize grip
    br = 126
    sunken(p, QRect(br + 5, 72 + 8, 82, 10))
    for i, kind in enumerate(["prev", "play", "pause", "stop", "next", "eject"]):
        r = QRect(br + 3 + i * 10, 72 + 22, 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        _mini_icon(p, kind, r)
    sunken(p, QRect(br + 64, 72 + 21, 27, 10))
    r = QRect(br + 150 - 22 - 22, 72 + 8, 22, 18)
    bevel(p, r)
    draw_label(p, "list", r.left() + 3, r.top() + 7, LABEL)
    p.setPen(FACE_HI)
    for i in range(3):
        p.drawLine(br + 140 + i * 3, 72 + 36, br + 148, 72 + 28 + i * 3)
    p.setPen(LABEL)
    _arrow(p, br + 150 - 15, 72 + 2, up=True)
    _arrow(p, br + 150 - 15, 72 + 8, up=False)
    # menu items
    menu = [
        (0, 111, ["url", "dir", "file"]),
        (54, 111, ["all", "crop", "sel", "misc"]),
        (104, 111, ["inv", "none", "all"]),
        (154, 111, ["sort", "info", "opts"]),
        (204, 111, ["new", "save", "load"]),
    ]
    for x, y0, labels in menu:
        for i, lab in enumerate(labels):
            for dx, pressed in ((0, False), (23, True)):
                r = QRect(x + dx, y0 + i * 19, 22, 18)
                bevel(p, r, face=ACCENT_DIM if pressed else FACE, pressed=pressed)
                draw_label(p, lab, r.left() + (22 - label_width(lab)) // 2,
                           r.top() + 7, ACCENT if pressed else LABEL)
    for x, h in ((48, 54), (100, 72), (150, 54), (200, 54), (250, 54)):
        p.fillRect(QRect(x, 111, 3, h), ACCENT_MID)
    p.end()
    return img


def _arrow(p: QPainter, x, y, up=True):
    for i in range(3):
        if up:
            p.drawLine(x + 3 - i, y + i, x + 3 + i, y + i)
        else:
            p.drawLine(x + 1 + i, y + i, x + 5 - i, y + i)


def _mini_icon(p: QPainter, kind: str, r: QRect):
    p.save()
    p.translate(r.left() + 1, r.top() + 1)
    p.setBrush(QColor(170, 178, 195))
    p.setPen(Qt.PenStyle.NoPen)
    if kind == "prev":
        p.drawRect(1, 2, 1, 5)
        p.drawPolygon(QPolygon([QPoint(6, 2), QPoint(6, 6), QPoint(3, 4)]))
    elif kind == "play":
        p.drawPolygon(QPolygon([QPoint(2, 1), QPoint(2, 7), QPoint(6, 4)]))
    elif kind == "pause":
        p.drawRect(2, 2, 2, 5)
        p.drawRect(5, 2, 2, 5)
    elif kind == "stop":
        p.drawRect(2, 2, 5, 5)
    elif kind == "next":
        p.drawPolygon(QPolygon([QPoint(2, 2), QPoint(2, 6), QPoint(5, 4)]))
        p.drawRect(6, 2, 1, 5)
    elif kind == "eject":
        p.drawPolygon(QPolygon([QPoint(1, 5), QPoint(7, 5), QPoint(4, 1)]))
        p.drawRect(1, 6, 7, 1)
    p.restore()


def make_gen() -> QImage:
    img = _img(194, 109)
    p = QPainter(img)
    for y, active in ((0, True), (21, False)):
        for x in (0, 26, 52, 78, 104, 130):
            _title_bar(p, QRect(x, y, 25, 20), "", active)
        _small_btn(p, 130 + 14, y + 4, "close")
    body_texture(p, QRect(0, 42, 125, 14))
    body_texture(p, QRect(0, 57, 125, 14))
    body_texture(p, QRect(127, 72, 25, 14))
    for x, w in ((127, 11), (158, 11)):
        p.fillRect(QRect(x, 42, w, 29), BG)
        p.setPen(BG_HI)
        p.drawLine(x, 42, x, 70)
    for x, w in ((139, 8), (170, 8)):
        p.fillRect(QRect(x, 42, w, 29), BG)
        p.setPen(BG_LO)
        p.drawLine(x + w - 1, 42, x + w - 1, 70)
    _small_btn(p, 148, 42, "close", True)
    p.end()
    return img


def make_genex() -> QImage:
    img = _img(96, 64)
    p = QPainter(img)
    colors = [LCD, ACCENT, BG, QColor(205, 212, 225), QColor(205, 212, 225),
              BG_HI, ACCENT_DIM, FACE, QColor(205, 212, 225), FACE_HI, FACE_LO,
              FACE_LO, BG, FACE, FACE_HI, ACCENT_MID, ACCENT, BG_LO,
              QColor(255, 255, 255), ACCENT_MID, QColor(255, 255, 255), ACCENT_DIM]
    for i, c in enumerate(colors):
        p.fillRect(QRect(48 + i * 2, 0, 2, 1), c)
    p.end()
    return img


_DEFAULT: ClassicSkin | None = None


def default_skin() -> ClassicSkin:
    global _DEFAULT
    if _DEFAULT is None:
        sheets = {
            "MAIN": make_main(), "CBUTTONS": make_cbuttons(),
            "TITLEBAR": make_titlebar(), "SHUFREP": make_shufrep(),
            "TEXT": make_text(), "NUMBERS": make_numbers(False),
            "NUMS_EX": make_numbers(True), "PLAYPAUS": make_playpaus(),
            "MONOSTER": make_monoster(), "POSBAR": make_posbar(),
            "VOLUME": _slider_strip(68, 28, "volume"),
            "BALANCE": _slider_strip(38, 28, "balance"),
            "EQMAIN": make_eqmain(), "EQ_EX": make_eq_ex(),
            "PLEDIT": make_pledit(), "GEN": make_gen(), "GENEX": make_genex(),
        }
        vis = [LCD, QColor(16, 30, 30)]
        for i in range(16):
            t = i / 15
            vis.append(QColor(int(240 - 200 * t), int(80 + 160 * t), int(60 + 140 * t)))
        vis += [QColor(220, 255, 245), QColor(160, 240, 220), QColor(110, 220, 190),
                QColor(70, 190, 160), QColor(50, 150, 130), QColor(200, 220, 230)]
        pledit = {"normal": QColor(62, 240, 200), "current": QColor(255, 255, 255),
                  "normalbg": QColor(6, 10, 12), "selectedbg": QColor(30, 70, 90),
                  "font": "Sans"}
        genex = None
        _DEFAULT = ClassicSkin(sheets, name="Zebes (default)", path=None,
                               fallback=None, viscolors=vis, pledit=pledit,
                               nums_ex=True)
        from .classic import load_classic  # noqa: F401  (keeps import graph tidy)
        img = sheets["GENEX"]
        names = ["item_bg", "item_fg", "window_bg", "button_text",
                 "window_text", "divider", "playlist_selection",
                 "list_header_bg", "list_header_text", "list_header_frame_tl",
                 "list_header_frame_br", "list_header_frame_pressed",
                 "list_header_dead", "scrollbar_one", "scrollbar_two",
                 "pressed_scrollbar_one", "pressed_scrollbar_two",
                 "scrollbar_dead", "list_text_highlighted",
                 "list_text_highlighted_bg", "list_text_selected",
                 "list_text_selected_bg"]
        genex = {n: QColor(img.pixel(48 + i * 2, 0)) for i, n in enumerate(names)}
        _DEFAULT.genex_colors = genex
    return _DEFAULT
