"""Classic playlist editor bound to MPD's queue."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..player import fmt_time, song_duration, song_title
from .base import Area, Button, Control, SkinPanel, draw_bitmap_text
from ..i18n import tr

MIME_URIS = "application/x-zebamp-uris"


class SpriteMenu(QWidget):
    """Winamp playlist button pop-up: a vertical strip of sprite buttons."""

    def __init__(self, panel: PlaylistPanel, bar: str, items, anchor: QPoint):
        super().__init__(panel, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.panel = panel
        self.bar = bar
        self.items = items          # [(sprite_name, callback, tooltip)], top -> bottom
        self.hover = -1
        s = panel.scale
        self.setFixedSize(25 * s, 18 * len(items) * s)
        self.setMouseTracking(True)
        # bottom item sits exactly over the button that opened it
        self.move(anchor.x() - 3 * s, anchor.y() - (len(items) - 1) * 18 * s)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def paintEvent(self, ev):
        p = QPainter(self)
        s = self.panel.scale
        p.scale(s, s)
        sk = self.panel.skin
        bar = sk.sprite("PLEDIT", self.bar)
        p.drawPixmap(0, 18 * len(self.items) - bar.height(), bar)
        for i, (name, _cb, _tip) in enumerate(self.items):
            sprite = name + ("_D" if i == self.hover else "")
            p.drawPixmap(3, i * 18, sk.sprite("PLEDIT", sprite))
        p.end()

    def _index(self, pos) -> int:
        s = self.panel.scale
        x, y = pos.x() / s, pos.y() / s
        if x < 3:
            return -1
        i = int(y // 18)
        return i if 0 <= i < len(self.items) else -1

    def mouseMoveEvent(self, ev):
        i = self._index(ev.position())
        if i != self.hover:
            self.hover = i
            self.setToolTip(self.items[i][2] if i >= 0 else "")
            self.update()

    def mouseReleaseEvent(self, ev):
        i = self._index(ev.position())
        self.close()
        if i >= 0:
            QTimer.singleShot(0, self.items[i][1])


class TrackList(Control):
    """The scrolling list itself."""

    def __init__(self, panel: PlaylistPanel, rect):
        super().__init__(rect)
        self.pl = panel
        self._press_row = None
        self._drag_started = False
        self._drag_origin = None
        self._dnd_out = False

    def row_at(self, pt) -> int:
        return self.pl.scroll + (pt.y() - self.rect.top() - 0) // self.pl.row_h

    def paint(self, p):
        self.pl.paint_tracks(p, self.rect)

    def press(self, pt, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        row = self.row_at(pt)
        pl = self.pl
        n = len(pl.queue)
        mods = ev.modifiers()
        if row >= n:
            if not mods:
                pl.select_none()
            return True
        if mods & Qt.KeyboardModifier.ShiftModifier:
            pl.select_range(pl.anchor if pl.anchor is not None else row, row,
                            add=bool(mods & Qt.KeyboardModifier.ControlModifier))
        elif mods & Qt.KeyboardModifier.ControlModifier:
            pl.toggle_row(row)
        else:
            if not pl.is_selected(row):
                pl.select_only(row)
            self._press_row = row
            self._drag_origin = pt
        pl.cursor_row = row
        pl.update()
        return True

    def drag(self, pt, ev):
        pl = self.pl
        if self._press_row is None:
            return
        # leaving the list starts an external drag (e.g. to a file manager)
        if not self.rect.adjusted(-8, -20, 8, 20).contains(pt) and not self._dnd_out:
            self._dnd_out = True
            pl.start_external_drag()
            return
        row = max(0, min(len(pl.queue) - 1, self.row_at(pt)))
        delta = row - self._press_row
        if delta:
            self._drag_started = True
            if pl.move_selection(delta):
                self._press_row += delta
        # autoscroll
        if pt.y() < self.rect.top():
            pl.scroll_by(-1)
        elif pt.y() > self.rect.bottom():
            pl.scroll_by(1)

    def release(self, pt, ev, inside):
        if self._press_row is not None and not self._drag_started and not self._dnd_out:
            mods = ev.modifiers()
            if not mods:
                self.pl.select_only(self._press_row)
        self._press_row = None
        self._drag_started = False
        self._dnd_out = False

    def double_click(self, pt, ev):
        row = self.row_at(pt)
        if 0 <= row < len(self.pl.queue):
            self.pl.app.player.play(row)
            return True
        return False

    def wheel(self, delta, ev):
        self.pl.scroll_by(-3 if delta > 0 else 3)
        return True

    def context(self, pt, gp):
        row = self.row_at(pt)
        if 0 <= row < len(self.pl.queue) and not self.pl.is_selected(row):
            self.pl.select_only(row)
        self.pl.app.show_playlist_context_menu(gp)
        return True


class ScrollHandle(Control):
    def __init__(self, panel: PlaylistPanel, rect):
        super().__init__(rect, cursor="pvscroll")
        self.pl = panel
        self._grab = 0

    def _track(self) -> tuple[int, int]:
        top = self.rect.top()
        return top, self.rect.height() - 18

    def handle_y(self) -> int:
        top, span = self._track()
        mx = self.pl.max_scroll()
        if mx <= 0 or span <= 0:
            return top
        return top + round(span * self.pl.scroll / mx)

    def paint(self, p):
        y = self.handle_y()
        p.drawPixmap(self.rect.left(), y, self.pl.skin.sprite(
            "PLEDIT", "SCROLL_HANDLE_SEL" if self.pressed else "SCROLL_HANDLE"))

    def press(self, pt, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        y = self.handle_y()
        self.pressed = True
        if y <= pt.y() < y + 18:
            self._grab = pt.y() - y
        else:
            self._grab = 9
            self.drag(pt, ev)
        self.update()
        return True

    def drag(self, pt, ev):
        top, span = self._track()
        mx = self.pl.max_scroll()
        if span <= 0 or mx <= 0:
            return
        y = max(0, min(span, pt.y() - self._grab - top))
        self.pl.set_scroll(round(y / span * mx))

    def release(self, pt, ev, inside):
        self.pressed = False
        self.update()

    def wheel(self, delta, ev):
        self.pl.scroll_by(-3 if delta > 0 else 3)
        return True


class PlaylistPanel(SkinPanel):
    default_cursor = "pnormal"

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.scroll = 0
        self.selected_ids: set = set()
        self.anchor: int | None = None
        self.cursor_row = 0
        self.setAcceptDrops(True)
        self._drop_row: int | None = None
        self._resize = None
        self._shade_tick = 0
        app.player.queueChanged.connect(self._on_queue)
        app.player.statusChanged.connect(self._on_status)
        app.player.songChanged.connect(self.update)
        app.vis.frame.connect(self._on_vis)
        self._last_cur = None
        self._total = 0.0
        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self._tick)      # runs only while shown
        self.rebuild()
        self._on_queue()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._clock.start()

    def hideEvent(self, ev):
        self._clock.stop()
        super().hideEvent(ev)

    # ---------------------------------------------------------- geometry
    @property
    def queue(self):
        return self.app.player.queue

    @property
    def shaded(self) -> bool:
        return bool(self.app.cfg["pl_shade"])

    @property
    def pw(self) -> int:
        return 275 + 25 * max(0, int(self.app.cfg["pl_width"]))

    @property
    def ph(self) -> int:
        return 116 + 29 * max(0, int(self.app.cfg["pl_height"]))

    def logical_size(self):
        return (self.pw, 14) if self.shaded else (self.pw, self.ph)

    @property
    def row_h(self) -> int:
        return max(10, int(self.app.cfg["pl_font_size"]) + 4)

    def list_rect(self) -> QRect:
        return QRect(12, 20, self.pw - 32, self.ph - 58)

    def visible_rows(self) -> int:
        return max(1, (self.list_rect().height() - 4) // self.row_h)

    def max_scroll(self) -> int:
        return max(0, len(self.queue) - self.visible_rows())

    def set_scroll(self, v: int):
        v = max(0, min(self.max_scroll(), int(v)))
        if v != self.scroll:
            self.scroll = v
            self.update()

    def scroll_by(self, d: int):
        self.set_scroll(self.scroll + d)

    def ensure_visible(self, row: int):
        vr = self.visible_rows()
        if row < self.scroll:
            self.set_scroll(row)
        elif row >= self.scroll + vr:
            self.set_scroll(row - vr + 1)

    def font(self) -> QFont:
        f = QFont(self.skin.pledit.get("font") or "Sans")
        f.setPixelSize(int(self.app.cfg["pl_font_size"]))
        return f

    # ------------------------------------------------------------ build
    def build(self):
        a = self.app
        W = self.pw
        if self.shaded:
            self.add(Area((0, 0, W, 14), on_press=self.start_move,
                          on_double=a.toggle_pl_shade, cursor="pwsnorm"))
            self.add(Button((W - 21, 3, 9, 9),
                            lambda: (None, self.skin.sprite("PLEDIT", "EXPAND_D")),
                            draw_normal=False, on_click=a.toggle_pl_shade))
            self.add(Button((W - 11, 3, 9, 9),
                            lambda: (None, self.skin.sprite("PLEDIT", "CLOSE_D")),
                            draw_normal=False, on_click=a.toggle_playlist_window,
                            cursor="pclose"))
            self.add(Area((W - 30, 3, 9, 9), on_press=self._resize_press,
                          on_drag=self._resize_drag, on_release=self._resize_release,
                          cursor="pwssize"))
            return
        H = self.ph
        self.add(Area((0, 0, W, 20), on_press=self.start_move,
                      on_double=a.toggle_pl_shade, cursor="ptbar"))
        self.add(Button((W - 21, 3, 9, 9),
                        lambda: (None, self.skin.sprite("PLEDIT", "COLLAPSE_D")),
                        draw_normal=False, on_click=a.toggle_pl_shade, cursor="pwinbut"))
        self.add(Button((W - 11, 3, 9, 9),
                        lambda: (None, self.skin.sprite("PLEDIT", "CLOSE_D")),
                        draw_normal=False, on_click=a.toggle_playlist_window, cursor="pclose"))
        self.tracklist = self.add(TrackList(self, self.list_rect()))
        self.add(ScrollHandle(self, (W - 15, 20, 8, H - 58)))
        # bottom buttons that open the sprite menus
        y = H - 30
        self.add(Area((14, y, 22, 18), on_press=lambda *_: self._menu("add")))
        self.add(Area((43, y, 22, 18), on_press=lambda *_: self._menu("rem")))
        self.add(Area((72, y, 22, 18), on_press=lambda *_: self._menu("sel")))
        self.add(Area((101, y, 22, 18), on_press=lambda *_: self._menu("misc")))
        self.add(Area((W - 44, y, 22, 18), on_press=lambda *_: self._menu("list")))
        # mini transport
        bx, by = W - 150 + 3, H - 38 + 22
        pl = a.player
        for i, fn in enumerate((pl.previous, pl.play, pl.pause, pl.stop, pl.next, a.open_files)):
            self.add(Area((bx + i * 10, by, 10, 10), on_click=fn))
        self.add(Area((W - 150 + 66, H - 38 + 23, 30, 8), on_click=a.toggle_time_mode))
        # scroll buttons
        self.add(Area((W - 15, H - 38 + 2, 8, 5), on_click=lambda: self.scroll_by(-1)))
        self.add(Area((W - 15, H - 38 + 8, 8, 5), on_click=lambda: self.scroll_by(1)))
        # resize grip
        self.add(Area((W - 20, H - 20, 20, 20), on_press=self._resize_press,
                      on_drag=self._resize_drag, on_release=self._resize_release,
                      cursor="psize"))
        self.ensure_scroll_bounds()

    def ensure_scroll_bounds(self):
        self.scroll = max(0, min(self.scroll, self.max_scroll()))

    # ---------------------------------------------------------- resize
    def _resize_press(self, pt, ev):
        self._resize = (ev.globalPosition().toPoint(), self.app.cfg["pl_width"], self.app.cfg["pl_height"])

    def _resize_drag(self, pt, ev):
        if not self._resize:
            return
        start, w0, h0 = self._resize
        d = ev.globalPosition().toPoint() - start
        s = self.scale
        w = max(0, w0 + round(d.x() / s / 25))
        h = h0 if self.shaded else max(0, h0 + round(d.y() / s / 29))
        if (w, h) != (self.app.cfg["pl_width"], self.app.cfg["pl_height"]):
            self.app.cfg["pl_width"], self.app.cfg["pl_height"] = w, h
            self.rebuild()
            # The grab target was recreated; re-attach to the new grip.
            for c in self.controls:
                if isinstance(c, Area) and c.on_press == self._resize_press:
                    self._grab = c
            self.app.relayout()

    def _resize_release(self, pt, ev):
        self._resize = None
        self.app.cfg.save()

    # -------------------------------------------------------- selection
    def is_selected(self, row: int) -> bool:
        if 0 <= row < len(self.queue):
            return self.queue[row].get("id") in self.selected_ids
        return False

    def selected_rows(self) -> list[int]:
        return [i for i, s in enumerate(self.queue) if s.get("id") in self.selected_ids]

    def select_only(self, row: int):
        self.selected_ids = {self.queue[row].get("id")} if 0 <= row < len(self.queue) else set()
        self.anchor = row
        self.cursor_row = row
        self.update()

    def toggle_row(self, row: int):
        sid = self.queue[row].get("id")
        if sid in self.selected_ids:
            self.selected_ids.discard(sid)
        else:
            self.selected_ids.add(sid)
        self.anchor = row
        self.update()

    def select_range(self, a: int, b: int, add=False):
        lo, hi = sorted((a, b))
        ids = {self.queue[i].get("id") for i in range(max(0, lo), min(len(self.queue), hi + 1))}
        self.selected_ids = (self.selected_ids | ids) if add else ids
        self.update()

    def select_all(self):
        self.selected_ids = {s.get("id") for s in self.queue}
        self.update()

    def select_none(self):
        self.selected_ids = set()
        self.update()

    def invert_selection(self):
        self.selected_ids = {s.get("id") for s in self.queue} - self.selected_ids
        self.update()

    def move_selection(self, delta: int) -> bool:
        rows = self.selected_rows()
        if not rows:
            return False
        n = len(self.queue)
        if rows[0] + delta < 0 or rows[-1] + delta >= n:
            return False
        q = list(self.queue)
        sel = set(rows)
        new_q = [None] * n
        for r in rows:
            new_q[r + delta] = q[r]
        rest = iter(s for i, s in enumerate(q) if i not in sel)
        for i in range(n):
            if new_q[i] is None:
                new_q[i] = next(rest)
        lo = min(rows[0], rows[0] + delta)
        hi = max(rows[-1], rows[-1] + delta)
        # optimistic local update keeps dragging smooth
        self.app.player.queue = new_q
        self.app.player.apply_order_range([s.get("id") for s in new_q], lo, hi)
        self.cursor_row = max(0, min(n - 1, self.cursor_row + delta))
        self.ensure_visible(self.cursor_row)
        self.update()
        return True

    # ----------------------------------------------------------- events
    def _on_queue(self):
        ids = {s.get("id") for s in self.queue}
        self.selected_ids &= ids
        self._total = sum(song_duration(s) for s in self.queue)
        self.ensure_scroll_bounds()
        self.update()

    def _on_status(self):
        cur = self.app.player.current_pos
        if cur != self._last_cur:
            self._last_cur = cur
            if cur >= 0 and self.app.cfg.get("pl_follow", True):
                self.ensure_visible(cur)
        self.update()

    def _tick(self):
        if self.app.player.state == "play":
            if self.shaded:
                self.update()
            else:
                self.update_logical(QRect(self.pw - 150, self.ph - 38, 150, 38))

    def _on_vis(self):
        if not self.shaded and self._vis_rect() is not None and self.app.cfg["main_shade"]:
            self.update_logical(self._vis_rect())

    def _vis_rect(self) -> QRect | None:
        W, H = self.pw, self.ph
        if W - 150 - 125 >= 75:
            return QRect(W - 150 - 75 + 2, H - 38 + 12, 72, 16)
        return None

    # ---------------------------------------------------------- menus
    def _menu(self, which: str):
        a = self.app
        W, H = self.pw, self.ph
        menus = {
            "add": ("BAR_ADD", 14, [("ADD_URL", a.add_url, tr("Añadir URL")),
                                    ("ADD_DIR", a.add_dir, tr("Añadir carpeta")),
                                    ("ADD_FILE", a.add_files, tr("Añadir archivos"))]),
            "rem": ("BAR_REM", 43, [("REM_MISC", lambda: a.show_remove_misc_menu(self._bottom_global(43)),
                                     tr("Otras opciones de borrado")),
                                    ("REM_ALL", a.clear_playlist, tr("Vaciar la lista")),
                                    ("REM_CROP", self.crop_selected, tr("Recortar (dejar solo lo seleccionado)")),
                                    ("REM_SEL", self.remove_selected, tr("Quitar seleccionados"))]),
            "sel": ("BAR_SEL", 72, [("SEL_INV", self.invert_selection, tr("Invertir selección")),
                                    ("SEL_ZERO", self.select_none, tr("No seleccionar nada")),
                                    ("SEL_ALL", self.select_all, tr("Seleccionar todo"))]),
            "misc": ("BAR_MISC", 101, [("MISC_SORT", lambda: a.show_sort_menu(self._bottom_global(101)),
                                        tr("Ordenar lista")),
                                       ("MISC_INFO", a.show_file_info_selected, tr("Información del archivo")),
                                       ("MISC_OPTS", lambda: a.show_misc_options_menu(self._bottom_global(101)),
                                        tr("Opciones"))]),
            "list": ("BAR_LIST", W - 44, [("LIST_NEW", a.new_playlist, tr("Nueva lista")),
                                          ("LIST_SAVE", a.save_playlist, tr("Guardar lista")),
                                          ("LIST_LOAD", a.load_playlist, tr("Cargar lista"))]),
        }
        bar, x, items = menus[which]
        s = self.scale
        anchor = self.mapToGlobal(QPoint(x * s, (H - 30) * s))
        m = SpriteMenu(self, bar, items, anchor)
        m.show()

    def _bottom_global(self, x) -> QPoint:
        s = self.scale
        return self.mapToGlobal(QPoint(x * s, (self.ph - 30) * s))

    # ---------------------------------------------------------- actions
    def remove_selected(self):
        rows = self.selected_rows()
        if rows:
            self.app.player.delete_positions(rows)
            self.selected_ids = set()

    def crop_selected(self):
        rows = self.selected_rows()
        if rows:
            self.app.player.crop(rows)

    def play_cursor(self):
        rows = self.selected_rows()
        row = rows[0] if rows else self.cursor_row
        if 0 <= row < len(self.queue):
            self.app.player.play(row)

    def handle_key(self, ev) -> bool:
        key = ev.key()
        mods = ev.modifiers()
        n = len(self.queue)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        nav = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1,
               Qt.Key.Key_PageUp: -self.visible_rows(), Qt.Key.Key_PageDown: self.visible_rows()}
        if n == 0 and key not in (Qt.Key.Key_Insert,):
            return False
        if key in nav:
            if alt:
                return self.move_selection(-1 if nav[key] < 0 else 1) or True
            row = max(0, min(n - 1, self.cursor_row + nav[key]))
        elif key == Qt.Key.Key_Home:
            row = 0
        elif key == Qt.Key.Key_End:
            row = n - 1
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.play_cursor()
            return True
        elif key == Qt.Key.Key_Delete:
            if ctrl:
                self.app.clear_playlist()
            elif shift:
                self.crop_selected()
            else:
                self.remove_selected()
            return True
        elif key == Qt.Key.Key_A and ctrl and not shift:
            self.select_all()
            return True
        elif key == Qt.Key.Key_I and ctrl:
            self.invert_selection()
            return True
        else:
            return False
        if shift:
            self.select_range(self.anchor if self.anchor is not None else self.cursor_row, row)
        else:
            self.select_only(row)
        self.cursor_row = row
        self.ensure_visible(row)
        self.update()
        return True

    # ------------------------------------------------------- painting
    def paint_background(self, p: QPainter):
        sk = self.skin
        W = self.pw
        active = self.is_active()
        if self.shaded:
            p.drawPixmap(0, 0, sk.sprite("PLEDIT", "SHADE_LEFT"))
            for x in range(25, W - 50, 25):
                p.drawPixmap(x, 0, sk.sprite("PLEDIT", "SHADE_BG"))
            p.drawPixmap(W - 50, 0, sk.sprite("PLEDIT", "SHADE_RIGHT_SEL" if active else "SHADE_RIGHT"))
            self._paint_shade_text(p)
            return
        H = self.ph
        suf = "_SEL" if active else ""
        for x in range(25, W - 25, 25):
            p.drawPixmap(x, 0, sk.sprite("PLEDIT", "TOP_TILE" + suf))
        p.drawPixmap(0, 0, sk.sprite("PLEDIT", "TOP_LEFT" + suf))
        p.drawPixmap(37 + (W - 175) // 2, 0, sk.sprite("PLEDIT", "TOP_TITLE" + suf))
        p.drawPixmap(W - 25, 0, sk.sprite("PLEDIT", "TOP_RIGHT" + suf))
        for y in range(20, H - 38, 29):
            p.drawPixmap(0, y, sk.sprite("PLEDIT", "LEFT_TILE"))
            p.drawPixmap(W - 20, y, sk.sprite("PLEDIT", "RIGHT_TILE"))
        # bottom
        for x in range(125, W - 150, 25):
            p.drawPixmap(x, H - 38, sk.sprite("PLEDIT", "BOTTOM_TILE"))
        p.drawPixmap(0, H - 38, sk.sprite("PLEDIT", "BOTTOM_LEFT"))
        vr = self._vis_rect()
        if vr is not None:
            p.drawPixmap(W - 150 - 75, H - 38, sk.sprite("PLEDIT", "VIS_BG"))
            if self.app.cfg["main_shade"] and self.app.vis.mode != "off":
                self.app.vis.renderer.paint(p, vr, self.app.vis.analyzer,
                                            self.app.vis.mode, self.app.cfg)
        p.drawPixmap(W - 150, H - 38, sk.sprite("PLEDIT", "BOTTOM_RIGHT"))
        self._paint_bottom_text(p)

    def _paint_bottom_text(self, p):
        W, H = self.pw, self.ph
        sk = self.skin
        sel_total = sum(song_duration(self.queue[r]) for r in self.selected_rows()) \
            if self.selected_ids else 0
        text = f"{fmt_time(sel_total)}/{fmt_time(self._total)}"
        if len(text) > 15:
            text = text[-15:]
        draw_bitmap_text(p, sk, text, W - 150 + 7, H - 38 + 10)
        pl = self.app.player
        if pl.state != "stop":
            t = pl.elapsed
            neg = False
            if self.app.cfg["time_remaining"] and pl.duration > 0:
                t = pl.duration - t
                neg = True
            m, s = divmod(int(max(0, t)), 60)
            mt = ("-" if neg else " ") + f"{m:02d}:{s:02d}"
            draw_bitmap_text(p, sk, mt[-6:], W - 150 + 66, H - 38 + 23)

    def _paint_shade_text(self, p):
        pl = self.app.player
        sk = self.skin
        W = self.pw
        if pl.song:
            pos = pl.current_pos
            t = f"{pos + 1}. {song_title(pl.song)}"
            dur = fmt_time(pl.duration) if pl.duration > 0 else ""
        else:
            t, dur = "", ""
        mapped = sk.bitmap_text(t)
        maxch = max(0, (W - 50 - 5 - 30) // 5)
        if mapped is not None or not t:
            draw_bitmap_text(p, sk, (mapped or "")[:maxch], 5, 4)
        else:
            # Non-Latin titles: TrueType fallback in the skin's text colour.
            f = QFont()
            f.setPixelSize(9)
            p.save()
            p.setFont(f)
            p.setPen(sk.text_fg)
            p.setClipRect(QRect(5, 1, maxch * 5, 12))
            p.drawText(QRect(5, 1, maxch * 5, 12), Qt.AlignmentFlag.AlignVCenter, t)
            p.restore()
        if dur:
            draw_bitmap_text(p, sk, dur, W - 30 - len(dur) * 5 + 5 - 5, 4)

    def paint_tracks(self, p: QPainter, rect: QRect):
        sk = self.skin
        cols = sk.pledit
        p.fillRect(rect, cols["normalbg"])
        q = self.queue
        if not q:
            return
        rh = self.row_h
        font = self.font()
        p.setFont(font)
        fm = QFontMetrics(font)
        cur = self.app.player.current_pos
        first = self.scroll
        last = min(len(q), first + self.visible_rows() + 1)
        width = rect.width()
        fm.horizontalAdvance(f"{len(q)}. ") if self.app.cfg["pl_show_numbers"] else 0
        p.save()
        p.setClipRect(rect)
        for i in range(first, last):
            s = q[i]
            y = rect.top() + 2 + (i - first) * rh
            if s.get("id") in self.selected_ids:
                p.fillRect(QRect(rect.left(), y, width, rh), cols["selectedbg"])
            color = cols["current"] if i == cur else cols["normal"]
            p.setPen(color)
            dur = song_duration(s)
            dtext = fmt_time(dur) if dur > 0 else ""
            dw = fm.horizontalAdvance(dtext) if dtext else 0
            if self.app.cfg["pl_show_numbers"]:
                title = f"{i + 1}. {song_title(s)}"
            else:
                title = song_title(s)
            avail = width - dw - 8
            el = fm.elidedText(title, Qt.TextElideMode.ElideRight, max(10, avail))
            p.drawText(QRect(rect.left() + 2, y, avail, rh),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, el)
            if dtext:
                p.drawText(QRect(rect.right() - dw - 3, y, dw + 2, rh),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, dtext)
            if i == self.cursor_row and self.hasFocus():
                pen = p.pen()
                p.setPen(QColor(cols["normal"]))
                p.drawRect(QRect(rect.left(), y, width - 1, rh - 1))
                p.setPen(pen)
        if self._drop_row is not None:
            y = rect.top() + 2 + (self._drop_row - first) * rh
            p.fillRect(QRect(rect.left(), y - 1, width, 2), cols["current"])
        p.restore()

    # ----------------------------------------------------- drag & drop
    def start_external_drag(self):
        rows = self.selected_rows()
        if not rows:
            return
        md = QMimeData()
        uris = [self.queue[r].get("file", "") for r in rows]
        md.setData(MIME_URIS, "\n".join(uris).encode("utf-8"))
        musicdir = self.app.player.music_directory
        urls = []
        for u in uris:
            if u.startswith("file://"):
                urls.append(QUrl(u))
            elif "://" not in u and musicdir:
                urls.append(QUrl.fromLocalFile(musicdir.rstrip("/") + "/" + u))
        if urls:
            md.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, ev):
        md = ev.mimeData()
        if md.hasUrls() or md.hasFormat(MIME_URIS):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if self.shaded:
            self._drop_row = None
        else:
            pt = self.to_logical(ev.position())
            r = self.list_rect()
            row = self.scroll + max(0, (pt.y() - r.top() - 2 + self.row_h // 2) // self.row_h)
            self._drop_row = min(len(self.queue), row)
        self.update()
        ev.acceptProposedAction()

    def dragLeaveEvent(self, ev):
        self._drop_row = None
        self.update()

    def dropEvent(self, ev):
        md = ev.mimeData()
        pos = self._drop_row
        self._drop_row = None
        if ev.source() is self:
            self.update()
            return
        if md.hasFormat(MIME_URIS):
            uris = bytes(md.data(MIME_URIS)).decode("utf-8").splitlines()
            self.app.player.add([u for u in uris if u], position=pos)
        elif md.hasUrls():
            paths, urls = [], []
            for u in md.urls():
                if u.isLocalFile():
                    paths.append(u.toLocalFile())
                else:
                    urls.append(u.toString())
            if paths:
                self.app.player.add_paths(paths, position=pos)
            if urls:
                self.app.player.add(urls, position=pos)
        ev.acceptProposedAction()
        self.update()
