"""Lyrics as a classic skinned window (Winamp "generic window" frame, GEN.BMP).

Docks/snaps like the equalizer and playlist; colours and font come from the
skin's playlist (pledit.txt).  Synced lyrics follow playback."""
from __future__ import annotations

import time

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QMenu

from .. import lyricsync as S
from . import lyrics as L
from .genpanel import GenPanel
from ..i18n import tr


class LyricsPanel(GenPanel):
    cfg_prefix = "ly"
    title = "LETRAS"
    close_tooltip = tr("Cerrar letras")

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.state = S.LyricsState()
        self._cur = -1
        self._flash_text = ""
        self._flash_until = 0.0
        self._scroll = 0.0          # logical px
        self._target = 0.0
        self._manual_until = 0.0
        self._layout_key = None
        self._rows: list[tuple[int, str]] = []    # (line index, wrapped text)
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._animate)
        self._follow_t = QTimer(self)
        self._follow_t.setInterval(150)
        self._follow_t.timeout.connect(self._follow)
        app.player.songChanged.connect(lambda: self.load())
        self.rebuild()

    # ---------------------------------------------------------- geometry
    def text_rect(self) -> QRect:
        return self.content_rect()

    def font(self) -> QFont:
        f = QFont(self.skin.pledit.get("font") or "Sans")
        f.setPixelSize(max(8, int(self.app.cfg["ly_font_size"])))
        return f

    def row_h(self) -> int:
        return max(10, int(self.app.cfg["ly_font_size"]) + 5)

    # ------------------------------------------------------------- build
    def build(self):
        self.build_frame()

    def close_panel(self):
        self.app.toggle_lyrics_panel()

    def resized(self):
        self._layout_key = None
        self._center(animate=False)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._follow_t.start()
        self.load()

    def hideEvent(self, ev):
        self._follow_t.stop()
        self._anim.stop()
        super().hideEvent(ev)

    # ----------------------------------------------------------- loading
    @property
    def lines(self):
        return self.state.lyrics.lines

    @property
    def synced(self) -> bool:
        return self.state.lyrics.synced

    def load(self, force=False):
        if not self.isVisible():
            return
        uri = (self.app.player.song or {}).get("file")
        same = uri == self.state.uri and (self.state.status or self.state.lyrics.found)
        if same and not force:
            return                        # already showing this song
        self._show(L.lookup(self.app, self._done, force=force))

    def _done(self, state):
        if state.uri == (self.app.player.song or {}).get("file"):
            self._show(state)
            if state.timing.reason:
                self.flash(state.timing.reason)

    def _show(self, state):
        self.state = state
        self._cur = -1
        self._scroll = self._target = 0.0
        self._layout_key = None
        self.setToolTip(state.info())
        self._follow()
        self.update()

    def flash(self, text, seconds=6.0):
        """Short message at the bottom of the text (sync changes)."""
        self._flash_text = text
        self._flash_until = time.monotonic() + seconds
        self.setToolTip(self.state.info())
        self.update_logical(self.text_rect())
        QTimer.singleShot(int(seconds * 1000) + 50, lambda: self.update_logical(self.text_rect()))

    # ------------------------------------------------------------ syncing
    def tap(self, idx: int):
        """Shift+click: this line is being sung now."""
        if self.state.tap(idx, self.app.player.elapsed):
            L.save_timing(self.state)
            self._resync(self.state.timing.reason)

    def nudge(self, seconds: float):
        self.state.timing.shift(seconds)
        L.save_timing(self.state)
        self._resync(tr("letra {0} ({1:+.1f} s)").format(tr("más tarde") if seconds > 0 else tr("antes"), seconds))

    def reset_sync(self):
        L.reset_timing(self.state, self.app.player.duration)
        self._resync(tr("sincronización restablecida"))

    def _resync(self, message):
        self._cur = -1
        self._manual_until = 0
        self._follow()
        self.flash(message)

    # --------------------------------------------------------- following
    def _follow(self):
        if not self.synced:
            return
        i = self.state.line_at(self.app.player.elapsed)
        if i != self._cur:
            self._cur = i
            if time.monotonic() > self._manual_until:
                self._center()
            self.update()

    def _center(self, animate=True):
        rows = self._layout()
        area = self.text_rect()
        rh = self.row_h()
        if self.synced and self._cur >= 0:
            idx = [n for n, (li, _t) in enumerate(rows) if li == self._cur]
            mid = (idx[0] + idx[-1] + 1) / 2 if idx else 0
            target = mid * rh - area.height() / 2
        else:
            target = self._target
        self._target = max(0.0, min(self._max_scroll(), target))
        if animate:
            if not self._anim.isActive():
                self._anim.start()
        else:
            self._scroll = self._target
            self.update()

    def _animate(self):
        d = self._target - self._scroll
        if abs(d) < 0.5:
            self._scroll = self._target
            self._anim.stop()
        else:
            self._scroll += d * 0.18
        self.update_logical(self.text_rect())

    def _max_scroll(self) -> float:
        area = self.text_rect()
        pad = area.height() / 2 if self.synced else 0
        return max(0.0, len(self._layout()) * self.row_h() - area.height() + pad)

    def wheelEvent(self, ev):
        d = ev.angleDelta().y()
        if not d or not self.lines:
            return super().wheelEvent(ev)
        self._manual_until = time.monotonic() + 5     # follow again after 5 s
        self._target = max(0.0, min(self._max_scroll(), self._target - d / 120 * self.row_h() * 3))
        if not self._anim.isActive():
            self._anim.start()

    def mouseDoubleClickEvent(self, ev):
        pt = self.to_logical(ev.position())
        if not self.text_rect().contains(pt) or not self._double(pt):
            super().mouseDoubleClickEvent(ev)

    def line_at_point(self, pt) -> int:
        """Lyrics line under a point of the panel (-1 if none)."""
        row = int((pt.y() - self.text_rect().y() + self._scroll) // self.row_h())
        rows = self._layout()
        return rows[row][0] if 0 <= row < len(rows) else -1

    def _double(self, pt):
        if not self.synced:
            return False
        t = self.state.seek_target(self.line_at_point(pt))
        if t is not None:
            self.app.player.seek(t)
            self._manual_until = 0
        return True

    def mousePressEvent(self, ev):
        pt = self.to_logical(ev.position())
        if ev.button() == Qt.MouseButton.LeftButton and ev.modifiers() & Qt.KeyboardModifier.ShiftModifier \
                and self.synced and self.text_rect().contains(pt):
            self.app.set_focused_panel(self)
            self.tap(self.line_at_point(pt))
            return
        super().mousePressEvent(ev)

    def context_menu(self, pt, gp):
        m = QMenu()
        m.setPalette(getattr(self.app, "dialog_palette", m.palette()))
        if self.synced:
            idx = self.line_at_point(pt) if self.text_rect().contains(pt) else -1
            if idx >= 0:
                m.addAction(tr("Esta línea suena ahora (sincronizar)   Mayús+clic"), lambda: self.tap(idx))
            m.addAction(tr("Letra más tarde (+0,5 s)"), lambda: self.nudge(0.5))
            m.addAction(tr("Letra antes (−0,5 s)"), lambda: self.nudge(-0.5))
            m.addAction(tr("Restablecer sincronización"), self.reset_sync)
            m.addSeparator()
        m.addAction(tr("Volver a buscar la letra"), lambda: self.load(force=True))
        m.addSeparator()
        m.addAction(tr("Letra más grande"), lambda: self._font_step(1))
        m.addAction(tr("Letra más pequeña"), lambda: self._font_step(-1))
        m.addSeparator()
        m.addAction(tr("Abrir en ventana aparte"), self.app.show_lyrics_window)
        m.addAction(tr("Cerrar letras"), self.app.toggle_lyrics_panel)
        self.app._last_menu = m
        m.popup(gp)

    def _font_step(self, d):
        cfg = self.app.cfg
        cfg["ly_font_size"] = max(8, min(30, int(cfg["ly_font_size"]) + d))
        cfg.save()
        self._layout_key = None
        self._center(animate=False)
        self.update()

    # ------------------------------------------------------------ layout
    def _layout(self) -> list[tuple[int, str]]:
        area = self.text_rect()
        key = (area.width(), self.app.cfg["ly_font_size"], id(self.lines), len(self.lines),
               self.skin.pledit.get("font"))
        if key == self._layout_key:
            return self._rows
        fm = QFontMetrics(self.font())
        maxw = area.width() - 10
        rows = []
        for li, (_t, text) in enumerate(self.lines):
            words = text.split(" ")
            line = ""
            for w in words:
                cand = (line + " " + w).strip()
                if line and fm.horizontalAdvance(cand) > maxw:
                    rows.append((li, line))
                    line = w
                else:
                    line = cand
            rows.append((li, line))
        self._rows = rows
        self._layout_key = key
        return rows

    # ---------------------------------------------------------- painting
    def paint_background(self, p: QPainter):
        self.paint_frame(p)
        self._paint_text(p)

    def _paint_text(self, p: QPainter):
        area = self.text_rect()
        pe = self.skin.pledit
        bg = pe.get("normalbg") or QColor(0, 0, 0)
        normal = pe.get("normal") or QColor(0, 255, 0)
        current = pe.get("current") or QColor(255, 255, 255)
        p.save()
        p.setClipRect(area, Qt.ClipOperation.IntersectClip)
        p.fillRect(area, bg)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = self.font()
        rh = self.row_h()
        if not self.lines:
            p.setFont(font)
            p.setPen(normal)
            msg = self.state.status or ""
            head = ""
            if self.state.uri:                  # a song is loaded: say which one
                artist, title, _album = S.song_query(self.app.player.song or {})
                head = f"{artist} - {title}" if artist and title else title
            p.drawText(QRectF(area.adjusted(6, 0, -6, 0)), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       f"{head}\n\n{msg}" if head and msg else (msg or head))
            p.restore()
            return
        rows = self._layout()
        dim = QColor(normal)
        dim.setAlphaF(0.55)
        bold = QFont(font)
        bold.setBold(True)
        first = max(0, int(self._scroll // rh))
        last = min(len(rows), first + area.height() // rh + 2)
        for n in range(first, last):
            li, text = rows[n]
            y = area.y() + n * rh - self._scroll
            if self.synced and li == self._cur:
                p.setFont(bold)
                p.setPen(current)
            else:
                p.setFont(font)
                p.setPen(dim if self.synced and li < self._cur else normal)
            p.drawText(QRectF(area.x() + 4, y, area.width() - 8, rh), Qt.AlignmentFlag.AlignCenter, text)
        if self._flash_text and time.monotonic() < self._flash_until:
            self._paint_flash(p, area, bg, normal)
        p.restore()

    def _paint_flash(self, p, area, bg, fg):
        f = self.font()
        f.setPixelSize(max(8, f.pixelSize() - 2))
        p.setFont(f)
        box = QRectF(area.x(), area.bottom() - 2 * self.row_h(), area.width(), 2 * self.row_h())
        shade = QColor(bg)
        shade.setAlphaF(0.85)
        p.fillRect(box, shade)
        p.setPen(fg)
        p.drawText(box.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   self._flash_text)
