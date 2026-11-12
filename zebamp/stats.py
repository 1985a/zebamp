"""Ratings and play statistics kept in MPD's sticker database.

Stickers are stored by MPD itself (`sticker_file` in mpd.conf), so they
survive Zebamp reinstalls and other clients can read them:

* ``rating``      0..10 (same scale as Cantata/other clients; 2 = one star)
* ``playCount``   times the song was played past half (or 4 minutes)
* ``lastPlayed``  unix time of the last counted play

If the server has no sticker database a local JSON file is used instead.
"""
from __future__ import annotations

import json
import logging
import os
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .config import DATA_DIR

log = logging.getLogger(__name__)
LOCAL = os.path.join(DATA_DIR, "stats.json")


class Stats(QObject):
    changed = Signal(str)       # uri
    played = Signal(dict, int)  # song counted as played, unix time it started

    def __init__(self, player):
        super().__init__()
        self.pl = player
        self.ratings: dict[str, int] = {}
        self.counts: dict[str, int] = {}
        self.last: dict[str, int] = {}
        self.use_stickers = True
        self._cur = None
        self._played = 0.0
        self._counted = False
        self._tick_t = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        player.songChanged.connect(self._song)
        player.statusChanged.connect(self._state)
        self._state()
        QTimer.singleShot(1500, self.load)

    # ------------------------------------------------------------- load
    def load(self):
        def job(c):
            out = {}
            try:
                for key in ("rating", "playCount", "lastPlayed"):
                    out[key] = c.sticker_find("song", "", key)
                return out
            except Exception as e:
                return {"error": str(e)}
        self.pl.conn.run_async(job, self._loaded)

    def _loaded(self, res):
        if not res or "error" in res:
            log.info("no MPD stickers (%s): using %s", (res or {}).get("error"), LOCAL)
            self.use_stickers = False
            try:
                with open(LOCAL, encoding="utf-8") as fh:
                    d = json.load(fh)
                self.ratings = {k: int(v) for k, v in d.get("rating", {}).items()}
                self.counts = {k: int(v) for k, v in d.get("playCount", {}).items()}
                self.last = {k: int(v) for k, v in d.get("lastPlayed", {}).items()}
            except (OSError, ValueError):
                pass
            return

        def conv(rows):
            out = {}
            for r in rows or []:
                f = r.get("file")
                v = r.get("sticker", "")
                if "=" in v:
                    v = v.split("=", 1)[1]
                try:
                    out[f] = int(float(v))
                except (TypeError, ValueError):
                    pass
            return out
        self.ratings = conv(res.get("rating"))
        self.counts = conv(res.get("playCount"))
        self.last = conv(res.get("lastPlayed"))
        self.changed.emit("")

    def _save_local(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            tmp = LOCAL + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"rating": self.ratings, "playCount": self.counts,
                           "lastPlayed": self.last}, fh)
            os.replace(tmp, LOCAL)
        except OSError as e:
            log.warning("stats not saved: %s", e)

    def _store(self, uri, key, value):
        if "://" in uri:
            return               # streams have no stickers
        if self.use_stickers:
            if value is None:
                self.pl.conn.run_async(lambda c: _safe(lambda: c.sticker_delete("song", uri, key)))
            else:
                self.pl.conn.run_async(lambda c: _safe(lambda: c.sticker_set("song", uri, key, str(value))))
        else:
            self._save_local()

    # ------------------------------------------------------------ ratings
    def rating(self, uri: str) -> int:
        """Stars 0..5."""
        return min(5, (self.ratings.get(uri, 0) + 1) // 2)

    def set_rating(self, uri: str, stars: int):
        if not uri or "://" in uri:
            return
        stars = max(0, min(5, int(stars)))
        if stars:
            self.ratings[uri] = stars * 2
        else:
            self.ratings.pop(uri, None)
        self._store(uri, "rating", stars * 2 if stars else None)
        self.changed.emit(uri)

    def rate_current(self, stars: int):
        self.set_rating((self.pl.song or {}).get("file", ""), stars)

    def playcount(self, uri: str) -> int:
        return self.counts.get(uri, 0)

    # -------------------------------------------------------- play count
    def _song(self):
        uri = (self.pl.song or {}).get("file")
        if uri != self._cur:
            self._cur = uri
            self._played = 0.0
            self._counted = False
            self._tick_t = None

    def _state(self):
        """The play counter only needs to tick while something plays."""
        if self.pl.state == "play":
            if not self.timer.isActive():
                self.timer.start()
        elif self.timer.isActive():
            self._tick()                # account for the last second
            self.timer.stop()
            self._tick_t = None

    def _tick(self):
        now = time.monotonic()
        el = self.pl.elapsed
        last = getattr(self, "_last_el", 0.0)
        self._last_el = el
        if self.pl.state == "play" and self._cur and el + 5 < last and el < 5:
            # same song started over (repeat one / replayed): a new play
            self._played = 0.0
            self._counted = False
        if self.pl.state != "play" or not self._cur or self._counted:
            self._tick_t = None
            return
        if self._tick_t is not None:
            self._played += min(2.0, now - self._tick_t)
        self._tick_t = now
        d = self.pl.duration
        need = min(240.0, d / 2) if d > 0 else 240.0
        if self._played >= max(5.0, need):
            self._counted = True
            uri = self._cur
            if "://" in uri:
                return
            self.played.emit(dict(self.pl.song or {}), int(time.time() - self._played))
            self.counts[uri] = self.counts.get(uri, 0) + 1
            self.last[uri] = int(time.time())
            self._store(uri, "playCount", self.counts[uri])
            self._store(uri, "lastPlayed", self.last[uri])
            self.changed.emit(uri)

    # -------------------------------------------------------------- lists
    def most_played(self, n=200):
        return [u for u, _ in sorted(self.counts.items(), key=lambda kv: -kv[1])[:n]]

    def top_rated(self, n=500):
        return [u for u, _ in sorted(self.ratings.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    def recently_played(self, n=200):
        return [u for u, _ in sorted(self.last.items(), key=lambda kv: -kv[1])[:n]]


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        log.debug("sticker op failed: %s", e)
        return None
