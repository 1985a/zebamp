"""In-memory index of the MPD library for instant search (100k+ songs).

MPD's own `search` takes ~250-500 ms per query on a 100k song database, too
slow for search-as-you-type.  The library is loaded once (in chunks, ~1 s for
100k songs), cached on disk keyed by MPD's `db_update` stamp, and searched in
memory: every keystroke only filters, and typing more characters narrows the
previous result instead of rescanning everything.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import unicodedata

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp")
FIELDS = ("file", "title", "artist", "album", "albumartist", "genre", "duration", "date")
CACHE_VERSION = 3      # bump when FIELDS change: older caches are rebuilt
CHUNK = 5000


def fold(text: str) -> str:
    """Lower case without accents: "Canción" matches "cancion"."""
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _row(song: dict) -> list:
    dur = song.get("duration") or song.get("time") or ""
    return [song.get("file", ""), _first(song.get("title")), _first(song.get("artist")),
            _first(song.get("album")), _first(song.get("albumartist")), _first(song.get("genre")),
            dur, _first(song.get("date"))]


def _hay(row) -> str:
    return fold(" ".join(x for x in row[:6] if x))


class LibraryIndex(QObject):
    ready = Signal()

    def __init__(self, player):
        super().__init__()
        self.player = player
        self.rows: list[list] = []
        self.hay: list[str] = []
        self.stamp = None
        self.loading = False
        self._last_q: tuple[list[str], list[int]] | None = None
        player.databaseChanged.connect(lambda: QTimer.singleShot(3000, self.refresh))

    # --------------------------------------------------------------- load
    def _cache_path(self) -> str:
        key = hashlib.md5(self.player.conn.addr.describe().encode()).hexdigest()[:10]
        return os.path.join(CACHE, f"library-{key}.json")

    def refresh(self):
        """Load from cache if MPD's database is unchanged, else from MPD."""
        if self.loading:
            return
        self.loading = True
        path = self._cache_path()

        def job(client):
            stamp = (client.stats() or {}).get("db_update")
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("stamp") == stamp and data.get("v") == CACHE_VERSION:
                    return stamp, data["rows"], data["hay"], False
            except (OSError, ValueError, KeyError):
                pass
            t = time.monotonic()
            rows, i = [], 0
            while True:
                # windows keep each reply below MPD's output buffer limit
                part = client.find("(file != \"\")", "window", f"{i}:{i + CHUNK}")
                rows.extend(_row(s) for s in part if "file" in s)
                i += CHUNK
                if len(part) < CHUNK:
                    break
            hay = [_hay(r) for r in rows]     # folding is slow: keep it off the GUI thread
            log.info("library index: %d songs in %.2fs", len(rows), time.monotonic() - t)
            return stamp, rows, hay, True

        self.player.conn.run_async(job, self._loaded)

    def _loaded(self, res):
        self.loading = False
        if not res:
            return
        stamp, rows, hay, fresh = res
        self.rows = rows
        self.hay = hay
        self.stamp = stamp
        self._last_q = None
        self.ready.emit()
        if fresh:
            try:
                os.makedirs(CACHE, exist_ok=True)
                tmp = self._cache_path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump({"v": CACHE_VERSION, "stamp": stamp, "rows": rows, "hay": hay}, fh,
                              ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, self._cache_path())
            except OSError as e:
                log.debug("library cache not written: %s", e)

    def by_file(self) -> dict:
        if getattr(self, "_by_file_n", -1) != len(self.rows):
            self._by_file = {r[0]: r for r in self.rows}
            self._by_file_n = len(self.rows)
        return self._by_file

    @property
    def is_ready(self) -> bool:
        return bool(self.rows)

    # ------------------------------------------------------------- search
    def search(self, text: str) -> list[int]:
        words = fold(text).split()
        if not words:
            return []
        cand = None
        if self._last_q is not None:
            pw, pres = self._last_q
            # each previous word is still contained in a new word -> narrow
            if len(words) >= len(pw) and all(p in w for p, w in zip(pw, words)):
                cand = pres
        hay = self.hay
        if cand is None:
            # most selective (longest) word first
            ws = sorted(words, key=len, reverse=True)
            first, rest = ws[0], ws[1:]
            res = [i for i, h in enumerate(hay) if first in h]
            for w in rest:
                res = [i for i in res if w in hay[i]]
        else:
            res = [i for i in cand if all(w in hay[i] for w in words)]
        self._last_q = (words, res)
        return res
