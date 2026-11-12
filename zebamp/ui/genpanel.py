"""Winamp's "generic window" as a skinned panel: the GEN.BMP frame with a
title, a close box and a resize grip.  The lyrics and album art windows are
built on it; like the playlist they grow in 25x29 px steps and dock/snap."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from .base import Area, Button, SkinPanel

TITLE_H, BOTTOM_H, LEFT_W, RIGHT_W = 20, 14, 11, 8
BASE_W, BASE_H, STEP_W, STEP_H = 275, 116, 25, 29


class GenPanel(SkinPanel):
    default_cursor = "normal"
    cfg_prefix = ""         # settings <prefix>_width / <prefix>_height (extra steps)
    title = ""
    close_tooltip = ""

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self._resize = None

    def close_panel(self):
        raise NotImplementedError

    def resized(self):
        """Called after the grip changed the size (before the relayout)."""

    # ---------------------------------------------------------- geometry
    @property
    def gw(self) -> int:
        return BASE_W + STEP_W * max(0, int(self.app.cfg[self.cfg_prefix + "_width"]))

    @property
    def gh(self) -> int:
        return BASE_H + STEP_H * max(0, int(self.app.cfg[self.cfg_prefix + "_height"]))

    def logical_size(self):
        return self.gw, self.gh

    def content_rect(self) -> QRect:
        return QRect(LEFT_W, TITLE_H, self.gw - LEFT_W - RIGHT_W, self.gh - TITLE_H - BOTTOM_H)

    # ------------------------------------------------------------- build
    def build_frame(self):
        """Title bar (move), close box, content area and resize grip."""
        W, H = self.gw, self.gh
        self.add(Area((0, 0, W, TITLE_H), on_press=self.start_move, cursor="titlebar"))
        self.add(Button((W - 11, 3, 9, 9), lambda: (None, self.skin.sprite("GEN", "CLOSE_D")),
                        draw_normal=False, on_click=self.close_panel, cursor="close",
                        tooltip=self.close_tooltip))
        self.add(Area(self.content_rect(), cursor="normal"))
        self.add(Area((W - 20, H - 20, 20, 20), on_press=self._resize_press,
                      on_drag=self._resize_drag, on_release=self._resize_release, cursor="psize"))

    # ------------------------------------------------------------ resize
    def _size_steps(self) -> tuple[int, int]:
        cfg = self.app.cfg
        return int(cfg[self.cfg_prefix + "_width"]), int(cfg[self.cfg_prefix + "_height"])

    def _resize_press(self, pt, ev):
        self._resize = (ev.globalPosition().toPoint(), *self._size_steps())

    def _resize_drag(self, pt, ev):
        if not self._resize:
            return
        start, w0, h0 = self._resize
        d = ev.globalPosition().toPoint() - start
        s = self.scale
        steps = (max(0, w0 + round(d.x() / s / STEP_W)), max(0, h0 + round(d.y() / s / STEP_H)))
        if steps == self._size_steps():
            return
        cfg = self.app.cfg
        cfg[self.cfg_prefix + "_width"], cfg[self.cfg_prefix + "_height"] = steps
        self.rebuild()
        # rebuild() made new controls: keep dragging with the new grip
        for c in self.controls:
            if isinstance(c, Area) and c.on_press == self._resize_press:
                self._grab = c
        self.resized()
        self.app.relayout()

    def _resize_release(self, pt, ev):
        self._resize = None
        self.app.cfg.save()

    # ------------------------------------------------------------- paint
    def paint_frame(self, p: QPainter):
        sk = self.skin
        W, H = self.gw, self.gh
        sel = "_SEL" if self.is_active() else ""
        g = lambda n: sk.sprite("GEN", n)   # noqa: E731
        # title bar: TL, fill, [TLE title TC... TRE], fill, TR
        p.drawPixmap(0, 0, g("TL" + sel))
        p.drawPixmap(W - 25, 0, g("TR" + sel))
        tw = min(W - 100, 75 + 25 * ((W - 150) // 100))
        tx = (W - tw) // 2
        x = 25
        while x < tx - 25:
            p.drawPixmap(x, 0, g("TLRF" + sel))
            x += 25
        p.drawPixmap(tx - 25, 0, g("TLE" + sel))
        x = tx
        while x < tx + tw:
            p.drawPixmap(x, 0, g("TC" + sel))
            x += 25
        p.drawPixmap(tx + tw, 0, g("TRE" + sel))
        x = tx + tw + 25
        while x < W - 25:
            p.drawPixmap(x, 0, g("TLRF" + sel))
            x += 25
        # sides
        y = TITLE_H
        while y < H - BOTTOM_H - 24:
            p.drawPixmap(0, y, g("ML"))
            p.drawPixmap(W - RIGHT_W, y, g("MR"))
            y += 29
        p.drawPixmap(0, H - BOTTOM_H - 24, g("MLB"))
        p.drawPixmap(W - RIGHT_W, H - BOTTOM_H - 24, g("MRB"))
        # bottom
        x = 125
        while x < W - 125:
            p.drawPixmap(x, H - BOTTOM_H, g("BF"))
            x += 25
        p.drawPixmap(0, H - BOTTOM_H, g("BL"))
        p.drawPixmap(W - 125, H - BOTTOM_H, g("BR"))
        # title text
        p.save()
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        f = QFont(self.skin.pledit.get("font") or "Sans")
        f.setPixelSize(8)
        f.setBold(True)
        p.setFont(f)
        gx = sk.genex_colors or {}
        p.setPen(gx.get("window_text") or QColor(220, 220, 220))
        p.drawText(QRect(tx - 6, 4, tw + 12, 11), Qt.AlignmentFlag.AlignCenter, self.title)
        p.restore()
