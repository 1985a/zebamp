"""Colour helpers: keep skin-provided text readable on its background."""
from __future__ import annotations

from PySide6.QtGui import QColor


def _lum(c: QColor) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a: QColor, b: QColor) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable(fg: QColor, bg: QColor, *alternatives: QColor, minimum: float = 4.0) -> QColor:
    """fg if it reads well on bg, else the best alternative (skin colours
    first, then white/black)."""
    if fg is not None and contrast(fg, bg) >= minimum:
        return fg
    cands = [c for c in alternatives if c is not None] + [QColor(255, 255, 255), QColor(0, 0, 0)]
    for c in cands:
        if contrast(c, bg) >= minimum:
            return c
    return max(cands, key=lambda c: contrast(c, bg))


def distinct_bg(bg: QColor, base: QColor, *alternatives: QColor) -> QColor:
    """A selection background that differs visibly from the list background."""
    if bg is not None and contrast(bg, base) >= 1.4:
        return bg
    for c in alternatives:
        if c is not None and contrast(c, base) >= 1.4:
            return c
    return QColor(48, 96, 168)
