"""Wasabi GUI objects (layers, buttons, text, sliders, groups, layouts...).

Each object knows how to lay itself out, paint itself and answer MAKI calls.
Unknown MAKI methods return a neutral default so skins keep running.
"""
from __future__ import annotations

import logging
import re
import time

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap

from .xmlparse import Node

log = logging.getLogger(__name__)
_TRACE = __import__("os").environ.get("ZEBAMP_MAKI_TRACE", "")


def _i(v, d=0) -> int:
    if v is None or v == "":
        return d
    try:
        return int(float(str(v).strip()))
    except ValueError:
        return d


_WINAMP = re.compile(r"\bwinamp\b", re.I)


def rebrand(text: str) -> str:
    """Skin captions say "WINAMP": show this program's name instead."""
    if not text or "inamp" not in text.lower():
        return text

    def sub(m):
        w = m.group(0)
        return "ZEBAMP" if w.isupper() else "zebamp" if w.islower() else "Zebamp"
    return _WINAMP.sub(sub, text)


_CELL_RATIO: dict = {}


def _em_for_cell(f: QFont, cell: int) -> int:
    """Windows/Winamp font sizes are the line (cell) height; Qt's pixel size
    is the em.  Convert so text has the size the skin was designed for."""
    key = (f.family(), f.bold(), f.italic())
    r = _CELL_RATIO.get(key)
    if r is None:
        g = QFont(f)
        g.setPixelSize(100)
        fm = QFontMetrics(g)
        r = max(1.0, min(1.6, (fm.ascent() + fm.descent()) / 100.0))
        _CELL_RATIO[key] = r
    return max(5, round(cell / r))


def _b(v, d=False) -> bool:
    if v is None or v == "":
        return d
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class GuiObj:
    cls = "GuiObject"
    interactive = False

    def __init__(self, node: Node | None, parent: GuiObj | None, engine, params=None):
        self.node = node
        self.parent = parent
        self.engine = engine
        self.params: dict = dict(params if params is not None else (node.attrs if node else {}))
        self.id = self.params.get("id", "")
        self.children: list[GuiObj] = []
        self.visible = _b(self.params.get("visible"), True)
        self.alpha = _i(self.params.get("alpha"), 255)
        self.ghost = _b(self.params.get("ghost"), False)
        self.enabled = True
        self.rect = QRect(0, 0, 0, 0)
        self._override: dict = {}
        self._target = None
        self.hover = False
        self.pressed = False

    # ---------------------------------------------------------- tree
    @property
    def skin(self):
        return self.engine.skin

    def layout_obj(self) -> Layout | None:
        o = self
        while o is not None and not isinstance(o, Layout):
            o = o.parent
        return o

    def is_shown(self) -> bool:
        """Visible itself and inside visible parents, with a real size."""
        if self.rect.width() <= 1 or self.rect.height() <= 1:
            return False
        o = self
        while o is not None:
            if not o.visible:
                return False
            o = o.parent
        return True

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, oid: str) -> GuiObj | None:
        oid = (oid or "").lower()
        if not oid:
            return None
        for c in self.children:
            if c.id.lower() == oid:
                return c
        for c in self.children:
            r = c.find(oid)
            if r is not None:
                return r
        return None

    def build(self):
        pass

    # -------------------------------------------------------- geometry
    def p(self, key, default=None):
        return self.params.get(key, default)

    def natural_size(self) -> tuple[int, int]:
        return 0, 0

    def _coord(self, val, relat, size):
        r = str(relat or "0").strip()
        if r == "1":
            return size + val
        if r == "2":
            return size * val // 100
        return val

    def compute_rect(self, parent: QRect):
        nw, nh = self.natural_size()
        if _b(self.p("fitparent")):
            self.rect = QRect(parent)
        else:
            x = self._coord(_i(self.p("x"), 0), self.p("relatx"), parent.width())
            y = self._coord(_i(self.p("y"), 0), self.p("relaty"), parent.height())
            w_raw, h_raw = self.p("w"), self.p("h")
            w = self._coord(_i(w_raw, nw), self.p("relatw"), parent.width()) if w_raw not in (None, "") else (
                nw if nw else (parent.width() - x if self.fills_parent() else 0))
            h = self._coord(_i(h_raw, nh), self.p("relath"), parent.height()) if h_raw not in (None, "") else (
                nh if nh else (parent.height() - y if self.fills_parent() else 0))
            self.rect = QRect(parent.x() + x, parent.y() + y, max(0, w), max(0, h))
        for c in self.children:
            c.compute_rect(self.rect)

    def fills_parent(self) -> bool:
        return False

    # -------------------------------------------------------- painting
    def paint(self, p: QPainter):
        if not self.visible or self.alpha <= 0:
            return
        if self._sysregion_cut():
            return     # drawn by the layout as a cut-out, not as an image
        clip = self.engine._clip
        if clip is not None and not isinstance(self, Layout) and not clip.intersects(self.rect):
            return
        try:
            self._paint(p)
        except Exception as e:
            if not getattr(self, "_paint_err", False):
                self._paint_err = True
                log.warning("paint %s %s: %s", self.cls, self.id, e)

    def _paint(self, p: QPainter):
        if self.alpha < 255:
            p.save()
            try:
                p.setOpacity(p.opacity() * self.alpha / 255.0)
                self.paint_self(p)
                for c in self.children:
                    c.paint(p)
            finally:
                p.restore()
        else:
            self.paint_self(p)
            for c in self.children:
                c.paint(p)
        if self.children:
            self._apply_cuts(p)

    def _apply_cuts(self, p: QPainter):
        """Wasabi sysregion="-1"/"-2" layers carve the window shape.  A cut
        belongs to its own group: it removes what that group (and anything
        under it) drew, never the groups painted on top later -- otherwise
        the EQ drawer's side cut-outs would eat the player's edges."""
        cuts = self.__dict__.get("_own_cuts")
        if cuts is None:
            cuts = [c for c in self.children if isinstance(c, GuiObj) and c._sysregion_cut()]
            self._own_cuts = cuts
        if not cuts:
            return
        clip = self.engine._clip
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        for o in cuts:
            if not o.visible or not o.rect.isValid() or (clip is not None and not clip.intersects(o.rect)):
                continue
            try:
                o.paint_self(p)
            except Exception:
                pass
        p.restore()

    def paint_self(self, p: QPainter):
        pass

    def _sysregion_cut(self) -> bool:
        v = self.params.get("sysregion")
        return v is not None and str(v).strip().startswith("-")

    def draw_pix(self, p: QPainter, pm: QPixmap | None, r: QRect | None = None, tile=False):
        if pm is None or pm.isNull():
            return
        r = r or self.rect
        if r.width() <= 0 or r.height() <= 0:
            return
        if (pm.width(), pm.height()) == (r.width(), r.height()):
            p.drawPixmap(r.topLeft(), pm)
        elif tile:
            p.drawTiledPixmap(r, pm)
        else:
            p.drawPixmap(r, pm)

    # ----------------------------------------------------------- input
    def hit(self, pt: QPoint) -> GuiObj | None:
        if not self.visible:
            return None
        for c in reversed(self.children):
            r = c.hit(pt)
            if r is not None:
                return r
        if self.ghost or not self.rect.contains(pt):
            return None
        if self.is_opaque_at(pt):
            return self
        return None

    def is_opaque_at(self, pt) -> bool:
        return True

    def update(self):
        self.engine.request_repaint(self)

    # ----------------------------------------------------------- MAKI
    def maki_call(self, name: str, args: list):
        fn = getattr(self, "m_" + name, None)
        if fn is None:
            if name.startswith("on"):
                # Scripts may call an event like a method: run its handlers.
                return self.engine.vm.dispatch(self, name, [("ANY", a) for a in args])
            (log.warning if _TRACE else log.debug)("MAKI missing: %s.%s", self.cls, name)
            return None
        try:
            return fn(*args)
        except TypeError:
            try:
                return fn(*args[: fn.__code__.co_argcount - 1])
            except Exception as e:
                log.debug("MAKI %s.%s%r: %s", self.cls, name, args, e)
                return None
        except Exception as e:
            log.debug("MAKI %s.%s%r: %s", self.cls, name, args, e)
            return None

    def fire(self, event: str, *args):
        n = self.engine.vm.dispatch(self, event, list(args))
        # embed_xui: an XUI group "is" its embedded object (e.g. Bento's tab
        # buttons): clicks on the inner button are also the group's clicks.
        g = self.parent
        while g is not None and not isinstance(g, Layout):
            gd = getattr(g, "groupdef", None)
            emb = gd.get("embed_xui") if gd is not None else None
            if emb:
                if emb.lower() == (self.id or "").lower():
                    n += self.engine.vm.dispatch(g, event, list(args))
                break
            g = g.parent
        return n

    # Object
    def m_getclassname(self):
        return self.cls

    def m_getid(self):
        return self.id

    def m_onnotify(self, *a):
        return 0

    # GuiObject
    # Tabs for features Zebamp doesn't have (video playback, web browser).
    UNSUPPORTED = {"switch.video", "switch.browser"}

    def _keep_visible(self) -> bool:
        """Seek bars stay on screen while a song is loaded (Bento's seek
        script hides them on release, relying on Winamp to show them again)."""
        if isinstance(self, ProgressGrid) or (isinstance(self, Slider) and
                                             (self.p("action") or "").lower() == "seek"
                                             and not _b(self.p("ghost"))):
            return self.engine.app.player.state in ("play", "pause")
        return False

    def m_show(self):
        if (self.id or "").lower() in self.UNSUPPORTED:
            return
        if not self.visible:
            self.visible = True
            self.fire("onsetvisible", ("BOOLEAN", 1))
            self.update()

    def m_hide(self):
        if self._keep_visible():
            return
        if self.visible:
            self.visible = False
            self.fire("onsetvisible", ("BOOLEAN", 0))
            self.update()

    def m_isvisible(self):
        return self.visible

    def m_setalpha(self, a):
        self.alpha = max(0, min(255, int(a)))
        self.update()

    def m_getalpha(self):
        return self.alpha

    def _rel(self):
        pr = self.parent.rect if self.parent is not None else QRect()
        return self.rect.x() - pr.x(), self.rect.y() - pr.y()

    def m_getleft(self):
        return self._rel()[0]

    def m_gettop(self):
        return self._rel()[1]

    def m_getwidth(self):
        return self.rect.width()

    def m_getheight(self):
        return self.rect.height()

    def m_resize(self, x, y, w, h):
        self.params.update({"x": str(int(x)), "y": str(int(y)), "w": str(int(w)), "h": str(int(h)),
                            "relatx": "0", "relaty": "0", "relatw": "0", "relath": "0"})
        self.relayout()

    def relayout(self):
        if self.parent is not None:
            self.compute_rect(self.parent.rect)
        elif isinstance(self, Layout):
            self.compute_rect(QRect(0, 0, self.rect.width(), self.rect.height()))
        self.engine.request_repaint(self, full=True)

    def m_getguix(self):
        return _i(self.p("x"))

    def m_getguiy(self):
        return _i(self.p("y"))

    def m_getguiw(self):
        return _i(self.p("w"), self.rect.width())

    def m_getguih(self):
        return _i(self.p("h"), self.rect.height())

    def m_getguirelatx(self):
        return _i(self.p("relatx"))

    def m_getguirelaty(self):
        return _i(self.p("relaty"))

    def m_getguirelatw(self):
        return _i(self.p("relatw"))

    def m_getguirelath(self):
        return _i(self.p("relath"))

    def m_getautowidth(self):
        return self.natural_size()[0] or self.rect.width()

    def m_getautoheight(self):
        return self.natural_size()[1] or self.rect.height()

    def m_setxmlparam(self, name, value):
        name = str(name).lower()
        self.params[name] = str(value)
        self.on_param(name, str(value))
        if name in ("x", "y", "w", "h", "relatx", "relaty", "relatw", "relath", "fitparent"):
            self.relayout()
        elif name == "visible":
            self.visible = _b(value, True)
        elif name == "alpha":
            self.alpha = _i(value, 255)
        elif name == "ghost":
            self.ghost = _b(value)
        self.update()

    def on_param(self, name, value):
        pass

    def m_getxmlparam(self, name):
        return self.params.get(str(name).lower(), "")

    def m_getparent(self):
        return self.parent

    def m_getparentlayout(self):
        return self.layout_obj()

    def m_ismouseoverrect(self):
        lay, pt = getattr(self.engine, "last_mouse", (None, None))
        return 1 if lay is not None and lay is self.layout_obj() and self.rect.contains(pt) else 0

    def m_ismouseover(self, *a):
        return self.m_ismouseoverrect()

    def m_leftclick(self):
        self.fire("onleftclick")

    def m_rightclick(self):
        self.fire("onrightclick")

    def m_gettopparent(self):
        return self.layout_obj()

    def m_isactive(self):
        return True

    def m_setenabled(self, on):
        self.enabled = bool(on)

    def m_getenabled(self):
        return self.enabled

    def m_setfocus(self):
        pass

    def m_bringtofront(self):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
            self.parent.children.append(self)
            self.update()

    def m_bringtoback(self):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
            self.parent.children.insert(0, self)
            self.update()

    def m_clienttoscreenx(self, x):
        return self.engine.client_to_screen(self, int(x), 0).x()

    def m_clienttoscreeny(self, y):
        return self.engine.client_to_screen(self, 0, int(y)).y()

    def m_screentoclientx(self, x):
        return int(x) - self.engine.client_to_screen(self, 0, 0).x()

    def m_screentoclienty(self, y):
        return int(y) - self.engine.client_to_screen(self, 0, 0).y()

    def m_getmouseposx(self):
        return self.engine.mouse_in(self).x()

    def m_getmouseposy(self):
        return self.engine.mouse_in(self).y()

    def m_sendaction(self, action, param, x, y, p1, p2):
        return 0

    def m_getnumchildren(self):
        return len(self.children)

    def m_getscroll(self):
        return 0

    def m_setposition(self, v):
        """Wasabi:Frame divider: v = size of the left/top pane in pixels."""
        sp = getattr(self, "split", None)
        if not sp or not sp.get("vertical"):
            return
        total = self.rect.width()
        gap = sp["gap"]
        v = int(v)
        if total > 0:
            v = max(0, min(v, total - gap - sp["min"]))
        left = self.find(sp["left"]) if sp["left"] else None
        right = self.find(sp["right"]) if sp["right"] else None
        if left is not None:
            left.params.update({"x": "0", "w": str(v), "relatw": "0", "relatx": "0"})
        if right is not None:
            right.params.update({"x": str(v + gap), "relatx": "0", "w": str(-(v + gap)), "relatw": "1"})
        self.split_pos = v
        self.relayout()
        self.update()

    def m_getposition(self):
        return getattr(self, "split_pos", 0)

    def m_setactivated(self, on):
        pass

    def m_getactivated(self):
        return 0

    def m_findobject(self, oid):
        # Wasabi searches the object's own subtree first (a line group asking
        # for its "text" must get its own text, not the first one in the window)
        r = self.find(oid) if self.children else None
        if r is not None:
            return r
        lay = self.layout_obj()
        return lay.find(oid) if lay is not None else None

    def m_init(self, parent):
        """Attach a dynamically created object to `parent`."""
        if parent is None:
            return
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = parent
        parent.children.append(self)
        self.engine.tree_changed()
        self.relayout()
        self.engine.start_scripts(self)

    # target animation ---------------------------------------------
    def _tgt(self):
        if self._target is None:
            x, y = self._rel()
            self._target = {"x": x, "y": y, "w": self.rect.width(), "h": self.rect.height(),
                            "a": self.alpha, "speed": 0.2}
        return self._target

    def m_settargetx(self, v):
        self._tgt()["x"] = int(v)

    def m_settargety(self, v):
        self._tgt()["y"] = int(v)

    def m_settargetw(self, v):
        self._tgt()["w"] = int(v)

    def m_settargeth(self, v):
        self._tgt()["h"] = int(v)

    def m_settargeta(self, v):
        self._tgt()["a"] = int(v)

    def m_settargetspeed(self, s):
        self._tgt()["speed"] = max(0.0, float(s))

    def m_gototarget(self):
        t = self._tgt()
        x, y = self._rel()
        t["from"] = (x, y, self.rect.width(), self.rect.height(), self.alpha)
        t["start"] = time.monotonic()
        self.engine.animate(self)

    def m_istargetreached(self):
        return self._target is None or "start" not in self._target

    def m_canceltarget(self):
        self._target = None

    def step_target(self) -> bool:
        """Advance the target animation; returns False when finished."""
        t = self._target
        if not t or "start" not in t:
            return False
        dur = t.get("speed", 0.2)
        k = 1.0 if dur <= 0 else min(1.0, (time.monotonic() - t["start"]) / dur)
        fx, fy, fw, fh, fa = t["from"]
        def lerp(a, b):
            return int(round(a + (b - a) * k))
        self.params.update({"x": str(lerp(fx, t["x"])), "y": str(lerp(fy, t["y"])),
                            "w": str(lerp(fw, t["w"])), "h": str(lerp(fh, t["h"])),
                            "relatx": "0", "relaty": "0", "relatw": "0", "relath": "0"})
        self.alpha = lerp(fa, t["a"])
        self.relayout()
        if k >= 1.0:
            self._target = None
            self.fire("ontargetreached")
            return False
        return True


class Group(GuiObj):
    cls = "Group"

    def __init__(self, node, parent, engine, groupdef: Node | None = None, params=None):
        merged = {}
        if groupdef is not None:
            merged.update(groupdef.attrs)
        merged.update(params if params is not None else (node.attrs if node else {}))
        # an instance's id wins over the groupdef id
        if node is not None and node.get("id"):
            merged["id"] = node.get("id")
        if node is not None and node.get("instanceid"):
            merged["id"] = node.get("instanceid")
        super().__init__(node, parent, engine, merged)
        self.groupdef = groupdef
        self.background = self.params.get("background")
        self.scripts = []

    def fills_parent(self) -> bool:
        return True

    def natural_size(self):
        bg = self.skin.bitmap(self.background) if self.background else None
        if bg is not None:
            return bg.width(), bg.height()
        gd = self.groupdef
        if gd is not None:
            return _i(gd.get("w") or gd.get("default_w")), _i(gd.get("h") or gd.get("default_h"))
        return 0, 0

    def build(self):
        src = self.groupdef if self.groupdef is not None else self.node
        if src is not None:
            self.engine.build_children(self, src)

    def paint_self(self, p):
        if self.background and _b(self.p("drawbackground"), True):
            self.draw_pix(p, self.skin.bitmap(self.background))

    def is_opaque_at(self, pt):
        return bool(self.background)

    def _paint(self, p):
        p.save()
        try:
            if not isinstance(self, Layout):
                p.setClipRect(self.rect, Qt.ClipOperation.IntersectClip)
            GuiObj._paint(self, p)
        finally:
            p.restore()

    def hit(self, pt):
        if not isinstance(self, Layout) and not self.rect.contains(pt):
            return None
        return GuiObj.hit(self, pt)

    def m_getobject(self, oid):
        return self.find(oid)

    def m_getnumobjects(self):
        return len(self.children)

    def m_enumobject(self, i):
        i = int(i)
        return self.children[i] if 0 <= i < len(self.children) else None

    def m_islayout(self):
        return isinstance(self, Layout)

    def compute_rect(self, parent):
        src = self.p("autowidthsource")
        if src and self.p("w") in (None, ""):
            o = self.find(src)
            if o is not None:
                w = o.natural_size()[0]
                if w:
                    self.params["w"] = str(w + _i(o.p("x")))
        src = self.p("autoheightsource")
        if src and self.p("h") in (None, ""):
            o = self.find(src)
            if o is not None:
                h = o.natural_size()[1]
                if h:
                    self.params["h"] = str(h + _i(o.p("y")))
        GuiObj.compute_rect(self, parent)

    def m_autoresize(self):
        pass


class Layout(Group):
    cls = "Layout"

    def __init__(self, node, container, engine):
        super().__init__(node, None, engine)
        self.container = container
        self.scale = 1.0
        bg = self.skin.bitmap(self.background) if self.background else None
        w = _i(self.p("w"), bg.width() if bg else 0) or _i(self.p("default_w"), 0)
        h = _i(self.p("h"), bg.height() if bg else 0) or _i(self.p("default_h"), 0)
        self.rect = QRect(0, 0, max(1, w or 275), max(1, h or 116))
        self.snap_adjust = tuple(_i(self.p("snapadjust" + k), 0)
                                 for k in ("left", "top", "right", "bottom"))

    def min_max(self):
        mw = _i(self.p("minimum_w"), 0)
        mh = _i(self.p("minimum_h"), 0)
        xw = _i(self.p("maximum_w"), 0)
        xh = _i(self.p("maximum_h"), 0)
        return mw, mh, xw, xh

    def set_size(self, w, h):
        mw, mh, xw, xh = self.min_max()
        w = max(w, mw, 16)
        h = max(h, mh, 8)
        if xw:
            w = min(w, xw)
        if xh:
            h = min(h, xh)
        self.rect = QRect(0, 0, int(w), int(h))
        self.compute_rect(self.rect)

    def compute_rect(self, parent):
        self.rect = QRect(0, 0, self.rect.width(), self.rect.height())
        for c in self.children:
            c.compute_rect(self.rect)

    def paint_self(self, p):
        if self.background and _b(self.p("drawbackground"), True):
            pm = self.skin.bitmap(self.background)
            if pm is not None:
                p.drawPixmap(0, 0, pm)

    def is_opaque_at(self, pt):
        return True

    def m_getcontainer(self):
        return self.container

    def m_center(self):
        pass

    def m_resize(self, x, y, w, h):
        self.set_size(int(w), int(h))
        self.engine.layout_resized(self)

    def m_getscale(self):
        return 1.0

    def m_setscale(self, s):
        pass

    def m_setdesktopalpha(self, on):
        pass

    def m_getdesktopalpha(self):
        return 1

    def m_istransparencysafe(self):
        return 1

    def m_islayoutanimationsafe(self):
        return 1

    def m_snapadjust(self, *a):
        try:
            self.snap_adjust = tuple(int(v) for v in a[:4])
        except (TypeError, ValueError):
            return
        w = self.container.window if self.container else None
        if w is not None and w.dock is not None:
            w.dock.schedule()

    def m_setredrawonresize(self, on):
        pass

    def m_beforeredock(self):
        pass

    def m_redock(self):
        pass

    def m_getleft(self):
        return self.engine.window_pos(self).x()

    def m_gettop(self):
        return self.engine.window_pos(self).y()


class Container:
    cls = "Container"

    def __init__(self, node: Node, engine):
        self.node = node
        self.engine = engine
        self.id = node.get("id", "")
        self.name = node.get("name", self.id)
        self.layouts: list[Layout] = []
        self.current: Layout | None = None
        dv = node.get("default_visible")
        # Dynamic containers are templates/components (hold="@all@" frames,
        # library, video…): only shown when the skin asks for them explicitly.
        dyn_default = not _b(node.get("dynamic"))
        self.visible = _b(dv, dyn_default) if dv is None or not dv.startswith("@") else False
        if node.get("hold"):
            self.visible = False
        self.window = None

    def maki_call(self, name, args):
        fn = getattr(self, "m_" + name, None)
        if fn is None:
            return None
        try:
            return fn(*args)
        except Exception as e:
            log.debug("MAKI Container.%s: %s", name, e)
            return None

    def layout(self, lid) -> Layout | None:
        lid = (lid or "").lower()
        for lay in self.layouts:
            if lay.id.lower() == lid:
                return lay
        return None

    def m_getid(self):
        return self.id

    def m_getclassname(self):
        return "Container"

    def m_getlayout(self, lid):
        return self.layout(lid)

    def m_getnumlayouts(self):
        return len(self.layouts)

    def m_enumlayout(self, i):
        i = int(i)
        return self.layouts[i] if 0 <= i < len(self.layouts) else None

    def m_getcurlayout(self):
        return self.current

    def m_switchtolayout(self, lid):
        self.engine.switch_layout(self, str(lid))

    def m_show(self):
        self.engine.show_container(self, True)

    def m_hide(self):
        self.engine.show_container(self, False)

    def m_close(self):
        self.engine.show_container(self, False)

    def m_toggle(self):
        self.engine.show_container(self, not self.visible)

    def m_isvisible(self):
        return self.visible

    def m_getname(self):
        return self.name

    def m_setname(self, n):
        self.name = str(n)

    def m_getguid(self):
        return self.node.get("component", "")

    def m_isdynamic(self):
        return 0

    def m_onnotify(self, *a):
        return 0


class Grid(GuiObj):
    """<grid>: a box drawn from up to nine bitmaps (corners, edges, middle)."""

    cls = "Grid"
    PARTS = ("topleft", "top", "topright", "left", "middle", "right",
             "bottomleft", "bottom", "bottomright")

    def natural_size(self):
        return 0, 0

    def _pm(self, k):
        v = self.p(k)
        return self.skin.bitmap(v) if v else None

    def paint_grid(self, p, r: QRect):
        if r.width() <= 0 or r.height() <= 0:
            return
        pm = {k: self._pm(k) for k in self.PARTS}

        def w(*ks):
            return max([pm[k].width() for k in ks if pm[k] is not None] or [0])

        def h(*ks):
            return max([pm[k].height() for k in ks if pm[k] is not None] or [0])
        top_h = h("topleft", "top", "topright")
        bot_h = h("bottomleft", "bottom", "bottomright")
        left_w = w("topleft", "left", "bottomleft")
        right_w = w("topright", "right", "bottomright")
        if top_h + bot_h > r.height():
            top_h = bot_h = r.height() // 2
        if left_w + right_w > r.width():
            left_w = right_w = r.width() // 2
        xs = (r.x(), r.x() + left_w, r.right() + 1 - right_w, r.right() + 1)
        ys = (r.y(), r.y() + top_h, r.bottom() + 1 - bot_h, r.bottom() + 1)
        for row, names in enumerate((("topleft", "top", "topright"), ("left", "middle", "right"),
                                     ("bottomleft", "bottom", "bottomright"))):
            for col, k in enumerate(names):
                m = pm[k]
                cell = QRect(xs[col], ys[row], xs[col + 1] - xs[col], ys[row + 1] - ys[row])
                if m is not None and cell.width() > 0 and cell.height() > 0:
                    self.draw_pix(p, m, cell)

    def paint_self(self, p):
        self.paint_grid(p, self.rect)

    def is_opaque_at(self, pt):
        return any(self.p(k) for k in self.PARTS)


class ProgressGrid(Grid):
    """<ProgressGrid>: grid filled up to the playback position."""

    cls = "ProgressGrid"

    def fraction(self) -> float:
        pl = self.engine.app.player
        d = pl.duration
        if pl.state == "stop" or not d:
            return 0.0
        return max(0.0, min(1.0, pl.elapsed / d))

    def paint_self(self, p):
        f = self.fraction()
        if f <= 0:
            return
        r = self.rect
        o = (self.p("orientation") or "right").lower()
        if o in ("left",):
            w = int(r.width() * f)
            part = QRect(r.right() + 1 - w, r.y(), w, r.height())
        elif o in ("down", "bottom"):
            part = QRect(r.x(), r.y(), r.width(), int(r.height() * f))
        elif o in ("up", "top"):
            hh = int(r.height() * f)
            part = QRect(r.x(), r.bottom() + 1 - hh, r.width(), hh)
        else:
            part = QRect(r.x(), r.y(), int(r.width() * f), r.height())
        p.save()
        p.setClipRect(part, Qt.ClipOperation.IntersectClip)
        self.paint_grid(p, r)
        p.restore()

    def is_opaque_at(self, pt):
        return False


class RectObj(GuiObj):
    """<rect color=.. filled=..>: a plain (optionally filled) rectangle."""

    cls = "GuiObject"

    def natural_size(self):
        return 0, 0

    def paint_self(self, p):
        c = self.skin.color(self.p("color"), QColor(0, 0, 0)) or QColor(0, 0, 0)
        r = self.rect
        if _b(self.p("filled")):
            p.fillRect(r, c)
        else:
            p.setPen(c)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(0, 0, -1, -1))

    def is_opaque_at(self, pt):
        return _b(self.p("filled"))


class WidgetHost(GuiObj):
    """Slot where a real Qt widget (our media library) is embedded."""

    cls = "GuiObject"

    def __init__(self, node, parent, engine, kind="library"):
        super().__init__(node, parent, engine)
        self.kind = kind
        self.widget = None

    def fills_parent(self):
        return True

    def natural_size(self):
        return 0, 0

    def shown(self) -> bool:
        q = self
        while q is not None:
            if not q.visible:
                return False
            if isinstance(q, Layout):
                return q.container is not None and q.container.current is q
            q = q.parent
        return False

    def is_opaque_at(self, pt):
        return True

    interactive = True


class Layer(GuiObj):
    cls = "Layer"

    def natural_size(self):
        pm = self.skin.bitmap(self.p("image"))
        return (pm.width(), pm.height()) if pm is not None else (0, 0)

    def paint_self(self, p):
        self.draw_pix(p, self.skin.bitmap(self.p("image")), tile=_b(self.p("tile")))

    def is_opaque_at(self, pt):
        pm = self.skin.bitmap(self.p("image"))
        if pm is None:
            return False
        img = self.engine.image_cache(self.p("image"))
        if img is None:
            return True
        x = (pt.x() - self.rect.x()) * img.width() // max(1, self.rect.width())
        y = (pt.y() - self.rect.y()) * img.height() // max(1, self.rect.height())
        if 0 <= x < img.width() and 0 <= y < img.height():
            return QColor.fromRgba(img.pixel(x, y)).alpha() > 8
        return False

    @property
    def interactive(self):
        return bool(self.p("resize")) or bool(self.p("dblclickaction"))

    def m_setregionfrommap(self, *a):
        pass

    def m_setregion(self, *a):
        pass

    def m_isinvalid(self):
        return 0

    def m_fx_setenabled(self, *a):
        pass

    def m_fx_update(self):
        pass


class AnimatedLayer(Layer):
    cls = "AnimatedLayer"

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.frame = 0
        self.start_frame = 0
        self.end_frame = -1
        self.speed = _i(self.p("speed"), 200)
        self.autoreplay = _b(self.p("autoreplay"), True)
        self.playing = _b(self.p("autoplay"))
        self.paused = False
        self.direction = 1
        if self.playing:
            engine.animate_layer(self)

    def _frames(self):
        pm = self.skin.bitmap(self.p("image"))
        if pm is None:
            return 1, pm, True
        fw = _i(self.p("framewidth"), 0) or _i(self.p("w"), 0) or pm.width()
        fh = _i(self.p("frameheight"), 0) or _i(self.p("h"), 0) or pm.height()
        if pm.width() > fw:
            return max(1, pm.width() // max(1, fw)), pm, True
        return max(1, pm.height() // max(1, fh)), pm, False

    def natural_size(self):
        n, pm, horiz = self._frames()
        if pm is None:
            return 0, 0
        return (pm.width() // n, pm.height()) if horiz else (pm.width(), pm.height() // n)

    def paint_self(self, p):
        n, pm, horiz = self._frames()
        if pm is None:
            return
        f = max(0, min(n - 1, self.frame))
        if horiz:
            fw = pm.width() // n
            src = QRect(f * fw, 0, fw, pm.height())
        else:
            fh = pm.height() // n
            src = QRect(0, f * fh, pm.width(), fh)
        p.drawPixmap(self.rect, pm, src)

    def tick(self) -> bool:
        if not self.playing or self.paused:
            return False
        n = self._frames()[0]
        end = self.end_frame if self.end_frame >= 0 else n - 1
        start = self.start_frame
        if self.frame == end:
            if self.autoreplay:
                self.frame = start
            else:
                self.playing = False
                self.fire("onstop")
                return False
        else:
            self.frame += 1 if end >= start else -1
            self.frame = max(0, min(n - 1, self.frame))
        self.fire("onframe", ("INT", self.frame))
        self.update()
        return True

    def m_play(self):
        self.playing = True
        self.paused = False
        self.engine.animate_layer(self)
        self.fire("onplay")

    def m_pause(self):
        self.paused = True
        self.fire("onpause")

    def m_stop(self):
        self.playing = False
        self.fire("onstop")

    def m_isplaying(self):
        return self.playing and not self.paused

    def m_ispaused(self):
        return self.paused

    def m_isstopped(self):
        return not self.playing

    def m_setspeed(self, ms):
        self.speed = max(10, int(ms))

    def m_gotoframe(self, f):
        self.frame = int(f)
        self.update()

    def m_getcurframe(self):
        return self.frame

    def m_setstartframe(self, f):
        self.start_frame = int(f)

    def m_setendframe(self, f):
        self.end_frame = int(f)

    def m_getstartframe(self):
        return self.start_frame

    def m_getendframe(self):
        return self.end_frame if self.end_frame >= 0 else self._frames()[0] - 1

    def m_getlength(self):
        return self._frames()[0]

    def m_setautoreplay(self, on):
        self.autoreplay = bool(on)

    def m_getautoreplay(self):
        return self.autoreplay

    def m_getdirection(self):
        return self.direction

    def m_setrealtime(self, on):
        pass


class Button(GuiObj):
    cls = "Button"
    interactive = True

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.activated = False

    def natural_size(self):
        pm = self.skin.bitmap(self.p("image"))
        return (pm.width(), pm.height()) if pm is not None else (0, 0)

    def current_image(self):
        if self.pressed and self.p("downimage"):
            return self.p("downimage")
        if self.activated and self.p("activeimage"):
            return self.p("activeimage")
        if self.hover and self.p("hoverimage"):
            return self.p("hoverimage")
        return self.p("image")

    def paint_self(self, p):
        self.draw_pix(p, self.skin.bitmap(self.current_image()))

    def is_opaque_at(self, pt):
        if _b(self.p("rectrgn"), False) or not self.p("image"):
            return True
        img = self.engine.image_cache(self.p("image"))
        if img is None:
            return True
        x = (pt.x() - self.rect.x()) * img.width() // max(1, self.rect.width())
        y = (pt.y() - self.rect.y()) * img.height() // max(1, self.rect.height())
        if 0 <= x < img.width() and 0 <= y < img.height():
            return QColor.fromRgba(img.pixel(x, y)).alpha() > 8
        return True

    def click(self):
        self.engine.do_action(self.p("action"), self.p("param"), self)
        self.fire("onleftclick")

    def m_setactivated(self, on):
        on = bool(on)
        if on != self.activated:
            self.activated = on
            self.fire("onactivate", ("INT", 1 if on else 0))
            self.update()

    def m_setactivatednocallback(self, on):
        self.activated = bool(on)
        self.update()

    def m_getactivated(self):
        return self.activated

    def m_leftclick(self):
        self.click()

    def m_rightclick(self):
        self.fire("onrightclick")


class ToggleButton(Button):
    cls = "ToggleButton"

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.activated = engine.cfg_toggle_state(self)

    def click(self):
        # Decide from the live MPD/config state, not a possibly stale flag.
        self.activated = not self.engine.cfg_toggle_state(self)
        self.engine.cfg_toggle_set(self, self.activated)
        self.engine.do_action(self.p("action"), self.p("param"), self)
        self.fire("ontoggle", ("INT", 1 if self.activated else 0))
        self.fire("onleftclick")
        self.update()

    def refresh_state(self):
        st = self.engine.cfg_toggle_state(self)
        if st != self.activated:
            self.activated = st
            self.update()

    def m_getcurcfgval(self):
        return 1 if self.activated else 0


class NStatesButton(Button):
    """Multi-state button: images are <image><state> (e.g. shuffle.normal0/1).

    With cfgattrib it mirrors a setting: shuffle (2 states) or repeat
    (cfgvals="0;1;-1": off / playlist / track)."""

    cls = "Button"

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.state = 0
        self.nstates = max(1, _i(self.p("nstates"), 2))
        vals = [v.strip() for v in (self.p("cfgvals") or "").split(";") if v.strip()]
        self.cfgvals = vals or [str(i) for i in range(self.nstates)]

    def _img(self, key):
        base = self.p(key)
        if not base:
            return None
        cand = f"{base}{self.state}"
        if self.skin.bitmap(cand) is not None:
            return cand
        return base if self.skin.bitmap(base) is not None else None

    def natural_size(self):
        self.sync_state()
        pm = self.skin.bitmap(self._img("image"))
        return (pm.width(), pm.height()) if pm is not None else (0, 0)

    def sync_state(self):
        if not self.p("cfgattrib"):
            return
        val = self.engine.cfg_nstate_value(self)
        if val is not None and val in self.cfgvals:
            self.state = self.cfgvals.index(val)

    def current_image(self):
        self.sync_state()
        if self.pressed and self.p("downimage"):
            return self._img("downimage") or self._img("image")
        if self.hover and self.p("hoverimage"):
            return self._img("hoverimage") or self._img("image")
        return self._img("image")

    def is_opaque_at(self, pt):
        return True

    def click(self):
        self.sync_state()
        self.state = (self.state + 1) % self.nstates
        if self.p("cfgattrib"):
            self.engine.cfg_nstate_set(self, self.cfgvals[self.state % len(self.cfgvals)])
        self.engine.do_action(self.p("action"), self.p("param"), self)
        self.fire("onleftclick")
        self.update()

    def m_getactivated(self):
        return 1 if self.state else 0


class Text(GuiObj):
    cls = "Text"

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.text = self.p("text", "") or self.p("default", "")
        self.alt_text: str | None = None
        self.scroll = 0
        self._scroll_dir = 1
        self._last_display = ""
        if _b(self.p("ticker")) or _b(self.p("scroll")):
            engine.register_ticker(self)

    def display_text(self) -> str:
        if self.alt_text is not None:
            return rebrand(self.alt_text)
        disp = (self.p("display") or "").lower()
        if disp:
            t = self.engine.display_value(disp, self)
            if t is not None:
                return t
        if self.text.startswith(":"):
            # ":componentname" and friends are placeholders filled by Winamp
            t = self.engine.display_value(self.text[1:].lower(), self)
            if t is not None:
                return t
        return rebrand(self.text)

    def font(self):
        fid = (self.p("font") or "").lower()
        f = self.skin.fonts.get(fid)
        size = _i(self.p("fontsize"), 0)
        if f is None or isinstance(f, str):
            qf = QFont(f or (self.p("font") or "Sans"))
            qf.setPixelSize(_em_for_cell(qf, max(6, size or 11)))
            qf.setBold(_b(self.p("bold")))
            if not _b(self.p("antialias"), True):
                qf.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
            return qf
        return f

    def color(self) -> QColor:
        return self.skin.color(self.p("color"), QColor(255, 255, 255)) or QColor(255, 255, 255)

    def text_width(self, text=None) -> int:
        text = self.display_text() if text is None else text
        f = self.font()
        if isinstance(f, QFont):
            return QFontMetrics(f).horizontalAdvance(text)
        return len(text) * (f.cw + f.hs)

    def natural_size(self):
        return 0, 0

    def fills_parent(self):
        return True

    def paint_self(self, p):
        text = self.display_text()
        if text != self._last_display:
            self._last_display = text
            self.scroll = 0
        r = self.rect
        if not text or r.width() <= 0:
            return
        f = self.font()
        if _b(self.p("forceupcase")) or _b(self.p("uppercase")):
            text = text.upper()
        if _b(self.p("forcelowcase")):
            text = text.lower()
        align = (self.p("align") or "left").lower()
        valign = (self.p("valign") or "center").lower()
        marquee = self.marquee()
        if marquee:
            text = text + self.SEP
        tw = self.text_width(text)
        ticker = marquee or ((_b(self.p("ticker")) or _b(self.p("scroll"))) and tw > r.width())
        gap = 0 if marquee else 30
        ox = _i(self.p("offsetx"))
        oy = _i(self.p("offsety"))
        p.save()
        p.setClipRect(r, Qt.ClipOperation.IntersectClip)
        if ticker:
            x = r.x() - self.scroll
        elif align == "right":
            x = r.right() + 1 - tw
        elif align == "center":
            x = r.x() + (r.width() - tw) // 2
        else:
            x = r.x()
        x += ox
        if isinstance(f, QFont):
            fm = QFontMetrics(f)
            if valign == "top":
                y = r.y() + fm.ascent()
            elif valign == "bottom":
                y = r.bottom() - fm.descent()
            else:
                y = r.y() + (r.height() + fm.ascent() - fm.descent()) // 2
            y += oy
            p.setFont(f)
            sc = self.skin.color(self.p("shadowcolor"))
            if sc is not None:
                p.setPen(sc)
                sx, sy = _i(self.p("shadowx"), 1), _i(self.p("shadowy"), 1)
                p.drawText(x + sx, y + sy, text)
                if ticker:
                    xx = x + tw + gap
                    while xx < r.right() + 1:
                        p.drawText(xx + sx, y + sy, text)
                        xx += tw + gap
            p.setPen(self.color())
            p.drawText(x, y, text)
            if ticker:
                p.drawText(x + tw + 30, y, text)
        else:
            y = r.y() + (r.height() - f.ch) // 2 + oy
            step = f.cw + f.hs
            reps = [0]
            if ticker:
                while reps[-1] + x < r.right() + 1:
                    reps.append(reps[-1] + tw + gap)
            for base in reps:
                for i, ch in enumerate(text):
                    cx = x + base + i * step
                    if cx > r.right():
                        break
                    if cx + f.cw >= r.x():
                        p.drawPixmap(cx, y, f.glyph(ch))
        p.restore()

    def tick(self):
        if not self.visible:
            return None
        lay = self.layout_obj()
        if lay is None or lay.container is None or lay.container.current is not lay \
                or lay.container.window is None or not lay.container.window.isVisible():
            return None
        text = self.display_text()
        marquee = self.marquee()
        key = (text, self.p("font"), self.p("fontsize"), marquee)
        if key != getattr(self, "_tw_key", None):
            self._tw_key = key
            self._tw = self.text_width(text + self.SEP if marquee else text)
        tw = self._tw
        if not text:
            return None
        if marquee:
            self.scroll = (self.scroll + 1) % max(1, tw)
            self.update()
            return True
        if tw > self.rect.width():
            self.scroll = (self.scroll + 1) % (tw + 30)
            self.update()
            return True
        return False

    SEP = "  ***  "

    def marquee(self) -> bool:
        """Scroll continuously like Winamp's song title (not only when long)."""
        return False

    def m_settext(self, t):
        self.text = str(t)
        self.engine.wake_tickers()
        self.params["display"] = ""
        self.fire("ontextchanged", ("STRING", self.text))
        self.update()

    def m_setalternatetext(self, t):
        self.alt_text = str(t) if t else None
        self.update()

    def m_gettext(self):
        return self.display_text()

    def m_gettextwidth(self):
        w = self.text_width()
        if (self.p("display") or "").lower().startswith("time"):
            # scripts lay out around the clock at load time, when it may be
            # blank: report the width it will need once a song plays
            w = max(w, self.text_width("00:00"))
        return w

    def m_getautowidth(self):
        return self.text_width() + 4

    def m_getautoheight(self):
        f = self.font()
        return QFontMetrics(f).height() if isinstance(f, QFont) else f.ch

    def on_param(self, name, value):
        if name == "text" or name == "default":
            self.text = value
        elif name == "display":
            self.text = ""


class Slider(GuiObj):
    cls = "Slider"
    interactive = True

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.low = _i(self.p("low"), 0)
        self.high = _i(self.p("high"), 255)
        self.vertical = (self.p("orientation") or "h").lower().startswith("v")
        self.position = self.low
        self.dragging = False
        self.locked = False
        self._grab = 0

    def thumb_pm(self):
        if self.dragging and self.p("downthumb"):
            return self.skin.bitmap(self.p("downthumb"))
        if self.hover and self.p("hoverthumb"):
            return self.skin.bitmap(self.p("hoverthumb"))
        return self.skin.bitmap(self.p("thumb"))

    def natural_size(self):
        bar = self.skin.bitmap(self.p("barmiddle") or self.p("image"))
        return (bar.width(), bar.height()) if bar is not None else (0, 0)

    def frac(self):
        rng = self.high - self.low
        return 0.0 if rng == 0 else (self.position - self.low) / rng

    def thumb_rect(self):
        pm = self.thumb_pm()
        tw = pm.width() if pm else 0
        th = pm.height() if pm else 0
        r = self.rect
        f = max(0.0, min(1.0, self.frac()))
        if self.vertical:
            y = r.bottom() + 1 - th - int(round(f * (r.height() - th)))
            return QRect(r.x(), y, tw, th)
        x = r.x() + int(round(f * (r.width() - tw)))
        return QRect(x, r.y(), tw, th)

    def paint_self(self, p):
        if not self.dragging and not self.locked:
            self.position = self.engine.slider_value(self, self.position)
        r = self.rect
        left = self.skin.bitmap(self.p("barleft"))
        mid = self.skin.bitmap(self.p("barmiddle"))
        right = self.skin.bitmap(self.p("barright"))
        if mid is not None:
            if self.vertical:
                p.drawTiledPixmap(r, mid)
            else:
                lw = left.width() if left else 0
                rw = right.width() if right else 0
                p.drawTiledPixmap(QRect(r.x() + lw, r.y(), max(0, r.width() - lw - rw), mid.height()), mid)
        if left is not None:
            p.drawPixmap(r.topLeft(), left)
        if right is not None:
            p.drawPixmap(r.right() + 1 - right.width(), r.y(), right)
        pm = self.thumb_pm()
        if pm is not None:
            p.drawPixmap(self.thumb_rect().topLeft(), pm)

    def value_at(self, pt):
        tr = self.thumb_rect()
        r = self.rect
        if self.vertical:
            span = r.height() - tr.height()
            off = r.bottom() + 1 - tr.height() - (pt.y() - self._grab)
        else:
            span = r.width() - tr.width()
            off = pt.x() - self._grab - r.x()
        f = 0.0 if span <= 0 else max(0.0, min(1.0, off / span))
        return int(round(self.low + f * (self.high - self.low)))

    def press_at(self, pt):
        tr = self.thumb_rect()
        if tr.contains(pt):
            self._grab = (pt.y() - tr.y()) if self.vertical else (pt.x() - tr.x())
        else:
            self._grab = (tr.height() if self.vertical else tr.width()) // 2
        self.dragging = True
        self.set_pos(self.value_at(pt), user=True)

    def drag_to(self, pt):
        if self.dragging:
            self.set_pos(self.value_at(pt), user=True)

    def release_at(self, pt):
        if self.dragging:
            self.dragging = False
            self.engine.slider_final(self, self.position)
            self.fire("onsetfinalposition", ("INT", self.position))
            self.update()

    def set_pos(self, v, user=False):
        v = max(min(self.low, self.high), min(max(self.low, self.high), int(v)))
        if v != self.position or user:
            self.position = v
            if user:
                self.engine.slider_changed(self, v)
                self.fire("onpostedposition", ("INT", v))
            self.fire("onsetposition", ("INT", v))
            self.update()

    def m_setposition(self, v):
        self.set_pos(v)

    def m_getposition(self):
        return self.position

    def m_lock(self):
        self.locked = True

    def m_unlock(self):
        self.locked = False

    def m_setlow(self, v):
        self.low = int(v)

    def m_sethigh(self, v):
        self.high = int(v)


class Status(GuiObj):
    cls = "GuiObject"

    def natural_size(self):
        pm = self.skin.bitmap(self.p("playbitmap"))
        return (pm.width(), pm.height()) if pm is not None else (0, 0)

    def paint_self(self, p):
        st = self.engine.app.player.state
        key = {"play": "playbitmap", "pause": "pausebitmap"}.get(st, "stopbitmap")
        self.draw_pix(p, self.skin.bitmap(self.p(key)))


class Vis(GuiObj):
    cls = "Vis"
    interactive = True

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.mode = _i(self.p("mode"), 1)
        sk = self.skin
        self.bands = []
        allb = sk.color(self.p("colorallbands"))
        for i in range(1, 17):
            c = sk.color(self.p(f"colorband{i}")) or allb
            self.bands.append(c)
        if not any(self.bands):
            self.bands = [QColor.fromHsv(int(120 - 120 * i / 15), 220, 230) for i in range(16)]
        else:
            last = QColor(0, 200, 0)
            for i, c in enumerate(self.bands):
                if c is None:
                    self.bands[i] = last
                else:
                    last = c
        self.peak = sk.color(self.p("colorbandpeak"), QColor(255, 255, 255))
        self._pal = None
        self._pal_h = -1
        self.osc = sk.color(self.p("coloroscillo1") or self.p("colorosc1"), QColor(255, 255, 255))

    def fills_parent(self):
        return True

    def paint_self(self, p):
        r = self.rect
        if r.width() <= 0 or r.height() <= 0 or self.mode == 0:
            return
        vis = self.engine.app.vis
        an = vis.analyzer
        style = getattr(self.engine, "vis_style", 0) if _b(self.p("zebamp_slot")) else None
        if self.mode == 2 or style == 3:
            sc = an.scope
            rd = vis.reader
            if r.width() > 2 * len(sc) and rd is not None and vis.timer.isActive():
                # wide panel: real samples instead of the 75-point scope
                sc = [max(-1.0, min(1.0, float(v) * 2.2)) for v in rd.buf[-min(len(rd.buf), r.width() * 2)::2]]
            n = len(sc)
            mid = r.y() + r.height() / 2
            p.setPen(QPen(self.osc, 1))
            prev = None
            for i in range(r.width()):
                v = sc[min(n - 1, i * n // max(1, r.width()))]
                y = int(mid - v * (r.height() / 2 - 1))
                if prev is not None:
                    p.drawLine(r.x() + i - 1, prev, r.x() + i, y)
                prev = y
            return
        import numpy as np
        from PySide6.QtGui import QImage
        w, h = r.width(), r.height()
        if self._pal is None or self._pal_h != h:
            rows = np.arange(h)
            band = np.clip(((h - 1 - rows) * 16) // max(1, h), 0, 15)
            cols = np.array([0xFF000000 | (c.red() << 16) | (c.green() << 8) | c.blue()
                             for c in self.bands], dtype=np.uint32)
            self._pal = cols[band][:, None]
            self._pal_h = h
            pk = self.peak
            self._peak_col = np.uint32(0xFF000000 | (pk.red() << 16) | (pk.green() << 8) | pk.blue())
        bars = an.bars
        n = len(bars)
        idx = np.minimum(n - 1, np.arange(w) * n // max(1, w))
        hh = np.clip((bars[idx] / 16.0 * h).astype(int), 0, h)
        img = np.zeros((h, w), dtype=np.uint32)
        rows = np.arange(h)[:, None]
        mask = rows >= (h - hh)[None, :]
        if style in (0, 1, 2) and w > 2 * n:
            # big panel: separate bars with gaps (thin style: narrower bars)
            bw = w / n
            pos = (np.arange(w) % bw) / bw
            mask &= (pos < (0.5 if style == 1 else 0.82))[None, :]
        if style == 2:
            # fire: colour by distance from each bar's top
            top = (h - hh)[None, :]
            band = np.clip(((rows - top) * 16) // max(1, h), 0, 15)
            cols = np.array([0xFF000000 | (c.red() << 16) | (c.green() << 8) | c.blue()
                             for c in self.bands], dtype=np.uint32)
            fire = cols[15 - band]
            img[mask] = fire[mask]
        else:
            img[mask] = np.broadcast_to(self._pal, (h, w))[mask]
        if _b(self.p("peaks"), True):
            ph = np.clip((an.peaks[idx] / 16.0 * h).astype(int), 0, h)
            cols = np.nonzero(ph > 0)[0]
            img[h - ph[cols], cols] = self._peak_col
        arr = np.ascontiguousarray(img)
        qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_ARGB32)
        p.drawImage(r.topLeft(), qimg)

    def m_setmode(self, m):
        self.mode = int(m)
        self.update()

    def m_getmode(self):
        return self.mode

    def m_nextmode(self):
        self.mode = (self.mode + 1) % 3
        self.update()

    def m_setrealtime(self, on):
        pass


class EqVis(GuiObj):
    cls = "EqVis"

    def fills_parent(self):
        return True

    def paint_self(self, p):
        from ..ui.eqwin import spline
        r = self.rect
        if r.width() < 4 or r.height() < 2:
            return
        eq = self.engine.app.eq
        xs = [i * (r.width() - 1) / 9 for i in range(10)]
        ys = [(1 - (b + 12) / 24) * (r.height() - 1) for b in eq.bands]
        pts = spline(xs, ys, list(range(r.width())))
        top = self.skin.color(self.p("colortop"), QColor(255, 80, 80))
        mid = self.skin.color(self.p("colormiddle"), QColor(255, 255, 80))
        bot = self.skin.color(self.p("colorbottom"), QColor(80, 255, 80))
        pre = self.skin.color(self.p("colorpreamp"))
        if pre is not None:
            py = int((1 - (eq.preamp + 12) / 24) * (r.height() - 1))
            p.fillRect(r.x(), r.y() + py, r.width(), 1, pre)
        prev = None
        for x, y in enumerate(pts):
            yi = max(0, min(r.height() - 1, int(round(y))))
            lo, hi = (yi, yi) if prev is None else (min(prev, yi), max(prev, yi))
            for yy in range(lo, hi + 1):
                f = yy / max(1, r.height() - 1)
                c = top if f < 0.33 else mid if f < 0.66 else bot
                p.fillRect(r.x() + x, r.y() + yy, 1, 1, c)
            prev = yi


class PlaylistView(GuiObj):
    """Stand-in for Winamp's built-in playlist component."""

    cls = "GuiObject"
    interactive = True

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.scroll = 0
        self.sel: set = set()

    def fills_parent(self):
        return True

    def row_h(self):
        return 14

    def colors(self):
        sk = self.skin
        def g(k, d):
            return sk.color(k) or QColor(d)
        return (g("wasabi.list.background", "#000000"), g("wasabi.list.text", "#00ff00"),
                g("wasabi.list.text.current", "#ffffff"),
                g("wasabi.list.text.selected.background", "#0000c0"))

    def paint_self(self, p):
        r = self.rect
        bg, fg, cur_c, sel_bg = self.colors()
        p.fillRect(r, bg)
        q = self.engine.app.player.queue
        cur = self.engine.app.player.current_pos
        rh = self.row_h()
        rows = max(1, r.height() // rh)
        self.scroll = max(0, min(self.scroll, max(0, len(q) - rows)))
        f = QFont()
        f.setPixelSize(11)
        p.setFont(f)
        fm = QFontMetrics(f)
        from ..player import fmt_time, song_duration, song_title
        p.save()
        p.setClipRect(r)
        for i in range(self.scroll, min(len(q), self.scroll + rows + 1)):
            y = r.y() + (i - self.scroll) * rh
            s = q[i]
            if s.get("id") in self.sel:
                p.fillRect(QRect(r.x(), y, r.width(), rh), sel_bg)
            p.setPen(cur_c if i == cur else fg)
            d = song_duration(s)
            dt = fmt_time(d) if d else ""
            dw = fm.horizontalAdvance(dt)
            p.drawText(QRect(r.x() + 3, y, r.width() - dw - 10, rh), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(f"{i + 1}. {song_title(s)}", Qt.TextElideMode.ElideRight,
                                     r.width() - dw - 10))
            p.drawText(QRect(r.right() - dw - 3, y, dw, rh), Qt.AlignmentFlag.AlignVCenter, dt)
        p.restore()

    def row_at(self, pt):
        return self.scroll + (pt.y() - self.rect.y()) // self.row_h()

    def click_at(self, pt, double=False):
        q = self.engine.app.player.queue
        row = self.row_at(pt)
        if 0 <= row < len(q):
            if double:
                self.engine.app.player.play(row)
            else:
                self.sel = {q[row].get("id")}
        self.update()

    def wheel(self, d):
        self.scroll = max(0, self.scroll + (-3 if d > 0 else 3))
        self.update()


class AlbumArt(GuiObj):
    """Cover of the playing song (fetched from MPD)."""

    cls = "AlbumArtLayer"

    def fills_parent(self):
        return True

    def paint_self(self, p):
        pm = self.engine.cover
        r = self.rect
        if pm is None or r.width() <= 0 or r.height() <= 0:
            return
        sc = pm.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(r.x() + (r.width() - sc.width()) // 2, r.y() + (r.height() - sc.height()) // 2, sc)

    def m_refresh(self):
        self.update()

    def m_isloading(self):
        return 0


class SongTicker(Text):
    """<Songticker>: scrolling 'N. Artist - Title (m:ss)'."""

    def __init__(self, node, parent, engine):
        super().__init__(node, parent, engine)
        self.params.setdefault("display", "songticker")
        self.params.setdefault("ticker", "1")
        if self not in engine._tickers:
            engine.register_ticker(self)

    def marquee(self):
        cfg = self.engine.app.cfg
        mode = str(self.p("ticker") or "1").strip().lower()
        return bool(cfg["marquee_scroll"]) and mode not in ("0", "off", "false", "no") \
            and bool(self.display_text())


class MenuObj(GuiObj):
    """<Menu menu="WA5:File" normal=.. hover=.. down=..>: a menubar entry."""

    cls = "Menu"
    interactive = True

    def _set_state(self, state):
        grp = self.parent
        if grp is None:
            return
        for key in ("normal", "hover", "down"):
            o = grp.find(self.p(key) or "")
            if o is not None:
                o.visible = (key == state)
        grp.update()

    def on_hover(self, on):
        self._set_state("hover" if on else "normal")

    def click(self):
        self._set_state("down")
        self.engine.popup_menu(self.p("menu") or "", self)
        self._set_state("normal")

    def m_getmenuid(self):
        return self.p("menu") or ""
