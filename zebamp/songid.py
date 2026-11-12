"""Knowing what a song is when its tags do not say.

Two ways, from cheap to costly:

* **the file name**: "Artist - Title.mp3" (the same reading the lyrics use);
* **its sound**: an acoustic fingerprint of the audio (`fpcalc`, from
  Chromaprint) is looked up in the AcoustID database, which answers with
  the MusicBrainz recording -- artist, title and album.

Recognising by sound needs the Internet and the user's own (free) AcoustID
application key; without them only the file name is used.  Programs that do
this offline carry their own song database, which a music player cannot.

What a file turned out to be is remembered (per file, until it changes), so
a song is fingerprinted once.  The top of the module is pure.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from .lyricsync import song_query
from .player import first
from .threads import USER_AGENT

log = logging.getLogger(__name__)

ACOUSTID = "https://api.acoustid.org/v2/lookup"
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp", "songid")
MIN_SCORE = 0.85            # AcoustID's confidence (0..1) to believe a match
FINGERPRINT_SECONDS = 120   # how much of the song fpcalc listens to (its default)
FPCALC_TIMEOUT = 40
HTTP_TIMEOUT = 12
NOT_FOUND_RETRY = 30 * 24 * 3600        # an unknown song is asked about again after a month
INVALID_KEY = 4             # AcoustID error code


@dataclass
class Identified:
    """What a song is, according to AcoustID / MusicBrainz."""
    artist: str
    title: str
    album: str = ""
    recording_id: str = ""
    group_id: str = ""          # MusicBrainz release group of `album`
    score: float = 0.0

    def as_tags(self) -> dict:
        """As MPD would give them (only what is known)."""
        tags = {"artist": self.artist, "title": self.title, "album": self.album,
                "musicbrainz_releasegroupid": self.group_id}
        return {k: v for k, v in tags.items() if v}


# ----------------------------------------------------------------- pure
def has_names(song: dict) -> bool:
    """The tags are enough to look the song up (artist and title or album)."""
    artist = first(song.get("artist")) or first(song.get("albumartist"))
    return bool(artist and (first(song.get("title")) or first(song.get("album"))))


def names_from_file(song: dict) -> dict:
    """`song` with the artist and title its tags lack read from the file
    name ("Artist - Title.mp3").  Tags that exist are never replaced."""
    if "://" in song.get("file", ""):
        return dict(song)
    artist, title, _album = song_query(song)
    if not artist:
        # a title tag alone: the file name may still name the artist
        artist = song_query({**song, "title": ""})[0]
    guessed = dict(song)
    if artist and not (first(song.get("artist")) or first(song.get("albumartist"))):
        guessed["artist"] = artist
    if title and not first(song.get("title")):
        guessed["title"] = title
    return guessed


def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _artist_names(recording: dict) -> str:
    parts = []
    for artist in _dicts(recording.get("artists")):
        parts.append(str(artist.get("name") or "") + str(artist.get("joinphrase") or ""))
    return "".join(parts).strip()


def _album_of(recording: dict) -> tuple[str, str]:
    """(title, id) of the recording's album: a studio album if it has one,
    rather than a compilation, a live record or a single."""
    groups = _dicts(recording.get("releasegroups"))

    def rank(group):
        plain_album = group.get("type") == "Album" and not group.get("secondarytypes")
        return (not plain_album, group.get("type") != "Album")
    for group in sorted(groups, key=rank)[:1]:
        return str(group.get("title") or ""), str(group.get("id") or "")
    return "", ""


def best_match(answer: dict, duration: float = 0.0) -> Identified | None:
    """The song an AcoustID answer points to, or None when it is not sure
    enough.  Among the recordings of the best result, the one whose length
    is closest to ours (the same sound is often filed under several)."""
    results = sorted(_dicts(answer.get("results")), key=lambda r: -_number(r.get("score")))
    for result in results[:1]:
        score = _number(result.get("score"))
        if score < MIN_SCORE:
            return None
        named = [r for r in _dicts(result.get("recordings")) if r.get("title") and _artist_names(r)]
        if not named:
            return None

        def distance(recording):
            length = _number(recording.get("duration"))
            return abs(length - duration) if length and duration else 1e9
        recording = min(named, key=distance)
        album, group_id = _album_of(recording)
        return Identified(_artist_names(recording), str(recording["title"]), album,
                          str(recording.get("id") or ""), group_id, score)
    return None


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def invalid_key(answer: dict) -> bool:
    error = answer.get("error")
    return isinstance(error, dict) and error.get("code") == INVALID_KEY


# ---------------------------------------------------------- fingerprint
def available() -> bool:
    """`fpcalc` (package chromaprint) is installed."""
    return shutil.which("fpcalc") is not None


def fingerprint(path: str) -> tuple[float, str] | None:
    """(duration, fingerprint) of an audio file, or None if it cannot be read."""
    try:
        out = subprocess.run(["fpcalc", "-json", "-length", str(FINGERPRINT_SECONDS), path],
                             capture_output=True, text=True, timeout=FPCALC_TIMEOUT).stdout
        data = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        log.info("fpcalc %s: %s", path, e)
        return None
    if not isinstance(data, dict) or not data.get("fingerprint"):
        return None
    return _number(data.get("duration")), str(data["fingerprint"])


def ask_acoustid(key: str, duration: float, print_: str) -> dict:
    """AcoustID's answer for a fingerprint.  Raises OSError when it cannot
    be asked (offline, overloaded)."""
    form = urllib.parse.urlencode({"client": key, "format": "json", "duration": int(round(duration)),
                                   "fingerprint": print_, "meta": "recordings releasegroups"}).encode()
    request = urllib.request.Request(ACOUSTID, data=form, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as reply:
            body = reply.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        with e:
            if e.code >= 500 or e.code == 429:
                raise OSError(f"HTTP {e.code}") from e
            body = e.read(64 * 1024)        # errors (a bad key…) come as JSON too
    try:
        answer = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        answer = {}
    return answer if isinstance(answer, dict) else {}


# ----------------------------------------------------------------- cache
class IdCache:
    """What each file was identified as: `<key>.json`, the key naming the
    file as it is now (path, size and date), so a replaced file is new."""

    def __init__(self, directory: str | None = None):
        self.directory = directory or CACHE

    def _path(self, file_path: str) -> str | None:
        try:
            info = os.stat(file_path)
        except OSError:
            return None
        key = hashlib.md5(f"{file_path}\n{info.st_size}\n{int(info.st_mtime)}".encode()).hexdigest()
        return os.path.join(self.directory, key + ".json")

    def _read(self, file_path: str) -> dict:
        path = self._path(file_path)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, file_path: str) -> Identified | None:
        found = self._read(file_path).get("found")
        try:
            return Identified(**found) if isinstance(found, dict) and found.get("artist") else None
        except TypeError:
            return None

    def tried(self, file_path: str, now: float | None = None) -> bool:
        """Already identified, or asked about recently without luck."""
        data = self._read(file_path)
        if data.get("found"):
            return True
        missed = data.get("missed")
        now = time.time() if now is None else now
        return isinstance(missed, (int, float)) and now - missed < NOT_FOUND_RETRY

    def put(self, file_path: str, identified: Identified | None):
        path = self._path(file_path)
        if path is None:
            return
        data = {"found": asdict(identified)} if identified else {"missed": time.time()}
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log.debug("song id cache: %s", e)


# -------------------------------------------------------------- identify
class BadKey(Exception):
    """AcoustID refused the application key."""


_identify_lock = threading.Lock()


def identify(file_path: str, key: str, cache: IdCache | None = None, force=False,
             make_print=None, ask=None) -> Identified | None:
    """What the audio in `file_path` is, or None when AcoustID does not know
    it (or cannot be asked now).  Blocking: call it from a worker thread.
    Raises BadKey when the key is not accepted."""
    cache = cache or IdCache()
    make_print, ask = make_print or fingerprint, ask or ask_acoustid
    # one at a time: several windows ask about the same song when it starts
    with _identify_lock:
        if not force and cache.tried(file_path):
            return cache.get(file_path)
        printed = make_print(file_path)
        if printed is None:
            return None
        duration, print_ = printed
        try:
            answer = ask(key, duration, print_)
        except OSError as e:
            log.info("acoustid unreachable: %s", e)
            return None                     # offline: not remembered, asked again later
        if invalid_key(answer):
            raise BadKey
        if answer.get("status") != "ok":
            log.info("acoustid: %s", answer.get("error"))
            return None
        identified = best_match(answer, duration)
        cache.put(file_path, identified)
        return identified


def key_accepted(key: str, ask=None) -> bool | None:
    """True/False whether AcoustID takes the key; None if it cannot be asked.
    (A made-up fingerprint is sent: a bad key is refused before it is read.)"""
    try:
        answer = (ask or ask_acoustid)(key, 1, "AQAAAA")
    except OSError:
        return None
    return not invalid_key(answer)


# ------------------------------------------------- names to search with
def local_file(song: dict, music_dir: str | None) -> str | None:
    """The song's file on this computer, if MPD's music folder is here."""
    uri = song.get("file", "")
    if not uri or "://" in uri or not music_dir:
        return None
    path = os.path.join(music_dir, uri)
    return path if os.path.isfile(path) else None


def described(song: dict, music_dir: str | None = None, cache: IdCache | None = None) -> dict:
    """`song` with the best names known for it, to search covers with: its
    tags; else what it was identified as by its sound (if that was done);
    else what the file name says."""
    if has_names(song):
        return dict(song)
    path = local_file(song, music_dir)
    identified = (cache or IdCache()).get(path) if path else None
    if identified is not None:
        return {**song, **identified.as_tags()}
    return names_from_file(song)


def can_identify(song: dict, music_dir: str | None, key: str, cache: IdCache | None = None) -> str | None:
    """The file to fingerprint when recognising `song` by its sound makes
    sense now: tags incomplete, key and fpcalc present, the file is here and
    it has not been tried lately.  None otherwise."""
    if not key or has_names(song) or not available():
        return None
    path = local_file(song, music_dir)
    if path is None or (cache or IdCache()).tried(path):
        return None
    return path
