"""Scrobbling: send what you listen to ListenBrainz and/or Last.fm.

Off unless the user enables a service in Preferences.  A song counts once it
played past half (or four minutes) -- the same moment `Stats` counts a play.
Listens wait in a small file queue, so nothing is lost while offline: they are
sent in the background and retried later with a growing pause.

The top half of this module is pure (building and signing requests); the
network lives in `ListenBrainz` / `LastFm`, and `Scrobbler` ties it to the
player.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QTimer, Signal

from . import __version__
from .config import DATA_DIR
from .player import first
from .threads import USER_AGENT, run_bg
from .i18n import tr

log = logging.getLogger(__name__)

LISTENBRAINZ_URL = "https://api.listenbrainz.org"
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_AUTH_URL = "https://www.last.fm/api/auth/"
MIN_SECONDS = 30            # shorter tracks are not scrobbled (Last.fm rule)
BATCH = 50                  # most listens per request (Last.fm limit)
QUEUE_LIMIT = 2000          # oldest listens are dropped beyond this
RETRY_FIRST, RETRY_MAX = 60, 3600      # seconds between attempts while failing
HTTP_TIMEOUT = 15

OK, RETRY, REJECTED, AUTH = "ok", "retry", "rejected", "auth"


# ----------------------------------------------------------------- pure
def _text(value) -> str:
    return str(first(value) or "").strip()


def _number(value) -> int:
    """Leading integer of a tag such as "3/12" (0 when there is none)."""
    try:
        return int(_text(value).split("/")[0])
    except ValueError:
        return 0


def listen_from_song(song: dict, started_at: int) -> dict | None:
    """What gets scrobbled for an MPD song, or None when it must not be:
    streams, files without artist/title tags and very short tracks."""
    uri = song.get("file", "")
    artist, title = _text(song.get("artist")), _text(song.get("title"))
    if not uri or "://" in uri or not artist or not title:
        return None
    try:
        duration = int(float(song.get("duration") or song.get("time") or 0))
    except (TypeError, ValueError):
        duration = 0
    if 0 < duration < MIN_SECONDS:
        return None
    return {"artist": artist, "title": title, "album": _text(song.get("album")),
            "albumartist": _text(song.get("albumartist")), "track": _number(song.get("track")),
            "duration": duration, "mbid": _text(song.get("musicbrainz_trackid")),
            "started_at": int(started_at)}


def listenbrainz_payload(listens: list[dict], now_playing=False) -> dict:
    def item(listen):
        info = {"media_player": "Zebamp", "submission_client": "Zebamp",
                "submission_client_version": __version__}
        if listen["duration"]:
            info["duration"] = listen["duration"]
        if listen["track"]:
            info["tracknumber"] = listen["track"]
        if listen["mbid"]:
            info["recording_mbid"] = listen["mbid"]
        meta = {"artist_name": listen["artist"], "track_name": listen["title"], "additional_info": info}
        if listen["album"]:
            meta["release_name"] = listen["album"]
        entry = {"track_metadata": meta}
        if not now_playing:
            entry["listened_at"] = listen["started_at"]
        return entry

    if now_playing:
        kind = "playing_now"
    else:
        kind = "single" if len(listens) == 1 else "import"
    return {"listen_type": kind, "payload": [item(x) for x in listens]}


def lastfm_signature(params: dict, secret: str) -> str:
    """api_sig: md5 of every parameter (name then value, sorted by name)
    followed by the shared secret; `format` and `callback` are not signed."""
    signed = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in ("format", "callback"))
    return hashlib.md5((signed + secret).encode("utf-8")).hexdigest()


def lastfm_signed(params: dict, secret: str) -> dict:
    return {**params, "api_sig": lastfm_signature(params, secret), "format": "json"}


def lastfm_scrobble_params(listens: list[dict], api_key: str, session_key: str) -> dict:
    params = {"method": "track.scrobble", "api_key": api_key, "sk": session_key}
    for i, listen in enumerate(listens):
        params.update(_lastfm_track(listen, f"[{i}]"))
        params[f"timestamp[{i}]"] = str(listen["started_at"])
    return params


def lastfm_now_playing_params(listen: dict, api_key: str, session_key: str) -> dict:
    return {"method": "track.updateNowPlaying", "api_key": api_key, "sk": session_key,
            **_lastfm_track(listen, "")}


def _lastfm_track(listen: dict, suffix: str) -> dict:
    fields = {"artist": listen["artist"], "track": listen["title"], "album": listen["album"],
              "albumArtist": listen["albumartist"], "mbid": listen["mbid"],
              "duration": listen["duration"] or "", "trackNumber": listen["track"] or ""}
    return {f"{name}{suffix}": str(value) for name, value in fields.items() if value}


def retry_delay(failures: int) -> int:
    """Seconds to wait after `failures` failed attempts in a row (1, 2, 4… min, at most 1 h)."""
    return min(RETRY_MAX, RETRY_FIRST * 2 ** max(0, failures - 1))


# -------------------------------------------------------------- network
def _http(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict]:
    """(HTTP status, JSON body) of a request; status 0 means "no answer"."""
    if not url.startswith(("http://", "https://")):
        # the server address is typed by the user: never let it name a local file
        log.warning("scrobble: %r is not an http(s) address", url)
        return 0, {}
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as reply:
            status, body = reply.status, reply.read()
    except urllib.error.HTTPError as e:
        with e:
            status, body = e.code, e.read()
    except (OSError, ValueError) as e:
        log.info("scrobble: %s unreachable (%s)", urllib.parse.urlsplit(url).netloc, e)
        return 0, {}
    try:
        parsed = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


def _outcome(status: int) -> str:
    if 200 <= status < 300:
        return OK
    if status in (401, 403):
        return AUTH
    if status == 0 or status == 429 or status >= 500:
        return RETRY
    return REJECTED


class ListenBrainz:
    name = "listenbrainz"
    label = "ListenBrainz"

    def __init__(self, token: str, url: str = ""):
        self.token = token
        self.url = (url or LISTENBRAINZ_URL).rstrip("/")

    def _post(self, payload: dict) -> str:
        status, _body = _http(self.url + "/1/submit-listens", json.dumps(payload).encode("utf-8"),
                              {"Authorization": f"Token {self.token}", "Content-Type": "application/json"})
        return _outcome(status)

    def submit(self, listens: list[dict]) -> str:
        return self._post(listenbrainz_payload(listens))

    def now_playing(self, listen: dict) -> str:
        return self._post(listenbrainz_payload([listen], now_playing=True))

    def check(self) -> tuple[bool, str]:
        """(token accepted, user name or reason)."""
        status, body = _http(self.url + "/1/validate-token", headers={"Authorization": f"Token {self.token}"})
        if status == 200 and body.get("valid"):
            return True, str(body.get("user_name") or "")
        if status == 0:
            return False, tr("sin conexión con el servidor")
        return False, str(body.get("message") or tr("token no válido"))


# Last.fm error codes: https://www.last.fm/api/errorcodes
_LASTFM_AUTH_ERRORS = {4, 9, 10, 14, 26}        # bad session/key: needs the user
_LASTFM_RETRY_ERRORS = {8, 11, 16, 29}          # their side or rate limit: try later


class LastFm:
    name = "lastfm"
    label = "Last.fm"

    def __init__(self, api_key: str, secret: str, session_key: str = "", url: str = ""):
        self.api_key = api_key
        self.secret = secret
        self.session_key = session_key
        self.url = url or LASTFM_URL

    def _call(self, params: dict) -> tuple[str, dict]:
        data = urllib.parse.urlencode(lastfm_signed(params, self.secret)).encode("utf-8")
        status, body = _http(self.url, data)
        code = body.get("error")
        if code in _LASTFM_AUTH_ERRORS:
            return AUTH, body
        if code in _LASTFM_RETRY_ERRORS:
            return RETRY, body
        if code:
            return REJECTED, body
        return _outcome(status), body

    def submit(self, listens: list[dict]) -> str:
        return self._call(lastfm_scrobble_params(listens, self.api_key, self.session_key))[0]

    def now_playing(self, listen: dict) -> str:
        return self._call(lastfm_now_playing_params(listen, self.api_key, self.session_key))[0]

    # Desktop sign-in: get a token, the user approves it in the browser, then
    # the token is exchanged for a session key that never expires.
    def request_token(self) -> str:
        _result, body = self._call({"method": "auth.getToken", "api_key": self.api_key})
        return str(body.get("token") or "")

    def approval_url(self, token: str) -> str:
        return LASTFM_AUTH_URL + "?" + urllib.parse.urlencode({"api_key": self.api_key, "token": token})

    def open_session(self, token: str) -> tuple[str, str]:
        """(session key, user name); both empty until the user approved."""
        _result, body = self._call({"method": "auth.getSession", "api_key": self.api_key, "token": token})
        session = body.get("session")
        if not isinstance(session, dict):
            return "", ""
        return str(session.get("key") or ""), str(session.get("name") or "")


def services_from_config(cfg) -> list:
    """The services the user enabled and finished setting up."""
    services = []
    if cfg["listenbrainz_enabled"] and cfg["listenbrainz_token"]:
        services.append(ListenBrainz(cfg["listenbrainz_token"], cfg["listenbrainz_url"]))
    if cfg["lastfm_enabled"] and cfg["lastfm_api_key"] and cfg["lastfm_secret"] and cfg["lastfm_session"]:
        services.append(LastFm(cfg["lastfm_api_key"], cfg["lastfm_secret"], cfg["lastfm_session"],
                               cfg["lastfm_url"]))
    return services


# ---------------------------------------------------------------- queue
class ListenQueue:
    """Listens waiting to be sent, per service, kept in a JSON file."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(DATA_DIR, "scrobble_queue.json")
        self.pending: dict[str, list[dict]] = {}
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for name, listens in data.items():
            if isinstance(listens, list):
                self.pending[name] = [x for x in listens if _is_listen(x)]

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.pending, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("scrobble queue not saved: %s", e)

    def add(self, service: str, listen: dict):
        listens = self.pending.setdefault(service, [])
        listens.append(listen)
        del listens[:-QUEUE_LIMIT]
        self.save()

    def batch(self, service: str) -> list[dict]:
        return list(self.pending.get(service, [])[:BATCH])

    def done(self, service: str, count: int):
        del self.pending.get(service, [])[:count]
        self.save()

    def count(self, service: str) -> int:
        return len(self.pending.get(service, []))


_LISTEN_KEYS = ("artist", "title", "album", "albumartist", "track", "duration", "mbid", "started_at")


def _is_listen(item) -> bool:
    return isinstance(item, dict) and all(k in item for k in _LISTEN_KEYS)


# ------------------------------------------------------------ controller
class Scrobbler(QObject):
    statusChanged = Signal()

    def __init__(self, cfg, player, stats, queue: ListenQueue | None = None):
        super().__init__()
        self.cfg = cfg
        self.player = player
        self.queue = queue or ListenQueue()
        self.services: list = []
        self.status: dict[str, str] = {}        # service name -> last outcome
        self._sending: set[str] = set()
        self._failures = 0
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self.flush)
        self._announced = None
        stats.played.connect(self._played)
        player.songChanged.connect(self._now_playing)
        player.statusChanged.connect(self._now_playing)
        self.configure()

    def configure(self):
        """(Re)read the settings; called at start and after Preferences."""
        self.services = services_from_config(self.cfg)
        self._failures = 0
        self._announced = None
        if self.services:
            QTimer.singleShot(0, self.flush)        # listens left from the last run
        else:
            self._retry.stop()

    # ------------------------------------------------------------ listens
    def _played(self, song: dict, started_at: int):
        listen = listen_from_song(song, started_at) if self.services else None
        if listen is None:
            return
        for service in self.services:
            self.queue.add(service.name, listen)
        self.flush()

    def flush(self):
        for service in self.services:
            batch = self.queue.batch(service.name)
            if batch and service.name not in self._sending:
                self._sending.add(service.name)
                run_bg(lambda s=service, b=batch: s.submit(b),
                       lambda outcome, s=service, n=len(batch): self._sent(s, n, outcome))

    def _sent(self, service, count: int, outcome):
        self._sending.discard(service.name)
        if isinstance(outcome, Exception):
            outcome = RETRY
        self.status[service.name] = outcome
        if outcome in (OK, REJECTED):
            # rejected listens would be refused forever: drop them too
            self.queue.done(service.name, count)
            self._failures = 0
            if self.queue.count(service.name):
                self.flush()
        elif outcome == RETRY:
            self._failures += 1
            self._retry.start(retry_delay(self._failures) * 1000)
        # AUTH: keep the listens; nothing is retried until the user signs in again
        self.statusChanged.emit()

    # -------------------------------------------------------- now playing
    def _now_playing(self):
        if not self.services or self.player.state != "play":
            return
        song = self.player.song or {}
        if song.get("file") == self._announced:
            return
        self._announced = song.get("file")
        listen = listen_from_song(song, 0)
        if listen is None:
            return
        for service in self.services:
            run_bg(lambda s=service: s.now_playing(listen))

    # ------------------------------------------------------------- status
    def describe(self, service_name: str) -> str:
        waiting = self.queue.count(service_name)
        text = {OK: tr("enviando bien"), RETRY: tr("sin conexión; se reintentará"), AUTH: tr("hay que volver a "
                                                                                     "conectar la cuenta"),
                REJECTED: tr("el servicio rechazó el último envío")}.get(self.status.get(service_name, ""), "")
        if waiting:
            text = (text + " · " if text else "") + tr("{0} en espera").format(waiting)
        return text
