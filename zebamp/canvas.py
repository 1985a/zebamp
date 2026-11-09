"""Helpers for the desktop-sized transparent canvas used to move skin windows
freely on Wayland (where an app cannot place its own top-level windows)."""
from __future__ import annotations

import json
import os
import subprocess

from PySide6.QtCore import QRect


def fit_to_workspace(widget) -> tuple[int, int] | None:
    """Size of the workspace holding `widget`; on sway also move it there."""
    if os.environ.get("SWAYSOCK"):
        try:
            tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True,
                                             text=True, timeout=2).stdout or "{}")
        except (OSError, ValueError, subprocess.SubprocessError):
            tree = None
        if tree:
            me, title = os.getpid(), widget.windowTitle()
            found = []

            def walk(n, ws):
                if n.get("type") == "workspace":
                    ws = n
                if n.get("pid") == me and n.get("name") == title and n.get("type") == "floating_con":
                    found.append((n, ws))
                for ch in n.get("nodes", []) + n.get("floating_nodes", []):
                    walk(ch, ws)
            walk(tree, None)
            if found and found[0][1] is not None:
                node, ws = found[0]
                r = ws["rect"]
                if (node["rect"]["x"], node["rect"]["y"]) != (r["x"], r["y"]):
                    subprocess.run(["swaymsg", f"[con_id={node['id']}] move absolute position {r['x']} {r['y']}"],
                                   capture_output=True, timeout=2)
                return int(r["width"]), int(r["height"])
    scr = widget.screen()
    if scr is not None:
        g = scr.availableGeometry()
        return g.width(), g.height()
    return None


def fit_to_desktop(widget):
    """Make `widget` cover every monitor's desktop.

    Returns (width, height, screens) where screens are the usable rect of each
    monitor in the widget's own coordinates, or None if unknown.  On sway the
    window is moved to the top-left of the union of the visible workspaces
    (bars excluded); sway draws floating windows across outputs, so skin
    windows can be dragged from one monitor to the other."""
    rects = []
    if os.environ.get("SWAYSOCK"):
        try:
            wss = json.loads(subprocess.run(["swaymsg", "-t", "get_workspaces"], capture_output=True,
                                            text=True, timeout=2).stdout or "[]")
            vis = [w for w in wss if w.get("visible")]
            vis.sort(key=lambda w: 0 if w.get("focused") else 1)      # focused monitor first
            rects = [QRect(w["rect"]["x"], w["rect"]["y"], w["rect"]["width"], w["rect"]["height"])
                     for w in vis]
        except (OSError, ValueError, subprocess.SubprocessError, KeyError):
            rects = []
    if not rects:
        from PySide6.QtGui import QGuiApplication
        rects = [s.availableGeometry() for s in QGuiApplication.screens()]
    if not rects:
        return None
    union = rects[0]
    for r in rects[1:]:
        union = union.united(r)
    if os.environ.get("SWAYSOCK"):
        _sway_move(widget, union.x(), union.y())
    screens = [r.translated(-union.x(), -union.y()) for r in rects]
    return union.width(), union.height(), screens, (union.x(), union.y()), (rects[0].x(), rects[0].y())


def _sway_move(widget, x, y):
    try:
        tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True,
                                         text=True, timeout=2).stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return
    me, title = os.getpid(), widget.windowTitle()
    found = []

    def walk(n):
        if n.get("pid") == me and n.get("name") == title and n.get("type") == "floating_con":
            found.append(n)
        for ch in n.get("nodes", []) + n.get("floating_nodes", []):
            walk(ch)
    walk(tree)
    if found and (found[0]["rect"]["x"], found[0]["rect"]["y"]) != (x, y):
        subprocess.run(["swaymsg", f"[con_id={found[0]['id']}] move absolute position {x} {y}"],
                       capture_output=True, timeout=2)


def keep_on_screens(r: QRect, screens: list[QRect], margin=40) -> tuple[int, int]:
    """(dx, dy) that brings rect r back onto the nearest monitor if it is
    (almost) entirely outside every monitor (e.g. below a smaller screen)."""
    if not screens:
        return 0, 0
    for sc in screens:
        inter = sc.intersected(r)
        if inter.width() >= min(margin, r.width()) and inter.height() >= min(14, r.height()):
            return 0, 0
    best = None
    for sc in screens:
        nx = min(max(r.x(), sc.x() - r.width() + margin), sc.x() + sc.width() - margin)
        ny = min(max(r.y(), sc.y()), sc.y() + sc.height() - 14)
        d = abs(nx - r.x()) + abs(ny - r.y())
        if best is None or d < best[0]:
            best = (d, nx - r.x(), ny - r.y())
    return best[1], best[2]


def snap_offsets(moving: list[QRect], static: list[QRect], canvas, snap: float):
    """Extra (dx, dy) that pulls the moving rects onto nearby edges.

    Edges of other windows win over the canvas (screen) edges."""
    def edges(m):
        return m.x(), m.x() + m.width(), m.y(), m.y() + m.height()

    best_x = best_y = None
    for m in moving:
        ml, mr, mt, mb = edges(m)
        for t in static:
            tl, tr, tt, tb = edges(t)
            if mt < tb + snap and mb > tt - snap:
                for d in (tr - ml, tl - mr, tl - ml, tr - mr):
                    if abs(d) <= snap and (best_x is None or abs(d) < abs(best_x)):
                        best_x = d
            if ml < tr + snap and mr > tl - snap:
                for d in (tb - mt, tt - mb, tt - mt, tb - mb):
                    if abs(d) <= snap and (best_y is None or abs(d) < abs(best_y)):
                        best_y = d
    ex = ey = None
    screens = canvas if isinstance(canvas, (list, tuple)) else [canvas]
    for m in moving:
        ml, mr, mt, mb = edges(m)
        for sc in screens:
            if not sc.intersects(m.adjusted(-int(snap), -int(snap), int(snap), int(snap))):
                continue
            for d in (sc.left() - ml, sc.x() + sc.width() - mr):
                if abs(d) <= snap and (ex is None or abs(d) < abs(ex)):
                    ex = d
            for d in (sc.top() - mt, sc.y() + sc.height() - mb):
                if abs(d) <= snap and (ey is None or abs(d) < abs(ey)):
                    ey = d
    return (best_x if best_x is not None else (ex or 0),
            best_y if best_y is not None else (ey or 0))


def touching(a: QRect, b: QRect, tol=1) -> bool:
    ar, br = a.x() + a.width(), b.x() + b.width()
    ab, bb = a.y() + a.height(), b.y() + b.height()
    v = a.y() < bb and b.y() < ab
    h = a.x() < br and b.x() < ar
    return (v and (abs(ar - b.x()) <= tol or abs(br - a.x()) <= tol)) or \
        (h and (abs(ab - b.y()) <= tol or abs(bb - a.y()) <= tol))


def fit_group(bb: QRect, screens: list[QRect]) -> tuple[int, int]:
    """(dx, dy) moving a whole group's bounding box fully onto the monitor it
    overlaps most (or the nearest one) when it doesn't fit where it is."""
    if not screens:
        return 0, 0
    for sc in screens:
        if sc.contains(bb):
            return 0, 0

    def score(sc):
        inter = sc.intersected(bb)
        area = inter.width() * inter.height() if inter.isValid() else 0
        cx = bb.center().x() - sc.center().x()
        cy = bb.center().y() - sc.center().y()
        return (-area, abs(cx) + abs(cy))
    sc = min(screens, key=score)
    nx = min(max(bb.x(), sc.x()), max(sc.x(), sc.x() + sc.width() - bb.width()))
    ny = min(max(bb.y(), sc.y()), max(sc.y(), sc.y() + sc.height() - bb.height()))
    return nx - bb.x(), ny - bb.y()


def workspace_rects() -> list:
    """Global rects of the visible workspace on each monitor (focused first)."""
    rects = []
    if os.environ.get("SWAYSOCK"):
        try:
            wss = json.loads(subprocess.run(["swaymsg", "-t", "get_workspaces"], capture_output=True,
                                            text=True, timeout=2).stdout or "[]")
            vis = [w for w in wss if w.get("visible")]
            vis.sort(key=lambda w: 0 if w.get("focused") else 1)
            rects = [QRect(w["rect"]["x"], w["rect"]["y"], w["rect"]["width"], w["rect"]["height"])
                     for w in vis]
        except (OSError, ValueError, subprocess.SubprocessError, KeyError):
            rects = []
    if not rects:
        from PySide6.QtGui import QGuiApplication
        rects = [sc.availableGeometry() for sc in QGuiApplication.screens()]
    return rects


def place_canvas(widget, chosen: list):
    """Size/move the canvas over the union of `chosen` monitor rects.

    Returns (width, height, screens_in_canvas_coords, origin)."""
    union = chosen[0]
    for r in chosen[1:]:
        union = union.united(r)
    if os.environ.get("SWAYSOCK"):
        _sway_move(widget, union.x(), union.y())
    if (widget.width(), widget.height()) != (union.width(), union.height()):
        widget.setFixedSize(union.width(), union.height())
    return union.width(), union.height(), [r.translated(-union.x(), -union.y()) for r in chosen], \
        (union.x(), union.y())


def home_monitors(rects: list, windows_global: list) -> list:
    """Monitors that hold skin windows.  The canvas only covers these, so the
    player belongs to one workspace instead of showing on every workspace of
    another monitor (sway draws floating windows across outputs)."""
    home = [r for r in rects if any(r.intersects(g) for g in windows_global)]
    return home or rects[:1]


class DragFrame:
    """Pointer bookkeeping for a canvas drag.

    The canvas only spans every monitor once the pointer really moved (a
    plain click must never move anything), and when the canvas is moved
    mid-drag, mouse events still queued in the old coordinate frame are
    recognised and translated instead of being read as a 2000 px jump."""

    THRESHOLD = 4

    def __init__(self, pt):
        self.start = pt
        self.last = pt
        self.moved = False
        self.spanned = False
        self.shifts: list[tuple[float, float]] = []

    def shift(self, sx: float, sy: float):
        """The canvas origin moved: points in the old frame are off by (sx, sy)."""
        if sx or sy:
            self.shifts.append((sx, sy))
            P = type(self.last)
            self.last = P(self.last.x() + sx, self.last.y() + sy)
            self.start = P(self.start.x() + sx, self.start.y() + sy)

    def fix(self, pt):
        best = pt
        bd = abs(pt.x() - self.last.x()) + abs(pt.y() - self.last.y())
        acc_x = acc_y = 0.0
        for sx, sy in reversed(self.shifts):
            acc_x += sx
            acc_y += sy
            alt = type(pt)(pt.x() + acc_x, pt.y() + acc_y)
            d = abs(alt.x() - self.last.x()) + abs(alt.y() - self.last.y())
            if d < bd:
                best, bd = alt, d
        self.last = best
        if not self.moved and (abs(best.x() - self.start.x()) + abs(best.y() - self.start.y())) > self.THRESHOLD:
            self.moved = True
        return best


def reaches_other_monitor(moving: list, canvas: QRect, all_screens: list) -> bool:
    """True when a dragged rect touches a monitor the canvas doesn't cover yet
    (the user is taking the window to the other screen)."""
    others = [sc for sc in all_screens if not canvas.contains(sc)]
    return any(r.intersects(sc) for r in moving for sc in others)
