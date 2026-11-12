"""Application controller: owns the model, skin, shell window and menus."""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QColor, QDesktopServices,
                           QGuiApplication, QKeySequence, QPalette, QRegion, QTransform)
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QMenu,
                               QMessageBox, QWidget)

from . import __version__
from .audio import pipewire as pw
from .audio.eq import Equalizer
from .config import SKIN_DIR, Config
from .mpdconn import autodetect_address
from .player import Player, first, song_title
from .skin.classic import ClassicSkin, is_classic_skin, load_classic
from .skin.zebamp_skin import zebamp_skin
from .ui.eqwin import EqPanel
from .ui.mainwin import MainPanel
from .ui.plwin import PlaylistPanel
from .vis import Visualizer
from .i18n import tr

log = logging.getLogger(__name__)


class Shell(QWidget):
    """Frameless top-level window that docks main, EQ and playlist panels."""

    def __init__(self, app: ZebampApp):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Zebamp")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(False)

    def keyPressEvent(self, ev):
        if not self.app.handle_key(ev):
            super().keyPressEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.app.classic_free():
            wh = self.windowHandle()
            if wh is not None and not getattr(self, "_hooked", False):
                self._hooked = True
                wh.screenChanged.connect(lambda *_: QTimer.singleShot(200, self.app.fit_classic_canvas))
            QTimer.singleShot(120, self.app.fit_classic_canvas)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == ev.Type.ActivationChange:
            for p in self.app.panels():
                p.update()

    def closeEvent(self, ev):
        tray = getattr(self.app, "tray", None)
        if self.app.cfg["close_to_tray"] and tray is not None and tray.icon is not None:
            ev.ignore()
            self.app.hide_all()
            return
        self.app.quit()
        ev.accept()



class _F1Filter(QObject):
    """F1 anywhere in Zebamp opens the help for the active window."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_F1 \
                and not ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            import time
            now = time.monotonic()
            if not ev.isAutoRepeat() and now - getattr(self, "_t", 0.0) > 0.3:
                self._t = now
                QTimer.singleShot(0, self.app.help_for_active_window)
            return True
        return False


class ZebampApp:
    def __init__(self, qapp: QApplication, args):
        self.qapp = qapp
        self._f1 = _F1Filter(self)
        qapp.installEventFilter(self._f1)
        self.args = args
        self.cfg = Config()
        os.makedirs(SKIN_DIR, exist_ok=True)
        self.scale = int(self.cfg["scale"]) or auto_scale()
        self.cfg["scale"] = self.scale
        # Modern skins: their art is drawn for 1x; zoom is fractional and smooth.
        self.mscale = float(self.cfg["modern_scale"] or 1.0)
        self.balance = int(self.cfg["balance"])
        self.focused_panel = None
        self.base_skin = zebamp_skin(self.scale)
        self.skin: ClassicSkin = self.base_skin
        self.modern = None
        self._shown = False
        addr = autodetect_address(self.cfg["mpd_host"], int(self.cfg["mpd_port"] or 0),
                                  self.cfg["mpd_password"])
        if args.host:
            addr = autodetect_address(args.host, args.port or 6600, self.cfg["mpd_password"])
        self.player = Player(addr)
        self.player.message.connect(self._on_mpd_message)
        self.pw = pw.PipeWireAudio() if (pw.available() and self.cfg["eq_backend"] == "pipewire") else None
        if self.pw is not None:
            self.pw.cleanup_stale()
        self.eq = Equalizer(self.cfg, self.pw)
        self.vis = Visualizer(self.cfg, self.player)
        self.vis.shown = lambda: self._shown and self.is_visible()
        from .notify import SongNotifier
        self.notifier = SongNotifier(self)
        from .stats import Stats
        self.stats = Stats(self.player)
        from .stallwatch import StallWatch
        self.stall_watch = StallWatch(self.player)
        self.stall_watch.stalled.connect(lambda text: self.main_panel.set_temp_text(text))
        from .scrobble import Scrobbler
        self.scrobbler = Scrobbler(self.cfg, self.player, self.stats)
        from .sleeptimer import SleepTimer
        self.sleep = SleepTimer(self.player)
        self.sleep.fired.connect(lambda: self.main_panel.set_temp_text(tr("Temporizador: música en pausa")))
        from .libindex import LibraryIndex
        # built in the background shortly after start: search is instant later
        self.library_index = LibraryIndex(self.player)
        QTimer.singleShot(4000, self.library_index.refresh)
        self._ppos = {}
        self._ppos_origin = None
        for k, v in (self.cfg["classic_positions"] or {}).items():
            try:
                if k == "_origin":
                    self._ppos_origin = (int(v[0]), int(v[1]))
                else:
                    self._ppos[k] = QPoint(int(v[0]), int(v[1]))
            except (TypeError, ValueError, IndexError):
                pass
        self._drag = None
        self.shell = Shell(self)
        self.main_panel = MainPanel(self, self.shell)
        self.eq_panel = EqPanel(self, self.shell)
        self.pl_panel = PlaylistPanel(self, self.shell)
        from .ui.lyricspanel import LyricsPanel
        self.ly_panel = LyricsPanel(self, self.shell)
        from .ui.artpanel import ArtPanel
        self.art_panel = ArtPanel(self, self.shell)
        for p in self.panels():
            p.sizeHintChanged.connect(self.relayout)
        self.library = None
        self.focused_panel = self.main_panel
        self.player.statusChanged.connect(self._on_status)
        self.player.songChanged.connect(self._on_song)
        self.player.connectionChanged.connect(lambda ok: self.main_panel._on_song())
        self._last_state = None
        # MPD recreates its PipeWire stream after stop/seek in some setups;
        # re-check the EQ routing periodically while playing (cheap, threaded).
        self._pw_watch = QTimer()
        self._pw_watch.setInterval(5000)
        self._pw_watch.timeout.connect(self._pw_check)
        skin_path = args.skin or self.cfg["skin"]
        if skin_path:
            self.load_skin(skin_path, save=False, quiet=True)
        else:
            self._apply_skin_side_effects()
        self.relayout()
        self.player.start()
        if self.balance and self.pw is not None:
            self.pw.set_balance(self.balance)

    # ------------------------------------------------------------ panels
    def panels(self):
        return [self.main_panel, self.eq_panel, self.pl_panel, self.ly_panel, self.art_panel]

    def visible_panels(self):
        out = [self.main_panel]
        if self.cfg["show_eq"]:
            out.append(self.eq_panel)
        if self.cfg["show_playlist"]:
            out.append(self.pl_panel)
        if self.cfg["show_lyrics_panel"] and self.modern is None:
            out.append(self.ly_panel)
        if self.cfg["show_art_panel"] and self.modern is None:
            out.append(self.art_panel)
        return out

    # --------------------------------------------- free (magnetic) layout
    PANEL_KEYS = ("main", "eq", "pl", "ly", "art")

    def classic_free(self) -> bool:
        return self.cfg["classic_layout"] == "free"

    def _pkey(self, p):
        return self.PANEL_KEYS[self.panels().index(p)]

    def fit_classic_canvas(self, span_all=False):
        """Cover the monitor(s) holding the windows; all of them while dragging."""
        if not self.classic_free() or not self.shell.isVisible():
            return
        if getattr(self, "_drag", None) is not None and not span_all:
            return          # never resize under a drag (screenChanged etc.); drag_end refits
        from .canvas import home_monitors, place_canvas, workspace_rects
        rects = workspace_rects()
        if not rects:
            return
        focus_origin = (rects[0].x(), rects[0].y())
        cur = self._ppos_origin or focus_origin
        s = self.scale
        glob = [QRect(cur[0] + v.x() * s, cur[1] + v.y() * s, p.width(), p.height())
                for p in self.visible_panels() for k, v in [(self._pkey(p), self._ppos.get(self._pkey(p)))]
                if v is not None]
        chosen = rects if span_all else home_monitors(rects, glob)
        _w, _h, screens, origin = place_canvas(self.shell, chosen)
        self._screens = screens
        self._all_monitors = len(rects)
        self._all_screens_dev = [r.translated(-origin[0], -origin[1]) for r in rects]
        # positions are relative to the canvas origin
        dx, dy = round((cur[0] - origin[0]) / s), round((cur[1] - origin[1]) / s)
        if dx or dy:
            for k, v in list(self._ppos.items()):
                self._ppos[k] = QPoint(v.x() + dx, v.y() + dy)
            d = getattr(self, "_drag", None)
            if d is not None:
                pt, group, sp = d
                sx, sy = cur[0] - origin[0], cur[1] - origin[1]
                self._drag = (QPoint(pt.x() + sx, pt.y() + sy), group,
                              {k: QPoint(v.x() + dx, v.y() + dy) for k, v in sp.items()})
                fr = getattr(self, "_dframe", None)
                if fr is not None:
                    fr.shift(sx, sy)
        self._ppos_origin = origin
        self.relayout()

    def _screens_dev(self):
        return getattr(self, "_screens", None) or [QRect(0, 0, self.shell.width(), self.shell.height())]

    def _panel_region(self, p, x, y) -> QRegion:
        path = p.region_path()
        if path is not None:
            s = self.scale
            scaled = QTransform().scale(s, s).map(path)
            scaled.translate(x, y)
            reg = QRegion()
            for poly in scaled.toFillPolygons():
                reg = reg.united(QRegion(poly.toPolygon()))
            return reg
        return QRegion(QRect(x, y, p.width(), p.height()))

    def _follow_bottom_edges(self, vis):
        """Shading/resizing a window drags the windows docked under it along
        (otherwise they are left behind and stop being part of the group)."""
        from .canvas import follow_bottom_edges
        pos = self._ppos
        heights = {self._pkey(p): p.logical_size()[1] for p in vis}
        last = getattr(self, "_last_heights", None)
        if last:
            rects = {}
            for p in vis:
                k = self._pkey(p)
                if k in pos and k in last:
                    rects[k] = QRect(pos[k].x(), pos[k].y(), p.logical_size()[0], last[k])
            for k, dy in follow_bottom_edges(rects, heights).items():
                pos[k] = QPoint(pos[k].x(), pos[k].y() + dy)
        self._last_heights = heights

    def _relayout_free(self, vis):
        s = self.scale
        pos = self._ppos
        if not self.shell.isVisible() and self.shell.width() < 400:
            scr = QGuiApplication.primaryScreen()
            g = scr.availableGeometry() if scr is not None else QRect(0, 0, 1280, 800)
            self.shell.setFixedSize(g.width(), g.height())
        scr0 = self._screens_dev()[0]
        for p in vis:
            p.apply_size()
        self._follow_bottom_edges(vis)
        # newcomers go under the last panel of the default stack (main/eq/pl)
        for p in vis:
            k = self._pkey(p)
            if k in pos:
                continue
            if k == "main":
                pos[k] = QPoint(int((scr0.x() + max(0, (scr0.width() - p.width()) / 2)) / s),
                                int((scr0.y()) / s) + 80)
            else:
                above = None
                for q in self.panels()[:self.panels().index(p)]:
                    if q in vis and self._pkey(q) in pos:
                        above = q
                if above is None:
                    pos[k] = QPoint(int((scr0.x() + max(0, (scr0.width() - p.width()) / 2)) / s),
                                    int(scr0.y() / s) + 80)
                else:
                    pos[k] = self._newcomer_spot(p, above, vis)
        region = QRegion()
        from .canvas import keep_on_screens
        for p in vis:
            k = self._pkey(p)
            q = pos[k]
            dx = dy = 0
            if getattr(self, "_screens", None):     # only once the canvas knows the monitors
                dx, dy = keep_on_screens(QRect(q.x() * s, q.y() * s, p.width(), p.height()), self._screens_dev())
            x, y = q.x() + round(dx / s), q.y() + round(dy / s)
            pos[k] = QPoint(x, y)
            p.move(x * s, y * s)
            region = region.united(self._panel_region(p, x * s, y * s))
        self.shell.setMask(region)

    def _skin_rect(self, panel) -> QRect:
        """A placed panel in skin pixels (its logical size: the widget may
        still have another scale's size)."""
        return QRect(self._ppos[self._pkey(panel)], QSize(*panel.logical_size()))

    def _newcomer_spot(self, panel, above, vis) -> QPoint:
        from .canvas import place_newcomer
        s = self.scale
        screens = [QRect(r.x() // s, r.y() // s, r.width() // s, r.height() // s) for r in self._screens_dev()]
        stack = [self._skin_rect(q) for q in vis if self._pkey(q) in self._ppos]
        return place_newcomer(*panel.logical_size(), self._skin_rect(above), stack, screens)

    def _drag_begin(self, panel, pt):
        group = [panel]
        if panel is self.main_panel:
            from .canvas import docked_keys
            rects = {self._pkey(o): self._skin_rect(o) for o in self.visible_panels()}
            by_key = dict(zip(self.PANEL_KEYS, self.panels(), strict=True))
            group = [by_key[k] for k in docked_keys("main", rects)]
        self._drag = (pt, group, {self._pkey(g): QPoint(self._ppos[self._pkey(g)]) for g in group})
        for g in group:
            g.raise_()
        from .canvas import DragFrame
        self._dframe = DragFrame(QPointF(pt))

    def drag_active(self, panel) -> bool:
        d = getattr(self, "_drag", None)
        return d is not None and panel in d[1]

    def drag_to(self, pt):
        d = getattr(self, "_drag", None)
        if d is None:
            return
        fr = getattr(self, "_dframe", None)
        if fr is not None:
            raw = QPointF(pt)
            fp = fr.fix(raw)
            if not fr.moved:
                return                          # a click is not a drag
            pt = QPoint(round(fp.x()), round(fp.y()))
            if not fr.spanned and getattr(self, "_all_monitors", 1) > 1:
                from .canvas import reaches_other_monitor
                start, group, start_pos = d
                s = self.scale
                mv = [QRect(start_pos[self._pkey(g)].x() * s + pt.x() - start.x(),
                            start_pos[self._pkey(g)].y() * s + pt.y() - start.y(), g.width(), g.height())
                      for g in group]
                if reaches_other_monitor(mv, QRect(0, 0, self.shell.width(), self.shell.height()),
                                         getattr(self, "_all_screens_dev", [])):
                    # only now, because the user is taking it there: open the way
                    fr.spanned = True
                    self.fit_classic_canvas(span_all=True)
                    d = self._drag
                    fp = fr.fix(raw)            # this event was in the old frame
                    pt = QPoint(round(fp.x()), round(fp.y()))
        from .canvas import snap_offsets
        start, group, start_pos = d
        s = self.scale
        dx, dy = pt.x() - start.x(), pt.y() - start.y()      # device px
        moving = [QRect(start_pos[self._pkey(g)].x() * s + dx, start_pos[self._pkey(g)].y() * s + dy,
                        g.width(), g.height()) for g in group]
        static = [o.geometry() for o in self.visible_panels() if o not in group]
        ax, ay = snap_offsets(moving, static, self._screens_dev(), 14)
        dx, dy = dx + ax, dy + ay
        region = QRegion()
        from .canvas import moved_together
        placed = moved_together({self._pkey(g): start_pos[self._pkey(g)] for g in group}, dx / s, dy / s)
        for g in group:
            q = placed[self._pkey(g)]
            self._ppos[self._pkey(g)] = q
            g.move(q.x() * s, q.y() * s)
        for o in self.visible_panels():
            region = region.united(self._panel_region(o, o.x(), o.y()))
        self.shell.setMask(region)

    def drag_end(self):
        if getattr(self, "_drag", None) is None:
            return
        _pt, group, _sp = self._drag
        self._drag = None
        fr = getattr(self, "_dframe", None)
        self._dframe = None
        if fr is not None and not fr.moved:
            return                              # just a click
        from .canvas import fit_group, keep_on_screens
        scr = self._screens_dev()
        rects = [g.geometry() for g in group]
        if any(keep_on_screens(r, scr) != (0, 0) for r in rects):
            bb = rects[0]
            for r in rects[1:]:
                bb = bb.united(r)
            dx, dy = fit_group(bb, scr)
            s = self.scale
            for g in group:
                q = self._ppos[self._pkey(g)]
                self._ppos[self._pkey(g)] = QPoint(q.x() + round(dx / s), q.y() + round(dy / s))
        self.relayout()
        if fr is not None and fr.spanned:
            self.fit_classic_canvas()
        self._save_classic_positions()

    def _save_classic_positions(self):
        data = {k: [v.x(), v.y()] for k, v in self._ppos.items()}
        if self._ppos_origin is not None:
            data["_origin"] = list(self._ppos_origin)
        self.cfg["classic_positions"] = data
        self.cfg.save()

    def relayout(self):
        vis = self.visible_panels()
        for p in self.panels():
            p.setVisible(p in vis)
        if self.classic_free():
            self._relayout_free(vis)
            return
        y = 0
        w = 0
        region = QRegion()
        for p in self.panels():
            p.setVisible(p in vis)
        for p in vis:
            p.apply_size()
            p.move(0, y)
            path = p.region_path()
            if path is not None:
                s = self.scale
                scaled = QTransform().scale(s, s).map(path)
                scaled.translate(0, y)
                for poly in scaled.toFillPolygons():
                    region = region.united(QRegion(poly.toPolygon()))
            else:
                region = region.united(QRegion(QRect(0, y, p.width(), p.height())))
            y += p.height()
            w = max(w, p.width())
        self.shell.setFixedSize(max(1, w), max(1, y))
        self.shell.setMask(region)

    def set_focused_panel(self, panel):
        if self.focused_panel is not panel:
            old = self.focused_panel
            self.focused_panel = panel
            if old is not None:
                old.update()
            panel.update()

    def start_move(self, panel, ev=None):
        if self.classic_free() and ev is not None:
            self._drag_begin(panel, panel.mapTo(self.shell, ev.position().toPoint()))
            return
        h = self.shell.windowHandle()
        if h is not None:
            h.startSystemMove()

    def show(self):
        self._shown = True
        if self.modern is not None:
            self._activate_frontend()
        else:
            self.shell.show()
            self.shell.raise_()
            self.shell.activateWindow()
        QTimer.singleShot(0, self.vis._on_state)

    def is_visible(self) -> bool:
        if self.modern is not None:
            return bool(self.modern.top_windows())
        return self.shell.isVisible()

    def hide_all(self):
        if self.modern is not None:
            self.modern.hide()
        else:
            self.shell.hide()
        self.vis._on_state()          # nothing to draw: stop analysing audio

    def request_close(self):
        """Close button / window close: hide to tray if asked to, else quit."""
        tray = getattr(self, "tray", None)
        if self.cfg["close_to_tray"] and tray is not None and tray.icon is not None:
            self.hide_all()
        else:
            self.quit()

    def toggle_visible(self):
        if self.is_visible():
            self.hide_all()
        else:
            self.show()

    def minimize(self):
        if self.modern is not None:
            for w in self.modern.top_windows():
                w.showMinimized()
            return
        self.shell.showMinimized()

    def quit(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        try:
            md = getattr(self, "milkdrop", None)
            if md is not None:
                md.close()
                md.shutdown()
            tray = getattr(self, "tray", None)
            if tray is not None:
                tray.hide()
            self._stop_modern()
            self.cfg["scale"] = self.scale
            self.cfg.save()
            self.vis.shutdown()
            if self.pw is not None:
                self.pw.shutdown()
                self.pw._thread.join(timeout=4)
            self.player.shutdown()
        finally:
            self.qapp.quit()

    # ----------------------------------------------------------- skin
    def load_skin(self, path: str, save=True, quiet=False) -> bool:
        path = os.path.expanduser(path)
        try:
            if os.path.splitext(path)[1].lower() == ".wal" or _is_modern_dir(path) or \
                    (path.lower().endswith(".zip") and _zip_is_modern(path)):
                from .modern import load_modern
                eng = load_modern(path, self)
                if eng is None:
                    raise ValueError("skin moderno no compatible (sin contenedores)")
                self._stop_modern()
                self.modern = eng
                self.skin = self.base_skin
            else:
                if not is_classic_skin(path):
                    raise ValueError("no parece un skin de Winamp")
                skin = load_classic(path, fallback=self.base_skin, smooth=self._classic_smooth())
                self._stop_modern()
                self.skin = skin
        except Exception as e:
            log.warning("skin %s: %s", path, e)
            if not quiet:
                QMessageBox.warning(None, "Zebamp", f"No se pudo cargar el skin:\n{path}\n\n{e}")
            return False
        if save:
            self.cfg["skin"] = path
            self.cfg.save()
        self._apply_skin_side_effects()
        return True

    def _stop_modern(self):
        if self.modern is not None:
            try:
                self.modern.stop()
            except Exception:
                log.exception("stopping modern skin")
            self.modern = None

    def use_default_skin(self):
        self._stop_modern()
        self.skin = self.base_skin
        self.cfg["skin"] = ""
        self.cfg.save()
        self._apply_skin_side_effects()

    def _apply_skin_side_effects(self):
        self.vis.renderer.set_colors(self.skin.viscolors)
        for p in self.panels():
            p.rebuild()
        self.main_panel._on_song()
        self.relayout()
        self._apply_palette()
        if self.library is not None:
            self.library.apply_skin()
        self._activate_frontend()

    def _activate_frontend(self):
        if not self._shown:
            return
        if self.modern is not None:
            self.shell.hide()
            if not self.modern.clock.isActive():
                self.modern.start()
            else:
                self.modern.show()
        else:
            self.shell.show()
            self.shell.raise_()

    def _apply_palette(self):
        g = self.skin.genex_colors or self.base_skin.genex_colors or {}
        pal = QPalette()
        def c(name, default):
            return g.get(name) or QColor(default)
        win = c("window_bg", "#262a34")
        text = c("window_text", "#d0d4dc")
        base = c("item_bg", "#0a0f12")
        from .colors import distinct_bg, readable
        item_fg = c("item_fg", "#3ef0c8")
        button = c("list_header_bg", "#363c4a")
        # some skins give selection text and background the same colour:
        # always keep text readable
        hl = distinct_bg(c("list_text_selected_bg", "#1e465a"), base,
                         g.get("playlist_selection"), g.get("list_text_highlighted_bg"))
        pal.setColor(QPalette.ColorRole.Window, win)
        pal.setColor(QPalette.ColorRole.WindowText, readable(text, win, item_fg))
        pal.setColor(QPalette.ColorRole.Base, base)
        pal.setColor(QPalette.ColorRole.AlternateBase, base.lighter(115))
        pal.setColor(QPalette.ColorRole.Text, readable(item_fg, base, text))
        pal.setColor(QPalette.ColorRole.Button, button)
        pal.setColor(QPalette.ColorRole.ButtonText, readable(c("button_text", "#d0d4dc"), button, text))
        pal.setColor(QPalette.ColorRole.Highlight, hl)
        pal.setColor(QPalette.ColorRole.HighlightedText,
                     readable(c("list_text_selected", "#ffffff"), hl, item_fg, text))
        ph = QColor(pal.color(QPalette.ColorRole.Text))
        ph.setAlpha(150)
        pal.setColor(QPalette.ColorRole.PlaceholderText, ph)
        pal.setColor(QPalette.ColorRole.ToolTipBase, base)
        pal.setColor(QPalette.ColorRole.ToolTipText, readable(item_fg, base, text))
        self.dialog_palette = pal

    def skin_files(self) -> list[str]:
        out = []
        seen = set()
        for d in self.cfg["skin_dirs"] or [SKIN_DIR]:
            d = os.path.expanduser(d)
            try:
                entries = sorted(os.listdir(d), key=str.lower)
            except OSError:
                continue
            for e in entries:
                full = os.path.join(d, e)
                ext = os.path.splitext(e)[1].lower()
                is_skin = ext in (".wsz", ".zip", ".wal") or (
                    os.path.isdir(full) and (is_classic_skin(full) or _is_modern_dir(full)))
                if is_skin and full not in seen:
                    seen.add(full)
                    out.append(full)
        return out

    # ----------------------------------------------------------- toggles
    def toggle_double_size(self):
        if self.modern is not None:
            self.set_modern_scale(1.0 if self.mscale > 1 else 1.5)
            return
        self.set_scale(1 if self.scale > 1 else 2)

    def set_modern_scale(self, s: float):
        self.mscale = float(s)
        self.cfg["modern_scale"] = self.mscale
        self.cfg.save()
        if self.modern is not None:
            self.modern.set_scale()

    def set_scale(self, s: int):
        self.scale = s
        self.cfg["scale"] = s
        self.cfg.save()
        # the built-in vector skin is redrawn at the new zoom (stays sharp)
        old = self.base_skin
        self.base_skin = zebamp_skin(s)
        if self.skin is old:
            self.skin = self.base_skin
        elif self.modern is None and getattr(self.skin, "path", None):
            # bitmap skins are re-enlarged for the new zoom
            if self.load_skin(self.skin.path, save=False, quiet=True):
                return
        elif getattr(self.skin, "fallback", None) is old:
            self.skin.fallback = self.base_skin
            self.skin._cache.clear()
            self.skin._font_glyphs.clear()
        self._apply_skin_side_effects()
        for p in self.panels():
            p.rebuild()
        self.relayout()
        if self.modern is not None:
            self.modern.set_scale()

    def _classic_smooth(self) -> int:
        return self.scale if self.cfg["classic_smooth"] and self.scale > 1 else 1

    def toggle_classic_smooth(self):
        self.cfg["classic_smooth"] = not self.cfg["classic_smooth"]
        self.cfg.save()
        if self.modern is None and getattr(self.skin, "path", None):
            self.load_skin(self.skin.path, save=False)

    def set_modern_layout(self, mode):
        self.cfg["modern_layout"] = mode
        self.cfg.save()
        if self.modern is not None and self.modern.skin.path:
            self.load_skin(self.modern.skin.path, save=False)

    def reset_modern_positions(self):
        if self.modern is None:
            return
        allpos = dict(self.cfg["modern_positions"] or {})
        allpos.pop(self.modern.skin.path or "", None)
        self.cfg["modern_positions"] = allpos
        self.cfg.save()
        if self.modern.dock is not None:
            self.modern.dock.pos.clear()
            self.modern.dock.relayout()

    def _toggle_cfg(self, key):
        self.cfg[key] = not self.cfg[key]
        self.cfg.save()

    def toggle_cover_online(self):
        """Look on the Internet for the covers the music does not carry."""
        self.cfg["cover_online"] = not self.cfg["cover_online"]
        self.cfg.save()
        self.art_panel.load(force=True)

    def toggle_notify(self):
        self.cfg["notify_song"] = not self.cfg["notify_song"]
        self.cfg.save()

    def toggle_always_on_top(self):
        on = not self.cfg.get("always_on_top", False)
        self.cfg["always_on_top"] = on
        self.shell.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.shell.show()
        self.main_panel.update()

    def toggle_time_mode(self):
        self.cfg["time_remaining"] = not self.cfg["time_remaining"]
        self.cfg.save()
        for p in self.panels():
            p.update()

    def cycle_vis_mode(self):
        order = ["spectrum", "oscilloscope", "off"]
        cur = self.cfg["vis_mode"]
        self.set_vis_mode(order[(order.index(cur) + 1) % 3 if cur in order else 0])

    def set_vis_mode(self, mode: str):
        self.cfg["vis_mode"] = mode
        self.cfg.save()
        self.vis._on_state()
        for p in self.panels():
            p.update()

    def _toggle_cfg_panel(self, key):
        self.cfg[key] = not self.cfg[key]
        self.cfg.save()
        self.relayout()
        self.main_panel.update()

    def toggle_eq_window(self):
        if self.modern is not None and self.modern.toggle("eq"):
            return
        self._toggle_cfg_panel("show_eq")
        if self.modern is not None:
            self.shell.setVisible(self.cfg["show_eq"] or self.cfg["show_playlist"])

    def toggle_playlist_window(self):
        if self.modern is not None and self.modern.toggle("pl"):
            return
        self._toggle_cfg_panel("show_playlist")
        if self.modern is not None:
            self.shell.setVisible(self.cfg["show_eq"] or self.cfg["show_playlist"])

    def _toggle_shade(self, key, panel):
        self.cfg[key] = not self.cfg[key]
        self.cfg.save()
        panel.rebuild()
        self.relayout()
        self.pl_panel.update()

    def toggle_main_shade(self):
        self._toggle_shade("main_shade", self.main_panel)

    def toggle_eq_shade(self):
        self._toggle_shade("eq_shade", self.eq_panel)

    def toggle_pl_shade(self):
        self._toggle_shade("pl_shade", self.pl_panel)

    def toggle_eq_auto(self):
        self.cfg["eq_auto"] = not self.cfg["eq_auto"]
        self.cfg.save()
        self.eq_panel.update()

    # ---------------------------------------------------------- balance
    def set_balance(self, b: int):
        self.balance = max(-100, min(100, int(b)))
        self.main_panel.update_logical(QRect(177, 57, 38, 13))
        if self.cfg["eq_shade"]:
            self.eq_panel.update()

    def commit_balance(self):
        self.cfg["balance"] = self.balance
        self.cfg.save()
        if self.pw is not None and self.cfg["balance_backend"]:
            self.pw.set_balance(self.balance)

    # ---------------------------------------------------------- events
    def _on_status(self):
        st = self.player.state
        if st != self._last_state:
            if st == "play" and self.pw is not None and (self.eq.enabled or self.balance):
                # MPD may have (re)created its PipeWire stream.
                QTimer.singleShot(300, self.pw.ensure)
            if st == "play" and self.pw is not None:
                self._pw_watch.start()
            else:
                self._pw_watch.stop()
            self._last_state = st

    def _pw_check(self):
        if self.pw is not None and (self.eq.enabled or self.balance):
            self.pw.ensure()

    def _on_song(self):
        s = self.player.song
        title = song_title(s) if s else ""
        self.shell.setWindowTitle(f"{title} - Zebamp" if title else "Zebamp")
        if self.cfg["eq_auto"] and s:
            self._auto_eq(s)

    def _auto_eq(self, song):
        """Winamp 'Auto': pick a preset named like the song's genre."""
        genre = str(first(song.get("genre"))).lower()
        if not genre:
            return
        presets = {**self.eq.builtin, **self.eq.user_presets}
        for name, p in presets.items():
            if name.lower() == genre or name.lower() in genre:
                self.eq.load_preset(p)
                return

    def _on_mpd_message(self, msg):
        self.main_panel.set_temp_text("MPD: " + msg)

    # ---------------------------------------------------------- keyboard
    def handle_key(self, ev) -> bool:
        key = ev.key()
        mods = ev.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        pl = self.player
        if self.focused_panel is self.pl_panel and self.cfg["show_playlist"] \
                and not self.cfg["pl_shade"] and self.pl_panel.handle_key(ev):
            return True
        K = Qt.Key
        if ctrl and alt and key == Qt.Key.Key_B:
            self.add_bookmark()
            return True
        if ctrl and shift and key == Qt.Key.Key_L:
            self.show_lyrics()
            return True
        if ctrl and shift and key == Qt.Key.Key_A:
            self.toggle_art_panel()
            return True
        if ctrl and alt and Qt.Key.Key_0 <= key <= Qt.Key.Key_5:
            self.stats.rate_current(key - Qt.Key.Key_0)
            self.main_panel.set_temp_text(tr("Valoración: ") + ("*" * (key - Qt.Key.Key_0) or tr("ninguna")))
            return True
        if alt:
            table = {K.Key_E: self.toggle_playlist_window, K.Key_G: self.toggle_eq_window,
                     K.Key_L: self.show_library, K.Key_S: self.show_skin_browser,
                     K.Key_3: self.show_file_info, K.Key_W: self.toggle_main_shade,
                     K.Key_R: self.show_radio,
                     K.Key_K: self.show_preferences}
            fn = table.get(key)
            if fn:
                fn()
                return True
            return False
        if ctrl:
            table = {K.Key_D: self.toggle_double_size, K.Key_L: self.add_url_play,
                     K.Key_P: self.show_preferences, K.Key_W: self.toggle_main_shade,
                     K.Key_T: self.toggle_time_mode, K.Key_Q: self.quit,
                     K.Key_J: self.show_jump_to_time, K.Key_F: self.show_search,
                     K.Key_K: self.toggle_milkdrop}
            fn = table.get(key)
            if fn:
                fn()
                return True
            return False
        if shift and key == K.Key_L:
            self.open_dir()
            return True
        table = {
            K.Key_Z: pl.previous, K.Key_X: pl.play, K.Key_C: pl.pause,
            K.Key_V: pl.stop, K.Key_B: pl.next, K.Key_L: self.open_files,
            K.Key_J: self.show_jump_to_file, K.Key_R: pl.toggle_repeat,
            K.Key_F3: self.show_search, K.Key_Slash: self.show_search,
            K.Key_S: pl.toggle_random,
            K.Key_Left: lambda: pl.seek_relative(-5), K.Key_Right: lambda: pl.seek_relative(5),
            K.Key_Up: lambda: pl.set_volume(pl.volume + 2),
            K.Key_Down: lambda: pl.set_volume(pl.volume - 2),
            K.Key_Insert: self.add_files, K.Key_Space: pl.toggle_play,
            K.Key_MediaPlay: pl.toggle_play, K.Key_MediaTogglePlayPause: pl.toggle_play,
            K.Key_MediaStop: pl.stop, K.Key_MediaNext: pl.next,
            K.Key_MediaPrevious: pl.previous,
        }
        fn = table.get(key)
        if fn:
            fn()
            if key in (K.Key_Up, K.Key_Down):
                self.main_panel.set_temp_text(tr("Volumen: {0}%").format(max(0, pl.volume)))
            return True
        return False

    # ----------------------------------------------------------- files
    def _music_dir(self) -> str:
        md = self.player.music_directory
        return md if md and os.path.isdir(md) else os.path.expanduser("~/Music")

    _FILTER = (tr("Audio (*.mp3 *.flac *.ogg *.oga *.opus *.m4a *.aac *.wav *.wv *.ape *.mpc *.wma "
                  "*.aiff *.dsf *.mod *.xm *.s3m *.it *.spc *.nsf *.vgm *.vgz *.sid *.mid *.m3u *.m3u8 "
                  "*.pls *.cue);;Todos (*)"))

    def _pick_files(self, title) -> list[str]:
        files, _ = QFileDialog.getOpenFileNames(None, title, self._music_dir(), self._FILTER)
        return files

    def open_files(self):
        files = self._pick_files(tr("Abrir archivos"))
        if files:
            self.player.add_paths(files, replace=True)

    def open_dir(self):
        d = QFileDialog.getExistingDirectory(None, tr("Abrir carpeta"), self._music_dir())
        if d:
            self.player.add_paths([d], replace=True)

    def add_files(self):
        files = self._pick_files(tr("Añadir archivos a la lista"))
        if files:
            self.player.add_paths(files)

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(None, tr("Añadir carpeta a la lista"), self._music_dir())
        if d:
            self.player.add_paths([d])

    def _ask_url(self, title) -> str | None:
        recent = self.cfg["recent_urls"] or []
        url, ok = QInputDialog.getItem(None, title, tr("URL (http://, https://, etc.):"),
                                       recent or [""], 0, True)
        url = (url or "").strip()
        if not ok or not url:
            return None
        recent = [url] + [u for u in recent if u != url]
        self.cfg["recent_urls"] = recent[:15]
        self.cfg.save()
        return url

    def add_url(self):
        url = self._ask_url(tr("Añadir URL"))
        if url:
            self.player.add([url])

    def add_url_play(self):
        url = self._ask_url(tr("Abrir URL"))
        if url:
            self.player.add([url], replace=True)

    def clear_playlist(self):
        self.player.clear()

    def new_playlist(self):
        self.player.clear()

    def save_playlist(self):
        from .ui.dialogs import save_playlist_dialog
        save_playlist_dialog(self)

    def load_playlist(self):
        from .ui.dialogs import PlaylistsDialog
        PlaylistsDialog(self).exec()

    # ----------------------------------------------------------- dialogs
    def keep(self, w):
        """Hold a Python reference to a non-modal window until it is destroyed
        (otherwise PySide deletes it while Qt is still painting it)."""
        if not hasattr(self, "_windows"):
            self._windows = []
        self._windows.append(w)
        w.destroyed.connect(lambda *_: self._windows.remove(w) if w in self._windows else None)
        return w

    def show_file_info(self, song=None):
        from .ui.dialogs import FileInfoDialog
        s = song or self.player.song
        if not s:
            return
        self.keep(FileInfoDialog(self, s)).show()

    def show_file_info_selected(self):
        rows = self.pl_panel.selected_rows()
        if rows:
            self.show_file_info(self.player.queue[rows[0]])
        else:
            self.show_file_info()

    def show_jump_to_file(self):
        from .ui.dialogs import JumpToFileDialog
        JumpToFileDialog(self).exec()

    # ------------------------------------------------------- milkdrop
    def toggle_milkdrop(self):
        w = getattr(self, "milkdrop", None)
        if w is not None and w.isVisible():
            w.close()
            return
        from . import milkdrop
        ok, err = milkdrop.available()
        if not ok:
            QMessageBox.warning(None, "MilkDrop", tr("La visualización MilkDrop necesita projectM.\n\n") + err)
            return
        if w is None:
            w = self.milkdrop = milkdrop.MilkdropWindow(self)
        if self.cfg["milkdrop_fullscreen"]:
            w.showFullScreen()
        else:
            w.show()
        w.raise_()
        w.activateWindow()

    def show_milkdrop_config(self):
        from .ui.milkdrop_config import MilkdropConfig
        d = getattr(self, "_mdcfg", None)
        if d is None or not d.isVisible():
            d = self._mdcfg = MilkdropConfig(self)
        d.show()
        d.raise_()
        d.activateWindow()

    def restart_milkdrop(self):
        w = getattr(self, "milkdrop", None)
        if w is None:
            return
        full = w.isFullScreen()
        w.close()
        w.shutdown()
        w.deleteLater()
        self.milkdrop = None
        self.toggle_milkdrop()
        if full and self.milkdrop is not None:
            self.milkdrop.showFullScreen()

    SKIN_EXT = (".wsz", ".wal")
    LIST_EXT = (".m3u", ".m3u8", ".pls")

    def open_paths(self, files: list[str]):
        """Files from the command line / "Open with": skins are installed and
        applied, playlists and songs replace the play queue."""
        from .player import read_playlist_file
        from .ui.dialogs import install_skin
        media = []
        for f in files:
            low = f.lower()
            if "://" not in f and low.endswith(self.SKIN_EXT) and os.path.isfile(f):
                dest = install_skin(f)
                if dest:
                    self.load_skin(dest)
                continue
            if "://" not in f and low.endswith(self.LIST_EXT) and os.path.isfile(f):
                try:
                    media += read_playlist_file(f)
                except OSError:
                    pass
                continue
            media.append(f)
        if not media:
            return
        paths = [f for f in media if "://" not in f]
        urls = [f for f in media if "://" in f]
        pl = self.player
        if paths:
            pl.add_paths(paths, replace=True)
        if urls:
            pl.add(urls, replace=not paths, play_first=bool(paths))

    def run_command(self, msg: dict):
        """Commands from `zebamp --…` (another process, e.g. a WM hotkey)."""
        pl = self.player
        files = msg.get("files") or []
        if files:
            self.open_paths(files)
        table = {"play": pl.play, "pause": pl.pause, "toggle": pl.toggle_play, "stop": pl.stop,
                 "next": pl.next, "prev": pl.previous, "search": self.show_search,
                 "jump": self.show_jump_to_file, "show": self.show,
                 "milkdrop": self.toggle_milkdrop, "lyrics": self.open_lyrics,
                 "radio": self.show_radio, "help": self.show_help}
        for c in msg.get("cmd") or []:
            fn = table.get(c)
            if fn is not None:
                fn()

    def show_search(self):
        from .ui.dialogs import SearchLibraryDialog
        d = getattr(self, "_search_dlg", None)
        if d is None:
            d = self._search_dlg = SearchLibraryDialog(self)
        d.show()
        d.raise_()
        d.activateWindow()
        d.edit.setFocus()
        d.edit.selectAll()
        self._wm_focus(d)

    def _wm_focus(self, w):
        """Wayland doesn't let a background app take focus by itself: when
        opened from a global hotkey, ask the compositor to focus the window."""
        import re

        from PySide6.QtCore import QProcess

        from . import compositor
        command = compositor.current().focus_command(re.escape(w.windowTitle()))
        if command:
            # startDetached: Qt reaps the process (no zombie left behind)
            QTimer.singleShot(150, lambda: QProcess.startDetached(command[0], command[1:]))

    def show_jump_to_time(self):
        pl = self.player
        if pl.state == "stop" or pl.duration <= 0:
            return
        prompt = tr("Tiempo (m:ss) — duración {0:.0f}:{1:02d}:").format(pl.duration // 60, int(pl.duration % 60))
        txt, ok = QInputDialog.getText(None, tr("Saltar a tiempo"), prompt)
        if not ok or not txt.strip():
            return
        try:
            parts = [float(x) for x in txt.strip().split(":")]
        except ValueError:
            return
        sec = 0.0
        for v in parts:
            sec = sec * 60 + v
        pl.seek(min(sec, pl.duration - 1))

    def show_preferences(self):
        from .ui.dialogs import PreferencesDialog
        PreferencesDialog(self).exec()

    def show_skin_browser(self):
        from .ui.dialogs import SkinBrowser
        SkinBrowser(self).exec()

    def show_help(self, section: str | None = None):
        from .ui.help import HelpWindow
        w = getattr(self, "_help_win", None)
        if w is None:
            w = self._help_win = HelpWindow(self)
        w.show_section(section or "inicio")
        w.show()
        w.raise_()
        w.activateWindow()
        self._wm_focus(w)

    def help_for_active_window(self):
        from PySide6.QtWidgets import QApplication
        from .ui.help import HelpWindow, context_section
        w = QApplication.activeWindow()
        if isinstance(w, HelpWindow):
            return
        self.show_help(context_section(self, w))

    def build_help_menu(self, parent) -> QMenu:
        m = QMenu(tr("Ayuda"), parent)
        self._act(m, tr("Ayuda de Zebamp"), self.help_for_active_window, "F1")
        m.addSeparator()
        for key, label in (("primeros", tr("Primeros pasos")), ("atajos", tr("Atajos de teclado")),
                           ("buscar", tr("Búsqueda instantánea")), ("skins", "Skins"),
                           ("problemas", tr("Solución de problemas"))):
            self._act(m, label, lambda k=key: self.show_help(k))
        m.addSeparator()
        self._act(m, tr("Acerca de Zebamp {0}…").format(__version__), self.show_about)
        return m

    def show_about(self):
        from .ui.dialogs import about_dialog
        about_dialog(self)

    def show_library(self):
        from .ui.library import LibraryWindow
        if self.library is None:
            self.library = LibraryWindow(self)
        if self.library.isVisible():
            self.library.hide()
        else:
            self.library.show()
            self.library.raise_()
            self.library.activateWindow()

    # ------------------------------------------------------------- menus
    def _menu(self) -> QMenu:
        m = QMenu()
        m.setPalette(getattr(self, "dialog_palette", m.palette()))
        return m

    def _act(self, menu, text, fn, shortcut=None, checked=None, enabled=True):
        a = menu.addAction(text)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutVisibleInContextMenu(True)
        if checked is not None:
            a.setCheckable(True)
            a.setChecked(bool(checked))
        a.setEnabled(enabled)
        a.triggered.connect(lambda _=False: fn())
        return a

    def build_main_menu(self) -> QMenu:
        m = self._menu()
        self._act(m, f"Zebamp {__version__}…", self.show_about)
        m.addSeparator()
        self._act(m, tr("Reproducir archivo…"), self.open_files, "L")
        self._act(m, tr("Reproducir carpeta…"), self.open_dir, "Shift+L")
        self._act(m, tr("Reproducir URL…"), self.add_url_play, "Ctrl+L")
        m.addSeparator()
        self._act(m, tr("Ventana principal compacta"), self.toggle_main_shade, "Ctrl+W",
                  checked=self.cfg["main_shade"])
        self._act(m, tr("Lista de reproducción"), self.toggle_playlist_window, "Alt+E",
                  checked=self.cfg["show_playlist"])
        self._act(m, tr("Ecualizador"), self.toggle_eq_window, "Alt+G", checked=self.cfg["show_eq"])
        self._act(m, tr("Biblioteca de medios"), self.show_library, "Alt+L",
                  checked=self.library is not None and self.library.isVisible())
        self._act(m, tr("Buscar canciones…"), self.show_search, "Ctrl+F")
        self._act(m, tr("Radio por Internet…"), self.show_radio, "Alt+R")
        if self.modern is None:
            self._act(m, tr("Letras"), self.toggle_lyrics_panel, "Ctrl+Shift+L",
                      checked=self.cfg["show_lyrics_panel"])
            self._act(m, tr("Carátula"), self.toggle_art_panel, "Ctrl+Shift+A",
                      checked=self.cfg["show_art_panel"])
        else:
            self._act(m, tr("Letras…"), self.show_lyrics, "Ctrl+Shift+L")
        m.addSeparator()
        m.addMenu(self.build_bookmarks_menu(m))
        m.addMenu(self.build_skins_menu(m))
        m.addMenu(self.build_options_menu(m))
        m.addMenu(self.build_playback_menu(m))
        vm = self.build_vis_menu(m)
        vm.setTitle(tr("Visualización"))
        m.addMenu(vm)
        m.addMenu(self.build_mpd_menu(m))
        m.addMenu(self.build_help_menu(m))
        m.addSeparator()
        self._act(m, tr("Salir"), self.quit, "Ctrl+Q")
        return m

    # ------------------------------------------------------- bookmarks
    def build_bookmarks_menu(self, parent) -> QMenu:
        m = QMenu(tr("Marcadores"), parent)
        self._act(m, tr("Añadir canción actual (en este punto)"), self.add_bookmark, "Ctrl+Alt+B")
        self._act(m, tr("Editar marcadores…"), self.edit_bookmarks)
        bms = list(self.cfg["bookmarks"] or [])
        if bms:
            m.addSeparator()
        for b in bms[:40]:
            pos = int(b.get("pos") or 0)
            label = b.get("title") or os.path.basename(b.get("file", ""))
            if pos:
                label += f"  [{pos // 60}:{pos % 60:02d}]"
            self._act(m, label[:80], lambda b=b: self.play_bookmark(b))
        return m

    def add_bookmark(self):
        pl = self.player
        s = pl.song or {}
        if not s.get("file"):
            return
        from .player import song_title
        bms = list(self.cfg["bookmarks"] or [])
        pos = int(pl.elapsed) if pl.state in ("play", "pause") and pl.elapsed > 5 else 0
        bms.insert(0, {"file": s["file"], "title": song_title(s), "pos": pos})
        self.cfg["bookmarks"] = bms[:200]
        self.cfg.save()
        self.main_panel.set_temp_text(tr("Marcador añadido"))

    def play_bookmark(self, b):
        pl = self.player
        f = b.get("file")
        idx = next((i for i, s in enumerate(pl.queue) if s.get("file") == f), None)
        if idx is None:
            pl.add([f], play_first=True)
        else:
            pl.play(idx)
        pos = int(b.get("pos") or 0)
        if pos:
            QTimer.singleShot(700, lambda: pl.seek(pos))

    def edit_bookmarks(self):
        from .ui.dialogs import BookmarksDialog
        BookmarksDialog(self).exec()

    def show_radio(self):
        from .ui.radio import RadioDialog
        d = getattr(self, "_radio", None)
        if d is None:
            d = self._radio = RadioDialog(self)
        d.show()
        d.raise_()
        d.activateWindow()

    def show_lyrics(self):
        """Ctrl+Shift+L: skinned lyrics window in classic skins, a normal
        window with modern skins."""
        if self.modern is None:
            self.toggle_lyrics_panel()
        else:
            self.show_lyrics_window()

    def open_lyrics(self):
        """Show the lyrics (never hides them): tray, IPC."""
        if self.modern is None:
            if not self.cfg["show_lyrics_panel"]:
                self.toggle_lyrics_panel()
            self.show()
        else:
            self.show_lyrics_window()

    def toggle_lyrics_panel(self):
        if self.modern is not None:
            self.show_lyrics_window()
            return
        self._toggle_cfg_panel("show_lyrics_panel")
        if self.cfg["show_lyrics_panel"]:
            self.set_focused_panel(self.ly_panel)

    def toggle_art_panel(self):
        """Ctrl+Shift+A: the album art window of classic skins."""
        if self.modern is not None:
            return                      # modern skins bring their own album art
        self._toggle_cfg_panel("show_art_panel")
        if self.cfg["show_art_panel"]:
            self.set_focused_panel(self.art_panel)

    def show_lyrics_window(self):
        from .ui.lyrics import LyricsWindow
        d = getattr(self, "_lyrics", None)
        if d is None:
            d = self._lyrics = LyricsWindow(self)
        d.show()
        d.raise_()
        d.activateWindow()

    def show_main_menu(self, gp: QPoint):
        self._last_menu = self.build_main_menu()
        self._last_menu.popup(gp)

    def build_skins_menu(self, parent) -> QMenu:
        m = QMenu("Skins", parent)
        self._act(m, tr("Explorador de skins…"), self.show_skin_browser, "Alt+S")
        self._act(m, tr("Cargar skin desde archivo…"), self.pick_skin_file)
        m.addSeparator()
        cur = self.cfg["skin"]
        self._act(m, tr("<Zebamp (predeterminado)>"), self.use_default_skin, checked=not cur)
        for f in self.skin_files()[:60]:
            name = os.path.splitext(os.path.basename(f))[0]
            self._act(m, name, lambda f=f: self.load_skin(f), checked=os.path.abspath(f) == os.path.abspath(cur or "-"))
        m.addSeparator()
        self._act(m, tr("Abrir carpeta de skins"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(SKIN_DIR)))
        self._act(m, tr("Conseguir más skins (Winamp Skin Museum)…"),
                  lambda: QDesktopServices.openUrl(QUrl("https://skins.webamp.org/")))
        return m

    def pick_skin_file(self):
        f, _ = QFileDialog.getOpenFileName(None, tr("Cargar skin"), os.path.expanduser("~/Downloads"),
                                           tr("Skins de Winamp (*.wsz *.wal *.zip);;Todos (*)"))
        if f:
            from .ui.dialogs import install_skin
            dest = install_skin(f)
            self.load_skin(dest or f)

    def build_options_menu(self, parent) -> QMenu:
        m = QMenu(tr("Opciones"), parent)
        pl = self.player
        self._act(m, tr("Preferencias…"), self.show_preferences, "Ctrl+P")
        m.addSeparator()
        self._act(m, tr("Tiempo restante"), self.toggle_time_mode, "Ctrl+T",
                  checked=self.cfg["time_remaining"])
        sm = m.addMenu(tr("Tamaño"))
        if self.modern is not None:
            for s in (1.0, 1.25, 1.5, 1.75, 2.0):
                self._act(sm, f"{s:g}x", lambda s=s: self.set_modern_scale(s),
                          "Ctrl+D" if s == 1.5 else None, checked=abs(self.mscale - s) < 0.01)
            sm.addSeparator()
            for key, label in (("free", tr("Ventanas sueltas con imán (como Winamp)")),
                               ("fixed", tr("Todas pegadas en un bloque"))):
                self._act(sm, label, lambda k=key: self.set_modern_layout(k),
                          checked=self.cfg["modern_layout"] == key)
            self._act(sm, tr("Reordenar ventanas del skin"), self.reset_modern_positions)
            sets = list(self.modern.skin.gammasets)
            if sets:
                tm = m.addMenu(tr("Tema de color del skin"))
                cur = self.modern.skin.gamma_name
                for n in sets:
                    self._act(tm, n, lambda n=n: self.modern.set_color_theme(n), checked=n == cur)
        else:
            for s in (1, 2, 3):
                self._act(sm, f"{s}x", lambda s=s: self.set_scale(s), "Ctrl+D" if s == 2 else None,
                          checked=self.scale == s)
            sm.addSeparator()
            self._act(sm, tr("Suavizar skins de mapa de bits (Scale2x/3x)"), self.toggle_classic_smooth,
                      checked=bool(self.cfg["classic_smooth"]))
        self._act(m, tr("Cerrar a la bandeja"), lambda: self._toggle_cfg("close_to_tray"),
                  checked=bool(self.cfg["close_to_tray"]))
        self._act(m, tr("Notificar cambio de canción"), self.toggle_notify,
                  checked=bool(self.cfg["notify_song"]))
        self._act(m, tr("Buscar carátulas en Internet"), self.toggle_cover_online,
                  checked=bool(self.cfg["cover_online"]))
        self._act(m, tr("Siempre visible"), self.toggle_always_on_top,
                  checked=self.cfg.get("always_on_top", False))
        m.addMenu(self.build_language_menu(m))
        m.addSeparator()
        rm = m.addMenu(tr("Repetir"))
        mode = "track" if pl.repeat and pl.single else "all" if pl.repeat else "off"
        for key, label in (("off", "No"), ("all", tr("Toda la lista")), ("track", tr("Pista actual"))):
            self._act(rm, label, lambda k=key: pl.set_repeat_mode(k), checked=mode == key)
        self._act(m, tr("Aleatorio"), pl.toggle_random, "S", checked=pl.random)
        self._act(m, tr("Consumir (quitar al reproducir)"), lambda: pl.set_option("consume", not pl.consume),
                  checked=pl.consume)
        self._act(m, tr("Parar tras la pista actual"), lambda: pl.set_option("single", not pl.single),
                  checked=pl.single and not pl.repeat)
        xm = m.addMenu(tr("Fundido entre pistas"))
        for secs in (0, 2, 4, 6, 8, 10):
            self._act(xm, tr("Desactivado") if secs == 0 else f"{secs} s",
                      lambda s=secs: pl.set_crossfade(s), checked=pl.crossfade == secs)
        m.addMenu(self.build_sleep_menu(m))
        return m

    # --------------------------------------------------------- language
    def build_language_menu(self, parent) -> QMenu:
        from . import i18n
        m = QMenu(tr("Idioma"), parent)
        current = self.cfg["language"]
        for code, name in i18n.LANGUAGES.items():
            self._act(m, name, lambda c=code: self.set_language(c), checked=current == code)
        self._act(m, tr("El del sistema"), lambda: self.set_language("auto"), checked=current == "auto")
        return m

    def set_language(self, code: str):
        """Saved now, used from the next start (see i18n.py for why)."""
        from . import i18n
        if code == self.cfg["language"]:
            return
        self.cfg["language"] = code
        self.cfg.save()
        if i18n.pick_language(code) != i18n.language():
            QMessageBox.information(None, "Zebamp", tr("El idioma cambiará al reiniciar Zebamp."))

    # ------------------------------------------------------ sleep timer
    SLEEP_MINUTES = (15, 30, 45, 60, 90, 120)

    def build_sleep_menu(self, parent) -> QMenu:
        from .sleeptimer import ALBUM
        sleep = self.sleep
        m = QMenu(tr("Temporizador de apagado"), parent)
        if sleep.active:
            state = m.addAction(sleep.describe())
            state.setEnabled(False)
            self._act(m, tr("Cancelar"), sleep.cancel)
            m.addSeparator()
        for minutes in self.SLEEP_MINUTES:
            self._act(m, tr("Pausar en {0} min").format(minutes), lambda n=minutes: self.start_sleep(n))
        self._act(m, tr("Pausar en…"), self.ask_sleep_minutes)
        self._act(m, tr("Pausar al terminar el álbum"), self.start_sleep_album, checked=sleep.mode == ALBUM)
        return m

    def start_sleep(self, minutes: float):
        self.sleep.start_minutes(minutes)
        self.main_panel.set_temp_text(tr("Temporizador: ") + self.sleep.describe().lower())

    def start_sleep_album(self):
        self.sleep.start_album()
        self.main_panel.set_temp_text(tr("Temporizador: al terminar el álbum"))

    def ask_sleep_minutes(self):
        minutes, ok = QInputDialog.getInt(None, tr("Temporizador de apagado"), tr("Pausar dentro de (minutos):"),
                                          30, 1, 24 * 60)
        if ok:
            self.start_sleep(minutes)

    def build_playback_menu(self, parent) -> QMenu:
        m = QMenu(tr("Reproducción"), parent)
        pl = self.player
        self._act(m, tr("Anterior"), pl.previous, "Z")
        self._act(m, tr("Reproducir"), pl.play, "X")
        self._act(m, tr("Pausa"), pl.pause, "C")
        self._act(m, tr("Detener"), pl.stop, "V")
        self._act(m, tr("Siguiente"), pl.next, "B")
        m.addSeparator()
        self._act(m, tr("Retroceder 5 s"), lambda: pl.seek_relative(-5), "Left")
        self._act(m, tr("Avanzar 5 s"), lambda: pl.seek_relative(5), "Right")
        self._act(m, tr("Subir volumen"), lambda: pl.set_volume(pl.volume + 2), "Up")
        self._act(m, tr("Bajar volumen"), lambda: pl.set_volume(pl.volume - 2), "Down")
        m.addSeparator()
        self._act(m, tr("Saltar a archivo…"), self.show_jump_to_file, "J")
        self._act(m, tr("Buscar canciones en la biblioteca…"), self.show_search, "Ctrl+F")
        self._act(m, tr("Saltar a tiempo…"), self.show_jump_to_time, "Ctrl+J")
        self._act(m, tr("Información del archivo…"), self.show_file_info, "Alt+3")
        rm = m.addMenu(tr("Valorar canción actual"))
        cur = self.stats.rating((self.player.song or {}).get("file", ""))
        for n in range(5, -1, -1):
            self._act(rm, "★" * n if n else tr("Sin valoración"), lambda n=n: self.stats.rate_current(n),
                      f"Ctrl+Alt+{n}", checked=cur == n)
        return m

    def build_vis_menu(self, parent=None) -> QMenu:
        m = QMenu(tr("Visualización"), parent)
        cfg = self.cfg

        def setc(k, v):
            cfg[k] = v
            cfg.save()
            if k == "vis_fps":
                self.vis.configure()
            for p in self.panels():
                p.update()
        g = m.addMenu(tr("Modo"))
        for key, label in (("spectrum", tr("Analizador de espectro")), ("oscilloscope", tr("Osciloscopio")),
                           ("off", tr("Desactivado"))):
            self._act(g, label, lambda k=key: self.set_vis_mode(k), checked=cfg["vis_mode"] == key)
        a = m.addMenu(tr("Analizador"))
        for key, label in (("normal", tr("Estilo normal")), ("fire", tr("Estilo fuego")), ("line", tr("Estilo línea"))):
            self._act(a, label, lambda k=key: setc("vis_coloring", k), checked=cfg["vis_coloring"] == key)
        a.addSeparator()
        self._act(a, tr("Barras gruesas"), lambda: setc("vis_bands", "thick"), checked=cfg["vis_bands"] == "thick")
        self._act(a, tr("Barras finas"), lambda: setc("vis_bands", "thin"), checked=cfg["vis_bands"] == "thin")
        a.addSeparator()
        self._act(a, tr("Mostrar picos"), lambda: setc("vis_peaks", not cfg["vis_peaks"]), checked=cfg["vis_peaks"])
        o = m.addMenu(tr("Osciloscopio"))
        for key, label in (("dots", tr("Puntos")), ("lines", tr("Líneas")), ("solid", tr("Sólido"))):
            self._act(o, label, lambda k=key: setc("vis_osc_style", k), checked=cfg["vis_osc_style"] == key)
        names = [tr("Más lenta"), tr("Lenta"), tr("Moderada"), tr("Rápida"), tr("Más rápida")]
        f = m.addMenu(tr("Caída del analizador"))
        for i, n in enumerate(names):
            self._act(f, n, lambda i=i: setc("vis_falloff", i), checked=cfg["vis_falloff"] == i)
        f = m.addMenu(tr("Caída de los picos"))
        for i, n in enumerate(names):
            self._act(f, n, lambda i=i: setc("vis_peak_falloff", i), checked=cfg["vis_peak_falloff"] == i)
        self._act(m, tr("«Siguiente preset» al azar"), lambda: setc("vis_next_random", not cfg["vis_next_random"]),
                  checked=bool(cfg["vis_next_random"]))
        if self.modern is not None:
            slot = m.addMenu(tr("Pestaña de visualización del skin"))
            for key, label in (("spectrum", tr("Analizador de espectro")), ("milkdrop", "MilkDrop (projectM)")):
                self._act(slot, label, lambda k=key: self.set_modern_vis_slot(k),
                          checked=cfg["modern_vis_slot"] == key)
        self._act(m, tr("Configurar MilkDrop…"), self.show_milkdrop_config)
        self._act(m, tr("MilkDrop (projectM)…"), self.toggle_milkdrop, "Ctrl+Shift+K",
                  checked=bool(getattr(self, "milkdrop", None) and self.milkdrop.isVisible()))
        m.addSeparator()
        r = m.addMenu(tr("Fotogramas por segundo"))
        for fps in (20, 30, 50, 60, 70):
            self._act(r, str(fps), lambda v=fps: setc("vis_fps", v), checked=cfg["vis_fps"] == fps)
        src = m.addMenu(tr("Fuente de audio"))
        for key, label in (("auto", tr("Automática (fifo; PipeWire si el fifo lo usa otro programa)")),
                           ("fifo", tr("Salida fifo de MPD")), ("pipewire", tr("Captura de PipeWire"))):
            self._act(src, label, lambda k=key: self._set_vis_source(k), checked=cfg["vis_source"] == key)
        from .vis import PipeWireCapture
        r = self.vis.reader
        if r is not None:
            m.addSeparator()
            if isinstance(r, PipeWireCapture):
                users = ", ".join(sorted(set(self.vis.shared_with)))
                why = tr(" (el fifo lo usa {0})").format(users) if users else ""
                info = tr("Audio: captura de PipeWire") + why
            else:
                info = tr("Audio: {0}").format(r.path)
            a = m.addAction(info)
            a.setEnabled(False)
        if not self.vis.available:
            m.addSeparator()
            a = m.addAction(tr("Sin datos: añade una salida fifo en mpd.conf"))
            a.setEnabled(False)
        return m

    def set_modern_vis_slot(self, kind: str):
        """What fills the visualisation tab of modern skins (Bento…)."""
        self.cfg["modern_vis_slot"] = kind
        self.cfg.save()
        if self.modern is not None and self.modern.skin.path:
            self.load_skin(self.modern.skin.path, save=False)      # slots are built with the skin

    def _set_vis_source(self, key):
        self.cfg["vis_source"] = key
        self.cfg.save()
        self.vis.configure()

    def show_vis_menu(self, gp: QPoint):
        self._last_menu = self.build_vis_menu()
        self._last_menu.setPalette(getattr(self, "dialog_palette", self._last_menu.palette()))
        self._last_menu.popup(gp)

    def show_options_menu(self, gp: QPoint):
        self._last_menu = self.build_options_menu(None)
        self._last_menu.popup(gp)

    def build_mpd_menu(self, parent) -> QMenu:
        m = QMenu("MPD", parent)
        pl = self.player
        st = tr("conectado a ") if pl.connected else tr("sin conexión con ")
        a = m.addAction(st + pl.conn.addr.describe())
        a.setEnabled(False)
        self._act(m, tr("Actualizar base de datos"), lambda: pl.update_database(), enabled=pl.connected)
        om = m.addMenu(tr("Salidas de audio"))
        for o in pl.outputs():
            self._act(om, o.get("outputname", "?"), lambda i=o.get("outputid"): pl.toggle_output(i),
                      checked=o.get("outputenabled") == "1")
        m.addMenu(self.build_profiles_menu(m))
        self._act(m, tr("Conexión…"), self.show_preferences)
        return m

    # ------------------------------------------------------ smart lists
    def smart_lists(self) -> list[dict]:
        from .smartlist import clean_smart_lists
        return clean_smart_lists(self.cfg["smart_lists"])

    def save_smart_lists(self, lists: list[dict]):
        self.cfg["smart_lists"] = lists
        self.cfg.save()

    # -------------------------------------------------- server profiles
    def profiles(self) -> list[dict]:
        from .profiles import clean_profiles
        return clean_profiles(self.cfg["mpd_profiles"])

    def build_profiles_menu(self, parent) -> QMenu:
        m = QMenu(tr("Servidor"), parent)
        current = self.cfg["mpd_profile"] or ""
        # a connection typed by hand in Preferences is neither automatic nor a profile
        manual = bool(self.cfg["mpd_host"]) and not current
        self._act(m, tr("Automático (este equipo)"), lambda: self.use_profile(""),
                  checked=not current and not manual)
        for profile in self.profiles():
            self._act(m, profile["name"], lambda n=profile["name"]: self.use_profile(n),
                      checked=profile["name"] == current)
        m.addSeparator()
        self._act(m, tr("Guardar la conexión actual como perfil…"), self.save_profile)
        if current:
            self._act(m, tr("Quitar el perfil «{0}»").format(current), lambda: self.remove_profile(current))
        return m

    def use_profile(self, name: str):
        """Connect to a saved server ("" = the automatic local one)."""
        from .profiles import find_profile, profile_address
        profile = find_profile(self.profiles(), name) if name else None
        if name and profile is None:
            return
        cfg = self.cfg
        cfg["mpd_profile"] = profile["name"] if profile else ""
        cfg["mpd_host"] = profile["host"] if profile else ""
        cfg["mpd_port"] = profile["port"] if profile else 6600
        cfg["mpd_password"] = profile["password"] if profile else ""
        cfg.save()
        self.connect_to(profile_address(profile))

    def connect_to(self, addr):
        """Switch server: ratings and the search index belong to each server."""
        self.player.set_address(addr)
        QTimer.singleShot(1500, self.stats.load)
        QTimer.singleShot(2000, self.library_index.refresh)

    def save_profile(self):
        from .profiles import with_profile
        addr = self.player.conn.addr
        name, ok = QInputDialog.getText(None, tr("Guardar perfil"), tr("Nombre para {0}:").format(addr.describe()))
        name = name.strip()
        if not ok or not name:
            return
        self.cfg["mpd_profiles"] = with_profile(
            self.profiles(), {"name": name, "host": addr.host, "port": addr.port, "password": addr.password})
        self.cfg["mpd_profile"] = name
        self.cfg["mpd_host"], self.cfg["mpd_port"], self.cfg["mpd_password"] = addr.host, addr.port, addr.password
        self.cfg.save()

    def remove_profile(self, name: str):
        from .profiles import without_profile
        self.cfg["mpd_profiles"] = without_profile(self.profiles(), name)
        if self.cfg["mpd_profile"] == name:
            self.cfg["mpd_profile"] = ""        # stay connected; it is now a manual connection
        self.cfg.save()

    def show_playlist_context_menu(self, gp: QPoint):
        m = self._menu()
        pp = self.pl_panel
        rows = pp.selected_rows()
        self._act(m, tr("Reproducir"), pp.play_cursor, "Enter", enabled=bool(rows))
        self._act(m, tr("Información del archivo…"), self.show_file_info_selected, "Alt+3", enabled=bool(rows))
        m.addSeparator()
        self._act(m, tr("Quitar"), pp.remove_selected, "Del", enabled=bool(rows))
        self._act(m, tr("Recortar"), pp.crop_selected, "Shift+Del", enabled=bool(rows))
        self._act(m, tr("Vaciar lista"), self.clear_playlist, "Ctrl+Del")
        m.addSeparator()
        self._act(m, tr("Seleccionar todo"), pp.select_all, "Ctrl+A")
        self._act(m, tr("Invertir selección"), pp.invert_selection, "Ctrl+I")
        m.addSeparator()
        sub = m.addMenu(tr("Enviar a lista guardada"))
        for name in self.player.stored_playlists():
            self._act(sub, name, lambda n=name: self._send_to_playlist(n, rows))
        self._act(sub, tr("Nueva lista…"), lambda: self._send_to_new_playlist(rows))
        m.addMenu(self.build_sort_menu(m))
        self._last_menu = m
        m.popup(gp)

    def _send_to_playlist(self, name, rows):
        cmds = [("playlistadd", name, self.player.queue[r].get("file")) for r in rows]
        self.player.conn.batch(cmds)

    def _send_to_new_playlist(self, rows):
        name, ok = QInputDialog.getText(None, tr("Nueva lista guardada"), tr("Nombre:"))
        if ok and name.strip():
            self._send_to_playlist(name.strip(), rows)

    def build_sort_menu(self, parent) -> QMenu:
        m = QMenu(tr("Ordenar"), parent)
        pl = self.player

        def k_title(s):
            return song_title(s).lower()

        def k_file(s):
            return s.get("file", "").rsplit("/", 1)[-1].lower()

        def k_path(s):
            return s.get("file", "").lower()

        def k_album(s):
            def num(v):
                try:
                    return int(str(first(v)).split("/")[0])
                except ValueError:
                    return 0
            return (str(first(s.get("albumartist") or s.get("artist"))).lower(),
                    str(first(s.get("date"))), str(first(s.get("album"))).lower(),
                    num(s.get("disc")), num(s.get("track")))
        self._act(m, tr("Ordenar por título"), lambda: pl.sort_queue(k_title))
        self._act(m, tr("Ordenar por nombre de archivo"), lambda: pl.sort_queue(k_file))
        self._act(m, tr("Ordenar por ruta y archivo"), lambda: pl.sort_queue(k_path))
        self._act(m, tr("Ordenar por artista / álbum / pista"), lambda: pl.sort_queue(k_album))
        m.addSeparator()
        self._act(m, tr("Invertir lista"), pl.reverse_queue)
        self._act(m, tr("Mezclar lista"), pl.randomize)
        return m

    def show_sort_menu(self, gp):
        self._last_menu = self.build_sort_menu(None)
        self._last_menu.popup(gp)

    def show_remove_misc_menu(self, gp):
        m = self._menu()
        self._act(m, tr("Quitar duplicados"), self.remove_duplicates)
        self._act(m, tr("Quitar entradas que no existen"), self.remove_dead)
        self._last_menu = m
        m.popup(gp)

    def remove_duplicates(self):
        seen = set()
        dup = []
        for i, s in enumerate(self.player.queue):
            f = s.get("file")
            if f in seen:
                dup.append(i)
            seen.add(f)
        self.player.delete_positions(dup)

    def remove_dead(self):
        md = self.player.music_directory
        dead = []
        for i, s in enumerate(self.player.queue):
            f = s.get("file", "")
            if f.startswith("file://"):
                if not os.path.exists(f[7:]):
                    dead.append(i)
            elif "://" not in f and md and not os.path.exists(os.path.join(md, f)):
                dead.append(i)
        self.player.delete_positions(dead)

    def show_misc_options_menu(self, gp):
        m = self._menu()
        self._act(m, tr("Mostrar números de pista"), lambda: self._toggle_cfg("pl_show_numbers"),
                  checked=self.cfg["pl_show_numbers"])
        fm = m.addMenu(tr("Tamaño de letra"))
        for size in (8, 9, 10, 11, 12, 14):
            self._act(fm, f"{size} px", lambda s=size: self._set_cfg("pl_font_size", s),
                      checked=self.cfg["pl_font_size"] == size)
        self._act(m, tr("Seguir la canción actual"), lambda: self._toggle_cfg("pl_follow"),
                  checked=self.cfg.get("pl_follow", True))
        self._last_menu = m
        m.popup(gp)

    def _toggle_cfg(self, k):
        self.cfg[k] = not self.cfg.get(k, True)
        self.cfg.save()
        for p in self.panels():
            p.rebuild()
        self.relayout()

    def _set_cfg(self, k, v):
        self.cfg[k] = v
        self.cfg.save()
        for p in self.panels():
            p.rebuild()
        self.relayout()

    def show_eq_presets_menu(self, gp):
        m = self._menu()
        lm = m.addMenu(tr("Cargar"))
        for name, p in self.eq.builtin.items():
            self._act(lm, name, lambda p=p: self.eq.load_preset(p))
        if self.eq.user_presets:
            lm.addSeparator()
            for name, p in sorted(self.eq.user_presets.items()):
                self._act(lm, name, lambda p=p: self.eq.load_preset(p))
        lm.addSeparator()
        self._act(lm, tr("Desde archivo .eqf…"), self._import_eqf)
        self._act(lm, tr("Restablecer (plano)"), lambda: self.eq.load_preset({"bands": [0] * 10, "preamp": 0}))
        sm = m.addMenu(tr("Guardar"))
        self._act(sm, tr("Preajuste…"), self._save_eq_preset)
        self._act(sm, tr("A archivo .eqf…"), self._export_eqf)
        if self.eq.user_presets:
            dm = m.addMenu(tr("Borrar"))
            for name in sorted(self.eq.user_presets):
                self._act(dm, name, lambda n=name: self.eq.delete_preset(n))
        m.addSeparator()
        if self.pw is None:
            a = m.addAction(tr("Sin backend de PipeWire: el EQ no afecta al audio"))
            a.setEnabled(False)
        elif self.pw.status:
            a = m.addAction(self.pw.status)
            a.setEnabled(False)
        self._last_menu = m
        m.popup(gp)

    def _save_eq_preset(self):
        name, ok = QInputDialog.getText(None, tr("Guardar preajuste"), tr("Nombre:"))
        if ok and name.strip():
            self.eq.save_preset(name.strip())

    def _import_eqf(self):
        f, _ = QFileDialog.getOpenFileName(None, tr("Cargar preajustes"), os.path.expanduser("~"),
                                           tr("Preajustes de Winamp (*.eqf *.q1);;Todos (*)"))
        if f:
            try:
                n = self.eq.import_eqf(f)
                self.main_panel.set_temp_text(tr("{0} preajuste(s) importados").format(n))
            except (OSError, ValueError) as e:
                QMessageBox.warning(None, "Zebamp", str(e))

    def _export_eqf(self):
        f, _ = QFileDialog.getSaveFileName(None, tr("Guardar preajuste"), os.path.expanduser("~/zebamp.eqf"),
                                           tr("Preajuste de Winamp (*.eqf)"))
        if f:
            self.eq.export_eqf(f)


def auto_scale() -> int:
    """Integer zoom that keeps the 275 px wide skin proportionate."""
    scr = QGuiApplication.primaryScreen()
    if scr is None:
        return 1
    h = scr.geometry().height() * scr.devicePixelRatio()
    if h >= 2000:
        return 3
    if h >= 1000:
        return 2
    return 1


def _zip_is_modern(path: str) -> bool:
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = [n.lower() for n in z.namelist()]
    except (OSError, zipfile.BadZipFile):
        return False
    return any(n == "skin.xml" or n.endswith("/skin.xml") for n in names) and \
        not any(n.rsplit("/", 1)[-1] == "main.bmp" for n in names)


def _is_modern_dir(path: str) -> bool:
    return os.path.isdir(path) and os.path.exists(os.path.join(path, "skin.xml"))
