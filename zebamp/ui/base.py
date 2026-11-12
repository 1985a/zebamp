"""Tiny retained-mode toolkit for pixel-exact skinned panels.

Everything is laid out in *skin pixels*; the panel scales the painter by an
integer factor (double size) using nearest-neighbour sampling.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (QFont, QPainter, QPixmap)
from PySide6.QtWidgets import QWidget

from ..skin.classic import ClassicSkin

SpriteFn = Callable[[], QPixmap | None]


def dropped_files(urls) -> list[str]:
    """Dropped QUrls as open_paths() wants them: local paths and stream URLs."""
    files = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in urls]
    return [f for f in files if f]


class Control:
    cursor_name: str | None = None

    def __init__(self, rect: QRect | tuple, *, visible=True, cursor=None,
                 tooltip: str | None = None):
        self.rect = QRect(*rect) if isinstance(rect, tuple) else QRect(rect)
        self._visible = visible
        self.pressed = False
        self.panel: SkinPanel | None = None
        if cursor:
            self.cursor_name = cursor
        self.tooltip = tooltip

    @property
    def visible(self) -> bool:
        v = self._visible
        return v() if callable(v) else bool(v)

    def contains(self, pt: QPoint) -> bool:
        return self.rect.contains(pt)

    def update(self):
        if self.panel is not None:
            self.panel.update_logical(self.rect)

    # events (logical coordinates)
    def paint(self, p: QPainter):
        pass

    def press(self, pt: QPoint, ev) -> bool:
        return False

    def drag(self, pt: QPoint, ev):
        pass

    def release(self, pt: QPoint, ev, inside: bool):
        pass

    def double_click(self, pt: QPoint, ev) -> bool:
        return False

    def wheel(self, delta: int, ev) -> bool:
        return False

    def context(self, pt: QPoint, global_pos: QPoint) -> bool:
        return False


class Area(Control):
    """Invisible clickable region."""

    def __init__(self, rect, *, on_press=None, on_click=None, on_double=None,
                 on_drag=None, on_release=None, on_context=None, on_wheel=None,
                 **kw):
        super().__init__(rect, **kw)
        self.on_press = on_press
        self.on_click = on_click
        self.on_double = on_double
        self.on_drag = on_drag
        self.on_release = on_release
        self.on_context = on_context
        self.on_wheel = on_wheel

    def press(self, pt, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        self.pressed = True
        if self.on_press:
            self.on_press(pt, ev)
        return True

    def drag(self, pt, ev):
        if self.on_drag:
            self.on_drag(pt, ev)

    def release(self, pt, ev, inside):
        self.pressed = False
        if self.on_release:
            self.on_release(pt, ev)
        if inside and self.on_click:
            self.on_click()

    def double_click(self, pt, ev):
        if self.on_double:
            self.on_double()
            return True
        return False

    def context(self, pt, gp):
        if self.on_context:
            self.on_context(gp)
            return True
        return False

    def wheel(self, delta, ev):
        if self.on_wheel:
            self.on_wheel(delta)
            return True
        return False


class Button(Area):
    """Sprite button.  `sprites` returns (normal, pressed) pixmaps."""

    def __init__(self, rect, sprites: Callable[[], tuple], *, on_click=None,
                 draw_normal=True, active: Callable[[], bool] | None = None,
                 **kw):
        super().__init__(rect, on_click=on_click, **kw)
        self.sprites = sprites
        self.draw_normal = draw_normal
        self.active = active

    def paint(self, p):
        normal, pressed = self.sprites()
        show_pressed = self.pressed or (self.active is not None and self.active())
        pm = pressed if show_pressed else (normal if self.draw_normal else None)
        if pm is not None and not pm.isNull():
            p.drawPixmap(self.rect.topLeft(), pm)

    def press(self, pt, ev):
        ok = super().press(pt, ev)
        if ok:
            self.update()
        return ok

    def drag(self, pt, ev):
        inside = self.rect.contains(pt)
        if inside != self.pressed:
            self.pressed = inside
            self.update()

    def release(self, pt, ev, inside):
        super().release(pt, ev, inside)
        self.update()


class Toggle(Button):
    """Button with a selected state: sprites() -> (n, n_pressed, s, s_pressed)."""

    def __init__(self, rect, sprites, *, selected: Callable[[], bool], **kw):
        super().__init__(rect, sprites, **kw)
        self.selected = selected

    def paint(self, p):
        n, nd, s, sd = self.sprites()
        sel = self.selected()
        if sel:
            pm = sd if self.pressed else s
        else:
            pm = nd if self.pressed else n
        if pm is not None and not pm.isNull():
            p.drawPixmap(self.rect.topLeft(), pm)


class Slider(Control):
    """Horizontal or vertical slider with a sprite thumb.

    value is 0..1 (for vertical sliders 1 is the top).
    """

    def __init__(self, rect, *, thumb_size: tuple[int, int], thumb_offset=0,
                 background: Callable[[QPainter, QRect, float], None] | None = None,
                 thumb: Callable[[bool, float], QPixmap | None] | None = None,
                 value: Callable[[], float], on_change=None, on_release=None,
                 on_press=None, vertical=False, wheel_step=0.05,
                 track_length: int | None = None, show_thumb=lambda: True,
                 jump_to_click=True, **kw):
        super().__init__(rect, **kw)
        self.thumb_size = thumb_size
        self.thumb_offset = thumb_offset
        self.background = background
        self.thumb = thumb
        self.value_fn = value
        self.on_change = on_change
        self.on_release = on_release
        self.on_press = on_press
        self.vertical = vertical
        self.wheel_step = wheel_step
        self.show_thumb = show_thumb
        self.jump_to_click = jump_to_click
        tw, th = thumb_size
        if vertical:
            length = rect[3] if isinstance(rect, tuple) else self.rect.height()
        else:
            length = self.rect.width()
        tl = th if vertical else tw
        self.range = (track_length if track_length is not None else length) - tl
        self.drag_value: float | None = None
        self._grab = 0

    @property
    def value(self) -> float:
        if self.drag_value is not None:
            return self.drag_value
        try:
            return max(0.0, min(1.0, float(self.value_fn())))
        except (TypeError, ValueError):
            return 0.0

    def thumb_pos(self, value: float) -> QPoint:
        if self.range <= 0:
            off = 0
        else:
            off = round(value * self.range) if not self.vertical else round((1 - value) * self.range)
        if self.vertical:
            return QPoint(self.rect.left() + self.thumb_offset, self.rect.top() + off)
        return QPoint(self.rect.left() + off, self.rect.top() + self.thumb_offset)

    def thumb_rect(self, value: float) -> QRect:
        tp = self.thumb_pos(value)
        return QRect(tp.x(), tp.y(), *self.thumb_size)

    def paint(self, p):
        v = self.value
        if self.background:
            self.background(p, self.rect, v)
        if self.thumb and self.show_thumb():
            pm = self.thumb(self.pressed, v)
            if pm is not None and not pm.isNull():
                p.drawPixmap(self.thumb_pos(v), pm)

    def _value_at(self, pt: QPoint) -> float:
        if self.range <= 0:
            return 0.0
        if self.vertical:
            off = pt.y() - self.rect.top() - self._grab
            return 1.0 - max(0, min(self.range, off)) / self.range
        off = pt.x() - self.rect.left() - self._grab
        return max(0, min(self.range, off)) / self.range

    def press(self, pt, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return False
        if not self.show_thumb():
            return False
        self.pressed = True
        tr = self.thumb_rect(self.value)
        if tr.contains(pt):
            self._grab = (pt.y() - tr.top()) if self.vertical else (pt.x() - tr.left())
        else:
            self._grab = (self.thumb_size[1] if self.vertical else self.thumb_size[0]) // 2
        if self.on_press:
            self.on_press()
        if not tr.contains(pt) and self.jump_to_click:
            self.drag_value = self._value_at(pt)
            if self.on_change:
                self.on_change(self.drag_value)
        else:
            self.drag_value = self.value
        self.update()
        return True

    def drag(self, pt, ev):
        if not self.pressed:
            return
        self.drag_value = self._value_at(pt)
        if self.on_change:
            self.on_change(self.drag_value)
        self.update()

    def release(self, pt, ev, inside):
        v = self.drag_value if self.drag_value is not None else self.value
        self.pressed = False
        if self.on_release:
            self.on_release(v)
        self.drag_value = None
        self.update()

    def wheel(self, delta, ev):
        if self.on_change is None and self.on_release is None:
            return False
        v = max(0.0, min(1.0, self.value + (self.wheel_step if delta > 0 else -self.wheel_step)))
        if self.on_change:
            self.on_change(v)
        if self.on_release:
            self.on_release(v)
        self.update()
        return True


# --------------------------------------------------------------- text
def draw_bitmap_text(p: QPainter, skin: ClassicSkin, text: str, x: int, y: int,
                     clip_w: int | None = None):
    for i, ch in enumerate(text):
        cx = x + i * 5
        if clip_w is not None and cx - x >= clip_w:
            break
        p.drawPixmap(cx, y, skin.glyph(ch))


def ttf_font(pixel_size: int, family: str = "", bold=False) -> QFont:
    f = QFont(family or "Sans")
    f.setPixelSize(pixel_size)
    f.setBold(bold)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


class SkinPanel(QWidget):
    """Base class for main/equalizer/playlist panels."""

    focused = Signal(object)
    sizeHintChanged = Signal()

    default_cursor = "normal"

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.controls: list[Control] = []
        self._grab: Control | None = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAcceptDrops(True)
        self._hover: Control | None = None

    # geometry --------------------------------------------------------
    @property
    def skin(self) -> ClassicSkin:
        return self.app.skin

    @property
    def scale(self) -> int:
        return self.app.scale

    def logical_size(self) -> tuple[int, int]:
        raise NotImplementedError

    def apply_size(self):
        w, h = self.logical_size()
        s = self.scale
        if (self.width(), self.height()) != (w * s, h * s):
            self.setFixedSize(w * s, h * s)
            self.sizeHintChanged.emit()

    def to_logical(self, pos) -> QPoint:
        s = self.scale
        return QPoint(int(pos.x() // s), int(pos.y() // s))

    def update_logical(self, r: QRect):
        s = self.scale
        self.update(QRect(r.x() * s, r.y() * s, r.width() * s, r.height() * s))

    def add(self, c: Control) -> Control:
        c.panel = self
        self.controls.append(c)
        return c

    def rebuild(self):
        """Recreate controls (after a skin, size or mode change)."""
        self.controls = []
        self._grab = None
        self._hover = None
        self.build()
        self.apply_size()
        self.update()

    def build(self):
        raise NotImplementedError

    def is_active(self) -> bool:
        return self.app.focused_panel is self and self.window().isActiveWindow()

    # drag and drop ----------------------------------------------------
    # Like Winamp: files dropped on a window are played (they replace the
    # queue); skins are installed.  The playlist overrides this to insert.
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        files = dropped_files(ev.mimeData().urls())
        if files:
            self.app.open_paths(files)
            ev.acceptProposedAction()

    def region_path(self):
        return None

    # painting ---------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        s = self.scale
        p.scale(s, s)
        clip = ev.rect()
        lr = QRect(clip.x() // s, clip.y() // s, clip.width() // s + 2,
                   clip.height() // s + 2)
        p.setClipRect(lr)
        path = self.region_path()
        if path is not None:
            p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        self.paint_background(p)
        for c in self.controls:
            if c.visible and c.rect.intersects(lr):
                c.paint(p)
        self.paint_overlay(p)
        p.end()

    def paint_background(self, p: QPainter):
        pass

    def paint_overlay(self, p: QPainter):
        pass

    # input ------------------------------------------------------------
    def control_at(self, pt: QPoint) -> Control | None:
        for c in reversed(self.controls):
            if c.visible and c.contains(pt):
                return c
        return None

    def mousePressEvent(self, ev):
        self.app.set_focused_panel(self)
        pt = self.to_logical(ev.position())
        c = self.control_at(pt)
        if ev.button() == Qt.MouseButton.RightButton:
            gp = ev.globalPosition().toPoint()
            if c is not None and c.context(pt, gp):
                return
            self.context_menu(pt, gp)
            return
        if c is not None and c.press(pt, ev):
            self._grab = c
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self.background_press(pt, ev)

    def mouseMoveEvent(self, ev):
        if self.app.drag_active(self):
            self.app.drag_to(self.mapTo(self.window(), ev.position().toPoint()))
            return
        pt = self.to_logical(ev.position())
        if self._grab is not None:
            self._grab.drag(pt, ev)
            return
        c = self.control_at(pt)
        if c is not self._hover:
            self._hover = c
            name = (c.cursor_name if c is not None and c.cursor_name else None) or self.default_cursor
            cur = self.skin.cursor(name) if name else None
            if cur is not None:
                self.setCursor(cur)
            else:
                self.unsetCursor()
            if c is not None and c.tooltip:
                self.setToolTip(c.tooltip)
            else:
                self.setToolTip("")

    def mouseReleaseEvent(self, ev):
        if self.app.drag_active(self):
            self.app.drag_end()
            if self._grab is not None:
                self._grab.pressed = False
                self._grab = None
            return
        if self._grab is not None:
            pt = self.to_logical(ev.position())
            g = self._grab
            self._grab = None
            g.release(pt, ev, g.rect.contains(pt))

    def mouseDoubleClickEvent(self, ev):
        pt = self.to_logical(ev.position())
        c = self.control_at(pt)
        if c is not None and c.double_click(pt, ev):
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            # Re-run as a press so drags still work after a double click.
            self.mousePressEvent(ev)

    def wheelEvent(self, ev):
        pt = self.to_logical(ev.position())
        c = self.control_at(pt)
        d = ev.angleDelta().y() or ev.angleDelta().x()
        if d == 0:
            return
        if c is not None and c.wheel(d, ev):
            return
        self.background_wheel(d)

    def background_press(self, pt, ev):
        self.app.start_move(self, ev)

    def background_wheel(self, delta: int):
        self.app.player.set_volume(self.app.player.volume + (2 if delta > 0 else -2))

    def context_menu(self, pt, gp):
        self.app.show_main_menu(gp)

    def start_move(self, *a):
        # used as on_press(pt, ev) callback by title bars
        ev = a[1] if len(a) > 1 else None
        self.app.start_move(self, ev)
