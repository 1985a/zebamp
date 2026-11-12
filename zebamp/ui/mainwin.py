"""Classic main window."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QToolTip

from ..player import fmt_time, song_title
from .base import (Area, Button, SkinPanel, Slider, Toggle, draw_bitmap_text,
                   ttf_font)
from ..i18n import tr

W, H = 275, 116
MARQUEE = QRect(111, 24, 154, 12)
MARQUEE_TEXT_Y = 27
VIS = QRect(24, 43, 76, 16)
SHADE_VIS = QRect(79, 5, 38, 5)



def _lw(pm) -> int:
    """Logical (skin pixel) width of a possibly high-DPI pixmap."""
    return round(pm.width() / pm.devicePixelRatio())


def _lh(pm) -> int:
    return round(pm.height() / pm.devicePixelRatio())

class Marquee:
    """Scrolling song title (bitmap font, TrueType fallback)."""

    SEP = "  ***  "

    def __init__(self, panel: MainPanel):
        self.panel = panel
        self.text = ""
        self.offset = 0
        self.override: str | None = None
        self._override_until = 0.0
        self.manual_drag: int | None = None
        self.timer = QTimer(panel)
        self.timer.timeout.connect(self._tick)
        self._cache_key = None
        self._cache: QPixmap | None = None

    def set_speed(self, idx: int):
        self.timer.setInterval([300, 160, 80][max(0, min(2, idx))])

    def set_text(self, text: str):
        if text != self.text:
            self.text = text
            self.offset = 0
            self._cache_key = None
            self._restart()

    def show_temp(self, text: str, seconds: float = 1.2):
        self.override = text
        self._override_until = time.monotonic() + seconds
        self._restart()
        self.panel.update_logical(MARQUEE)

    def clear_temp(self):
        self.override = None
        self.panel.update_logical(MARQUEE)

    def _restart(self):
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self):
        if self.override is not None and time.monotonic() > self._override_until:
            self.override = None
            self.panel.update_logical(MARQUEE)
        if not self.panel.app.cfg["marquee_scroll"]:
            if self.override is None:
                self.timer.stop()
            return
        pm = self._strip()
        if pm is not None and _lw(pm) > MARQUEE.width() and self.manual_drag is None \
                and self.override is None:
            step = 5 if self.panel.app.cfg["use_bitmap_font"] else 2
            self.offset = (self.offset + step) % self._period
            self.panel.update_logical(MARQUEE)
        elif self.override is None and (pm is None or _lw(pm) <= MARQUEE.width()):
            self.timer.stop()

    def _pixmap(self, w, h) -> QPixmap:
        # drawn at the screen zoom so vector glyphs/TTF text stay sharp
        k = max(1, int(self.panel.scale))
        pm = QPixmap(max(1, w) * k, h * k)
        pm.setDevicePixelRatio(k)
        return pm

    def _render(self, text: str) -> QPixmap:
        """Render text to a strip pixmap (height 6 for bitmap, 12 for TTF)."""
        skin = self.panel.skin
        mapped = skin.bitmap_text(text) if self.panel.app.cfg["use_bitmap_font"] else None
        if mapped is not None:
            pm = self._pixmap(len(mapped) * 5, 6)
            pm.fill(skin.text_bg)
            p = QPainter(pm)
            draw_bitmap_text(p, skin, mapped, 0, 0)
            p.end()
            return pm
        font = ttf_font(10)
        fm = QFontMetrics(font)
        w = max(1, fm.horizontalAdvance(text) + 2)
        pm = self._pixmap(w, 12)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setFont(font)
        p.setPen(skin.text_fg)
        p.drawText(QRect(0, 0, w, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()
        return pm

    def _strip(self) -> QPixmap | None:
        text = self.text
        if not text:
            return None
        key = (text, id(self.panel.skin), self.panel.app.cfg["use_bitmap_font"])
        if key != self._cache_key:
            single = self._render(text)
            if _lw(single) > MARQUEE.width():
                looped = self._render(text + self.SEP)
                self._period = _lw(looped)
                pm = self._pixmap(_lw(looped) * 2, _lh(looped))
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.drawPixmap(0, 0, looped)
                p.drawPixmap(_lw(looped), 0, looped)
                p.end()
                self._cache = pm
            else:
                self._period = max(1, _lw(single))
                self._cache = single
            self._cache_key = key
        return self._cache

    def paint(self, p: QPainter):
        p.save()
        p.setClipRect(MARQUEE, Qt.ClipOperation.IntersectClip)
        if self.override is not None:
            pm = self._render(self.override)
            off = 0
        else:
            pm = self._strip()
            off = self.offset if pm is not None and _lw(pm) > MARQUEE.width() else 0
            if self.manual_drag is not None:
                off = self.manual_drag % max(1, self._period)
        if pm is not None:
            y = MARQUEE_TEXT_Y if _lh(pm) == 6 else MARQUEE.top()
            p.drawPixmap(MARQUEE.left() - off, y, pm)
        p.restore()


class MainPanel(SkinPanel):
    default_cursor = "normal"

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.marquee = Marquee(self)
        self.marquee.set_speed(app.cfg["marquee_speed"])
        self._seek_preview: float | None = None
        self._blink = True
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self._on_blink)
        self.clock = QTimer(self)
        self.clock.setInterval(250)
        self.clock.timeout.connect(self._on_clock)   # runs only while shown
        self._last_sec = None
        self._drag_marquee_start = None
        p = app.player
        p.statusChanged.connect(self._on_status)
        p.songChanged.connect(self._on_song)
        p.queueChanged.connect(self._on_song)
        p.volumeChanged.connect(lambda: self.update_logical(QRect(107, 57, 110, 13)))
        p.optionsChanged.connect(lambda: self.update_logical(QRect(164, 89, 74, 15)))
        app.vis.frame.connect(self._on_vis)
        self.rebuild()
        self._on_song()

    # ---------------------------------------------------------- layout
    @property
    def shaded(self) -> bool:
        return bool(self.app.cfg["main_shade"])

    def logical_size(self):
        return (W, 14) if self.shaded else (W, H)

    def region_path(self):
        return self.skin.region_path("windowshade" if self.shaded else "normal")

    def build(self):
        a = self.app
        def sk(sheet, n):
            return (lambda: (self.skin.sprite(sheet, n), self.skin.sprite(sheet, n + "_D")))
        # title bar drag area (first so buttons sit on top)
        self.add(Area((0, 0, W, 14), on_press=self.start_move,
                      on_double=a.toggle_main_shade, cursor="titlebar"))
        self.add(Button((6, 3, 9, 9), sk("TITLEBAR", "OPTIONS"),
                        on_click=lambda: a.show_main_menu(self._global(QPoint(6, 12))),
                        cursor="mainmenu", tooltip=tr("Menú principal")))
        self.add(Button((244, 3, 9, 9), sk("TITLEBAR", "MINIMIZE"),
                        on_click=a.minimize, cursor="min", tooltip=tr("Minimizar")))
        if self.shaded:
            self.add(Button((254, 3, 9, 9), sk("TITLEBAR", "UNSHADE"),
                            on_click=a.toggle_main_shade, cursor="wsnormal"))
        else:
            self.add(Button((254, 3, 9, 9), sk("TITLEBAR", "SHADE"),
                            on_click=a.toggle_main_shade, cursor="winbut",
                            tooltip=tr("Modo compacto")))
        self.add(Button((264, 3, 9, 9), sk("TITLEBAR", "CLOSE"),
                        on_click=a.request_close, cursor="close", tooltip=tr("Cerrar")))
        if self.shaded:
            self._build_shade()
        else:
            self._build_normal()

    def _build_normal(self):
        a = self.app
        pl = a.player
        # clutter bar
        cb = [("O", (10, 25, 8, 8), lambda: a.show_options_menu(self._global(QPoint(18, 25))), None),
              ("A", (10, 33, 8, 7), a.toggle_always_on_top, lambda: a.cfg.get("always_on_top", False)),
              ("I", (10, 40, 8, 7), a.show_file_info, None),
              ("D", (10, 47, 8, 8), a.toggle_double_size, lambda: a.scale > 1),
              ("V", (10, 55, 8, 7), lambda: a.show_vis_menu(self._global(QPoint(18, 55))), None)]
        tips = {"O": tr("Opciones"), "A": tr("Siempre visible"), "I": tr("Información del archivo"),
                "D": tr("Tamaño doble"), "V": tr("Visualización")}
        for letter, rect, cb_fn, active in cb:
            self.add(Button(rect, (lambda lt=letter: (None, self.skin.sprite("TITLEBAR", "CLUTTER_" + lt))),
                            on_click=cb_fn, draw_normal=False, active=active,
                            tooltip=tips[letter]))
        # time display (click toggles elapsed/remaining)
        self.add(Area((36, 26, 63, 13), on_click=a.toggle_time_mode,
                      tooltip=tr("Tiempo transcurrido / restante")))
        # visualiser
        self.add(Area(VIS, on_click=a.cycle_vis_mode,
                      on_context=lambda gp: a.show_vis_menu(gp)))
        # marquee
        self.add(Area(MARQUEE, on_press=self._marquee_press, on_drag=self._marquee_drag,
                      on_release=self._marquee_release, on_double=a.show_file_info,
                      cursor="songname"))
        # volume
        self.add(Slider((107, 57, 68, 13), thumb_size=(14, 11), thumb_offset=1,
                        track_length=65,
                        background=self._paint_volume_bg,
                        thumb=lambda pr, v: self.skin.sprite("VOLUME", "VOL_THUMB_SEL" if pr else "VOL_THUMB")
                        if self.skin.has_volume_thumb("VOLUME") else None,
                        value=lambda: max(0, pl.volume) / 100.0,
                        on_change=self._volume_change, on_release=self._volume_release,
                        cursor="volbal", wheel_step=0.03))
        # balance
        self.add(Slider((177, 57, 38, 13), thumb_size=(14, 11), thumb_offset=1,
                        background=self._paint_balance_bg,
                        thumb=lambda pr, v: self.skin.sprite("BALANCE", "BAL_THUMB_SEL" if pr else "BAL_THUMB")
                        if self.skin.has_volume_thumb("BALANCE") else None,
                        value=lambda: (a.balance + 100) / 200.0,
                        on_change=self._balance_change, on_release=self._balance_release,
                        cursor="volbal", wheel_step=0.05))
        # EQ / PL toggles
        self.add(Toggle((219, 58, 23, 12),
                        lambda: (self.skin.sprite("SHUFREP", "EQ"), self.skin.sprite("SHUFREP", "EQ_D"),
                                 self.skin.sprite("SHUFREP", "EQ_SEL"), self.skin.sprite("SHUFREP", "EQ_SEL_D")),
                        selected=lambda: a.cfg["show_eq"], on_click=a.toggle_eq_window,
                        tooltip=tr("Ecualizador (Alt+G)")))
        self.add(Toggle((242, 58, 23, 12),
                        lambda: (self.skin.sprite("SHUFREP", "PL"), self.skin.sprite("SHUFREP", "PL_D"),
                                 self.skin.sprite("SHUFREP", "PL_SEL"), self.skin.sprite("SHUFREP", "PL_SEL_D")),
                        selected=lambda: a.cfg["show_playlist"], on_click=a.toggle_playlist_window,
                        tooltip=tr("Lista de reproducción (Alt+E)")))
        # position bar
        self.add(Slider((16, 72, 248, 10), thumb_size=(29, 10),
                        background=lambda p, r, v: p.drawPixmap(r.topLeft(), self.skin.sprite("POSBAR", "POS_BG")),
                        thumb=lambda pr, v: self.skin.sprite("POSBAR", "POS_THUMB_SEL" if pr else "POS_THUMB"),
                        value=self._position_value, on_change=self._seek_change,
                        on_release=self._seek_release, show_thumb=self._can_seek,
                        cursor="posbar", wheel_step=0.02))
        # transport
        cbs = [("PREV", (16, 88, 23, 18), pl.previous, tr("Anterior (Z)")),
               ("PLAY", (39, 88, 23, 18), pl.play, tr("Reproducir (X)")),
               ("PAUSE", (62, 88, 23, 18), pl.pause, tr("Pausa (C)")),
               ("STOP", (85, 88, 23, 18), pl.stop, tr("Detener (V)")),
               ("NEXT", (108, 88, 22, 18), pl.next, tr("Siguiente (B)")),
               ("EJECT", (136, 89, 22, 16), a.open_files, tr("Abrir archivos (L)"))]
        for name, rect, fn, tip in cbs:
            self.add(Button(rect, (lambda n=name: (self.skin.sprite("CBUTTONS", n),
                                                   self.skin.sprite("CBUTTONS", n + "_D"))),
                            on_click=fn, tooltip=tip))
        self.add(Toggle((164, 89, 47, 15),
                        lambda: tuple(self.skin.sprite("SHUFREP", n) for n in
                                      ("SHUFFLE", "SHUFFLE_D", "SHUFFLE_SEL", "SHUFFLE_SEL_D")),
                        selected=lambda: pl.random, on_click=pl.toggle_random,
                        tooltip=tr("Aleatorio (S)")))
        self.add(Toggle((210, 89, 28, 15),
                        lambda: tuple(self.skin.sprite("SHUFREP", n) for n in
                                      ("REPEAT", "REPEAT_D", "REPEAT_SEL", "REPEAT_SEL_D")),
                        selected=lambda: pl.repeat, on_click=pl.toggle_repeat,
                        tooltip=tr("Repetir: no / todo / pista (R)")))
        self.add(Area((253, 91, 13, 15), on_click=a.show_about, tooltip=tr("Acerca de")))

    def _build_shade(self):
        a = self.app
        pl = a.player
        for rect, fn in (((169, 2, 7, 10), pl.previous), ((176, 2, 10, 10), pl.play),
                         ((186, 2, 9, 10), pl.pause), ((195, 2, 9, 10), pl.stop),
                         ((204, 2, 10, 10), pl.next), ((215, 2, 10, 10), a.open_files)):
            self.add(Area(rect, on_click=fn))
        self.add(Area((127, 4, 30, 6), on_click=a.toggle_time_mode))
        self.add(Area(SHADE_VIS, on_click=a.cycle_vis_mode,
                      on_context=lambda gp: a.show_vis_menu(gp)))

        def thumb(pr, v):
            if v <= 0.05:
                return self.skin.sprite("TITLEBAR", "SHADE_POS_THUMB_LEFT")
            if v >= 0.95:
                return self.skin.sprite("TITLEBAR", "SHADE_POS_THUMB_RIGHT")
            return self.skin.sprite("TITLEBAR", "SHADE_POS_THUMB")
        self.add(Slider((226, 4, 17, 7), thumb_size=(3, 7), thumb=thumb,
                        value=self._position_value, on_change=self._seek_change,
                        on_release=self._seek_release, show_thumb=self._can_seek,
                        cursor="wsposbar"))

    def _global(self, logical: QPoint) -> QPoint:
        return self.mapToGlobal(QPoint(logical.x() * self.scale, logical.y() * self.scale))

    # --------------------------------------------------------- painting
    def paint_background(self, p: QPainter):
        sk = self.skin
        active = self.is_active()
        if self.shaded:
            p.drawPixmap(0, 0, sk.sprite("TITLEBAR", "SHADE_BG_SEL" if active else "SHADE_BG"))
            self._paint_shade_time(p)
            if self.app.vis.mode != "off":
                self.app.vis.renderer.paint(p, SHADE_VIS, self.app.vis.small,
                                            self.app.vis.mode, self.app.cfg, small=True)
            return
        p.drawPixmap(0, 0, sk.sprite("MAIN", "MAIN_WINDOW_BACKGROUND"))
        p.drawPixmap(0, 0, sk.sprite("TITLEBAR", "TITLE_SEL" if active else "TITLE"))
        p.drawPixmap(10, 22, sk.sprite("TITLEBAR", "CLUTTER_BG"))
        self._paint_state(p)
        self._paint_time(p)
        self._paint_info(p)
        self._paint_vis(p)
        self.marquee.paint(p)

    def _paint_state(self, p):
        st = self.app.player.state
        sk = self.skin
        if not self.app.player.connected:
            p.drawPixmap(26, 28, sk.sprite("PLAYPAUS", "STOPPED"))
            return
        if st == "play":
            p.drawPixmap(26, 28, sk.sprite("PLAYPAUS", "PLAYING"))
            p.drawPixmap(24, 28, sk.sprite("PLAYPAUS", "WORKING"))
        elif st == "pause":
            p.drawPixmap(26, 28, sk.sprite("PLAYPAUS", "PAUSED"))
        else:
            p.drawPixmap(26, 28, sk.sprite("PLAYPAUS", "STOPPED"))

    def _time_digits(self) -> tuple[bool, str] | None:
        pl = self.app.player
        if pl.state == "stop" or not pl.connected:
            return None
        t = self._seek_preview if self._seek_preview is not None else pl.elapsed
        neg = False
        if self.app.cfg["time_remaining"] and pl.duration > 0:
            t = max(0.0, pl.duration - t)
            neg = True
        t = int(t)
        m, s = divmod(t, 60)
        if not neg and 60 <= m < 600:
            # 1-9 h: the hour goes in an extra digit on the left so the
            # seconds keep running ("1 43:21") instead of a frozen h:mm
            h, m = divmod(m, 60)
            return neg, f"{m:02d}{s:02d}", h
        if m >= 100:
            m, s = divmod(m, 60)   # 10 h+ (or remaining 100 min+): h:mm
        return neg, f"{m:02d}{s:02d}", None

    def _paint_time(self, p):
        d = self._time_digits()
        if d is None:
            return
        if self.app.player.state == "pause" and not self._blink:
            return
        neg, digits, hour = d
        sk = self.skin
        if hour is not None:
            p.drawPixmap(35, 26, sk.digit(str(hour)))
            # little colon between hours and minutes, in the display colour
            c = sk.text_fg
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            for cy in (29.5, 35.5):
                p.drawRect(QRectF(45.3, cy, 1.4, 1.4))
            p.restore()
        if neg:
            if sk.nums_ex:
                p.drawPixmap(39, 26, sk.digit("-"))
            else:
                p.drawPixmap(38 + 2, 32, sk.digit("-"))
        for x, ch in zip((48, 60, 78, 90), digits):
            p.drawPixmap(x, 26, sk.digit(ch))

    def _paint_shade_time(self, p):
        d = self._time_digits()
        if d is None or (self.app.player.state == "pause" and not self._blink):
            return
        neg, digits, hour = d
        if hour is not None:
            text = f"{hour}:{digits[:2]}:{digits[2:]}"
        else:
            text = ("-" if neg else " ") + digits[:2] + ":" + digits[2:]
        draw_bitmap_text(p, self.skin, text, 120 if hour is not None else 125, 4)

    def _paint_info(self, p):
        pl = self.app.player
        sk = self.skin
        if pl.state != "stop" and pl.connected:
            br = pl.bitrate
            if br > 0:
                kb = str(br) if br < 10000 else f"{br // 1000}k"[:4]
                if len(kb) > 3:
                    # hi-res/lossless: stretch the box a little to the left
                    self._widen_box(p, box_left=109, text_x=111, extra=4)
                    draw_bitmap_text(p, sk, kb.rjust(4), 106, 43)
                else:
                    draw_bitmap_text(p, sk, kb.rjust(3), 111, 43)
            rate, _bits, ch = pl.audio
            if rate:
                kh = str(rate // 1000) if rate < 1000000 else f"{rate // 1000000}M"
                if len(kh) > 2:
                    self._widen_box(p, box_left=154, text_x=156, extra=5)
                    draw_bitmap_text(p, sk, kh.rjust(3)[:3], 151, 43)
                else:
                    draw_bitmap_text(p, sk, kh.rjust(2), 156, 43)
            mono = ch == 1
            stereo = ch >= 2
        else:
            mono = stereo = False
        p.drawPixmap(212, 41, sk.sprite("MONOSTER", "MONO_SEL" if mono else "MONO"))
        p.drawPixmap(239, 41, sk.sprite("MONOSTER", "STEREO_SEL" if stereo else "STEREO"))

    def _widen_box(self, p, box_left: int, text_x: int, extra: int):
        """Extend a skin's info box `extra` px to the left by repeating its own
        pixels (interior columns, then its left edge), so any skin keeps its look."""
        sk = self.skin
        y0, h = 39, 14
        nl = box_left - extra
        fill_w = text_x - (nl + 2)
        p.drawPixmap(nl + 2, y0, sk.crop("MAIN", (text_x + 1, y0, fill_w, h)))
        p.drawPixmap(nl, y0, sk.crop("MAIN", (box_left, y0, 2, h)))

    def info_tooltip(self) -> str:
        pl = self.app.player
        if pl.state == "stop" or not pl.connected:
            return ""
        rate, bits, ch = pl.audio
        a = pl.status.get("audio", "")
        parts = []
        f = (pl.song or {}).get("file", "")
        ext = os.path.splitext(f.split("?")[0])[1].lstrip(".").upper()
        if "://" in f:
            ext = tr("Radio/stream")
        if ext:
            parts.append(ext)
        if rate:
            parts.append(f"{rate / 1000:g} kHz")
        if ":f:" in a:
            parts.append(tr("32 bit flotante"))
        elif bits:
            parts.append(f"{bits} bit")
        if ch:
            parts.append({1: "mono", 2: tr("estéreo")}.get(ch, tr("{0} canales").format(ch)))
        br = pl.bitrate
        if br:
            parts.append(f"{br} kbps")
        return " · ".join(parts)

    def event(self, ev):
        if ev.type() == QEvent.Type.ToolTip:
            pt = self.to_logical(ev.pos())
            if not self.shaded and QRect(104, 39, 163, 14).contains(pt):
                t = self.info_tooltip()
                if t:
                    QToolTip.showText(ev.globalPos(), t, self)
                    return True
        return super().event(ev)

    def _paint_vis(self, p):
        vis = self.app.vis
        if vis.mode == "off":
            return
        vis.renderer.paint(p, VIS, vis.analyzer, vis.mode, self.app.cfg)

    def _paint_volume_bg(self, p, r, v):
        frame = int(round(v * 27))
        p.drawPixmap(r.topLeft(), self.skin.volume_frame(frame))

    def _paint_balance_bg(self, p, r, v):
        bal = abs(v * 200 - 100)
        frame = int(bal / 100 * 27)
        p.drawPixmap(r.topLeft(), self.skin.balance_frame(frame))

    # ---------------------------------------------------------- updates
    def _on_status(self):
        self.update()
        st = self.app.player.state
        if st == "pause":
            if not self.blink_timer.isActive():
                self._blink = True
                self.blink_timer.start()
        else:
            self.blink_timer.stop()
            self._blink = True

    def _on_blink(self):
        self._blink = not self._blink
        self.update_logical(QRect(36, 26, 66, 13))
        if self.shaded:
            self.update_logical(QRect(120, 2, 45, 10))

    def showEvent(self, ev):
        super().showEvent(ev)
        self.clock.start()

    def hideEvent(self, ev):
        self.clock.stop()       # hidden (modern skin, tray): no wake-ups
        super().hideEvent(ev)

    def _on_clock(self):
        pl = self.app.player
        if pl.state != "play":
            return
        sec = int(pl.elapsed)
        if sec != self._last_sec:
            self._last_sec = sec
            if self.shaded:
                self.update_logical(QRect(120, 2, 45, 10))
                self.update_logical(QRect(226, 4, 17, 7))
            else:
                self.update_logical(QRect(36, 26, 66, 13))
        if not self.shaded:
            self.update_logical(QRect(16, 72, 248, 10))

    def _on_vis(self):
        if self.shaded:
            self.update_logical(SHADE_VIS)
        else:
            self.update_logical(VIS)

    def song_text(self) -> str:
        pl = self.app.player
        if not pl.connected:
            addr = pl.conn.addr.describe()
            return tr("MPD no conectado ({0})").format(addr)
        if not pl.song:
            return tr("Zebamp para MPD")
        pos = pl.current_pos
        title = song_title(pl.song)
        dur = pl.duration
        s = f"{pos + 1}. {title}" if pos >= 0 else title
        if dur > 0:
            s += f" ({fmt_time(dur)})"
        return s

    def _on_song(self):
        self.marquee.set_text(self.song_text())
        self.update()

    def set_temp_text(self, text: str):
        self.marquee.show_temp(text)

    # -------------------------------------------------------- handlers
    def _position_value(self) -> float:
        pl = self.app.player
        d = pl.duration
        if d <= 0:
            return 0.0
        return pl.elapsed / d

    def _can_seek(self) -> bool:
        pl = self.app.player
        return pl.state != "stop" and pl.duration > 0

    def _seek_change(self, v):
        pl = self.app.player
        d = pl.duration
        self._seek_preview = v * d
        self.marquee.show_temp(tr("Ir a: {0}/{1} ({2}%)").format(fmt_time(v * d), fmt_time(d), int(v * 100)), 0.6)
        self.update_logical(QRect(36, 26, 66, 13))

    def _seek_release(self, v):
        pl = self.app.player
        pl.seek(v * pl.duration)
        self._seek_preview = None
        self.marquee.clear_temp()
        self.update()

    def _volume_change(self, v):
        vol = int(round(v * 100))
        self.app.player.set_volume(vol)
        self.marquee.show_temp(tr("Volumen: {0}%").format(vol))
        self.update_logical(QRect(107, 57, 68, 13))

    def _volume_release(self, v):
        self._volume_change(v)

    def _balance_change(self, v):
        b = int(round(v * 200 - 100))
        if abs(b) < 8:
            b = 0   # snap to centre like Winamp
        self.app.set_balance(b)
        if b == 0:
            txt = tr("Balance: centro")
        elif b < 0:
            txt = tr("Balance: {0}% izquierda").format(-b)
        else:
            txt = tr("Balance: {0}% derecha").format(b)
        self.marquee.show_temp(txt)
        self.update_logical(QRect(177, 57, 38, 13))

    def _balance_release(self, v):
        self._balance_change(v)
        self.app.commit_balance()

    def _marquee_press(self, pt, ev):
        self._drag_marquee_start = (pt.x(), self.marquee.offset)
        self.marquee.manual_drag = self.marquee.offset

    def _marquee_drag(self, pt, ev):
        if self._drag_marquee_start is None:
            return
        x0, off0 = self._drag_marquee_start
        self.marquee.manual_drag = max(0, off0 - (pt.x() - x0))
        self.update_logical(MARQUEE)

    def _marquee_release(self, pt, ev):
        if self.marquee.manual_drag is not None:
            self.marquee.offset = self.marquee.manual_drag % max(1, getattr(self.marquee, "_period", 1))
        self.marquee.manual_drag = None
        self._drag_marquee_start = None
