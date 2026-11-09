"""Lyrics logic without any GUI: LRC parsing, picking the right version of a
song, and the time mapping between the song and its lyrics.

Why a time mapping: synced lyrics are often timed for another release of the
song (a sped-up edit, a version with a longer intro).  We model the relation
as a straight line

    lyric_time = speed * song_time + offset

- `speed` != 1 fixes lyrics timed for a faster/slower version,
- `offset` fixes a longer/shorter intro.

Both can come from the durations (automatic guess) or from the user tapping
lines while they are sung ("anchors"): one anchor fixes the offset, two or
more far apart fix the speed too (least squares).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

# [mm:ss], [mm:ss.xx], [mm:ss:xx] (some editors use ':' for hundredths)
_STAMP = re.compile(r"\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORD_STAMP = re.compile(r"<\d+:\d{1,2}(?:[.:]\d{1,3})?>")      # enhanced LRC word timing
_TAG = re.compile(r"^\[(ar|ti|al|by|offset|length|re|ve|au|#):(.*)\]\s*$", re.IGNORECASE)


def _seconds(m: str, s: str, frac: str | None) -> float:
    value = int(m) * 60 + int(s)
    if frac:
        value += int(frac) / (10 ** len(frac))
    return value


@dataclass
class Lyrics:
    lines: list[tuple[float | None, str]] = field(default_factory=list)   # (time, text)
    synced: bool = False
    duration: float | None = None      # length of the release the lyrics were timed for
    source: str = ""                   # "archivo .lrc", "etiquetas", "lrclib.net"
    instrumental: bool = False

    @property
    def found(self) -> bool:
        return bool(self.lines) or self.instrumental


def parse_lrc(text: str) -> tuple[list[tuple[float, str]], float | None]:
    """Synced lines from LRC text, and the [length:] tag if present.

    Honours the standard [offset:±ms] tag (positive = lyrics earlier)."""
    lines: list[tuple[float, str]] = []
    offset = 0.0
    length = None
    for raw in (text or "").splitlines():
        tag = _TAG.match(raw.strip())
        if tag:
            name, value = tag.group(1).lower(), tag.group(2).strip()
            if name == "offset":
                try:
                    offset = int(value) / 1000.0
                except ValueError:
                    pass
            elif name == "length":
                m = re.match(r"(\d+):(\d{1,2})", value)
                if m:
                    length = float(int(m.group(1)) * 60 + int(m.group(2)))
            continue
        stamps = _STAMP.findall(raw)
        if not stamps:
            continue
        words = _WORD_STAMP.sub("", _STAMP.sub("", raw)).strip()
        for m, s, frac in stamps:
            lines.append((max(0.0, _seconds(m, s, frac) - offset), words))
    lines.sort(key=lambda x: x[0])
    return lines, length


def looks_synced(text: str) -> bool:
    return bool(text) and len(_STAMP.findall(text)) >= 3


# ------------------------------------------------------------ what to search
def song_query(song: dict, first=lambda v: v[0] if isinstance(v, list) else v) -> tuple[str, str, str]:
    """(artist, title, album) to look the song up with.

    Tags first; then "Artist - Title" in the title (radio streams); then the
    file name ("Artist - Title.flac", "05 - Title.mp3" with the artist taken
    from the folder)."""
    artist = (first(song.get("artist")) or first(song.get("albumartist")) or "").strip()
    title = (first(song.get("title")) or "").strip()
    album = (first(song.get("album")) or "").strip()
    if not artist and " - " in title:
        artist, title = (x.strip() for x in title.split(" - ", 1))
    if not title:
        path = song.get("file", "")
        if "://" not in path:
            stem = os.path.splitext(os.path.basename(path))[0]
            stem = re.sub(r"^\s*\d{1,3}[\s.\-_]+", "", stem)          # leading track number
            if " - " in stem:
                a, t = (x.strip() for x in stem.split(" - ", 1))
                artist = artist or a
                title = t
            else:
                title = stem.replace("_", " ").strip()
            if not artist:
                parts = path.split("/")
                if len(parts) >= 3:
                    artist = parts[-3]                                # Artist/Album/track
    return artist, title, album


def choose_candidate(hits: list[dict], duration: float | None) -> dict | None:
    """Best lrclib result: closest duration to our song, synced preferred.

    A synced version more than 15 s away loses against an unsynced one that
    matches; among equals the shorter distance wins."""
    usable = [h for h in hits or [] if h.get("syncedLyrics") or h.get("plainLyrics") or h.get("instrumental")]
    if not usable:
        return None

    def score(h):
        try:
            dist = abs(float(h.get("duration")) - duration) if duration else 30.0
        except (TypeError, ValueError):     # missing or malformed duration
            dist = 30.0
        synced_bonus = 0 if h.get("syncedLyrics") else 15
        return dist + synced_bonus

    return min(usable, key=score)


# ------------------------------------------------------------- time mapping
@dataclass
class Timing:
    speed: float = 1.0
    offset: float = 0.0
    anchors: list[tuple[float, float]] = field(default_factory=list)    # (song_t, lyric_t)
    reason: str = ""                   # shown to the user ("velocidad ajustada…")

    def lyric_time(self, song_t: float) -> float:
        return self.speed * song_t + self.offset

    def song_time(self, lyric_t: float) -> float:
        return (lyric_t - self.offset) / self.speed if self.speed else lyric_t

    def add_anchor(self, song_t: float, lyric_t: float):
        """The user says: the line timed `lyric_t` is being sung at `song_t`."""
        # replace an anchor for (almost) the same line
        self.anchors = [a for a in self.anchors if abs(a[1] - lyric_t) > 1.0]
        self.anchors.append((song_t, lyric_t))
        self.anchors.sort()
        self._fit()

    def shift(self, seconds: float):
        """Manual nudge: positive shows the lyrics later."""
        self.offset -= seconds
        self.reason = "ajuste manual"

    def _fit(self):
        pts = self.anchors
        spread = (pts[-1][0] - pts[0][0]) if len(pts) >= 2 else 0.0
        if len(pts) >= 2 and spread >= 20.0:
            n = len(pts)
            mx = sum(s for s, _ in pts) / n
            my = sum(lt for _, lt in pts) / n
            sxx = sum((s - mx) ** 2 for s, _ in pts)
            sxy = sum((s - mx) * (lt - my) for s, lt in pts)
            speed = sxy / sxx if sxx else 1.0
            if 0.5 <= speed <= 2.0:                  # reject absurd fits (wrong taps)
                self.speed = speed
                self.offset = my - speed * mx
                self.reason = f"sincronizada a mano ({n} puntos)"
                return
        s, lt = pts[-1]
        self.offset = lt - self.speed * s
        self.reason = "sincronizada a mano"

    def to_json(self) -> dict:
        return {"speed": self.speed, "offset": self.offset, "anchors": self.anchors}

    @classmethod
    def from_json(cls, d: dict) -> Timing:
        t = cls(float(d.get("speed", 1.0)), float(d.get("offset", 0.0)),
                [tuple(a) for a in d.get("anchors", [])], "sincronización guardada")
        return t


def auto_timing(lyrics_duration: float | None, song_duration: float | None) -> Timing:
    """Guess the mapping from the two durations.

    A clearly different length (4-30 %) is almost always a sped-up/slowed
    release, so the speed is scaled.  Small differences are ambiguous (intro
    or outro?) and are left alone: the user can tap a line to fix them."""
    t = Timing()
    if not lyrics_duration or not song_duration:
        return t
    ratio = lyrics_duration / song_duration
    if 1.04 <= ratio <= 1.30 or 1 / 1.30 <= ratio <= 1 / 1.04:
        t.speed = ratio
        t.reason = (f"la letra es de una versión de {_mmss(lyrics_duration)} y esta dura "
                    f"{_mmss(song_duration)}: velocidad ajustada ×{ratio:.2f}")
    elif abs(lyrics_duration - song_duration) > 3:
        t.reason = (f"la letra es de una versión de {_mmss(lyrics_duration)} (esta dura "
                    f"{_mmss(song_duration)}); si va desfasada, Mayús+clic en una línea al oírla")
    return t


def current_line(lines: list[tuple[float | None, str]], lyric_t: float) -> int:
    """Index of the line being sung at lyric time `lyric_t` (-1 before the first)."""
    lo, hi = 0, len(lines)
    while lo < hi:                       # binary search: lines are sorted by time
        mid = (lo + hi) // 2
        t = lines[mid][0]
        if t is not None and t <= lyric_t:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def _mmss(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# ------------------------------------------------------ what the UI shows
NOTHING_PLAYING = "Nada sonando"
SEARCHING = "Buscando la letra…"
NOT_FOUND = "No se encontró la letra de esta canción"
NO_INFO = "No se encontró la letra: la canción no tiene título"
OFFLINE = "No se pudo buscar la letra: lrclib.net no responde"
INSTRUMENTAL = "♪ Instrumental ♪"


@dataclass
class LyricsState:
    """Everything a lyrics view needs; shared by the classic panel and the
    lyrics window so both behave the same."""

    uri: str | None = None
    lyrics: Lyrics = field(default_factory=Lyrics)
    timing: Timing = field(default_factory=Timing)
    status: str = ""

    LEAD = 0.25          # highlight a line a bit early: reading takes time

    def line_at(self, song_t: float) -> int:
        if not self.lyrics.synced:
            return -1
        return current_line(self.lyrics.lines, self.timing.lyric_time(song_t + self.LEAD))

    def seek_target(self, idx: int) -> float | None:
        """Song position where line `idx` starts (None if not synced)."""
        if not self.lyrics.synced or not 0 <= idx < len(self.lyrics.lines):
            return None
        t = self.lyrics.lines[idx][0]
        return None if t is None else max(0.0, self.timing.song_time(t))

    def tap(self, idx: int, song_t: float) -> bool:
        """User: line `idx` is being sung right now."""
        if not self.lyrics.synced or not 0 <= idx < len(self.lyrics.lines):
            return False
        t = self.lyrics.lines[idx][0]
        if t is None:
            return False
        self.timing.add_anchor(song_t, t)
        return True

    def info(self) -> str:
        """One line for the status area: source and sync state."""
        if not self.lyrics.lines:
            return self.status
        parts = [self.lyrics.source] if self.lyrics.source else []
        if not self.lyrics.synced:
            parts.append("sin sincronizar")
        elif self.timing.reason:
            parts.append(self.timing.reason)
        return " · ".join(parts)


# ------------------------------------------------------- per-song storage
class SyncStore:
    """User corrections per song (file uri), in a small JSON file."""

    def __init__(self, path: str):
        self.path = path
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def get(self, uri: str) -> Timing | None:
        d = self._load().get(uri)
        return Timing.from_json(d) if d else None

    def put(self, uri: str, timing: Timing | None):
        data = self._load()
        if timing is None:
            data.pop(uri, None)
        else:
            data[uri] = timing.to_json()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass
