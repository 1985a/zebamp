"""System tray icon (StatusNotifierItem on Wayland bars such as swaybar/waybar)."""
from __future__ import annotations

import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .player import song_title
from .i18n import tr


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        ico = QIcon.fromTheme("zebamp", QIcon(os.path.join(os.path.dirname(__file__), "data", "zebamp.png")))
        self.icon = QSystemTrayIcon(ico)
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._build)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        p = app.player
        p.songChanged.connect(self._tip)
        p.statusChanged.connect(self._tip)
        self._tip()
        self.icon.show()

    def _tip(self):
        if self.icon is None:
            return
        p = self.app.player
        state = {"play": "▶", "pause": "⏸"}.get(p.state, "⏹")
        t = song_title(p.song) if p.song else "Zebamp"
        self.icon.setToolTip(f"{state} {t}")

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.app.toggle_visible()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.app.player.toggle_play()

    def _build(self):
        m = self.menu
        m.clear()
        a = self.app
        p = a.player
        if p.song:
            t = m.addAction(song_title(p.song)[:60])
            t.setEnabled(False)
            m.addSeparator()
        m.addAction(tr("Pausa") if p.state == "play" else tr("Reproducir"), p.toggle_play)
        m.addAction(tr("Detener"), p.stop)
        m.addAction(tr("Anterior"), p.previous)
        m.addAction(tr("Siguiente"), p.next)
        m.addSeparator()
        r = m.addMenu(tr("Valorar"))
        for n in range(5, -1, -1):
            r.addAction("★" * n if n else tr("Sin valoración"), lambda n=n: a.stats.rate_current(n))
        m.addAction(tr("Buscar canciones…"), a.show_search)
        m.addAction(tr("Radio por Internet…"), a.show_radio)
        m.addAction(tr("Letras…"), a.open_lyrics)
        m.addAction(tr("Ayuda…"), a.show_help)
        m.addSeparator()
        m.addAction(tr("Ocultar ventana") if a.is_visible() else tr("Mostrar ventana"), a.toggle_visible)
        m.addAction(tr("Salir"), a.quit)

    def hide(self):
        if self.icon is not None:
            self.icon.hide()
