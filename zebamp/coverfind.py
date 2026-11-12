"""Album covers from the Internet, for music that carries none.

Local art always wins (embedded picture, MPD's cover.*, the album folder);
this module is only asked when there is nothing local, and only if the user
left "look for covers on the Internet" on.

The search is built to be right rather than to always return something:

1. the MusicBrainz release id in the file's tags, when it has one: exact;
2. artist + album on MusicBrainz (pictures from the Cover Art Archive), then
   Deezer, then iTunes;
3. for songs without an album tag, artist + title + duration.

A candidate is accepted only if its title and artist really match (see
`album_score` / `track_score`); otherwise the album simply has no cover.
The top half of the module is pure (text matching, reading the services'
answers); the network and the cache are at the bottom.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .libindex import fold
from .player import first
from .threads import USER_AGENT

log = logging.getLogger(__name__)

MUSICBRAINZ = "https://musicbrainz.org/ws/2"
COVER_ART_ARCHIVE = "https://coverartarchive.org"
DEEZER = "https://api.deezer.com"
ITUNES = "https://itunes.apple.com"

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp", "covers")
NOT_FOUND_RETRY = 7 * 24 * 3600         # look again after a week
HTTP_TIMEOUT = 10
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MUSICBRAINZ_PAUSE = 1.1                 # seconds between requests (their limit is 1 per second)
CANDIDATES_TO_TRY = 3                   # best matches whose picture is downloaded, in order

MIN_TITLE, MIN_ARTIST = 0.88, 0.80      # how alike names must be to accept a candidate
MIN_TITLE_ALONE = 0.95                  # compilations: the artist cannot be checked
DURATION_SLACK = 7                      # seconds a track may differ from ours

VARIOUS = {"various artists", "various", "varios artistas", "varios", "va", "varios interpretes"}
# "(Remastered 2011)", "[Deluxe Edition]", " - Single"…: the same album
_EDITION = (r"remaster(ed)?|remasterizad[oa]|deluxe|expanded|edition|edicion|bonus|anniversary|aniversario|"
            r"version|mono|stereo|reissue|special|explicit|single|ep|disc ?\d+|cd ?\d+|\d{4}")
_BRACKETED = re.compile(r"[\(\[][^\)\]]*\b(" + _EDITION + r")\b[^\)\]]*[\)\]]")
_DASH_SUFFIX = re.compile(r"\s+-\s+[^-]*\b(" + _EDITION + r")\b[^-]*$")
_BRACKETED_ANY_CASE = re.compile(_BRACKETED.pattern, re.IGNORECASE)
_DASH_SUFFIX_ANY_CASE = re.compile(_DASH_SUFFIX.pattern, re.IGNORECASE)
_FEATURING = re.compile(r"\s+(feat\.?|ft\.?|featuring|con)\s+.*$")
_NOT_WORD = re.compile(r"[^a-z0-9]+")
_NUMBER_WORD = re.compile(r"\d+|[ivx]+")


# ------------------------------------------------------------- matching
def clean(text: str) -> str:
    """A name reduced to what identifies it: no accents, case, punctuation
    or edition notes ("Disco (Deluxe Edition)" -> "disco")."""
    text = fold(str(text or "")).replace("&", " and ")
    text = _DASH_SUFFIX.sub("", _BRACKETED.sub(" ", text))
    return _NOT_WORD.sub(" ", text).strip()


def clean_artist(text: str) -> str:
    """Main artist: "The Band feat. Someone" -> "band"."""
    name = clean(_FEATURING.sub("", fold(str(text or ""))))
    return name[4:] if name.startswith("the ") else name


def _markers(name: str) -> list[str]:
    """The numbers and Roman numerals of a cleaned name, in order."""
    return [word for word in name.split() if _NUMBER_WORD.fullmatch(word)]


def similarity(a: str, b: str) -> float:
    """0..1 between two cleaned names.  Names that differ in a number are
    different things however alike they look ("Hits 2001" / "Hits 2002",
    "Vol. 1" / "Vol. 2", "II" / "III")."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if _markers(a) != _markers(b):
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class Query:
    """What is known about the music a cover is wanted for."""
    artist: str
    album: str = ""
    title: str = ""
    year: str = ""
    duration: float = 0.0
    release_id: str = ""        # MusicBrainz ids from the tags
    group_id: str = ""

    @property
    def various(self) -> bool:
        return clean(self.artist) in VARIOUS

    def key(self) -> str:
        """Names the album (or the lone song) in the cache."""
        what = clean(self.album) or "song:" + clean(self.title)
        return hashlib.md5(f"{clean_artist(self.artist)}\n{what}".encode()).hexdigest()


@dataclass
class Candidate:
    """A cover a service offers."""
    source: str
    ident: str                  # unique within all sources
    title: str
    artist: str
    year: str = ""
    duration: float = 0.0
    images: list = field(default_factory=list)      # URLs to try, best first


def _text(value) -> str:
    return str(first(value) or "").strip()


def query_from_song(song: dict) -> Query | None:
    """The search for an MPD song; None when there is nothing to search with
    (streams, files without tags)."""
    uri = song.get("file", "")
    artist = _text(song.get("albumartist")) or _text(song.get("artist"))
    album, title = _text(song.get("album")), _text(song.get("title"))
    release_id = _text(song.get("musicbrainz_albumid"))
    if not uri or "://" in uri:
        return None
    group_id = _text(song.get("musicbrainz_releasegroupid"))
    if not (release_id or group_id) and (not artist or not (album or title)):
        return None
    try:
        duration = float(song.get("duration") or song.get("time") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return Query(artist=artist, album=album, title=title, year=_text(song.get("date"))[:4], duration=duration,
                 release_id=release_id, group_id=group_id)


def artist_similarity(a: str, b: str) -> float:
    """0..1 between two cleaned artist names.  Services often add to the
    name ("Juan Luis Guerra" / "Juan Luis Guerra 4.40", "Queen" / "Queen +
    Adam Lambert"): one name starting the other, by whole words, is a match."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    short, long = sorted((a, b), key=len)
    if long.startswith(short + " "):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def _artist_match(query: Query, candidate: Candidate) -> float:
    return artist_similarity(clean_artist(query.artist), clean_artist(candidate.artist))


def search_name(text: str) -> str:
    """A name as it is typed into a search: without the edition notes that
    the services do not have ("Disco (Remastered)" -> "Disco")."""
    plain = _DASH_SUFFIX_ANY_CASE.sub("", _BRACKETED_ANY_CASE.sub(" ", text))
    return " ".join(plain.split()) or text


def album_score(query: Query, candidate: Candidate) -> float:
    """How well a candidate album fits; 0 = not the same album."""
    title = similarity(clean(query.album), clean(candidate.title))
    if query.various:
        if title < MIN_TITLE_ALONE:
            return 0.0
        artist = 1.0 if clean(candidate.artist) in VARIOUS else 0.9
    else:
        artist = _artist_match(query, candidate)
        if title < MIN_TITLE or artist < MIN_ARTIST:
            return 0.0
    same_year = bool(query.year) and query.year == candidate.year
    return 0.6 * title + 0.4 * artist + (0.05 if same_year else 0.0)


def track_score(query: Query, candidate: Candidate) -> float:
    """The same for a single song (candidate.title is the song's title)."""
    title = similarity(clean(query.title), clean(candidate.title))
    artist = _artist_match(query, candidate)
    if title < MIN_TITLE or artist < MIN_ARTIST:
        return 0.0
    if query.duration and candidate.duration and abs(query.duration - candidate.duration) > DURATION_SLACK:
        return 0.0              # another recording of the song (live, remix…)
    return 0.6 * title + 0.4 * artist


def ranked(query: Query, candidates: list[Candidate], rejected=()) -> list[Candidate]:
    """Acceptable candidates, best first (ties keep the service's order)."""
    score = album_score if query.album else track_score
    scored = [(score(query, c), c) for c in candidates if c.ident not in rejected and c.images]
    return [c for s, c in sorted(scored, key=lambda sc: -sc[0]) if s > 0]


# ----------------------------------------------- reading the services
def _lucene(text: str) -> str:
    return '"' + text.replace("\\", " ").replace('"', " ") + '"'


def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _credit(entry: dict) -> str:
    """MusicBrainz artist-credit as one name."""
    parts = []
    for credit in _dicts(entry.get("artist-credit")):
        parts.append(str(credit.get("name") or "") + str(credit.get("joinphrase") or ""))
    return "".join(parts).strip()


def _archive_images(release_id: str, group_id: str = "") -> list[str]:
    urls = [f"{COVER_ART_ARCHIVE}/release/{release_id}/front-500"] if release_id else []
    if group_id:
        urls.append(f"{COVER_ART_ARCHIVE}/release-group/{group_id}/front-500")
    return urls


def musicbrainz_album_url(query: Query) -> str:
    search = f"release:{_lucene(search_name(query.album))}"
    if not query.various:
        search += f" AND artist:{_lucene(query.artist)}"
    return f"{MUSICBRAINZ}/release?" + urllib.parse.urlencode({"query": search, "fmt": "json", "limit": 10})


def musicbrainz_albums(answer: dict) -> list[Candidate]:
    out = []
    for release in _dicts(answer.get("releases")):
        ident = str(release.get("id") or "")
        group = release.get("release-group") if isinstance(release.get("release-group"), dict) else {}
        if ident:
            out.append(Candidate("MusicBrainz", "mb:" + ident, str(release.get("title") or ""), _credit(release),
                                 str(release.get("date") or "")[:4],
                                 images=_archive_images(ident, str(group.get("id") or ""))))
    return out


def musicbrainz_track_url(query: Query) -> str:
    search = f"recording:{_lucene(search_name(query.title))} AND artist:{_lucene(query.artist)}"
    return f"{MUSICBRAINZ}/recording?" + urllib.parse.urlencode({"query": search, "fmt": "json", "limit": 10})


def musicbrainz_tracks(answer: dict) -> list[Candidate]:
    """One candidate per recording: the cover of its first album release
    (or of its first release of any kind)."""
    out = []
    for recording in _dicts(answer.get("recordings")):
        releases = _dicts(recording.get("releases"))

        def is_album(release):
            group = release.get("release-group")
            return isinstance(group, dict) and group.get("primary-type") == "Album"
        chosen = sorted(releases, key=lambda r: (not is_album(r), str(r.get("date") or "9999")))[:1]
        for release in chosen:
            ident = str(release.get("id") or "")
            group = release.get("release-group") if isinstance(release.get("release-group"), dict) else {}
            try:
                seconds = float(recording.get("length") or 0) / 1000
            except (TypeError, ValueError):
                seconds = 0.0
            if ident:
                out.append(Candidate("MusicBrainz", "mb:" + ident, str(recording.get("title") or ""),
                                     _credit(recording), duration=seconds,
                                     images=_archive_images(ident, str(group.get("id") or ""))))
    return out


def _plain_search(query: Query, what: str) -> str:
    """Words for a free-text search (Deezer and iTunes find more that way
    than with field filters; the answers are checked strictly afterwards)."""
    what = search_name(what)
    return what if query.various else f"{query.artist} {what}"


def deezer_album_url(query: Query) -> str:
    return f"{DEEZER}/search/album?" + urllib.parse.urlencode({"q": _plain_search(query, query.album), "limit": 10})


def _deezer_cover(album: dict) -> list[str]:
    url = str(album.get("cover_xl") or album.get("cover_big") or "")
    # albums without art get a placeholder whose address has an empty picture id
    return [url] if url.startswith("https://") and "/cover//" not in url else []


def _name(value) -> str:
    return str(value.get("name") or "") if isinstance(value, dict) else ""


def deezer_albums(answer: dict) -> list[Candidate]:
    return [Candidate("Deezer", f"deezer:{a.get('id')}", str(a.get("title") or ""), _name(a.get("artist")),
                      images=_deezer_cover(a))
            for a in _dicts(answer.get("data"))]


def deezer_track_url(query: Query) -> str:
    return f"{DEEZER}/search/track?" + urllib.parse.urlencode({"q": _plain_search(query, query.title), "limit": 10})


def deezer_tracks(answer: dict) -> list[Candidate]:
    out = []
    for track in _dicts(answer.get("data")):
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        try:
            seconds = float(track.get("duration") or 0)
        except (TypeError, ValueError):
            seconds = 0.0
        out.append(Candidate("Deezer", f"deezer:{album.get('id')}", str(track.get("title") or ""),
                             _name(track.get("artist")), duration=seconds, images=_deezer_cover(album)))
    return out


def _itunes_url(query: Query, entity: str, what: str) -> str:
    return f"{ITUNES}/search?" + urllib.parse.urlencode({"term": _plain_search(query, what), "entity": entity,
                                                         "limit": 10})


def itunes_album_url(query: Query) -> str:
    return _itunes_url(query, "album", query.album)


def itunes_track_url(query: Query) -> str:
    return _itunes_url(query, "song", query.title)


def _itunes_art(item: dict) -> list[str]:
    url = str(item.get("artworkUrl100") or "")
    # the address carries the size: ask for a bigger picture of the same art
    return [url.replace("100x100", "600x600")] if url.startswith("https://") else []


def itunes_albums(answer: dict) -> list[Candidate]:
    return [Candidate("iTunes", f"itunes:{r.get('collectionId')}", str(r.get("collectionName") or ""),
                      str(r.get("artistName") or ""), str(r.get("releaseDate") or "")[:4], images=_itunes_art(r))
            for r in _dicts(answer.get("results"))]


def itunes_tracks(answer: dict) -> list[Candidate]:
    out = []
    for r in _dicts(answer.get("results")):
        try:
            seconds = float(r.get("trackTimeMillis") or 0) / 1000
        except (TypeError, ValueError):
            seconds = 0.0
        out.append(Candidate("iTunes", f"itunes:{r.get('collectionId')}", str(r.get("trackName") or ""),
                             str(r.get("artistName") or ""), duration=seconds, images=_itunes_art(r)))
    return out


# (service, address of the search, reader of its answer) in the order they are asked
ALBUM_SOURCES = ((musicbrainz_album_url, musicbrainz_albums), (deezer_album_url, deezer_albums),
                 (itunes_album_url, itunes_albums))
TRACK_SOURCES = ((musicbrainz_track_url, musicbrainz_tracks), (deezer_track_url, deezer_tracks),
                 (itunes_track_url, itunes_tracks))


# --------------------------------------------------------------- network
class Unreachable(Exception):
    """No service could be asked (offline): do not remember "not found"."""


_musicbrainz_lock = threading.Lock()
_musicbrainz_last = 0.0


def _get(url: str, limit: int) -> bytes | None:
    """Body of a GET; None for "not there" (404…).  Raises OSError when the
    service cannot answer now (offline, overloaded, asking us to slow down)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, image/*"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as reply:
            return reply.read(limit + 1)
    except urllib.error.HTTPError as e:
        with e:
            if e.code >= 500 or e.code == 429:
                raise OSError(f"HTTP {e.code}") from e
        return None


def _get_musicbrainz(url: str, limit: int) -> bytes | None:
    """MusicBrainz allows one request per second: they are made one at a
    time and spaced out, and a "slow down" answer is tried once more."""
    global _musicbrainz_last
    with _musicbrainz_lock:
        for attempt in (1, 2):
            wait = _musicbrainz_last + MUSICBRAINZ_PAUSE - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _musicbrainz_last = time.monotonic()
            try:
                return _get(url, limit)
            except OSError:
                if attempt == 2:
                    raise
    return None


def _open(url: str, limit: int) -> bytes | None:
    if not url.startswith("https://"):
        return None                 # addresses come from the services' answers: never a local file
    return _get_musicbrainz(url, limit) if url.startswith(MUSICBRAINZ) else _get(url, limit)


def fetch_json(url: str) -> dict:
    body = _open(url, 2 * 1024 * 1024)
    try:
        answer = json.loads(body.decode("utf-8", "replace")) if body else {}
    except ValueError:
        answer = {}
    return answer if isinstance(answer, dict) else {}


def fetch_image(url: str) -> bytes | None:
    body = _open(url, MAX_IMAGE_BYTES)
    return body if body and len(body) <= MAX_IMAGE_BYTES else None


# ---------------------------------------------------------------- search
@dataclass
class Found:
    data: bytes
    source: str
    ident: str


def _first_picture(candidates: list[Candidate], is_image, get_image, state: dict) -> Found | None:
    for candidate in candidates[:CANDIDATES_TO_TRY]:
        for url in candidate.images:
            try:
                data = get_image(url)
            except OSError as e:
                log.info("cover: %s unreachable (%s)", urllib.parse.urlsplit(url).netloc, e)
                continue
            state["reached"] = True
            if data and is_image(data):
                return Found(data, candidate.source, candidate.ident)
    return None


def find_cover(query: Query, is_image, rejected=(), get_json=None, get_image=None) -> Found | None:
    """The cover for `query`, or None when no service has one that matches.

    `is_image(bytes)` tells whether a download really is a usable picture;
    `rejected` are candidates the user said were wrong.  Raises Unreachable
    when nothing could be asked at all."""
    get_json, get_image = get_json or fetch_json, get_image or fetch_image
    state = {"reached": False}
    exact_id = "mb:" + (query.release_id or query.group_id)
    if (query.release_id or query.group_id) and exact_id not in rejected:
        # ids from the tags, or from recognising the song by its sound: no guessing
        exact = Candidate("MusicBrainz", exact_id, query.album, query.artist,
                          images=_archive_images(query.release_id, query.group_id))
        found = _first_picture([exact], is_image, get_image, state)
        if found:
            return found
    if not query.artist or not (query.album or query.title):
        return None
    for make_url, read in (ALBUM_SOURCES if query.album else TRACK_SOURCES):
        url = make_url(query)
        try:
            candidates = read(get_json(url))
        except OSError as e:
            log.info("cover: %s unreachable (%s)", urllib.parse.urlsplit(url).netloc, e)
            continue
        state["reached"] = True
        found = _first_picture(ranked(query, candidates, rejected), is_image, get_image, state)
        if found:
            return found
    if not state["reached"]:
        raise Unreachable
    return None


# ----------------------------------------------------------------- cache
class CoverCache:
    """Downloaded covers, one per album: `<key>.img` is the picture and
    `<key>.json` what is known about it (where it came from, when nothing was
    found, which candidates the user rejected)."""

    def __init__(self, directory: str | None = None):
        self.directory = directory or CACHE

    def image_path(self, query: Query) -> str:
        return os.path.join(self.directory, f"online-{query.key()}.img")

    def _meta_path(self, query: Query) -> str:
        return os.path.join(self.directory, f"online-{query.key()}.json")

    def meta(self, query: Query) -> dict:
        try:
            with open(self._meta_path(query), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_meta(self, query: Query, meta: dict):
        try:
            os.makedirs(self.directory, exist_ok=True)
            tmp = self._meta_path(query) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(meta, fh)
            os.replace(tmp, self._meta_path(query))
        except OSError as e:
            log.debug("cover cache: %s", e)

    def has_image(self, query: Query) -> bool:
        return os.path.exists(self.image_path(query))

    def rejected(self, query: Query) -> list[str]:
        return [str(x) for x in self.meta(query).get("rejected") or []]

    def should_search(self, query: Query, now: float | None = None) -> bool:
        """False while a recent search found nothing (or the user said no)."""
        meta = self.meta(query)
        if meta.get("off"):
            return False
        missed = meta.get("missed")
        now = time.time() if now is None else now
        return not (isinstance(missed, (int, float)) and now - missed < NOT_FOUND_RETRY)

    def store(self, query: Query, found: Found) -> str | None:
        path = self.image_path(query)
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(path + ".tmp", "wb") as fh:
                fh.write(found.data)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log.debug("cover cache: %s", e)
            return None
        self._write_meta(query, {"source": found.source, "ident": found.ident, "rejected": self.rejected(query)})
        return path

    def store_miss(self, query: Query):
        self._write_meta(query, {"missed": time.time(), "rejected": self.rejected(query)})

    def reject(self, query: Query, give_up=False):
        """The cover shown is wrong: forget it and never offer it again.
        With `give_up` nothing more is searched for this album."""
        meta = self.meta(query)
        rejected = self.rejected(query)
        if meta.get("ident") and meta["ident"] not in rejected:
            rejected.append(meta["ident"])
        try:
            os.unlink(self.image_path(query))
        except OSError:
            pass
        self._write_meta(query, {"rejected": rejected, "off": bool(give_up)})

    def forget(self, query: Query):
        """Search from scratch next time (rejections included)."""
        for path in (self.image_path(query), self._meta_path(query)):
            try:
                os.unlink(path)
            except OSError:
                pass


_search_lock = threading.Lock()


def online_cover(song: dict, is_image, cache: CoverCache | None = None, force=False,
                 get_json=None, get_image=None) -> str | None:
    """Path of the downloaded cover of `song`, searching if needed.
    Blocking: call it from a worker thread."""
    query = query_from_song(song)
    if query is None:
        return None
    cache = cache or CoverCache()
    # one search at a time: the notification, MPRIS and the album art window
    # all ask when a song starts, and the second one must find the first's answer
    with _search_lock:
        if cache.has_image(query):
            return cache.image_path(query)
        if not force and not cache.should_search(query):
            return None
        try:
            found = find_cover(query, is_image, cache.rejected(query), get_json, get_image)
        except Unreachable:
            return None                 # offline: try again next time
        if found is None:
            cache.store_miss(query)
            return None
        return cache.store(query, found)
