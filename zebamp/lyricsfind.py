"""Find the lyrics of a song, most trustworthy source first:

1. a ``.lrc`` file next to the song (your own, already in sync),
2. lyrics embedded in the file's tags (read through MPD, works remotely),
3. the local cache of earlier lookups,
4. lrclib.net, choosing the release whose duration matches the song.

Runs in a worker thread (it does disk and network I/O); returns a
:class:`zebamp.lyricsync.Lyrics`.  "Not found" is cached for a few days so
songs without lyrics don't hit the network on every play.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from urllib.parse import urlencode

from .lyricsync import Lyrics, choose_candidate, looks_synced, parse_lrc, song_query
from .threads import http_json
from .i18n import tr

log = logging.getLogger(__name__)

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp", "lyrics")
NOT_FOUND_RETRY = 3 * 24 * 3600          # look again after 3 days
API = "https://lrclib.net/api"


class LyricsUnavailable(Exception):
    """Network failure (as opposed to "no lyrics exist")."""


def _from_text(text: str, source: str, duration: float | None = None) -> Lyrics:
    if looks_synced(text):
        lines, length = parse_lrc(text)
        return Lyrics(lines=[(t, x or "♪") for t, x in lines], synced=True,
                      duration=duration or length, source=source)
    plain = [x.rstrip() for x in (text or "").strip().splitlines()]
    return Lyrics(lines=[(None, x) for x in plain], source=source, duration=duration)


def from_sidecar(song: dict, music_dir: str | None) -> Lyrics | None:
    path = song.get("file", "")
    if not music_dir or "://" in path:
        return None
    base = os.path.splitext(os.path.join(music_dir, path))[0]
    for ext in (".lrc", ".LRC"):
        try:
            with open(base + ext, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if text.strip():
            return _from_text(text, tr("archivo .lrc"))
    return None


def from_tags(client, song: dict) -> Lyrics | None:
    """LYRICS / SYNCEDLYRICS / UNSYNCEDLYRICS (Vorbis, APE…) via MPD."""
    uri = song.get("file", "")
    if client is None or not uri or "://" in uri:
        return None
    try:
        comments = client.readcomments(uri) or {}
    except Exception as e:
        log.debug("readcomments %s: %s", uri, e)
        return None
    texts = [v for k, v in comments.items() if "lyric" in k.lower() and v]
    texts = [t if isinstance(t, str) else "\n".join(t) for t in texts]
    texts.sort(key=lambda t: 0 if looks_synced(t) else 1)       # synced first
    return _from_text(texts[0], tr("etiquetas del archivo")) if texts else None


def _cache_path(artist: str, title: str, duration: float | None) -> str:
    # duration rounded to 5 s: a sped-up release gets its own entry
    bucket = int(round((duration or 0) / 5.0))
    key = hashlib.md5(f"v2\n{artist}\n{title}\n{bucket}".lower().encode()).hexdigest()
    return os.path.join(CACHE, key + ".json")


def _read_cache(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    if d.get("notfound") and time.time() - d.get("ts", 0) > NOT_FOUND_RETRY:
        return None
    return d


def _write_cache(path: str, data: dict):
    try:
        os.makedirs(CACHE, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        log.debug("lyrics cache: %s", e)


def fetch_lrclib(artist: str, title: str, album: str, duration: float | None) -> dict | None:
    """The best lrclib record, or None if it has no lyrics.  Raises
    LyricsUnavailable when the service can't be reached."""
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(round(duration))
    hits = []
    reached = False
    try:
        rec = http_json(f"{API}/get?" + urlencode(params))   # exact match (±2 s)
        reached = True
        if isinstance(rec, dict):                            # never trust remote data shapes
            hits.append(rec)
    except Exception as e:
        reached = reached or "404" in str(e)
    if not hits or not hits[0].get("syncedLyrics"):
        try:
            q = {"track_name": title}
            if artist:
                q["artist_name"] = artist
            found = http_json(f"{API}/search?" + urlencode(q))
            reached = True
            if isinstance(found, list):
                hits += [h for h in found if isinstance(h, dict)]
        except Exception as e:
            log.debug("lrclib search: %s", e)
    if not reached:
        raise LyricsUnavailable(tr("lrclib.net no responde"))
    return choose_candidate(hits, duration)


def find_lyrics(song: dict, music_dir: str | None, duration: float | None,
                client=None, force: bool = False) -> Lyrics:
    """Lyrics for `song` from the best available source (see module doc).

    Returns an empty Lyrics (``found`` False) when there are none; raises
    LyricsUnavailable only when nothing local exists and the network failed."""
    for local in (from_sidecar(song, music_dir), from_tags(client, song)):
        if local is not None and local.found:
            return local
    artist, title, album = song_query(song)
    if not title:
        return Lyrics()
    path = _cache_path(artist, title, duration)
    data = None if force else _read_cache(path)
    if data is None:
        rec = fetch_lrclib(artist, title, album, duration)
        if rec is None:
            data = {"notfound": True, "ts": time.time()}
        else:
            data = {"synced": rec.get("syncedLyrics") or "", "plain": rec.get("plainLyrics") or "",
                    "instrumental": bool(rec.get("instrumental")), "duration": rec.get("duration")}
        _write_cache(path, data)
    if data.get("notfound"):
        return Lyrics()
    if data.get("instrumental"):
        return Lyrics(instrumental=True, source="lrclib.net")
    return _from_text(data.get("synced") or data.get("plain") or "", "lrclib.net", data.get("duration"))
