"""Sleep timer: pause the music after some minutes or when the album ends.

Nothing polls: the minutes mode is one single-shot timer, and the album mode
only listens to the player's signals while it is armed.  The album mode lets
MPD do the stopping (``single oneshot``), so the last song is never cut.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .player import first
from .i18n import tr

OFF, MINUTES, ALBUM = "off", "minutes", "album"


def album_key(song: dict) -> tuple[str, str]:
    """What makes two songs "the same album": its name plus the album artist,
    or the folder when the files carry no album tag."""
    album = str(first(song.get("album")) or "").strip().lower()
    if album:
        return album, str(first(song.get("albumartist")) or "").strip().lower()
    return "", os.path.dirname(song.get("file", ""))


def ends_album(current: dict, following: dict | None) -> bool:
    """True when `current` is the last song of its album in play order."""
    if not current:
        return False
    return not following or album_key(following) != album_key(current)


def remaining_text(seconds: float) -> str:
    """«1 h 05 min», «12 min», «menos de 1 min»."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return tr("menos de 1 min")
    if minutes < 60:
        return tr("{0} min").format(minutes)
    return tr("{0} h {1:02d} min").format(minutes // 60, minutes % 60)


class SleepTimer(QObject):
    changed = Signal()          # armed, cancelled or fired
    fired = Signal()            # the music was paused by the timer

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.mode = OFF
        self._deadline = 0.0
        self._oneshot = False       # we asked MPD to stop after this song
        self._clock = QTimer(self)
        self._clock.setSingleShot(True)
        self._clock.timeout.connect(self._minutes_up)

    # ------------------------------------------------------------- state
    @property
    def active(self) -> bool:
        return self.mode != OFF

    def remaining(self) -> float:
        """Seconds left in minutes mode (0 otherwise)."""
        return max(0.0, self._deadline - time.monotonic()) if self.mode == MINUTES else 0.0

    def describe(self) -> str:
        if self.mode == MINUTES:
            return tr("Quedan {0}").format(remaining_text(self.remaining()))
        if self.mode == ALBUM:
            return tr("Se pausará al terminar el álbum")
        return tr("Desactivado")

    # ----------------------------------------------------------- control
    def start_minutes(self, minutes: float):
        self.cancel(quiet=True)
        if minutes <= 0:
            self.changed.emit()
            return
        self.mode = MINUTES
        self._deadline = time.monotonic() + minutes * 60
        self._clock.start(int(minutes * 60 * 1000))
        self.changed.emit()

    def start_album(self):
        self.cancel(quiet=True)
        self.mode = ALBUM
        self.player.songChanged.connect(self._album_check)
        self.player.queueChanged.connect(self._album_check)
        self.player.statusChanged.connect(self._album_check)
        self._album_check()
        self.changed.emit()

    def cancel(self, quiet=False):
        if self.mode == ALBUM:
            self._unlisten()
            self._arm_oneshot(False)
        self._clock.stop()
        was_active = self.active
        self.mode = OFF
        if was_active and not quiet:
            self.changed.emit()

    # ------------------------------------------------------------ minutes
    def _minutes_up(self):
        self.mode = OFF
        if self.player.state == "play":
            self.player.pause()
        self.changed.emit()
        self.fired.emit()

    # -------------------------------------------------------------- album
    def _unlisten(self):
        self.player.songChanged.disconnect(self._album_check)
        self.player.queueChanged.disconnect(self._album_check)
        self.player.statusChanged.disconnect(self._album_check)

    def _following(self) -> dict | None:
        """The song MPD will play next (it knows, even with random on)."""
        try:
            pos = int(self.player.status.get("nextsong", -1))
        except (TypeError, ValueError):
            return None
        queue = self.player.queue
        return queue[pos] if 0 <= pos < len(queue) else None

    def _album_check(self):
        """Runs on every player change while the album mode is armed.

        MPD stops by itself after the album's last song: in the middle of the
        queue it pauses on the next song and resets `single`; at the end of
        the queue it just stops.  A pause by the user (still `oneshot`) is not
        the timer firing.  Otherwise MPD is asked to stop after this song only
        while it is the album's last one."""
        state, single = self.player.state, self.player.status.get("single")
        if self._oneshot and (state == "stop" or (state == "pause" and single == "0")):
            self._arm_oneshot(False)
            self._unlisten()
            self.mode = OFF
            self.changed.emit()
            self.fired.emit()
        elif state != "stop":
            self._arm_oneshot(ends_album(self.player.song, self._following()))

    def _arm_oneshot(self, on: bool):
        if on != self._oneshot:
            self._oneshot = on
            self.player.conn.call("single", "oneshot" if on else 0)
