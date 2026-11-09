"""Runtime for modern skins: windows, actions, MAKI System object, timers."""
from __future__ import annotations

import logging
import math
import os
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QRegion
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

from ..player import first, fmt_time, song_title
from . import gui as G
from .maki import VM, MakiError, Program, class_name
from .skin import ModernSkin
from .xmlparse import Node

log = logging.getLogger(__name__)

PL_GUID = "45f3f7c1-a6f3-4ee6-a15e-125e92fc3f8d"
ML_GUID = "6b0edf80-c9a5-11d3-9f26-00c04f39ffc6"
EQ_GUID = "{fc3eaf78-c66e-4ed2-a0aa-1494dfcc13ff}"
AVS_GUID = "0000000a-000c-0010-ff7b-01014263450c"

TAGS = {
    "layer": G.Layer, "animatedlayer": G.AnimatedLayer, "button": G.Button,
    "togglebutton": G.ToggleButton, "nstatesbutton": G.NStatesButton,
    "text": G.Text, "slider": G.Slider, "status": G.Status, "vis": G.Vis,
    "eqvis": G.EqVis,
}


def _late_tags():
    TAGS["songticker"] = G.SongTicker
    TAGS["menu"] = G.MenuObj
    TAGS["grid"] = G.Grid
    TAGS["progressgrid"] = G.ProgressGrid
    TAGS["rect"] = G.RectObj


XUI_ALIASES = {
    "wasabi:standardframe:status": "wasabi.standardframe.statusbar",
    "wasabi:standardframe:nostatus": "wasabi.standardframe.nostatusbar",
    "wasabi:standardframe:modal": "wasabi.standardframe.modal",
    "wasabi:standardframe:static": "wasabi.standardframe.static",
    "wasabi:titlebar": "wasabi.titlebar",
}
GUI_PARAMS = {"id", "x", "y", "w", "h", "relatx", "relaty", "relatw", "relath", "visible",
              "alpha", "ghost", "tooltip", "move", "fitparent", "sysregion"}


def _n(tag, **attrs) -> Node:
    return Node(tag, {k.lower(): str(v) for k, v in attrs.items()})


def builtin_frame(kind: str, inst: Node) -> Node:
    """Minimal stand-in for Winamp's built-in Wasabi standard frame."""
    status = kind.endswith("statusbar") and "nostatus" not in kind
    bottom = 19 if status else 5
    g = Node("groupdef", {"id": kind, "background": "wasabi.frame.basetexture"})
    ch = g.children
    ch += [
        _n("layer", id="window.top.left", x=0, y=0, image="wasabi.frame.top.left", resize="topleft"),
        _n("layer", id="window.top", x=15, y=0, w=-30, relatw=1, image="wasabi.frame.top", resize="top"),
        _n("layer", id="window.top.right", x=-15, relatx=1, y=0, image="wasabi.frame.top.right", resize="topright"),
        _n("layer", id="window.left", x=0, y=15, h=-15 - bottom, relath=1, image="wasabi.frame.left", resize="left"),
        _n("layer", id="window.right", x=-5, relatx=1, y=15, h=-15 - bottom, relath=1,
           image="wasabi.frame.right", resize="right"),
        _n("layer", id="window.bottom.left", x=0, y=-bottom, relaty=1, image="wasabi.frame.bottom.left",
           resize="bottomleft"),
        _n("layer", id="window.bottom", x=15, y=-bottom, relaty=1, w=-30, relatw=1, image="wasabi.frame.bottom",
           resize="bottom"),
        _n("layer", id="window.bottom.right", x=-15, relatx=1, y=-bottom, relaty=1,
           image="wasabi.frame.bottom.right", resize="bottomright"),
        _n("wasabi:titlebar", id="wasabi.titlebar", x=22, y=2, w=-42, relatw=1, h=11),
        _n("button", id="controlmenu", action="controlmenu", x=5, y=3, image="wasabi.button.sysmenu",
           downimage="wasabi.button.sysmenu.pressed", tooltip="Menú"),
        _n("button", id="Close", action="CLOSE", x=-18, relatx=1, y=3, image="wasabi.button.close",
           downimage="wasabi.button.close.pressed", tooltip="Cerrar"),
    ]
    content = inst.get("content")
    if content:
        ch.append(_n("group", id=content, x=5, y=15, w=-10, h=-15 - bottom, relatw=1, relath=1))
    return g


def builtin_split_frame(inst: Node) -> Node:
    """<Wasabi:Frame left=.. right=..>: two groups split by a divider."""
    vertical = (inst.get("orientation") or "v").lower().startswith("v")
    size = int(float(inst.get("width") or inst.get("height") or 200))
    gap = 8
    g = Node("groupdef", {"id": "wasabi.frame." + (inst.get("id") or "split")})
    left, right = inst.get("left") or inst.get("top"), inst.get("right") or inst.get("bottom")
    from_right = (inst.get("from") or "l").lower().startswith(("r", "b"))
    if vertical and from_right:
        # width belongs to the right-hand pane
        if left:
            g.children.append(_n("group", id=left, x=0, y=0, w=-(size + gap), relatw=1, h=0, relath=1))
        if right:
            g.children.append(_n("group", id=right, x=-size, relatx=1, y=0, w=size, h=0, relath=1))
    elif vertical:
        if left:
            g.children.append(_n("group", id=left, x=0, y=0, w=size, h=0, relath=1))
        if right:
            g.children.append(_n("group", id=right, x=size + gap, y=0, w=-(size + gap), relatw=1, h=0, relath=1))
    else:
        if left:
            g.children.append(_n("group", id=left, x=0, y=0, w=0, relatw=1, h=size))
        if right:
            g.children.append(_n("group", id=right, x=0, y=size + gap, w=0, relatw=1, h=-(size + gap), relath=1))
    return g


def builtin_titlebar(inst: Node) -> Node:
    g = Node("groupdef", {"id": "wasabi.titlebar"})
    g.children += [
        _n("layer", id="titlebar.left", x=0, y=0, image="wasabi.titlebar.left.active"),
        _n("layer", id="titlebar.center", x=4, y=0, w=-8, relatw=1, h=0, relath=1,
           image="wasabi.titlebar.center.active"),
        _n("layer", id="titlebar.right", x=-4, relatx=1, y=0, image="wasabi.titlebar.right.active"),
        _n("text", id="window.titlebar.title", x=0, y=0, w=0, h=0, relatw=1, relath=1,
           display="windowtitle", align="center", color="wasabi.titlebar", fontsize=10),
        _n("layer", id="mousetrap", x=0, y=0, w=0, h=0, relatw=1, relath=1, move=1,
           dblclickaction="SWITCH;shade"),
    ]
    return g


def _band(action: str, param) -> int:
    """EQ slider target: 0..9 for bands, -1 for the preamp."""
    if action == "eq_preamp" or str(param or "").strip().lower() in ("preamp", "pre", "0p"):
        return -1
    try:
        b = int(float(str(param).strip())) - 1
    except ValueError:
        return -1
    return max(0, min(9, b))


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes")


def _norm_guid(s: str) -> str:
    s = (s or "").strip()
    if s.lower().startswith("guid:"):
        s = s[5:]
    return s.strip().strip("{}").lower()


# =================================================================== window
class ModernDock(QWidget):
    """One frameless window holding every visible container, docked edge to
    edge like Winamp arranges them on Windows (Wayland cannot place separate
    windows next to each other)."""

    def __init__(self, engine: ModernEngine):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.engine = engine
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Zebamp")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self._pending = False
        # free: a transparent canvas the size of the desktop; containers move
        # freely inside it and snap to each other (input only where they are)
        self.free = engine.app.cfg["modern_layout"] == "free"
        self.pos: dict[str, QPoint] = {}
        self._drag = None
        self._fit_done = False
        if self.free:
            scr = QGuiApplication.primaryScreen()
            g = scr.availableGeometry() if scr is not None else QRect(0, 0, 1280, 800)
            self.setFixedSize(g.width(), g.height())
            saved = (engine.app.cfg["modern_positions"] or {}).get(engine.skin.path or "", {})
            self._saved_origin = None
            for cid, xy in saved.items():
                try:
                    if cid == "_origin":
                        self._saved_origin = (int(xy[0]), int(xy[1]))
                    else:
                        self.pos[cid] = QPoint(int(xy[0]), int(xy[1]))
                except (TypeError, ValueError, IndexError):
                    pass

    # ------------------------------------------------------------ free mode
    SNAP_PX = 14      # device pixels: how close edges must be to pull together

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.free:
            wh = self.windowHandle()
            if wh is not None and not getattr(self, "_screen_hooked", False):
                self._screen_hooked = True
                wh.screenChanged.connect(lambda *_: QTimer.singleShot(200, self.fit_canvas))
            QTimer.singleShot(120, self.fit_canvas)

    def _canvas_l(self) -> QRect:
        s = self.engine.scale
        return QRect(0, 0, int(self.width() / s), int(self.height() / s))

    def fit_canvas(self, span_all=False):
        """Cover the monitor(s) holding the skin windows (all monitors while
        a window is being dragged, so it can cross to the other screen)."""
        if not self.free or not self.isVisible():
            return
        if self._drag is not None and not span_all:
            return          # never resize under a drag (screenChanged etc.); end_drag refits
        from ..canvas import home_monitors, place_canvas, workspace_rects
        rects = workspace_rects()
        if not rects:
            return
        focus_origin = (rects[0].x(), rects[0].y())
        cur = getattr(self, "origin", None) or self._saved_origin or focus_origin
        s = self.engine.scale
        glob = []
        for c in self._shown():
            p = self.pos.get(c.id)
            if p is not None:
                r = self.solid_of(c, p.x(), p.y())
                glob.append(QRect(round(cur[0] + r.x() * s), round(cur[1] + r.y() * s),
                                  round(r.width() * s), round(r.height() * s)))
        chosen = rects if span_all else home_monitors(rects, glob)
        _w, _h, screens, origin = place_canvas(self, chosen)
        self.screens = screens
        self._all_screens = [r.translated(-origin[0], -origin[1]) for r in rects]
        self._rebase(origin, focus_origin)
        self._fit_done = True
        self.relayout()

    def _rebase(self, origin, focus_origin):
        """Saved positions are relative to the canvas origin at save time;
        convert them when the canvas now starts elsewhere (e.g. it grew to
        cover both monitors).  Older saves without an origin were relative to
        the workspace the canvas used to cover (the focused one)."""
        s = self.engine.scale
        old = (getattr(self, "origin", None) and tuple(self.origin)) or self._saved_origin or focus_origin
        self.origin = origin
        dx, dy = round((old[0] - origin[0]) / s), round((old[1] - origin[1]) / s)
        self._saved_origin = origin
        self._rebase_delta = (old[0] - origin[0], old[1] - origin[1])   # device px
        if (dx or dy) and self.pos:
            for k, v in list(self.pos.items()):
                self.pos[k] = QPoint(v.x() + dx, v.y() + dy)
            if self._drag is not None:
                st, group, sp = self._drag
                sx, sy = old[0] - origin[0], old[1] - origin[1]
                self._drag = (QPointF(st.x() + sx, st.y() + sy), group,
                              {k: QPoint(v.x() + dx, v.y() + dy) for k, v in sp.items()})
                fr = getattr(self, "_dframe", None)
                if fr is not None:
                    fr.shift(sx, sy)
            if hasattr(self, "_last_solid"):
                del self._last_solid

    def _screens_l(self) -> list:
        s = self.engine.scale
        scr = getattr(self, "screens", None) or [QRect(0, 0, self.width(), self.height())]
        return [QRect(int(r.x() / s), int(r.y() / s), int(r.width() / s), int(r.height() / s)) for r in scr]

    def _sway_fit(self):
        import json
        import subprocess
        try:
            tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True,
                                             text=True, timeout=2).stdout or "{}")
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        me, title = os.getpid(), self.windowTitle()
        found = []

        def walk(n, ws):
            if n.get("type") == "workspace":
                ws = n
            if n.get("pid") == me and n.get("name") == title and n.get("type") == "floating_con":
                found.append((n, ws))
            for ch in n.get("nodes", []) + n.get("floating_nodes", []):
                walk(ch, ws)
        walk(tree, None)
        if not found or found[0][1] is None:
            return None
        node, ws = found[0]
        r = ws["rect"]
        w, h = int(r["width"]), int(r["height"])
        if (node["rect"]["x"], node["rect"]["y"]) != (r["x"], r["y"]):
            subprocess.run(["swaymsg", f"[con_id={node['id']}] move absolute position {r['x']} {r['y']}"],
                           capture_output=True, timeout=2)
        return w, h

    def _relayout_free(self):
        s = self.engine.scale
        shown = self._shown()
        if not shown:
            self.hide()
            return
        missing = [c for c in shown if c.id not in self.pos]
        if missing:
            placed = self._arrange(shown)
            # keep containers that already have a place where they are; put the
            # rest in Winamp's default arrangement, centred near the top
            known = {c.id for c in shown if c.id in self.pos}
            if not known:
                bb = placed[0][1]
                for _c, f, _s in placed:
                    bb = bb.united(f)
                cv = self._screens_l()[0]
                ox = cv.x() + max(0, (cv.width() - bb.width()) // 2) - bb.x()
                oy = cv.y() + max(0, min(80, cv.height() - bb.height())) - bb.y()
                for c, f, _s in placed:
                    self.pos[c.id] = QPoint(f.x() + ox, f.y() + oy)
            else:
                anchor = next(c for c in shown if c.id in known)
                af = next(f for c, f, _s in placed if c is anchor)
                base = self.pos[anchor.id] - af.topLeft()
                for c, f, _s in placed:
                    if c.id not in self.pos:
                        self.pos[c.id] = f.topLeft() + base
        self._follow_bottom_edges(shown)
        from ..canvas import keep_on_screens
        screens = self._screens_l()
        for c in shown:
            lay = c.current
            p = self.pos[c.id]
            # keep every window reachable on some monitor
            dx, dy = keep_on_screens(self.solid_of(c, p.x(), p.y()), screens)
            x, y = p.x() + dx, p.y() + dy
            self.pos[c.id] = QPoint(x, y)
            c.window.setGeometry(round(x * s), round(y * s), max(1, round(lay.rect.width() * s)),
                                 max(1, round(lay.rect.height() * s)))
        self._update_mask()

    def _follow_bottom_edges(self, shown):
        """Like Winamp: when a window's solid bottom moves (Winamp Modern's EQ
        drawer opening/closing), windows docked under it move with it."""
        last = getattr(self, "_last_solid", None)
        if last is None:
            # first layout: windows saved against an open drawer's edge while
            # it is now closed come back up against the window's solid edge
            for c in shown:
                if c.id not in self.pos:
                    continue
                b = c.current.snap_adjust[3]
                if not b:
                    continue
                full_bottom = self.pos[c.id].y() + c.current.rect.height()
                for o in shown:
                    if o is c or o.id not in self.pos:
                        continue
                    if abs(self.pos[o.id].y() - full_bottom) <= 1:
                        p = self.pos[o.id]
                        self.pos[o.id] = QPoint(p.x(), p.y() - b)
            last = {}
        cur = {c.id: self.solid_of(c, self.pos[c.id].x(), self.pos[c.id].y())
               for c in shown if c.id in self.pos}
        moved = set()
        for cid, r in cur.items():
            old = last.get(cid)
            if old is None or old.x() != r.x() or old.y() != r.y():
                continue          # the window itself moved: nothing to follow
            delta = (r.y() + r.height()) - (old.y() + old.height())
            if not delta:
                continue
            ob = old.y() + old.height()
            todo = [(c2, cur[c2]) for c2 in cur if c2 != cid and c2 not in moved
                    and abs(cur[c2].y() - ob) <= 1
                    and cur[c2].x() < old.x() + old.width() and old.x() < cur[c2].x() + cur[c2].width()]
            while todo:
                c2, r2 = todo.pop()
                if c2 in moved:
                    continue
                moved.add(c2)
                p = self.pos[c2]
                self.pos[c2] = QPoint(p.x(), p.y() + delta)
                b2 = r2.y() + r2.height()
                todo += [(c3, cur[c3]) for c3 in cur if c3 not in moved and c3 not in (cid, c2)
                         and abs(cur[c3].y() - b2) <= 1
                         and cur[c3].x() < r2.x() + r2.width() and r2.x() < cur[c3].x() + cur[c3].width()]
        self._last_solid = {c.id: self.solid_of(c, self.pos[c.id].x(), self.pos[c.id].y())
                            for c in shown if c.id in self.pos}
        if moved:
            self.save_positions()

    def _update_mask(self):
        from PySide6.QtGui import QRegion
        s = self.engine.scale
        reg = QRegion()
        for c in self._shown():
            p = self.pos.get(c.id)
            if p is None:
                continue
            r = self.solid_of(c, p.x(), p.y())
            reg = reg.united(QRegion(round(r.x() * s), round(r.y() * s),
                                     max(1, round(r.width() * s)), max(1, round(r.height() * s))))
        wh = self.windowHandle()
        if wh is not None:
            # input region only: clicks elsewhere reach the windows underneath
            wh.setMask(reg)

    def _touching(self, a: QRect, b: QRect) -> bool:
        ar, br = a.x() + a.width(), b.x() + b.width()
        ab, bb = a.y() + a.height(), b.y() + b.height()
        v_overlap = a.y() < bb and b.y() < ab
        h_overlap = a.x() < br and b.x() < ar
        return (v_overlap and (abs(ar - b.x()) <= 1 or abs(br - a.x()) <= 1)) or \
            (h_overlap and (abs(ab - b.y()) <= 1 or abs(bb - a.y()) <= 1))

    def _cluster(self, start) -> list:
        shown = self._shown()
        rects = {c.id: self.solid_of(c, self.pos[c.id].x(), self.pos[c.id].y())
                 for c in shown if c.id in self.pos}
        group, todo = [start], [start]
        while todo:
            c = todo.pop()
            for o in shown:
                if o not in group and o.id in rects and self._touching(rects[c.id], rects[o.id]):
                    group.append(o)
                    todo.append(o)
        return group

    def begin_drag(self, win, scene_pt):
        c = win.container
        main = self.engine.main_container()
        # like Winamp: the main window drags what is docked to it; any other
        # window comes loose and moves alone
        group = self._cluster(c) if c is main else [c]
        self._drag = (scene_pt, group, {g.id: QPoint(self.pos[g.id]) for g in group})
        from ..canvas import DragFrame
        self._dframe = DragFrame(QPointF(scene_pt))
        win.raise_()

    def drag_to(self, scene_pt):
        if self._drag is None:
            return None
        fr = getattr(self, "_dframe", None)
        if fr is not None:
            raw = QPointF(scene_pt)
            scene_pt = fr.fix(raw)
            if not fr.moved:
                return None                          # a click is not a drag
        start, group, start_pos = self._drag
        s = self.engine.scale
        dx = (scene_pt.x() - start.x()) / s
        dy = (scene_pt.y() - start.y()) / s
        ids = {g.id for g in group}
        moving = [self.solid_of(g, start_pos[g.id].x() + dx, start_pos[g.id].y() + dy) for g in group]
        if fr is not None and not fr.spanned and len(getattr(self, "_all_screens", []) or []) > 1:
            from ..canvas import reaches_other_monitor
            dev = [QRect(round(r.x() * s), round(r.y() * s), round(r.width() * s), round(r.height() * s))
                   for r in moving]
            if reaches_other_monitor(dev, QRect(0, 0, self.width(), self.height()), self._all_screens):
                # only now, because the user is taking it there: open the way
                fr.spanned = True
                self.fit_canvas(span_all=True)
                return self.drag_to(raw)
        static = [self.solid_of(c, self.pos[c.id].x(), self.pos[c.id].y())
                  for c in self._shown() if c.id not in ids and c.id in self.pos]
        snap = self.SNAP_PX / s
        from ..canvas import snap_offsets
        best_x, best_y = snap_offsets(moving, static, self._screens_l(), snap)
        dx += best_x or 0
        dy += best_y or 0
        for g in group:
            p = start_pos[g.id]
            self.pos[g.id] = QPoint(round(p.x() + dx), round(p.y() + dy))
            if hasattr(self, "_last_solid"):
                self._last_solid[g.id] = self.solid_of(g, self.pos[g.id].x(), self.pos[g.id].y())
            g.window.move(round(self.pos[g.id].x() * s), round(self.pos[g.id].y() * s))
        self._update_mask()

    def end_drag(self):
        if self._drag is None:
            return
        _start, group, _sp = self._drag
        self._drag = None
        fr = getattr(self, "_dframe", None)
        self._dframe = None
        if fr is not None and not fr.moved:
            return                              # just a click
        # dropped into a gap between monitors: pull the group back on screen
        from ..canvas import fit_group, keep_on_screens
        screens = self._screens_l()
        rects = [self.solid_of(g, self.pos[g.id].x(), self.pos[g.id].y()) for g in group]
        bb = rects[0]
        for r in rects[1:]:
            bb = bb.united(r)
        dx, dy = (0, 0)
        if any(keep_on_screens(r, screens) != (0, 0) for r in rects):
            # part of the group fell off every monitor: move the group as one
            dx, dy = fit_group(bb, screens)
        if dx or dy:
            for g in group:
                p = self.pos[g.id]
                self.pos[g.id] = QPoint(p.x() + dx, p.y() + dy)
            self.relayout()
        if fr is not None and fr.spanned:
            self.fit_canvas()                   # back to the monitor(s) it is on
        self.save_positions()

    def save_positions(self):
        if not self.free:
            return
        cfg = self.engine.app.cfg
        allpos = dict(cfg["modern_positions"] or {})
        data = {k: [v.x(), v.y()] for k, v in self.pos.items()}
        origin = getattr(self, "origin", None)
        if origin is not None:
            data["_origin"] = [origin[0], origin[1]]
        allpos[self.engine.skin.path or ""] = data
        cfg["modern_positions"] = allpos
        cfg.save()

    def schedule(self):
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.relayout)

    # ------------------------------------------------------------ common
    def _shown(self):
        eng = self.engine
        shown = [c for c in eng.containers if c.visible and c.window is not None
                 and c.window.parent() is self and c.current is not None]
        main = eng.main_container()
        shown.sort(key=lambda c: (c is not main,))
        return shown

    @staticmethod
    def solid_of(c, x, y) -> QRect:
        lay = c.current
        l_, t_, r_, b_ = lay.snap_adjust
        w, h = lay.rect.width(), lay.rect.height()
        return QRect(int(x) + l_, int(y) + t_, max(1, w - l_ - r_), max(1, h - t_ - b_))

    def relayout(self):
        self._pending = False
        if self.free:
            self._relayout_free()
        else:
            self._relayout_fixed()

    def _arrange(self, shown):
        """Winamp's default arrangement: [(container, full rect, solid rect)]."""
        eng = self.engine
        main = eng.main_container()
        placed: list[tuple[G.Container, QRect, QRect]] = []   # (c, full, solid)
        solid_of = self.solid_of

        def free(r):
            return all(not r.intersects(sr) for _c, _f, sr in placed)

        for c in shown:
            lay = c.current
            node = c.node
            dx, dy = node.get("default_x"), node.get("default_y")
            if c is main or not placed:
                x, y = 0, 0
            elif dx not in (None, "") or dy not in (None, ""):
                x, y = G._i(dx, 0), G._i(dy, 0)
                # Re-anchor to the edges actually used (main may be shaded or wider).
                m_solid = placed[0][2]
                if x >= m_solid.width() - 2 and y < m_solid.height():
                    x = m_solid.right() + 1
                    y = m_solid.top()
                elif y >= m_solid.height() - 2 and x < m_solid.width():
                    y = m_solid.bottom() + 1
            else:
                x, y = None, None
            if x is None or not free(solid_of(c, x, y)):
                cands = []
                for _c, _f, sr in placed:
                    cands += [(sr.right() + 1, sr.top()), (sr.left(), sr.bottom() + 1)]
                best = None
                for cx, cy in cands:
                    r = solid_of(c, cx, cy)
                    if not free(r):
                        continue
                    bb = r
                    for _c, f, _s in placed:
                        bb = bb.united(f)
                    score = (bb.width() * bb.height(), cy, cx)
                    if best is None or score < best[0]:
                        best = (score, cx, cy)
                x, y = (best[1], best[2]) if best else (0, sum(f.height() for _c, f, _s in placed))
            full = QRect(x, y, lay.rect.width(), lay.rect.height())
            placed.append((c, full, solid_of(c, x, y)))
        return placed

    def _relayout_fixed(self):
        s = self.engine.scale
        placed = self._arrange(self._shown())
        if not placed:
            self.hide()
            return
        bb = placed[0][1]
        for _c, f, _s in placed:
            bb = bb.united(f)
        ox, oy = -bb.x(), -bb.y()
        for c, f, _s in placed:
            w = c.window
            w.setGeometry(round((f.x() + ox) * s), round((f.y() + oy) * s),
                          max(1, round(f.width() * s)), max(1, round(f.height() * s)))
        # main on top so its drawer slides over the windows docked below it
        for c, _f, _s in reversed(placed):
            c.window.raise_()
        if placed[0][0].window is not None:
            placed[0][0].window.raise_()
        self.setFixedSize(max(1, round(bb.width() * s)), max(1, round(bb.height() * s)))
        self.update()

    def keyPressEvent(self, ev):
        if not self.engine.app.handle_key(ev):
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        ev.ignore()
        self.engine.app.request_close()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.engine.app.player.add_paths(paths)

    def mousePressEvent(self, ev):
        # empty space between docked windows: drag the whole thing
        if not self.free and ev.button() == Qt.MouseButton.LeftButton and self.windowHandle() is not None:
            self.windowHandle().startSystemMove()


class ModernWindow(QWidget):
    def __init__(self, engine: ModernEngine, container: G.Container, dock: ModernDock | None = None):
        if dock is not None:
            super().__init__(dock)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        else:
            super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dock = dock
        self.engine = engine
        self.container = container
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(f"{container.name} - Zebamp")
        self._grab: G.GuiObj | None = None
        self._hover: G.GuiObj | None = None
        self._resize = None
        self._fwd: QWidget | None = None
        self._fwd_hover: QWidget | None = None
        self._dragging = False
        self.setAcceptDrops(True)
        self.sync_size()

    @property
    def layout(self) -> G.Layout | None:
        return self.container.current

    @property
    def scale(self) -> float:
        return self.engine.scale

    def sync_size(self):
        lay = self.layout
        if lay is None:
            return
        s = self.scale
        w, h = max(1, round(lay.rect.width() * s)), max(1, round(lay.rect.height() * s))
        if self.dock is not None:
            if (self.width(), self.height()) != (w, h):
                self.resize(w, h)
            self.dock.schedule()
        else:
            self.setFixedSize(w, h)
        self.update()

    def to_l(self, pos) -> QPoint:
        s = self.scale
        return QPoint(int(math.floor(pos.x() / s)), int(math.floor(pos.y() / s)))

    def _dock_pt(self, ev):
        # position in the canvas: stable while this child moves under the mouse
        return self.mapTo(self.dock, ev.position().toPoint()).toPointF()

    def start_move(self, ev=None):
        if self.dock is not None and self.dock.free and ev is not None:
            self._dragging = True
            self.dock.begin_drag(self, self._dock_pt(ev))
            return
        top = self.window()
        wh = top.windowHandle() if top is not None else None
        if wh is not None:
            wh.startSystemMove()

    def paintEvent(self, ev):
        lay = self.layout
        if lay is None:
            return
        p = QPainter(self)
        s = self.scale
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, s != int(s) or s < 1 or
                        self.engine.app.cfg["modern_smooth"])
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self.dock is None:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(ev.rect(), Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.scale(s, s)
        # clip to the exact damaged region (not its bounding box): a vis
        # frame and the clock far apart must not repaint everything between
        clip = QRegion()
        for r in ev.region():
            clip += QRect(int(r.x() / s) - 1, int(r.y() / s) - 1,
                          int(r.width() / s) + 3, int(r.height() / s) + 3)
        self.engine._clip = clip
        try:
            lay.paint(p)
        except Exception:
            log.exception("modern paint failed")
        finally:
            self.engine._clip = None
        p.end()
        self.sync_hosts()

    def sync_hosts(self):
        """Place/show embedded Qt widgets (media library) over their slots."""
        lay = self.layout
        hosts = []
        for c_lay in self.container.layouts:
            hosts += getattr(c_lay, "_hosts", None) if getattr(c_lay, "_hosts", None) is not None else \
                c_lay.__dict__.setdefault("_hosts", [o for o in c_lay.walk() if isinstance(o, G.WidgetHost)])
        s = self.scale
        for h in hosts:
            on = h.layout_obj() is lay and h.shown() and h.rect.width() > 20 and h.rect.height() > 20
            if on and h.widget is None:
                from ..ui.library import LibraryWindow
                h.widget = LibraryWindow(self.engine.app, embedded_in=self)
            if h.widget is None:
                continue
            if on:
                r = h.rect
                g = QRect(round(r.x() * s), round(r.y() * s), round(r.width() * s), round(r.height() * s))
                if h.widget.geometry() != g:
                    h.widget.setGeometry(g)
                if not h.widget.isVisible():
                    h.widget.show()
                    h.widget.raise_()
            elif h.widget.isVisible():
                h.widget.hide()

    # ------------------------------------------------- docked pass-through
    def opaque_at(self, pt: QPoint) -> bool:
        """True if the layout draws something at logical point `pt`."""
        lay = self.layout
        if lay is None or not lay.rect.contains(pt):
            return False
        from PySide6.QtGui import QImage, qAlpha
        img = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.translate(-pt.x(), -pt.y())
        old = self.engine._clip
        self.engine._clip = QRect(pt.x() - 1, pt.y() - 1, 3, 3)
        try:
            lay.paint(p)
        except Exception:
            pass
        finally:
            self.engine._clip = old
            p.end()
        return qAlpha(img.pixel(0, 0)) > 8

    def _below(self, ev) -> QWidget | None:
        if self.dock is None:
            return None
        gp = ev.globalPosition().toPoint()
        for w in reversed(self.dock.children()):
            if w is self or not isinstance(w, ModernWindow) or not w.isVisible():
                continue
            if w.geometry().contains(self.dock.mapFromGlobal(gp)):
                return w
        return None

    def _forward(self, target, ev, kind):
        from PySide6.QtGui import QMouseEvent
        gp = ev.globalPosition()
        lp = target.mapFromGlobal(gp.toPoint())
        e2 = QMouseEvent(ev.type(), lp.toPointF() if hasattr(lp, "toPointF") else lp, gp,
                         ev.button(), ev.buttons(), ev.modifiers())
        getattr(target, kind)(e2)

    def _passthrough(self, ev) -> QWidget | None:
        """Docked windows let clicks through their transparent areas."""
        if self.dock is None:
            return None
        pt = self.to_l(ev.position())
        lay = self.layout
        if lay is not None and lay.rect.contains(pt):
            o = lay.hit(pt)
            # invisible buttons (tab mousetraps, hotspots) still own the click
            if o is not None and o is not lay and (isinstance(o, (G.Button, G.Slider, G.PlaylistView))
                                                  or getattr(o, "interactive", False)):
                return None
        if self.opaque_at(pt):
            return None
        return self._below(ev) or self.dock

    # ----------------------------------------------------------- mouse
    def mousePressEvent(self, ev):
        lay = self.layout
        if lay is None:
            return
        t = self._passthrough(ev)
        if t is not None:
            self._fwd = t
            self._forward(t, ev, "mousePressEvent")
            return
        self._fwd = None
        if self.dock is not None and self.dock.free:
            self.raise_()
        pt = self.to_l(ev.position())
        self.engine.last_mouse = (lay, pt)
        obj = lay.hit(pt) or lay
        eng = self.engine
        if ev.button() == Qt.MouseButton.RightButton:
            if eng.vm.dispatch(obj, "onrightbuttondown", [("INT", pt.x()), ("INT", pt.y())]) == 0:
                eng.app.show_main_menu(ev.globalPosition().toPoint())
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._grab = obj
        handled = eng.vm.dispatch(obj, "onleftbuttondown", [("INT", pt.x()), ("INT", pt.y())])
        if isinstance(obj, G.Slider):
            obj.press_at(pt)
            return
        if isinstance(obj, G.MenuObj):
            obj.click()
            self._grab = None
            return
        if isinstance(obj, G.Button):
            obj.pressed = True
            obj.update()
            return
        if isinstance(obj, G.PlaylistView):
            obj.click_at(pt)
            return
        rz = (obj.p("resize") or "").lower() if isinstance(obj, G.GuiObj) else ""
        if rz:
            self._resize = (rz, ev.globalPosition().toPoint(), lay.rect.width(), lay.rect.height())
            return
        explicit_move = str(obj.p("move") or "").strip() == "1"
        if explicit_move or (not handled and not eng.has_handler(obj, ("onmousemove", "onleftbuttonup"))
                             and str(obj.p("move", "1")) != "0"):
            self._grab = None
            self.start_move(ev)

    def mouseMoveEvent(self, ev):
        lay = self.layout
        if lay is None:
            return
        if self._fwd is not None:
            self._forward(self._fwd, ev, "mouseMoveEvent")
            return
        if self._dragging:
            self.dock.drag_to(self._dock_pt(ev))
            return
        if self.dock is not None and self._grab is None and not self._resize \
                and ev.buttons() == Qt.MouseButton.NoButton:
            t = self._passthrough(ev)
            if t is not None and t is not self.dock:
                self._fwd_hover = t
                self._forward(t, ev, "mouseMoveEvent")
                self._set_hover(None)
                return
            if self._fwd_hover is not None:
                self._fwd_hover._set_hover(None)
                self._fwd_hover = None
            if t is self.dock:
                self._set_hover(None)
                return
        pt = self.to_l(ev.position())
        if self._resize:
            mode, start, w0, h0 = self._resize
            d = ev.globalPosition().toPoint() - start
            s = self.scale
            w = w0 + (int(d.x() / s) if "right" in mode or mode == "1" else 0)
            h = h0 + (int(d.y() / s) if "bottom" in mode or mode == "1" else 0)
            lay.set_size(w, h)
            self.engine.layout_resized(lay)
            return
        g = self._grab
        if g is not None:
            self.engine.vm.dispatch(g, "onmousemove", [("INT", pt.x()), ("INT", pt.y())])
            if isinstance(g, G.Slider):
                g.drag_to(pt)
            elif isinstance(g, G.Button):
                inside = g.rect.contains(pt)
                if inside != g.pressed:
                    g.pressed = inside
                    g.update()
            return
        self.engine.last_mouse = (lay, pt)
        obj = lay.hit(pt)
        self._set_hover(obj)
        if self._hover is not None and self.engine.has_handler(self._hover, ("onmousemove",)):
            self.engine.vm.dispatch(self._hover, "onmousemove", [("INT", pt.x()), ("INT", pt.y())])

    def leaveEvent(self, ev):
        self._set_hover(None)
        if self._fwd_hover is not None:
            self._fwd_hover._set_hover(None)
            self._fwd_hover = None

    def _set_hover(self, obj):
        if obj is not self._hover:
            old = self._hover
            self._hover = obj
            if isinstance(old, G.MenuObj):
                old.on_hover(False)
            if isinstance(obj, G.MenuObj):
                obj.on_hover(True)
            if old is not None:
                old.hover = False
                self.engine.vm.dispatch(old, "onleavearea")
                old.update()
            if obj is not None:
                obj.hover = True
                self.engine.vm.dispatch(obj, "onenterarea")
                tip = obj.p("tooltip") if isinstance(obj, G.GuiObj) else None
                self.setToolTip(tip or "")
                obj.update()

    def mouseReleaseEvent(self, ev):
        if self._dragging:
            self._dragging = False
            self.dock.end_drag()
            return
        if self._fwd is not None:
            t, self._fwd = self._fwd, None
            self._forward(t, ev, "mouseReleaseEvent")
            return
        pt = self.to_l(ev.position())
        if self.layout is not None:
            self.engine.last_mouse = (self.layout, pt)
        if self._resize:
            self._resize = None
            return
        g = self._grab
        self._grab = None
        if g is None:
            return
        eng = self.engine
        eng.vm.dispatch(g, "onleftbuttonup", [("INT", pt.x()), ("INT", pt.y())])
        if isinstance(g, G.Slider):
            g.release_at(pt)
        elif isinstance(g, G.Button):
            inside = g.rect.contains(pt)
            g.pressed = False
            g.update()
            if inside:
                g.click()

    def mouseDoubleClickEvent(self, ev):
        lay = self.layout
        if lay is None:
            return
        t = self._passthrough(ev)
        if t is not None:
            if t is not self.dock:
                self._fwd = t
                self._forward(t, ev, "mouseDoubleClickEvent")
            return
        pt = self.to_l(ev.position())
        obj = lay.hit(pt) or lay
        if isinstance(obj, G.PlaylistView):
            obj.click_at(pt, double=True)
            return
        n = self.engine.vm.dispatch(obj, "onleftbuttondblclk", [("INT", pt.x()), ("INT", pt.y())])
        dca = obj.p("dblclickaction") if isinstance(obj, G.GuiObj) else None
        if dca:
            act, _, param = dca.partition(";")
            self.engine.do_action(act, param, obj)
        elif n == 0 and not isinstance(obj, (G.Button, G.Slider)):
            self.mousePressEvent(ev)

    def wheelEvent(self, ev):
        lay = self.layout
        d = ev.angleDelta().y()
        if lay is None or d == 0:
            return
        obj = lay.hit(self.to_l(ev.position()))
        if isinstance(obj, G.PlaylistView):
            obj.wheel(d)
            return
        pl = self.engine.app.player
        pl.set_volume(pl.volume + (2 if d > 0 else -2))

    def keyPressEvent(self, ev):
        if not self.engine.app.handle_key(ev):
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        ev.ignore()
        if self.dock is None:
            self.engine.show_container(self.container, False)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        urls = [u.toString() for u in ev.mimeData().urls() if not u.isLocalFile()]
        if paths:
            self.engine.app.player.add_paths(paths)
        if urls:
            self.engine.app.player.add(urls)


# ============================================================ MAKI objects
class MakiObj:
    cls = "Object"

    def maki_call(self, name, args):
        fn = getattr(self, "m_" + name, None)
        if fn is None:
            eng = getattr(self, "engine", None)
            if name.startswith("on") and eng is not None:
                return eng.vm.dispatch(self, name, [("ANY", a) for a in args])
            (log.warning if os.environ.get("ZEBAMP_MAKI_TRACE") else log.debug)("MAKI missing: %s.%s", self.cls, name)
            return None
        try:
            return fn(*args)
        except Exception as e:
            log.debug("MAKI %s.%s%r: %s", self.cls, name, args, e)
            return None

    def m_getclassname(self):
        return self.cls

    def m_getid(self):
        return ""


class MakiTimer(MakiObj):
    cls = "Timer"

    def __init__(self, engine):
        self.engine = engine
        self.t = QTimer()
        self.t.setInterval(1000)
        self.t.timeout.connect(self._fire)

    def _fire(self):
        self.engine.vm.dispatch(self, "ontimer")

    def m_setdelay(self, ms):
        self.t.setInterval(max(1, int(ms)))

    def m_getdelay(self):
        return self.t.interval()

    def m_start(self):
        self.t.start()

    def m_stop(self):
        self.t.stop()

    def m_isrunning(self):
        return self.t.isActive()

    def m_getskipped(self):
        return 0

    def maki_delete(self):
        self.t.stop()


class ConfigAttribute(MakiObj):
    cls = "ConfigAttribute"

    def __init__(self, engine, item, name):
        self.engine, self.item, self.name = engine, item, name

    def m_getdata(self):
        return self.engine.cfg_get(self.item.guid, self.name)

    def m_setdata(self, v):
        self.engine.cfg_set(self.item.guid, self.name, str(v))
        self.engine.vm.dispatch(self, "ondatachanged")

    def m_getparentitem(self):
        return self.item

    def m_getattributename(self):
        return self.name


class ConfigItem(MakiObj):
    cls = "ConfigItem"

    def __init__(self, engine, guid, name=""):
        self.engine, self.guid, self.name = engine, guid, name
        self.attrs: dict[str, ConfigAttribute] = {}

    def m_getattribute(self, name):
        key = str(name).lower()
        if key not in self.attrs:
            self.attrs[key] = ConfigAttribute(self.engine, self, key)
        return self.attrs[key]

    # Defaults that suit Zebamp better (it has no embedded Winamp library).
    DEFAULT_OVERRIDES = {"show playlist tab": "1"}

    def m_newattribute(self, name, default):
        a = self.m_getattribute(name)
        if self.engine.cfg_get(self.guid, a.name) == "":
            default = self.DEFAULT_OVERRIDES.get(str(name).strip().lower(), default)
            self.engine.cfg_set(self.guid, a.name, str(default))
        return a

    def m_getguid(self):
        return self.guid

    def m_getname(self):
        return self.name


class ConfigObj(MakiObj):
    cls = "Config"

    def __init__(self, engine):
        self.engine = engine
        self.items: dict[str, ConfigItem] = {}

    def _item(self, key, name=""):
        k = str(key).lower()
        if k not in self.items:
            self.items[k] = ConfigItem(self.engine, k, name)
        return self.items[k]

    def m_getitem(self, name):
        return self._item("name:" + str(name), str(name))

    def m_getitembyguid(self, guid):
        return self._item(_norm_guid(str(guid)))

    def m_newitem(self, name, guid):
        return self._item(_norm_guid(str(guid)), str(name))


class WinampConfigGroup(MakiObj):
    cls = "WinampConfigGroup"

    def __init__(self, engine, name):
        self.engine, self.name = engine, name

    def m_getbool(self, item):
        return self.engine.cfg_get("wa:" + self.name, str(item).lower()) in ("1", "true")

    def m_setbool(self, item, v):
        self.engine.cfg_set("wa:" + self.name, str(item).lower(), "1" if v else "0")

    def m_getint(self, item):
        try:
            return int(self.engine.cfg_get("wa:" + self.name, str(item).lower()) or 0)
        except ValueError:
            return 0

    def m_setint(self, item, v):
        self.engine.cfg_set("wa:" + self.name, str(item).lower(), str(int(v)))

    def m_getstring(self, item):
        return self.engine.cfg_get("wa:" + self.name, str(item).lower())

    def m_setstring(self, item, v):
        self.engine.cfg_set("wa:" + self.name, str(item).lower(), str(v))


class WinampConfig(MakiObj):
    cls = "WinampConfig"

    def __init__(self, engine):
        self.engine = engine

    def m_getgroup(self, name):
        return WinampConfigGroup(self.engine, str(name))


class PopupMenu(MakiObj):
    cls = "PopupMenu"

    def __init__(self, engine):
        self.engine = engine
        self.menu = QMenu()
        self.actions = {}

    def m_addcommand(self, text, cid, checked, disabled):
        a = self.menu.addAction(str(text))
        a.setCheckable(bool(checked))
        a.setChecked(bool(checked))
        a.setEnabled(not disabled)
        a.setData(int(cid))
        self.actions[int(cid)] = a

    def m_addseparator(self):
        self.menu.addSeparator()

    def m_addsubmenu(self, sub, text):
        if isinstance(sub, PopupMenu):
            sub.menu.setTitle(str(text))
            self.menu.addMenu(sub.menu)

    def m_checkcommand(self, cid, on):
        a = self.actions.get(int(cid))
        if a:
            a.setCheckable(True)
            a.setChecked(bool(on))

    def m_disablecommand(self, cid, dis):
        a = self.actions.get(int(cid))
        if a:
            a.setEnabled(not dis)

    def m_getnumcommands(self):
        return len(self.actions)

    def _exec(self, pos):
        a = self.menu.exec(pos)
        return int(a.data()) if a is not None and a.data() is not None else -1

    def m_popatxy(self, x, y):
        return self._exec(QPoint(int(x), int(y)))

    def m_popatmouse(self):
        return self._exec(QCursor.pos())


class SystemObj(MakiObj):
    cls = "System"

    def __init__(self, engine, group, param="", script_id=""):
        self.engine = engine
        self.group = group
        self.param = param or ""
        self.script_id = script_id

    @property
    def app(self):
        return self.engine.app

    @property
    def pl(self):
        return self.engine.app.player

    # containers / groups
    def m_getcontainer(self, cid):
        return self.engine.container(str(cid))

    def m_getnumcontainers(self):
        return len(self.engine.containers)

    def m_enumcontainer(self, i):
        i = int(i)
        return self.engine.containers[i] if 0 <= i < len(self.engine.containers) else None

    def m_getscriptgroup(self):
        return self.group

    def m_getparam(self):
        # Winamp substitutes these before scripts see them
        return str(self.param or "").replace("@HAVE_LIBRARY@", "1")

    def m_newgroup(self, gid):
        return self.engine.new_group(str(gid))

    def m_newgroupaslayout(self, gid):
        return self.engine.new_group(str(gid))

    def m_newdynamiccontainer(self, cid):
        return None

    def m_getwac(self, guid):
        return None

    def m_getskinname(self):
        return self.engine.skin.name

    def m_switchskin(self, name):
        pass

    # playback
    def m_play(self):
        self.pl.play()

    def m_stop(self):
        self.pl.stop()

    def m_pause(self):
        self.pl.pause()

    def m_next(self):
        self.pl.next()

    def m_previous(self):
        self.pl.previous()

    def m_eject(self):
        self.app.open_files()

    def m_seekto(self, ms):
        self.pl.seek(int(ms) / 1000.0)

    def m_getposition(self):
        return int(self.pl.elapsed * 1000)

    def m_getplayitemlength(self):
        return int(self.pl.duration * 1000) if self.pl.duration > 0 else -1

    def m_getstatus(self):
        return {"play": 1, "pause": -1}.get(self.pl.state, 0)

    def m_isplaying(self):
        return self.pl.state == "play"

    def m_getvolume(self):
        return int(max(0, self.pl.volume) * 255 / 100)

    def m_setvolume(self, v):
        self.pl.set_volume(int(round(int(v) * 100 / 255)))

    def m_getbalance(self):
        return int(self.app.balance * 127 / 100)

    def m_setbalance(self, v):
        self.app.set_balance(int(int(v) * 100 / 127))
        self.app.commit_balance()

    def m_getplayitemstring(self):
        return song_title(self.pl.song)

    def m_getplayitemdisplaytitle(self):
        return song_title(self.pl.song)

    def m_getplayitemmetadatastring(self, name):
        n = str(name).lower()
        s = self.pl.song
        if n == "bitrate":
            return str(self.pl.bitrate)
        if n == "year":
            n = "date"
        return str(first(s.get(n, "")))

    def m_getmetadatastring(self, fn, name):
        return self.m_getplayitemmetadatastring(name)

    def m_getsonginfotext(self):
        if self.pl.state == "stop":
            return ""
        rate, _b, ch = self.pl.audio
        return f"{self.pl.bitrate}kbps {'mono' if ch == 1 else 'stereo'} {rate // 1000}khz"

    def m_getsonginfotexttranslated(self):
        return self.m_getsonginfotext()

    def m_debugstring(self, s, severity):
        log.debug("skin debug: %s", s)

    def m_lockui(self):
        pass

    def m_unlockui(self):
        pass

    def m_getplaylistlength(self):
        return len(self.pl.queue)

    def m_getplaylistindex(self):
        return self.pl.current_pos

    def m_clearplaylist(self):
        self.pl.clear()

    def m_getleftvumeter(self):
        return self.engine.vu(0)

    def m_getrightvumeter(self):
        return self.engine.vu(1)

    def m_getvisband(self, channel, band):
        bars = self.app.vis.analyzer.bars
        b = max(0, min(len(bars) - 1, int(band)))
        return int(bars[b] / 16 * 255)

    # eq
    def m_geteqband(self, band):
        b = int(band)
        if 0 <= b < 10:
            return int(self.app.eq.bands[b] / 12 * 127)
        return 0

    def m_seteqband(self, band, v):
        b = int(band)
        if 0 <= b < 10:
            self.app.eq.set_band(b, int(v) / 127 * 12)

    def m_geteqpreamp(self):
        return int(self.app.eq.preamp / 12 * 127)

    def m_seteqpreamp(self, v):
        self.app.eq.set_preamp(int(v) / 127 * 12)

    def m_geteq(self):
        return 1 if self.app.eq.enabled else 0

    def m_seteq(self, on):
        self.app.eq.set_enabled(bool(on))

    # strings / numbers
    def m_integertostring(self, v):
        return str(int(v))

    def m_stringtointeger(self, s):
        try:
            return int(float(str(s).strip() or 0))
        except ValueError:
            return 0

    def m_floattostring(self, f, digits):
        return f"{float(f):.{max(0, int(digits))}f}"

    def m_stringtofloat(self, s):
        try:
            return float(str(s).strip() or 0)
        except ValueError:
            return 0.0

    def m_integertotime(self, ms):
        return fmt_time(int(ms) / 1000)

    def m_integertolongtime(self, ms):
        sec = int(int(ms) / 1000)
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        return f"{h}:{m:02d}:{s:02d}"

    def m_datetotime(self, d):
        return time.strftime("%H:%M:%S", time.localtime(int(d)))

    def m_datetolongtime(self, d):
        return time.strftime("%c", time.localtime(int(d)))

    def m_formatdate(self, d):
        return time.strftime("%x", time.localtime(int(d)))

    def m_formatlongdate(self, d):
        return time.strftime("%A, %d %B %Y", time.localtime(int(d)))

    def m_getdate(self):
        return int(time.time())

    def m_gettimeofday(self):
        t = time.localtime()
        return (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec) * 1000

    def m_getdatedmonth(self, d):
        return time.localtime(int(d)).tm_mon - 1

    def m_getdateyear(self, d):
        return time.localtime(int(d)).tm_year - 1900

    def m_getdatehour(self, d):
        return time.localtime(int(d)).tm_hour

    def m_getdatemin(self, d):
        return time.localtime(int(d)).tm_min

    def m_getdatesec(self, d):
        return time.localtime(int(d)).tm_sec

    def m_getdatedday(self, d):
        return time.localtime(int(d)).tm_mday

    def m_getdatedweek(self, d):
        return (time.localtime(int(d)).tm_wday + 1) % 7

    def m_strlen(self, s):
        return len(str(s))

    def m_strupper(self, s):
        return str(s).upper()

    def m_strlower(self, s):
        return str(s).lower()

    def m_strleft(self, s, n):
        return str(s)[: max(0, int(n))]

    def m_strright(self, s, n):
        n = int(n)
        return str(s)[-n:] if n > 0 else ""

    def m_strmid(self, s, start, n):
        start = max(0, int(start))
        n = int(n)
        return str(s)[start:start + n] if n >= 0 else str(s)[start:]

    def m_strsearch(self, s, sub):
        return str(s).find(str(sub))

    def m_gettoken(self, s, sep, n):
        parts = str(s).split(str(sep)) if sep else [str(s)]
        n = int(n)
        return parts[n] if 0 <= n < len(parts) else ""

    def m_removepath(self, s):
        return str(s).replace("\\", "/").rsplit("/", 1)[-1]

    def m_getpath(self, s):
        return str(s).replace("\\", "/").rsplit("/", 1)[0]

    def m_getextension(self, s):
        return os.path.splitext(str(s))[1].lstrip(".")

    def m_translate(self, s):
        return str(s)

    def m_getstring(self, table, n):
        return ""

    def m_getlanguageid(self):
        return "es-es"

    def m_urlencode(self, s):
        from urllib.parse import quote
        return quote(str(s))

    # math
    def m_random(self, mx):
        mx = int(mx)
        return random.randrange(mx) if mx > 0 else 0

    def m_integer(self, d):
        return int(d)

    def m_frac(self, d):
        return float(d) - int(d)

    def m_sin(self, v):
        return math.sin(float(v))

    def m_cos(self, v):
        return math.cos(float(v))

    def m_tan(self, v):
        return math.tan(float(v))

    def m_asin(self, v):
        return math.asin(max(-1.0, min(1.0, float(v))))

    def m_acos(self, v):
        return math.acos(max(-1.0, min(1.0, float(v))))

    def m_atan(self, v):
        return math.atan(float(v))

    def m_atan2(self, y, x):
        return math.atan2(float(y), float(x))

    def m_pow(self, v, e):
        try:
            return math.pow(float(v), float(e))
        except (ValueError, OverflowError):
            return 0.0

    def m_sqr(self, v):
        return float(v) * float(v)

    def m_sqrt(self, v):
        return math.sqrt(max(0.0, float(v)))

    def m_log(self, v):
        return math.log(float(v)) if float(v) > 0 else 0.0

    def m_log10(self, v):
        return math.log10(float(v)) if float(v) > 0 else 0.0

    # private / public settings
    def m_getprivatestring(self, sec, item, default):
        v = self.engine.cfg_get("priv:" + str(sec), str(item))
        return v if v != "" else str(default)

    def m_setprivatestring(self, sec, item, value):
        self.engine.cfg_set("priv:" + str(sec), str(item), str(value))

    def m_getprivateint(self, sec, item, default):
        v = self.engine.cfg_get("priv:" + str(sec), str(item))
        try:
            return int(v) if v != "" else int(default)
        except ValueError:
            return int(default)

    def m_setprivateint(self, sec, item, value):
        self.engine.cfg_set("priv:" + str(sec), str(item), str(int(value)))

    def m_getpublicstring(self, item, default):
        return self.m_getprivatestring("public", item, default)
    def m_setpublicstring(self, item, value):
        return self.m_setprivatestring("public", item, value)
    def m_getpublicint(self, item, default):
        return self.m_getprivateint("public", item, default)
    def m_setpublicint(self, item, value):
        return self.m_setprivateint("public", item, value)

    # environment
    def m_messagebox(self, msg, title, flags, notagain):
        # Never block the UI from a script: show it non-modally.
        log.info("skin message: %s: %s", title, msg)
        key = f"{title}|{msg}"
        if key in self.engine._shown_msgs:
            return 1
        self.engine._shown_msgs.add(key)
        box = QMessageBox(QMessageBox.Icon.Information, str(title) or "Zebamp", str(msg))
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        self.engine.app.keep(box).show()
        return 1

    def m_getruntimeversion(self):
        return 5.666

    def m_getbuildnumber(self):
        return 3516

    def m_isdesktopalphaavailable(self):
        return 1

    def m_istransparencyavailable(self):
        return 1

    def m_isobjectvalid(self, o):
        return o is not None

    def m_isappactive(self):
        return 1

    def m_isminimized(self):
        return 0

    def m_minimizeapplication(self):
        self.app.minimize()

    def m_restoreapplication(self):
        pass

    def m_activateapplication(self):
        pass

    def _screen(self):
        s = QGuiApplication.primaryScreen()
        return s.availableGeometry() if s else QRect(0, 0, 1920, 1080)

    def m_getviewportwidth(self):
        return self._screen().width()

    def m_getviewportheight(self):
        return self._screen().height()

    def m_getviewportleft(self):
        return self._screen().x()

    def m_getviewporttop(self):
        return self._screen().y()

    m_getmonitorwidth = m_getviewportwidth
    m_getmonitorheight = m_getviewportheight
    m_getmonitorleft = m_getviewportleft
    m_getmonitortop = m_getviewporttop

    def m_getviewportleftfromguiobject(self, o):
        return self._screen().x()

    def m_getviewporttopfromguiobject(self, o):
        return self._screen().y()

    def m_getviewportwidthfromguiobject(self, o):
        return self._screen().width()

    def m_getviewportheightfromguiobject(self, o):
        return self._screen().height()

    def m_getmousex(self):
        return QCursor.pos().x()

    def m_getmousey(self):
        return QCursor.pos().y()

    def m_getcurappleft(self):
        return 0

    def m_getcurapptop(self):
        return 0

    def m_getcurappwidth(self):
        return 275

    def m_getcurappheight(self):
        return 116

    def m_navigateurl(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(str(url)))

    m_navigateurlbrowser = m_navigateurl

    def m_hasvideosupport(self):
        return 0

    def m_isvideo(self):
        return 0

    def m_isvideofullscreen(self):
        return 0

    def m_getidealvideowidth(self):
        return 0

    def m_getidealvideoheight(self):
        return 0

    def m_iskeydown(self, vk):
        return 0

    def m_setclipboardtext(self, t):
        QGuiApplication.clipboard().setText(str(t))

    def m_getdecodername(self, fn):
        return ""

    def m_onnotify(self, *a):
        return 0

    def m_invokedebugger(self):
        pass

    def m_setmenutransparency(self, a):
        pass

    def m_getsongtime(self):
        return int(self.pl.elapsed * 1000)

    def m_getcurrenttrackrating(self):
        st = getattr(self.engine.app, "stats", None)
        return st.rating((self.pl.song or {}).get("file", "")) if st else 0

    def m_setcurrenttrackrating(self, r):
        st = getattr(self.engine.app, "stats", None)
        if st is not None:
            st.rate_current(int(r))
            for s_ in list(self.engine.systems):
                self.engine.vm.dispatch(s_, "oncurrenttrackrated", [("INT", int(r))])

    def m_getextfamily(self, ext):
        return "Audio"

    def m_ismemorized(self, *a):
        return 0

    def m_getappname(self):
        return "Zebamp"

    def m_getruntimecompiled(self):
        return 1


# ================================================================ engine
class ModernEngine:
    def __init__(self, app, skin: ModernSkin):
        self.app = app
        self.skin = skin
        self.vm = VM(self)
        self.containers: list[G.Container] = []
        self.systems: list[SystemObj] = []
        self._pending_scripts: list[tuple] = []
        self._images: dict = {}
        self._anims: list = []
        self._anim_layers: list = []
        self._tickers: list = []
        self.config = ConfigObj(self)
        self.winamp_config = WinampConfig(self)
        self._store = app.cfg.get("modern_store") or {}
        self._last_state = app.player.state
        self.anim_timer = QTimer()
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._step_anims)
        self.layer_timer = QTimer()
        self.layer_timer.setInterval(50)
        self.layer_timer.timeout.connect(self._step_layers)
        self.dock: ModernDock | None = None
        self.vis_style = 0
        self.vis_random_timer = QTimer()
        self.vis_random_timer.setInterval(15000)
        self.vis_random_timer.timeout.connect(self._vis_random_tick)
        self._shown = False
        self.ticker_timer = QTimer()
        self.ticker_timer.setInterval(60)
        self.ticker_timer.timeout.connect(self._step_tickers)
        self.clock = QTimer()
        self.clock.setInterval(250)
        self.clock.timeout.connect(self._on_clock)
        self._layer_acc: dict = {}
        self._shown_msgs: set = set()
        self._xui: list = []
        self._clip: QRect | None = None
        self.cover = None

    # ------------------------------------------------------------ build
    def build(self):
        for cnode in self.skin.containers:
            c = G.Container(cnode, self)
            for lnode in cnode.children:
                if lnode.tag != "layout":
                    continue
                lay = G.Layout(lnode, c, self)
                self.build_children(lay, lnode)
                lay.compute_rect(lay.rect)
                c.layouts.append(lay)
            if c.layouts:
                c.current = c.layout("normal") or c.layouts[0]
                self.containers.append(c)
        self.tree_changed()
        for snode in self.skin.scripts:
            self._pending_scripts.append((snode, None))
        p = self.app.player
        p.statusChanged.connect(self._on_status)
        p.songChanged.connect(self._on_song)
        p.volumeChanged.connect(self._on_volume)
        p.optionsChanged.connect(self._refresh_toggles)
        self.app.eq.changed.connect(self._on_eq)
        self.app.vis.frame.connect(self._on_vis)
        return bool(self.containers)

    def build_children(self, parent: G.GuiObj, node: Node, _depth=0):
        inh = (node.get("inherit_group") or "").lower() if node.tag == "groupdef" else ""
        if inh and _depth < 8:
            base = self.skin.groupdefs.get(inh)
            if base is not None and base is not node:
                self.build_children(parent, base, _depth + 1)
        for c in node.children:
            t = c.tag
            if t in ("groupdef", "elements", "include", "layout", "container"):
                if t == "groupdef":
                    gid = (c.get("id") or "").lower()
                    if gid:
                        self.skin.groupdefs[gid] = c
                continue
            if t == "script":
                self._pending_scripts.append((c, parent))
                continue
            if t == "sendparams":
                self._sendparams(parent, c)
                continue
            if t == "hideobject":
                for tid in (c.get("target") or "").split(";"):
                    o = parent.find(tid)
                    if o is not None:
                        o.visible = False
                continue
            obj = self.make(c, parent)
            if obj is not None:
                parent.children.append(obj)
                obj.build()
                self.tree_changed()

    def make(self, node: Node, parent) -> G.GuiObj | None:
        t = node.tag
        cls = TAGS.get(t)
        if cls is not None:
            return cls(node, parent, self)
        if t == "group":
            gd = self.skin.groupdefs.get((node.get("id") or "").lower())
            return G.Group(node, parent, self, groupdef=gd)
        if t in ("windowholder", "component", "playlisteditor", "pleditor", "list"):
            hold = _norm_guid(node.get("hold") or node.get("component") or node.get("param") or "")
            if hold == PL_GUID or t in ("playlisteditor", "pleditor") or "playlist" in (node.get("id") or "").lower():
                return G.PlaylistView(node, parent, self)
            if hold == ML_GUID:
                return G.WidgetHost(node, parent, self, "library")
            if hold == AVS_GUID:
                # Winamp's AVS/visualisation slot: our spectrum analyser
                vn = Node("vis", dict(node.attrs))
                vn.attrs.setdefault("mode", "1")
                vn.attrs.setdefault("colorallbands", "")
                vn.attrs["zebamp_slot"] = "1"     # follows the VIS_Next/Prev styles
                return G.Vis(vn, parent, self)
            return G.GuiObj(node, parent, self)
        if t == "wasabi:frame" and t not in self.skin.xuitags:
            g = G.Group(node, parent, self, groupdef=builtin_split_frame(node))
            g.split = {"vertical": (node.get("orientation") or "v").lower().startswith("v"),
                       "left": node.get("left") or node.get("top"),
                       "right": node.get("right") or node.get("bottom"),
                       "min": G._i(node.get("minwidth") or node.get("minheight"), 0), "gap": 8}
            return g
        gd = self.skin.xuitags.get(t)
        if gd is None and t in XUI_ALIASES:
            gid = XUI_ALIASES[t]
            gd = self.skin.groupdefs.get(gid)
            if gd is None:
                gd = builtin_titlebar(node) if t == "wasabi:titlebar" else builtin_frame(gid, node)
        if gd is not None:
            g = G.Group(node, parent, self, groupdef=gd)
            self._xui.append((g, node))
            return g
        if t.startswith("wasabi:") or ":" in t:
            return G.GuiObj(node, parent, self)
        if t in ("albumart", "albumartlayer"):
            return G.AlbumArt(node, parent, self)
        return G.GuiObj(node, parent, self)

    def _host_component(self, c: G.Container, lay: G.Layout):
        """Containers bound to Winamp's playlist component get our playlist
        view in the frame's client area (Winamp did this internally)."""
        comp = _norm_guid(c.node.get("component") or "")
        if comp not in (PL_GUID, ML_GUID):
            return False
        if any(isinstance(o, (G.PlaylistView, G.WidgetHost)) for o in lay.walk()):
            return False
        if lay.rect.height() < 60:
            return False  # windowshade layouts have no room for a list
        geo = None
        for o in lay.walk():
            n = o.node if isinstance(o, G.GuiObj) else None
            src = getattr(o, "groupdef", None) or n
            if src is None:
                continue
            for ch in src.children:
                if ch.tag == "script" and "standardframe" in (ch.get("file") or "").lower() and ch.get("param"):
                    geo = (o, ch.get("param"))
                    break
            if geo:
                break
        x, y, w, h, rx, ry, rw, rh = 5, 15, -10, -20, 0, 0, 1, 1
        host = lay
        if geo:
            try:
                vals = [int(v) for v in geo[1].split(",")]
                x, y, w, h, rx, ry, rw, rh = ([*vals, 0, 0, 1, 1])[:8]
                host = geo[0]
            except ValueError:
                pass
        geo_attrs = {"x": str(x), "y": str(y), "w": str(w), "h": str(h), "relatx": str(rx),
                     "relaty": str(ry), "relatw": str(rw), "relath": str(rh)}
        if comp == ML_GUID:
            pv = G.WidgetHost(Node("windowholder", dict(geo_attrs, id="zebamp.library")), host, self)
        else:
            pv = G.PlaylistView(Node("playlisteditor", dict(geo_attrs, id="zebamp.playlist")), host, self)
        host.children.append(pv)
        self.tree_changed()
        return True

    def _sendparams(self, group, node: Node):
        targets = [t for t in (node.get("target") or "").split(";") if t]
        params = {k: v for k, v in node.attrs.items() if k not in ("target", "group")}
        scope = group
        if node.get("group"):
            scope = group.find(node.get("group"))
            if scope is None:
                return
        for tid in targets:
            o = scope.find(tid)
            if o is not None:
                o.params.update(params)
                for k, v in params.items():
                    o.on_param(k, v)

    def new_group(self, gid):
        gd = self.skin.groupdefs.get(gid.lower())
        if gd is None:
            return None
        g = G.Group(Node("group", {"id": gid}), None, self, groupdef=gd)
        g.build()
        return g

    def start(self):
        self._start_scripts()
        for c in self.containers:
            for lay in c.layouts:
                if self._host_component(c, lay):
                    lay.compute_rect(lay.rect)
                lay.compute_rect(lay.rect)
                self.fire_resize(lay)
        for c in self.containers:
            for lay in c.layouts:
                for o in lay.walk():
                    if isinstance(o, G.GuiObj) and (o.id or "").lower() in G.GuiObj.UNSUPPORTED:
                        o.visible = False
        self.show()
        self.clock.start()
        self.vis_random_timer.start()
        QTimer.singleShot(0, self._collapse_empty_panes)
        self._refresh_toggles()
        self._fetch_cover()

    def _send_xui(self, target, node):
        for k, v in node.attrs.items():
            if k not in GUI_PARAMS:
                self.vm.dispatch(target, "onsetxuiparam", [("STRING", k), ("STRING", v)])

    def _start_scripts(self):
        pending, self._pending_scripts = self._pending_scripts, []
        # XUI instance params go to each script right after it loads (as in
        # Winamp), so later scripts already see e.g. a tab's text.
        xui, self._xui = self._xui, []
        xui_of = {}
        for g, node in xui:
            xui_of.setdefault(id(g), (g, node))
        sent_group = set()
        for snode, group in pending:
            data = self.skin.script_data(snode)
            if not data:
                continue
            try:
                prog = Program(data, snode.get("file", ""))
            except (MakiError, IndexError, Exception) as e:
                log.warning("cannot load MAKI %s: %s", snode.get("file"), e)
                continue
            system = SystemObj(self, group, snode.get("param", ""), snode.get("file", ""))
            if prog.vars and prog.vars[0].type == "OBJECT":
                prog.vars[0].value = system
            for v in prog.vars:
                if v.type == "OBJECT" and v.value is None and v.guid:
                    n = class_name(v.guid)
                    if n == "Config":
                        v.value = self.config
                    elif n == "WinampConfig":
                        v.value = self.winamp_config
            self.systems.append(system)
            self.vm.add(prog)
            self.vm.dispatch(system, "onscriptloaded")
            gx = xui_of.get(id(group))
            if gx is not None:
                if id(group) not in sent_group:
                    sent_group.add(id(group))
                    self._send_xui(group, gx[1])
                self._send_xui(system, gx[1])
        for g, node in xui:
            if id(g) not in sent_group:
                sent_group.add(id(g))
                self._send_xui(g, node)

    def start_scripts(self, obj):
        if self._pending_scripts:
            self._start_scripts()

    def stop(self):
        for s in list(self.systems):
            self.vm.dispatch(s, "onscriptunloading")
        for t in (self.anim_timer, self.layer_timer, self.ticker_timer, self.clock,
                  self.vis_random_timer):
            t.stop()
        for c in self.containers:
            if c.window is not None:
                c.window.hide()
                c.window.deleteLater()
                c.window = None
        if self.dock is not None:
            self.dock.save_positions()
            self.dock.hide()
            self.dock.deleteLater()
            self.dock = None
        p = self.app.player
        for sig, fn in ((p.statusChanged, self._on_status), (p.songChanged, self._on_song),
                        (p.volumeChanged, self._on_volume), (p.optionsChanged, self._refresh_toggles),
                        (self.app.eq.changed, self._on_eq), (self.app.vis.frame, self._on_vis)):
            try:
                sig.disconnect(fn)
            except (RuntimeError, TypeError):
                pass
        self.app.cfg["modern_store"] = self._store
        self.app.cfg.save()
        self.skin.vfs.close()
        if self.skin.ff is not None:
            self.skin.ff.close()

    # ------------------------------------------------------- containers
    def container(self, cid: str) -> G.Container | None:
        k = (cid or "").lower()
        nk = _norm_guid(cid)
        for c in self.containers:
            if c.id.lower() == k or (_norm_guid(c.node.get("component", "")) == nk and nk):
                return c
        aliases = {"pl": ("pledit", "playlist", PL_GUID), "pledit": ("pl", PL_GUID),
                   "eq": ("equalizer",), "ml": ("library", ML_GUID), PL_GUID: ("pl", "pledit"),
                   ML_GUID: ("ml", "library")}
        for alt in aliases.get(k, ()) + aliases.get(nk, ()):
            for c in self.containers:
                if c.id.lower() == alt or _norm_guid(c.node.get("component", "")) == alt:
                    return c
        return None

    @property
    def scale(self) -> float:
        return self.app.mscale

    def docked(self) -> bool:
        return self.app.cfg["modern_layout"] in ("free", "fixed")

    def _window(self, c: G.Container) -> ModernWindow:
        if c.window is None:
            dock = None
            lay = c.current
            free_floating = lay is not None and (_truthy(lay.p("noparent")) or _truthy(lay.p("nodock")))
            if self.docked() and not free_floating:
                if self.dock is None:
                    self.dock = ModernDock(self)
                dock = self.dock
            c.window = ModernWindow(self, c, dock)
        return c.window

    def show_container(self, c: G.Container, on: bool):
        c.visible = on
        if on:
            w = self._window(c)
            w.sync_size()
            w.show()
            w.raise_()
            if w.dock is not None:
                w.dock.relayout()
                if self._shown:
                    w.dock.show()
        elif c.window is not None:
            c.window.hide()
            if c.window.dock is not None:
                c.window.dock.relayout()
        if c is self.main_container() and not on:
            c.visible = True        # so showing again (tray) brings it back
            self.app.request_close()

    def _component_of(self, cid):
        c = None
        k = (cid or "").lower()
        for x in self.containers:
            if x.id.lower() == k:
                c = x
        return c.node.get("component", "") if c is not None else ""

    def main_container(self):
        return self.container("main") or (self.containers[0] if self.containers else None)

    def toggle(self, cid):
        if _norm_guid(cid) in (AVS_GUID, "avs", "vis", "visualizations") or \
                _norm_guid(self._component_of(cid)) == AVS_GUID:
            # Winamp's AVS/MilkDrop window -> our projectM window
            self.app.toggle_milkdrop()
            return True
        c = self.container(cid)
        if c is None:
            k = _norm_guid(cid)
            if k in (ML_GUID, "ml", "library"):
                self.app.show_library()
            return False
        self.show_container(c, not (c.visible and c.window is not None and c.window.isVisible()))
        return True

    def switch_layout(self, c: G.Container, lid: str):
        new = c.layout(lid)
        if new is None or new is c.current:
            return
        old = c.current
        self.vm.dispatch(c, "onbeforeswitchtolayout", [("OBJECT", old), ("OBJECT", new)])
        c.current = new
        new.compute_rect(new.rect)
        if c.window is not None:
            c.window.sync_size()
        if old is not None:
            self.vm.dispatch(old, "onsetvisible", [("BOOLEAN", 0)])
        self.vm.dispatch(new, "onsetvisible", [("BOOLEAN", 1)])
        self.vm.dispatch(c, "onswitchtolayout", [("OBJECT", new)])

    def layout_resized(self, lay: G.Layout):
        c = lay.container
        if c is not None and c.window is not None and c.current is lay:
            c.window.sync_size()
        self.fire_resize(lay)

    def fire_resize(self, root):
        """onResize for every object (under root) that a script listens to."""
        listening = set()
        for prog in self.vm.programs:
            for var_i, _ in prog.events.get("onresize", ()):
                v = prog.vars[var_i]
                if v.value is not None:
                    listening.add(id(v.value))
                for m in v.members:
                    if prog.vars[m].value is not None:
                        listening.add(id(prog.vars[m].value))
        if not listening:
            return
        for o in list(root.walk()):
            if id(o) in listening:
                x, y = o._rel() if o.parent is not None else (0, 0)
                self.vm.dispatch(o, "onresize", [("INT", x), ("INT", y), ("INT", o.rect.width()),
                                                 ("INT", o.rect.height())])

    def set_scale(self):
        for c in self.containers:
            if c.window is not None:
                c.window.sync_size()
        if self.dock is not None:
            self.dock.relayout()

    def show(self):
        self._shown = True
        for c in self.containers:
            if c.visible:
                self._window(c).show()
        if self.dock is not None:
            self.dock.relayout()
            self.dock.show()

    def hide(self):
        self._shown = False
        for c in self.containers:
            if c.window is not None:
                c.window.hide()
        if self.dock is not None:
            self.dock.hide()

    def top_windows(self):
        out = []
        for c in self.containers:
            w = c.window
            if w is not None and w.isVisible():
                t = w.window()
                if t not in out:
                    out.append(t)
        return out

    # -------------------------------------------------------- painting
    def request_repaint(self, obj, full=False):
        lay = obj.layout_obj() if hasattr(obj, "layout_obj") else None
        if lay is None or lay.container is None:
            return
        w = lay.container.window
        if w is None or lay.container.current is not lay:
            return
        if full:
            w.update()
        else:
            s = self.scale
            r = obj.rect.adjusted(-1, -1, 1, 1)
            w.update(QRect(int(r.x() * s), int(r.y() * s), math.ceil(r.width() * s) + 1,
                           math.ceil(r.height() * s) + 1))

    def image_cache(self, bid):
        if not bid:
            return None
        key = bid.lower()
        if key not in self._images:
            self._images[key] = self.skin.image_of(bid)
        return self._images[key]

    def client_to_screen(self, obj, x, y) -> QPoint:
        lay = obj.layout_obj()
        w = lay.container.window if lay and lay.container else None
        s = self.scale
        base = w.mapToGlobal(QPoint(0, 0)) if w is not None else QPoint(0, 0)
        return QPoint(base.x() + round((obj.rect.x() + x) * s), base.y() + round((obj.rect.y() + y) * s))

    def mouse_in(self, obj) -> QPoint:
        g = QCursor.pos()
        o = self.client_to_screen(obj, 0, 0)
        s = self.scale
        return QPoint(int((g.x() - o.x()) / s), int((g.y() - o.y()) / s))

    def window_pos(self, lay) -> QPoint:
        w = lay.container.window if lay.container else None
        return w.mapToGlobal(QPoint(0, 0)) if w is not None else QPoint(0, 0)

    def has_handler(self, obj, events) -> bool:
        for prog in self.vm.programs:
            for ev in events:
                for var_i, _ in prog.events.get(ev, ()):
                    v = prog.vars[var_i]
                    if v.value is obj:
                        return True
                    if v.is_class and any(prog.vars[m].value is obj for m in v.members):
                        return True
        return False

    # ------------------------------------------------------- animation
    def animate(self, obj):
        if obj not in self._anims:
            self._anims.append(obj)
        if not self.anim_timer.isActive():
            self.anim_timer.start()

    def _step_anims(self):
        for o in list(self._anims):
            if not o.step_target() and o in self._anims:
                self._anims.remove(o)
        if not self._anims:
            self.anim_timer.stop()

    def animate_layer(self, layer):
        if layer not in self._anim_layers:
            self._anim_layers.append(layer)
        if not self.layer_timer.isActive():
            self.layer_timer.start()

    def _step_layers(self):
        now = time.monotonic()
        for layer in list(self._anim_layers):
            last = self._layer_acc.get(id(layer), 0)
            if (now - last) * 1000 >= layer.speed:
                self._layer_acc[id(layer)] = now
                if not layer.tick() and not layer.playing:
                    self._anim_layers.remove(layer)
        if not self._anim_layers:
            self.layer_timer.stop()

    def register_ticker(self, t):
        self._tickers.append(t)
        if not self.ticker_timer.isActive():
            self.ticker_timer.start()

    TICK_FAST, TICK_IDLE = 60, 1000

    def _step_tickers(self):
        """Scroll long texts.  When nothing needs to scroll (short title,
        hidden window) the timer drops to one check per second."""
        moved = False
        for t in self._tickers:
            moved = bool(t.tick()) or moved
        want = self.TICK_FAST if moved else self.TICK_IDLE
        if self.ticker_timer.interval() != want:
            self.ticker_timer.setInterval(want)

    def wake_tickers(self):
        if self._tickers and self.ticker_timer.interval() != self.TICK_FAST:
            self.ticker_timer.setInterval(self.TICK_FAST)
            if not self.ticker_timer.isActive():
                self.ticker_timer.start()

    # ---------------------------------------------------------- player
    def tree_changed(self):
        """Objects were added or moved between parents: drop the type index."""
        self._by_cls = {}

    def _each(self, cls) -> list:
        """Every object of a given type, from a cached index.

        Walking the whole tree (thousands of objects in Big Bento) on every
        visualiser frame and clock tick was the main CPU cost; the index is
        rebuilt only after the tree changes (see tree_changed)."""
        index = self.__dict__.setdefault("_by_cls", {})
        objs = index.get(cls)
        if objs is None:
            objs = [o for c in self.containers for lay in c.layouts for o in lay.walk()
                    if isinstance(o, cls)]
            index[cls] = objs
        return objs

    def _repaint_all(self):
        for c in self.containers:
            if c.window is not None and c.window.isVisible():
                c.window.update()

    def _on_status(self):
        st = self.app.player.state
        old = self._last_state
        if st != old:
            ev = {"play": "onresume" if old == "pause" else "onplay", "pause": "onpause",
                  "stop": "onstop"}.get(st)
            if ev:
                for s in list(self.systems):
                    self.vm.dispatch(s, ev)
            self._last_state = st
            if st in ("play", "pause"):
                for o in self._each(G.GuiObj):
                    if o._keep_visible() and not o.visible:
                        o.visible = True
                        o.update()
        info = self.display_value("songinfo", None) or ""
        if info != getattr(self, "_last_info", None):
            self._last_info = info
            for s in list(self.systems):
                self.vm.dispatch(s, "oninfochange", [("STRING", info)])
        self._refresh_toggles()
        self.wake_tickers()
        self._repaint_all()

    def _on_song(self):
        self._fetch_cover()
        t = song_title(self.app.player.song)
        for s in list(self.systems):
            self.vm.dispatch(s, "ontitlechange", [("STRING", t)])
            self.vm.dispatch(s, "oninfochange", [("STRING", self.display_value("songinfo", None) or "")])
        self.wake_tickers()
        self._repaint_all()

    def _fetch_cover(self):
        uri = (self.app.player.song or {}).get("file")
        if uri == getattr(self, "_cover_uri", None):
            return
        self._cover_uri = uri
        if not uri or not any(True for _ in self._each(G.AlbumArt)):
            self._set_cover(None)
            return

        def job(client):
            for cmd in ("readpicture", "albumart"):
                try:
                    r = getattr(client, cmd)(uri)
                    if isinstance(r, dict) and r.get("binary"):
                        return r["binary"]
                except Exception:
                    continue
            return None
        self.app.player.conn.run_async(job, self._set_cover)

    def _set_cover(self, data):
        from PySide6.QtGui import QImage, QPixmap
        pm = None
        if data:
            img = QImage.fromData(data)
            if not img.isNull():
                pm = QPixmap.fromImage(img)
        self.cover = pm
        for o in self._each(G.AlbumArt):
            o.update()

    def _on_volume(self):
        v = int(max(0, self.app.player.volume) * 255 / 100)
        for s in list(self.systems):
            self.vm.dispatch(s, "onvolumechanged", [("INT", v)])
        for sl in self._each(G.Slider):
            if (sl.p("action") or "").lower() == "volume":
                sl.update()

    def _on_eq(self):
        for s in list(self.systems):
            self.vm.dispatch(s, "oneqchanged", [("INT", 1 if self.app.eq.enabled else 0)])
        for sl in self._each(G.Slider):
            if (sl.p("action") or "").lower().startswith("eq"):
                sl.update()
        for o in self._each(G.EqVis):
            o.update()

    def _on_vis(self):
        # Only visualisers that can be seen: Big Bento keeps a 624x445 one
        # hidden behind the playlist, and repainting it 50 times a second
        # redrew half the window.
        for o in self._each(G.Vis):
            if o.is_shown():
                o.update()

    def _on_clock(self):
        if self.app.player.state == "play":
            for o in self._each(G.Text):
                if (o.p("display") or "").lower().startswith("time") and o.is_shown():
                    o.update()
            for sl in self._each(G.Slider):
                if (sl.p("action") or "").lower() == "seek" and sl.is_shown():
                    sl.update()
            for pg in self._each(G.ProgressGrid):
                if pg.is_shown():
                    pg.update()

    def vu(self, ch):
        import numpy as np
        r = self.app.vis.reader
        if r is None or self.app.player.state != "play":
            return 0
        buf = r.buf[-512:]
        return int(min(255, float(np.sqrt(np.mean(buf * buf))) * 255 * 3))

    def _refresh_toggles(self):
        for t in self._each(G.ToggleButton):
            t.refresh_state()
        for b in self._each(G.NStatesButton):
            if b.p("cfgattrib"):
                old = b.state
                b.sync_state()
                if b.state != old:
                    b.update()

    # --------------------------------------------------------- values
    def display_value(self, disp: str, text_obj) -> str | None:
        pl = self.app.player
        s = pl.song
        if disp in ("songname", "songtitle", "pe_info"):
            if not s:
                return ""
            pos = pl.current_pos
            return f"{pos + 1}. {song_title(s)}" if disp == "songname" and pos >= 0 else song_title(s)
        if disp == "songinfo":
            if pl.state == "stop":
                return ""
            rate, _bits, ch = pl.audio
            parts = []
            if pl.bitrate:
                parts.append(f"{pl.bitrate}kbps")
            parts.append("mono" if ch == 1 else "stereo")
            if rate:
                parts.append(f"{rate / 1000:g}khz")
            return " ".join(parts)
        if disp == "songticker":
            if not s:
                return "Zebamp" if pl.connected else "MPD no conectado"
            pos = pl.current_pos
            t = f"{pos + 1}. {song_title(s)}" if pos >= 0 else song_title(s)
            if text_obj is not None and _truthy(text_obj.p("showlen")) and pl.duration > 0:
                t += f" ({fmt_time(pl.duration)})"
            return t
        if disp in ("windowtitle", "layouttitle", "containername", "componentname"):
            lay = text_obj.layout_obj() if text_obj is not None else None
            c = lay.container if lay is not None else None
            return (c.name if c is not None else "").upper()
        if disp in ("songartist",):
            return str(first(s.get("artist", "")))
        if disp in ("songalbum",):
            return str(first(s.get("album", "")))
        if disp == "songlength":
            return fmt_time(pl.duration) if pl.duration > 0 else ""
        if disp in ("time", "timeelapsed", "timeremaining"):
            style = str(text_obj.p("timeroffstyle", "0")) if text_obj is not None else "0"
            if pl.state == "stop":
                return {"1": "00:00", "2": "  :  "}.get(style, "")
            remaining = disp == "timeremaining" or (disp == "time" and self.app.cfg["time_remaining"])
            if remaining and pl.duration > 0:
                return "-" + fmt_time(pl.duration - pl.elapsed)
            t = int(pl.elapsed)
            m, sec = divmod(t, 60)
            return f"{m:02d}:{sec:02d}" if style != "3" else f"{m}:{sec:02d}"
        return None

    def slider_value(self, sl: G.Slider, cur):
        act = (sl.p("action") or "").lower()
        pl = self.app.player
        if act == "seek":
            d = pl.duration
            return int(sl.low + (pl.elapsed / d if d > 0 else 0) * (sl.high - sl.low))
        if act == "volume":
            return int(sl.low + max(0, pl.volume) / 100 * (sl.high - sl.low))
        if act == "pan":
            return int(sl.low + (self.app.balance + 100) / 200 * (sl.high - sl.low))
        if act in ("eq_band", "eq_preamp"):
            eq = self.app.eq
            b = _band(act, sl.p("param"))
            db = eq.preamp if b < 0 else eq.bands[b]
            return int(sl.low + (db + 12) / 24 * (sl.high - sl.low))
        return cur

    def _frac(self, sl, v):
        rng = sl.high - sl.low
        return 0.0 if rng == 0 else (v - sl.low) / rng

    def slider_changed(self, sl: G.Slider, v):
        act = (sl.p("action") or "").lower()
        f = self._frac(sl, v)
        if act == "volume":
            self.app.player.set_volume(int(round(f * 100)))
        elif act == "pan":
            self.app.set_balance(int(round(f * 200 - 100)))
        elif act in ("eq_band", "eq_preamp"):
            b = _band(act, sl.p("param"))
            if b < 0:
                self.app.eq.set_preamp(round(f * 24 - 12, 1))
            else:
                self.app.eq.set_band(b, round(f * 24 - 12, 1))

    def slider_final(self, sl: G.Slider, v):
        act = (sl.p("action") or "").lower()
        f = self._frac(sl, v)
        if act == "seek":
            self.app.player.seek(f * self.app.player.duration)
        elif act == "pan":
            self.app.commit_balance()
        elif act.startswith("eq"):
            self.app.eq.commit()

    # ------------------------------------------------------- toggles
    def _cfg_key(self, btn):
        attr = btn.p("cfgattrib") or ""
        guid, _, name = attr.partition(";")
        return _norm_guid(guid), name.strip().lower()

    def cfg_toggle_state(self, btn) -> bool:
        guid, name = self._cfg_key(btn)
        pl = self.app.player
        if not name:
            act = (btn.p("action") or "").lower()
            return {"eq_toggle": self.app.eq.enabled, "eq_auto": bool(self.app.cfg["eq_auto"])}.get(act, False)
        if "repeat" in name:
            return pl.repeat
        if "shuffle" in name:
            return pl.random
        if "crossfad" in name:
            return pl.crossfade > 0
        if name in ("enabled", "eq enabled", "equalizer enabled") or ("equalizer" in name and "auto" not in name):
            return self.app.eq.enabled
        if "auto" in name:
            return bool(self.app.cfg["eq_auto"])
        val = self.cfg_get(guid, name)
        want = btn.p("cfgval")
        return val == want if want else val in ("1", "true")

    def cfg_toggle_set(self, btn, on: bool):
        guid, name = self._cfg_key(btn)
        pl = self.app.player
        if not name:
            return
        if "repeat" in name:
            pl.set_repeat_mode("all" if on else "off")
        elif "shuffle" in name:
            pl.set_option("random", on)
        elif "crossfad" in name:
            pl.set_crossfade(5 if on else 0)
        elif name in ("enabled", "eq enabled", "equalizer enabled") or ("equalizer" in name and "auto" not in name):
            self.app.eq.set_enabled(on)
        elif "auto" in name:
            self.app.cfg["eq_auto"] = on
            self.app.cfg.save()
        else:
            self.cfg_set(guid, name, (btn.p("cfgval") or "1") if on else "0")

    def cfg_nstate_value(self, btn) -> str | None:
        """Current cfgvals value for an NStatesButton bound to a setting."""
        _guid, name = self._cfg_key(btn)
        pl = self.app.player
        if "repeat" in name:
            if not pl.repeat:
                return "0"
            return "-1" if pl.single else "1"
        if "shuffle" in name:
            return "1" if pl.random else "0"
        v = self.cfg_get(_guid, name)
        return v if v != "" else None

    def cfg_nstate_set(self, btn, value: str):
        guid, name = self._cfg_key(btn)
        pl = self.app.player
        if "repeat" in name:
            pl.set_repeat_mode({"0": "off", "1": "all", "-1": "track", "2": "track"}.get(value, "off"))
        elif "shuffle" in name:
            pl.set_option("random", value not in ("0", ""))
        else:
            self.cfg_set(guid, name, value)

    def cfg_get(self, sec, item) -> str:
        return str(self._store.get(f"{sec}|{str(item).lower()}", ""))

    def cfg_set(self, sec, item, value):
        self._store[f"{sec}|{str(item).lower()}"] = str(value)
        self.app.cfg["modern_store"] = self._store

    # -------------------------------------------------------- actions
    def _collapse_empty_panes(self):
        """Bento's top-right mini playlist is empty while the playlist lives in
        its own tab: give that room to the song info next to the cover."""
        for c in self.containers:
            for lay in c.layouts:
                for o in lay.walk():
                    sp = getattr(o, "split", None)
                    if not sp or not sp.get("vertical") or "playlist" not in (sp.get("right") or "").lower():
                        continue
                    right = o.find(sp["right"])
                    if right is None:
                        continue
                    pls = [v for v in right.walk() if isinstance(v, G.PlaylistView)]
                    if pls and not any(self._shown_in(v, lay) for v in pls):
                        total = o.rect.width()
                        if total > 0:
                            mn, sp["min"] = sp["min"], 0
                            o.m_setposition(total)
                            sp["min"] = mn
                            right.visible = False

    @staticmethod
    def _shown_in(obj, lay):
        q = obj
        while q is not None and q is not lay:
            if not q.visible:
                return False
            q = q.parent
        return True

    def set_color_theme(self, name):
        self.skin.set_gamma(name)
        themes = dict(self.app.cfg["modern_gamma"] or {})
        themes[self.skin.path] = name
        self.app.cfg["modern_gamma"] = themes
        self.app.cfg.save()
        self._images.clear()
        for c in self.containers:
            if c.window is not None:
                c.window.update()

    VIS_STYLES = ("Barras", "Barras finas", "Fuego", "Osciloscopio")

    def _vis_random_on(self) -> bool:
        if self.app.cfg["vis_next_random"]:
            return True
        return any((o.id or "").lower() == "vis.random" and o.activated
                   for o in self._each(G.ToggleButton))

    def step_vis_style(self, d=1):
        cur = getattr(self, "vis_style", 0)
        if d > 0 and self._vis_random_on():
            # "next" picks any other preset at random
            self.vis_style = random.choice([i for i in range(len(self.VIS_STYLES)) if i != cur])
        else:
            self.vis_style = (cur + d) % len(self.VIS_STYLES)
        for v in self._each(G.Vis):
            v.update()

    def _vis_random_tick(self):
        for o in self._each(G.ToggleButton):
            if (o.id or "").lower() == "vis.random" and o.activated and o.visible:
                self.step_vis_style(1)
                return

    def do_action(self, action, param, obj):
        if not action:
            return
        a = str(action).strip().lower()
        p = (param or "").strip()
        app = self.app
        pl = app.player
        simple = {
            "play": pl.play, "pause": pl.pause, "stop": pl.stop, "prev": pl.previous,
            "previous": pl.previous, "next": pl.next, "eject": app.open_files,
            "eject_url": app.add_url_play, "minimize": app.minimize,
            "repeat": pl.toggle_repeat, "shuffle": pl.toggle_random,
            "eq_toggle": app.eq.toggle, "eq_auto": app.toggle_eq_auto,
            "eq_reset": lambda: app.eq.set_all(0), "about": app.show_about,
            "prefs": app.show_preferences, "preferences": app.show_preferences,
            "rewind5s": lambda: pl.seek_relative(-5), "ffwd5s": lambda: pl.seek_relative(5),
            "volume_up": lambda: pl.set_volume(pl.volume + 5),
            "volume_down": lambda: pl.set_volume(pl.volume - 5),
            "pe_add": app.add_files, "pe_rem": app.clear_playlist,
            "pe_list": app.load_playlist, "jumptofile": app.show_jump_to_file,
            "toggle_ml": app.show_library, "skin_select": app.show_skin_browser,
        }
        fn = simple.get(a)
        if fn is not None:
            fn()
            return
        if a in ("vis_next", "vis_prev"):
            self.step_vis_style(1 if a == "vis_next" else -1)
            return
        if a == "vis_fs":
            app.toggle_milkdrop()
            md = getattr(app, "milkdrop", None)
            if md is not None and md.isVisible():
                md.showFullScreen()
            return
        if a in ("vis_cfg", "vis_plugin", "vis_presets"):
            app.show_milkdrop_config()
            return
        if a == "vis_menu":
            app.show_vis_menu(QCursor.pos())
            return
        lay = obj.layout_obj() if obj is not None else None
        cont = lay.container if lay is not None else None
        if a in ("switch", "switchtolayout") and cont is not None:
            self.switch_layout(cont, p)
        elif a in ("close", "close_window"):
            if cont is not None:
                self.show_container(cont, False)
        elif a == "toggle":
            if p.lower() in ("eq", "equalizer") and self.container(p) is None:
                app.eq.toggle()
            else:
                self.toggle(p)
        elif a in ("menu", "sysmenu", "controlmenu", "mainmenu"):
            app.show_main_menu(QCursor.pos())
        elif a in ("eq_preset", "eq_presets", "presets", "load_preset"):
            app.show_eq_presets_menu(QCursor.pos())
        elif a in ("pe_sel", "pe_misc"):
            app.show_sort_menu(QCursor.pos())
        elif a == "crossfade":
            pl.set_crossfade(0 if pl.crossfade else 5)
        else:
            log.debug("unhandled skin action %s (%s)", a, p)

    def popup_menu(self, menu_id: str, obj):
        """Winamp 5 menubar entries -> Zebamp's own menus."""
        app = self.app
        key = menu_id.split(":")[-1].strip().lower()
        if key == "file":
            m = app._menu()
            app._act(m, "Reproducir archivo…", app.open_files, "L")
            app._act(m, "Reproducir carpeta…", app.open_dir, "Shift+L")
            app._act(m, "Reproducir URL…", app.add_url_play, "Ctrl+L")
            m.addSeparator()
            app._act(m, "Cargar lista…", app.load_playlist)
            app._act(m, "Guardar lista…", app.save_playlist)
            m.addSeparator()
            app._act(m, "Información del archivo…", app.show_file_info, "Alt+3")
            m.addSeparator()
            app._act(m, "Salir", app.quit, "Ctrl+Q")
        elif key == "play":
            m = app.build_playback_menu(None)
        elif key == "options":
            m = app.build_options_menu(None)
            m.addMenu(app.build_skins_menu(m))
            vm = app.build_vis_menu(m)
            m.addMenu(vm)
        elif key == "view":
            m = app._menu()
            app._act(m, "Lista de reproducción", app.toggle_playlist_window, "Alt+E")
            app._act(m, "Ecualizador", app.toggle_eq_window, "Alt+G")
            app._act(m, "Biblioteca de medios", app.show_library, "Alt+L")
            app._act(m, "Explorador de skins", app.show_skin_browser, "Alt+S")
            m.addMenu(app.build_mpd_menu(m))
        elif key == "playlist":
            m = app._menu()
            app._act(m, "Añadir archivos…", app.add_files, "Insert")
            app._act(m, "Añadir carpeta…", app.add_dir)
            app._act(m, "Añadir URL…", app.add_url)
            m.addSeparator()
            app._act(m, "Vaciar lista", app.clear_playlist)
            app._act(m, "Quitar duplicados", app.remove_duplicates)
            app._act(m, "Quitar entradas que no existen", app.remove_dead)
            m.addSeparator()
            app._act(m, "Cargar lista…", app.load_playlist)
            app._act(m, "Guardar lista…", app.save_playlist)
            app._act(m, "Saltar a archivo…", app.show_jump_to_file, "J")
        elif key == "sort":
            m = app.build_sort_menu(None)
        elif key == "help":
            m = app.build_help_menu(None)
        else:
            m = app.build_main_menu()
        m.setPalette(getattr(app, "dialog_palette", m.palette()))
        app._last_menu = m
        m.exec(self.client_to_screen(obj, 0, obj.rect.height()))

    # ------------------------------------------------------------ new
    def maki_new(self, guid):
        n = class_name(guid or "")
        if n == "Timer":
            return MakiTimer(self)
        if n == "PopupMenu":
            return PopupMenu(self)
        if n in ("Group", "Layer", "Text", "Button", "GuiObject", "AnimatedLayer"):
            cls = {"Group": G.Group, "Layer": G.Layer, "Text": G.Text, "Button": G.Button,
                   "AnimatedLayer": G.AnimatedLayer}.get(n, G.GuiObj)
            return cls(Node(n.lower()), None, self)
        return MakiObj()


def freeform_dir() -> str | None:
    from ..config import DATA_DIR
    for d in (os.path.join(DATA_DIR, "freeform"),):
        if os.path.isdir(os.path.join(d, "xml")):
            return d
    return None


_late_tags()


def load_modern(path: str, app) -> ModernEngine | None:
    skin = ModernSkin(path, freeform_dir())
    if not skin.load():
        skin.vfs.close()
        return None
    themes = app.cfg["modern_gamma"] or {}
    skin.set_gamma(themes.get(path, skin.default_gamma()))
    eng = ModernEngine(app, skin)
    if not eng.build():
        skin.vfs.close()
        return None
    return eng
