"""Lyrics window (used with modern skins) and the lookup shared by every
lyrics view.

The logic lives in :mod:`zebamp.lyricsync` (timing, state) and
:mod:`zebamp.lyricsfind` (sources); this module only wires them to Qt.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QVBoxLayout)

from .. import lyricsfind
from .. import lyricsync as S
from ..config import DATA_DIR
from ..i18n import tr

SYNC_STORE = S.SyncStore(os.path.join(DATA_DIR, "lyrics_sync.json"))


def lookup(app, on_done, force: bool = False) -> S.LyricsState:
    """Start looking up the current song's lyrics.

    Returns the state to show right away ("Buscando…" / "Nada sonando");
    `on_done(state)` is called in the GUI thread with the final one."""
    pl = app.player
    song = dict(pl.song or {})
    uri = song.get("file")
    if not uri:
        return S.LyricsState(status=S.NOTHING_PLAYING)
    state = S.LyricsState(uri=uri, status=S.SEARCHING)
    music_dir, duration = pl.music_directory, pl.duration or None

    def job(client):
        try:
            return lyricsfind.find_lyrics(song, music_dir, duration, client=client, force=force)
        except lyricsfind.LyricsUnavailable:
            return "offline"

    def done(result):
        final = S.LyricsState(uri=uri)
        if isinstance(result, S.Lyrics):
            final.lyrics = result
            if result.instrumental:
                final.status = S.INSTRUMENTAL
            elif not result.found:
                final.status = S.NOT_FOUND if S.song_query(song)[1] else S.NO_INFO
            final.timing = SYNC_STORE.get(uri) or S.auto_timing(result.duration, duration)
        else:                                   # "offline" or the worker failed
            final.status = S.OFFLINE
        on_done(final)

    pl.conn.run_async(job, done)
    return state


def save_timing(state: S.LyricsState):
    if state.uri:
        SYNC_STORE.put(state.uri, state.timing)


def reset_timing(state: S.LyricsState, song_duration: float | None):
    if state.uri:
        SYNC_STORE.put(state.uri, None)
    state.timing = S.auto_timing(state.lyrics.duration, song_duration)


class LyricsWindow(QDialog):
    """Plain Qt lyrics window (modern skins; classic ones use LyricsPanel)."""

    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(tr("Letras - Zebamp"))
        self.setPalette(getattr(app, "dialog_palette", self.palette()))
        self.resize(460, 600)
        lay = QVBoxLayout(self)
        self.head = QLabel("")
        self.head.setWordWrap(True)
        f = self.head.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.15)
        self.head.setFont(f)
        lay.addWidget(self.head)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.itemDoubleClicked.connect(self._seek_to)
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        b = QPushButton(tr("Volver a buscar"))
        b.clicked.connect(lambda: self._load(force=True))
        row.addWidget(b)
        lay.addLayout(row)
        self.state = S.LyricsState()
        self._cur = -1
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._follow)
        app.player.songChanged.connect(self._load)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._load()
        self.timer.start()

    def hideEvent(self, ev):
        self.timer.stop()               # nothing to follow while hidden
        super().hideEvent(ev)

    # ------------------------------------------------------------ loading
    def _load(self, force=False):
        if not self.isVisible():
            return
        uri = (self.app.player.song or {}).get("file")
        same = uri == self.state.uri and (self.state.status or self.state.lyrics.found)
        if same and not force:
            return                        # already showing this song
        artist, title, _album = S.song_query(self.app.player.song or {})
        self.head.setText(f"{title}\n{artist}" if artist else title)
        self._show(lookup(self.app, self._done, force=force))

    def _done(self, state):
        if state.uri == (self.app.player.song or {}).get("file"):
            self._show(state)

    def _show(self, state):
        self.state = state
        self._cur = -1
        self.list.clear()
        for _t, text in state.lyrics.lines:
            it = QListWidgetItem(text)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.list.addItem(it)
        self._update_status()
        self._follow()

    def _update_status(self):
        info = self.state.info()
        if self.state.lyrics.synced:
            info += tr(" — doble clic: ir a la línea · Mayús+clic: «esta línea suena ahora»")
        self.status.setText(info)

    # ---------------------------------------------------------- following
    def _follow(self):
        i = self.state.line_at(self.app.player.elapsed)
        if i == self._cur:
            return
        base = self.list.font()
        if 0 <= self._cur < self.list.count():
            it = self.list.item(self._cur)
            it.setFont(base)
            it.setForeground(self.palette().text())
        self._cur = i
        if 0 <= i < self.list.count():
            it = self.list.item(i)
            f = QFont(base)
            f.setBold(True)
            f.setPointSizeF(base.pointSizeF() * 1.2)
            it.setFont(f)
            it.setForeground(QColor(110, 205, 255))
            self.list.scrollToItem(it, QListWidget.ScrollHint.PositionAtCenter)

    # -------------------------------------------------------- interaction
    def _seek_to(self, item):
        t = self.state.seek_target(self.list.row(item))
        if t is not None:
            self.app.player.seek(t)

    def _clicked(self, item):
        from PySide6.QtWidgets import QApplication
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.tap(self.list.row(item))

    def tap(self, idx):
        if self.state.tap(idx, self.app.player.elapsed):
            save_timing(self.state)
            self._cur = -1
            self._update_status()
            self._follow()

    def nudge(self, seconds):
        self.state.timing.shift(seconds)
        save_timing(self.state)
        self._cur = -1
        self._update_status()
        self._follow()

    def _menu(self, pos):
        m = QMenu(self)
        item = self.list.itemAt(pos)
        if item is not None and self.state.lyrics.synced:
            m.addAction(tr("Esta línea suena ahora (sincronizar)"), lambda: self.tap(self.list.row(item)))
        if self.state.lyrics.synced:
            m.addAction(tr("Letra más tarde (+0,5 s)"), lambda: self.nudge(0.5))
            m.addAction(tr("Letra antes (−0,5 s)"), lambda: self.nudge(-0.5))
            m.addAction(tr("Restablecer sincronización"), self._reset)
            m.addSeparator()
        m.addAction(tr("Volver a buscar la letra"), lambda: self._load(force=True))
        m.popup(self.list.viewport().mapToGlobal(pos))

    def _reset(self):
        reset_timing(self.state, self.app.player.duration)
        self._cur = -1
        self._update_status()
        self._follow()
