"""MilkDrop visualisation through projectM (libprojectM 3.x).

projectM only offers a C++ API, so a tiny C shim (native/pmshim.cpp) is
compiled on first use and loaded with ctypes.  projectM draws into an
offscreen framebuffer and the frames are shown in a plain widget.
"""
from __future__ import annotations

import ctypes
import glob
import hashlib
import logging
import os
import shutil
import subprocess

import numpy as np
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import (QImage, QOffscreenSurface, QOpenGLContext, QPainter,
                           QSurfaceFormat)
from PySide6.QtOpenGL import (QOpenGLFramebufferObject,
                              QOpenGLFramebufferObjectFormat)
from PySide6.QtWidgets import (QDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QVBoxLayout, QWidget)

from .player import song_title
from .i18n import tr

log = logging.getLogger(__name__)

SRC = os.path.join(os.path.dirname(__file__), "native", "pmshim.cpp")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp")
DATADIRS = ["/usr/share/projectM", "/usr/local/share/projectM", "/usr/share/projectm"]


def find_datadir() -> str | None:
    for d in DATADIRS:
        if os.path.isdir(os.path.join(d, "presets")):
            return d
    return None


def preset_dirs(cfg) -> str | None:
    custom = os.path.expanduser(cfg["milkdrop_presets"] or "")
    if custom and os.path.isdir(custom):
        return custom
    d = find_datadir()
    return os.path.join(d, "presets") if d else None


_LIB = None
_ERR = ""


def load_lib():
    """Compile (once) and load the shim.  Returns (lib, error)."""
    global _LIB, _ERR
    if _LIB is not None or _ERR:
        return _LIB, _ERR
    try:
        with open(SRC, "rb") as fh:
            digest = hashlib.sha1(fh.read()).hexdigest()[:12]
    except OSError as e:
        _ERR = tr("falta {0}: {1}").format(SRC, e)
        return None, _ERR
    so = os.path.join(CACHE, f"libzpm-{digest}.so")
    if not os.path.exists(so):
        cxx = shutil.which("g++") or shutil.which("c++") or shutil.which("clang++")
        if not cxx:
            _ERR = tr("no hay compilador de C++ (g++) para preparar MilkDrop")
            return None, _ERR
        if not glob.glob("/usr/include/libprojectM/projectM.hpp") and \
                not glob.glob("/usr/local/include/libprojectM/projectM.hpp"):
            _ERR = tr("projectM no está instalado (paquete «projectm»)")
            return None, _ERR
        os.makedirs(CACHE, exist_ok=True)
        tmp = so + ".tmp"
        r = subprocess.run([cxx, "-O2", "-shared", "-fPIC", "-o", tmp, SRC, "-lprojectM"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            _ERR = tr("no se pudo compilar el puente de projectM:\n") + r.stderr[-800:]
            return None, _ERR
        os.replace(tmp, so)
        for old in glob.glob(os.path.join(CACHE, "libzpm-*.so")):
            if old != so:
                try:
                    os.unlink(old)
                except OSError:
                    pass
    try:
        lib = ctypes.CDLL(so)
    except OSError as e:
        _ERR = tr("no se pudo cargar projectM: {0}").format(e)
        return None, _ERR
    vp, ci, cc, cf = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_float)
    lib.zpm_create.restype = vp
    lib.zpm_create.argtypes = [cc, cc] + [ci] * 9 + [ci, ci, ctypes.c_float, ctypes.c_float, ci]
    for name, args in (("zpm_destroy", [vp]), ("zpm_resize", [vp, ci, ci]), ("zpm_render", [vp]),
                       ("zpm_pcm_float", [vp, cf, ci]), ("zpm_next", [vp, ci]), ("zpm_prev", [vp, ci]),
                       ("zpm_random", [vp, ci]), ("zpm_lock", [vp, ci]), ("zpm_shuffle", [vp, ci]),
                       ("zpm_select", [vp, ctypes.c_uint, ci]), ("zpm_title", [vp, cc]),
                       ("zpm_duration", [vp, ci]), ("zpm_toast", [vp, cc]), ("zpm_key", [vp, ci, ci, ci])):
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = None
    lib.zpm_error.argtypes = []
    lib.zpm_error.restype = cc
    lib.zpm_locked.argtypes = [vp]
    lib.zpm_locked.restype = ci
    lib.zpm_count.argtypes = [vp]
    lib.zpm_count.restype = ctypes.c_uint
    lib.zpm_index.argtypes = [vp]
    lib.zpm_index.restype = ci
    lib.zpm_name.argtypes = [vp, ctypes.c_uint]
    lib.zpm_name.restype = cc
    _LIB = lib
    return lib, ""


def available() -> tuple[bool, str]:
    if find_datadir() is None:
        return False, tr("projectM no está instalado (paquete «projectm»)")
    lib, err = load_lib()
    return lib is not None, err


class MilkdropWindow(QWidget):
    """projectM renders into an offscreen FBO; the frame is shown with QPainter.

    Rendering straight into a Wayland EGL window is not safe: NVIDIA's EGL
    blocks in eglSwapBuffers while the window is on a hidden workspace, which
    would freeze the whole player.
    """

    BUDGET = {"low": 400_000, "medium": 1_000_000, "high": 2_100_000, "custom": 8_300_000}

    def __init__(self, app, embedded_in: QWidget | None = None):
        # embedded: a child filling the visualisation tab of a modern skin
        self.embedded = embedded_in is not None
        if self.embedded:
            super().__init__(embedded_in)
        else:
            super().__init__(None, Qt.WindowType.Window)
        self.app = app
        self.lib, _ = load_lib()
        self.pm = None
        self.error = ""
        self.ctx = None
        self.surf = None
        self.fbo = None
        self._img = None
        self._rsize = (0, 0)
        self._pending: list[np.ndarray] = []
        self.setWindowTitle("MilkDrop - Zebamp")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(160, 120)
        cfg = app.cfg
        if not self.embedded:
            self.resize(int(cfg["milkdrop_w"]), int(cfg["milkdrop_h"]))
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self._menu = None
        self._title_shown = None
        app.player.songChanged.connect(self._on_song)

    # ----------------------------------------------------------- audio
    def _feed(self, samples: np.ndarray):
        self._pending.append(samples)
        if len(self._pending) > 32:
            del self._pending[:-32]

    def _attach(self):
        r = self.app.vis.reader
        if r is not None and self._feed not in r.extra:
            r.extra.append(self._feed)

    def _detach(self):
        r = self.app.vis.reader
        if r is not None and self._feed in r.extra:
            r.extra.remove(self._feed)

    # ------------------------------------------------------------- GL
    def _render_size(self):
        dpr = self.devicePixelRatioF()
        w, h = max(16, int(self.width() * dpr)), max(16, int(self.height() * dpr))
        budget = self.BUDGET.get(self.app.cfg["milkdrop_quality"], 1_000_000)
        if w * h > budget:
            f = (budget / (w * h)) ** 0.5
            w, h = max(16, int(w * f)), max(16, int(h * f))
        return w, h

    def _init_gl(self) -> bool:
        if self.pm:
            return True
        if self.lib is None or self.error:
            return False
        fmt = QSurfaceFormat()
        # Qt may default to OpenGL ES on Wayland/EGL; projectM wants desktop GL.
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.ctx = QOpenGLContext()
        self.ctx.setFormat(fmt)
        if not self.ctx.create():
            self.error = tr("no se pudo crear un contexto OpenGL 3.3")
            return False
        self.surf = QOffscreenSurface()
        self.surf.setFormat(self.ctx.format())
        self.surf.create()
        if not self.ctx.makeCurrent(self.surf):
            self.error = tr("no se pudo activar el contexto OpenGL")
            return False
        w, h = self._render_size()
        self._make_fbo(w, h)
        cfg = self.app.cfg
        presets = preset_dirs(cfg)
        data = find_datadir() or "/usr/share/projectM"
        mesh = {"low": (32, 24), "medium": (48, 36), "high": (64, 48)}.get(cfg["milkdrop_quality"], (48, 36))
        tex = {"low": 512, "medium": 1024, "high": 2048}.get(cfg["milkdrop_quality"], 1024)
        if cfg["milkdrop_quality"] == "custom":
            mesh = (int(cfg["milkdrop_mesh_x"]), int(cfg["milkdrop_mesh_y"]))
            tex = int(cfg["milkdrop_texture"])
        self.pm = self.lib.zpm_create((presets or "").encode(), data.encode(), w, h,
                                      int(cfg["milkdrop_fps"]), mesh[0], mesh[1], tex,
                                      int(cfg["milkdrop_duration"]), int(cfg["milkdrop_smooth"]),
                                      1 if cfg["milkdrop_shuffle"] else 0,
                                      1 if cfg["milkdrop_hardcut"] else 0, int(cfg["milkdrop_hardcut_min"]),
                                      float(cfg["milkdrop_hardcut_sens"]), float(cfg["milkdrop_beat"]),
                                      1 if cfg["milkdrop_aspect"] else 0)
        if not self.pm:
            self.error = self.lib.zpm_error().decode("utf-8", "replace") or tr("projectM no arrancó")
            log.warning("projectM failed to initialise: %s", self.error)
            self.ctx.doneCurrent()
            return False
        self._rsize = (w, h)
        if cfg["milkdrop_shuffle"]:
            self.lib.zpm_random(self.pm, 1)
        self.ctx.doneCurrent()
        self._on_song()
        return True

    def _make_fbo(self, w, h):
        ff = QOpenGLFramebufferObjectFormat()
        ff.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        self.fbo = QOpenGLFramebufferObject(w, h, ff)

    def _tick(self):
        if not self.isVisible() or self.isMinimized():
            return
        vis = self.app.vis
        r = vis.reader
        if r is not None:
            self._attach()
            if self.app.player.state == "play" and not vis.timer.isActive():
                # the classic analyser is off: read the fifo ourselves
                r.open()
                r.poll()
        if not self._init_gl():
            self.timer.stop()
            self.update()
            return
        if not self.ctx.makeCurrent(self.surf):
            return
        try:
            w, h = self._render_size()
            if (w, h) != self._rsize:
                self._make_fbo(w, h)
                self.lib.zpm_resize(self.pm, w, h)
                self._rsize = (w, h)
            if self._pending:
                data = np.concatenate(self._pending).astype(np.float32)
                self._pending.clear()
                # projectM keeps ~2048 samples; older data would be dropped anyway
                data = np.ascontiguousarray(data[-2048:])
                self.lib.zpm_pcm_float(self.pm, data.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                       len(data))
            self.fbo.bind()
            self.lib.zpm_render(self.pm)
            img = self.fbo.toImage(False)
            # opaque format: painting becomes a plain copy (no alpha blending)
            img.reinterpretAsFormat(QImage.Format.Format_RGB32)
            self._img = img
            self.fbo.release()
        finally:
            self.ctx.doneCurrent()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        if self._img is None or self._img.isNull():
            p.fillRect(self.rect(), Qt.GlobalColor.black)
            if self.error:
                p.setPen(Qt.GlobalColor.white)
                p.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.TextFlag.TextWordWrap,
                           tr("MilkDrop no pudo arrancar:\n") + self.error)
            p.end()
            return
        dpr = self.devicePixelRatioF()
        if (self._img.width(), self._img.height()) == (round(self.width() * dpr), round(self.height() * dpr)):
            self._img.setDevicePixelRatio(dpr)
            p.drawImage(0, 0, self._img)
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(self.rect(), self._img)
        p.end()

    # --------------------------------------------------------- control
    def start(self):
        self.timer.setInterval(int(1000 / max(10, min(144, int(self.app.cfg["milkdrop_fps"])))))
        self._attach()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self._detach()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.start()

    def hideEvent(self, ev):
        self.stop()
        super().hideEvent(ev)

    def closeEvent(self, ev):
        self.stop()
        if not self.embedded and not self.isFullScreen():
            self.app.cfg["milkdrop_w"] = self.width()
            self.app.cfg["milkdrop_h"] = self.height()
            self.app.cfg.save()
        super().closeEvent(ev)

    def shutdown(self):
        self.stop()
        if self.pm and self.ctx is not None and self.ctx.makeCurrent(self.surf):
            self.lib.zpm_destroy(self.pm)
            self.pm = None
            self.fbo = None
            self.ctx.doneCurrent()

    def _on_song(self):
        if not self.pm or not self.app.cfg["milkdrop_title"]:
            return
        s = self.app.player.song or {}
        if not s:
            return
        t = song_title(s)
        if t != self._title_shown:
            self._title_shown = t
            self.lib.zpm_title(self.pm, t.encode("utf-8", "replace"))

    def next_preset(self, hard=False):
        if self.pm:
            if self.app.cfg["milkdrop_shuffle"]:
                self.lib.zpm_random(self.pm, 1 if hard else 0)
            else:
                self.lib.zpm_next(self.pm, 1 if hard else 0)
            self._toast_name()

    def prev_preset(self):
        if self.pm:
            self.lib.zpm_prev(self.pm, 1)
            self._toast_name()

    def toggle_lock(self):
        if self.pm:
            on = not self.lib.zpm_locked(self.pm)
            self.lib.zpm_lock(self.pm, 1 if on else 0)
            self.lib.zpm_toast(self.pm, (tr("Preset bloqueado") if on else tr("Preset desbloqueado")).encode())

    def toggle_shuffle(self):
        cfg = self.app.cfg
        cfg["milkdrop_shuffle"] = not cfg["milkdrop_shuffle"]
        cfg.save()
        if self.pm:
            self.lib.zpm_shuffle(self.pm, 1 if cfg["milkdrop_shuffle"] else 0)
            order = tr("Orden aleatorio") if cfg["milkdrop_shuffle"] else tr("Orden secuencial")
            self.lib.zpm_toast(self.pm, order.encode())

    def current_name(self) -> str:
        if not self.pm:
            return ""
        i = self.lib.zpm_index(self.pm)
        if i < 0:
            return ""
        return self.lib.zpm_name(self.pm, i).decode("utf-8", "replace")

    def _toast_name(self):
        QTimer.singleShot(50, lambda: self.pm and self.lib.zpm_toast(
            self.pm, os.path.splitext(self.current_name())[0].encode("utf-8", "replace")))

    def toggle_fullscreen(self):
        if self.embedded:
            self.app.toggle_milkdrop()      # the tab cannot go full screen: open the real window
            return
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def set_duration(self, sec):
        self.app.cfg["milkdrop_duration"] = sec
        self.app.cfg.save()
        if self.pm:
            self.lib.zpm_duration(self.pm, sec)

    def choose_preset(self):
        if not self.pm:
            return
        names = [self.lib.zpm_name(self.pm, i).decode("utf-8", "replace")
                 for i in range(self.lib.zpm_count(self.pm))]
        dlg = PresetPicker(self.app, names, self.lib.zpm_index(self.pm))
        if dlg.exec() and dlg.chosen is not None:
            self.lib.zpm_select(self.pm, dlg.chosen, 0)
            self._toast_name()

    # ----------------------------------------------------------- input
    def keyPressEvent(self, ev):
        K = Qt.Key
        k = ev.key()
        shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if k in (K.Key_Space, K.Key_N):
            self.next_preset(hard=shift)
        elif k == K.Key_H:
            self.next_preset(hard=True)
        elif k in (K.Key_Backspace, K.Key_P):
            self.prev_preset()
        elif k in (K.Key_ScrollLock, K.Key_K):
            self.toggle_lock()
        elif k == K.Key_R:
            self.toggle_shuffle()
        elif k == K.Key_L:
            self.choose_preset()
        elif k in (K.Key_Return, K.Key_Enter, K.Key_F) or (k == K.Key_F11):
            self.toggle_fullscreen()
        elif k == K.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif k == K.Key_T:
            self._title_shown = None
            self._on_song()
        elif k == K.Key_C:
            self.app.show_milkdrop_config()
        elif not self.app.handle_key(ev):
            super().keyPressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.toggle_fullscreen()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            self._context(ev.globalPosition().toPoint())
        elif ev.button() == Qt.MouseButton.LeftButton and self.windowHandle() is not None:
            self.windowHandle().startSystemMove()

    def wheelEvent(self, ev):
        pl = self.app.player
        d = ev.angleDelta().y()
        if d:
            pl.set_volume(pl.volume + (2 if d > 0 else -2))

    def _context(self, gp: QPoint):
        m = QMenu()
        m.setPalette(getattr(self.app, "dialog_palette", m.palette()))
        name = os.path.splitext(self.current_name())[0]
        if name:
            a = m.addAction(name)
            a.setEnabled(False)
            m.addSeparator()
        m.addAction(tr("Siguiente preset\tEspacio"), lambda: self.next_preset())
        m.addAction(tr("Corte brusco (aleatorio)\tH"), lambda: self.next_preset(True))
        m.addAction(tr("Preset anterior\tRetroceso"), self.prev_preset)
        m.addAction(tr("Elegir preset…\tL"), self.choose_preset)
        a = m.addAction(tr("Bloquear preset\tK"), self.toggle_lock)
        a.setCheckable(True)
        a.setChecked(bool(self.pm and self.lib.zpm_locked(self.pm)))
        a = m.addAction(tr("Orden aleatorio\tR"), self.toggle_shuffle)
        a.setCheckable(True)
        a.setChecked(bool(self.app.cfg["milkdrop_shuffle"]))
        d = m.addMenu(tr("Cambiar de preset cada"))
        for sec in (10, 15, 20, 30, 60, 120):
            a = d.addAction(f"{sec} s", lambda s=sec: self.set_duration(s))
            a.setCheckable(True)
            a.setChecked(int(self.app.cfg["milkdrop_duration"]) == sec)
        q = m.addMenu(tr("Calidad"))
        for key, label in (("low", tr("Baja (más ligera)")), ("medium", tr("Media")), ("high", tr("Alta"))):
            a = q.addAction(label, lambda k=key: self._set_quality(k))
            a.setCheckable(True)
            a.setChecked(self.app.cfg["milkdrop_quality"] == key)
        f = m.addMenu(tr("Fotogramas por segundo"))
        for fps in (30, 45, 60, 75, 120):
            a = f.addAction(str(fps), lambda v=fps: self._set_fps(v))
            a.setCheckable(True)
            a.setChecked(int(self.app.cfg["milkdrop_fps"]) == fps)
        a = m.addAction(tr("Mostrar título al cambiar de canción"), self._toggle_title)
        a.setCheckable(True)
        a.setChecked(bool(self.app.cfg["milkdrop_title"]))
        m.addSeparator()
        m.addAction(tr("Configuración de MilkDrop…\tC"), self.app.show_milkdrop_config)
        m.addAction(tr("Pantalla completa\tEnter / doble clic"), self.toggle_fullscreen)
        m.addAction(tr("Cerrar\tEsc"), self.close)
        self._menu = m
        m.popup(gp)

    def _set_fps(self, v):
        self.app.cfg["milkdrop_fps"] = v
        self.app.cfg.save()
        self.start()

    def _toggle_title(self):
        self.app.cfg["milkdrop_title"] = not self.app.cfg["milkdrop_title"]
        self.app.cfg.save()

    def _set_quality(self, k):
        self.app.cfg["milkdrop_quality"] = k
        self.app.cfg.save()
        self.app.restart_milkdrop()


class PresetPicker(QDialog):
    def __init__(self, app, names, current):
        super().__init__(None)
        self.setWindowTitle(tr("Elegir preset de MilkDrop"))
        self.setPalette(getattr(app, "dialog_palette", self.palette()))
        self.resize(560, 520)
        self.chosen = None
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Buscar entre {0} presets…").format(len(names)))
        self.edit.setClearButtonEnabled(True)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        lay.addWidget(self.list)
        self.names = names
        self.edit.textChanged.connect(self._filter)
        self.list.itemActivated.connect(self._pick)
        self.edit.returnPressed.connect(lambda: self._pick(self.list.currentItem()))
        self._filter("")
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == current:
                self.list.setCurrentRow(i)
                break

    def _filter(self, text):
        words = text.lower().split()
        self.list.clear()
        for i, n in enumerate(self.names):
            low = n.lower()
            if all(w in low for w in words):
                it = QListWidgetItem(os.path.splitext(n)[0])
                it.setData(Qt.ItemDataRole.UserRole, i)
                self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _pick(self, it):
        if it is not None:
            self.chosen = it.data(Qt.ItemDataRole.UserRole)
            self.accept()
