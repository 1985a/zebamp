"""Player model: mirrors MPD state and exposes Winamp-style operations."""
from __future__ import annotations

import logging
import os
import random
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .mpdconn import IdleThread, MpdAddress, MpdConnection

log = logging.getLogger(__name__)


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def first(v):
    """MPD tags may come back as lists when repeated."""
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def song_duration(song: dict) -> float:
    return _f(song.get("duration"), _f(song.get("time"), 0.0))


def song_title(song: dict) -> str:
    """Winamp-like display title: 'Artist - Title', falling back to the file."""
    if not song:
        return ""
    title = first(song.get("title"))
    artist = first(song.get("artist")) or first(song.get("albumartist"))
    name = first(song.get("name"))
    if title and artist:
        return f"{artist} - {title}"
    if title:
        return f"{name} - {title}" if name and name != title else title
    if name:
        return name
    f = song.get("file", "")
    base = f.rstrip("/").rsplit("/", 1)[-1]
    if "://" in f and not base:
        return f
    return os.path.splitext(base)[0] if "." in base else base


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class Player(QObject):
    connectionChanged = Signal(bool)
    statusChanged = Signal()
    songChanged = Signal()
    queueChanged = Signal()
    optionsChanged = Signal()
    volumeChanged = Signal()
    storedPlaylistsChanged = Signal()
    databaseChanged = Signal()
    outputsChanged = Signal()
    updatingChanged = Signal(bool)
    message = Signal(str)

    def __init__(self, addr: MpdAddress, parent=None):
        super().__init__(parent)
        self.conn = MpdConnection(addr, self)
        self.conn.connectionChanged.connect(self._on_conn)
        self.conn.error.connect(self.message)
        self.idle = IdleThread(addr)
        self.idle.changed.connect(self._on_idle)
        self.status: dict = {}
        self.song: dict = {}
        self.queue: list[dict] = []
        self._pl_version = None
        self._elapsed = 0.0
        self._elapsed_ts = time.monotonic()
        self.music_directory: str | None = None
        self.updating = False
        # Poll status while playing to follow VBR bitrate (MPD has no event
        # for it).  This is a single cheap command per second.
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._refresh_status)
        self._vol_pending = None
        self._vol_timer = QTimer(self)
        self._vol_timer.setSingleShot(True)
        self._vol_timer.setInterval(40)
        self._vol_timer.timeout.connect(self._flush_volume)

    # ------------------------------------------------------------ setup
    def start(self):
        self.conn.connect_now()
        self.idle.start()

    def shutdown(self):
        self.idle.stop()
        self.conn.disconnect_now()

    def set_address(self, addr: MpdAddress):
        self.idle.stop()
        self.idle = IdleThread(addr)
        self.idle.changed.connect(self._on_idle)
        self._pl_version = None
        self.queue = []
        self.conn.set_address(addr)
        self.idle.start()

    @property
    def connected(self) -> bool:
        return self.conn.connected

    def _on_conn(self, ok: bool):
        if ok:
            cfg = self.conn.call("config", default=None)
            if isinstance(cfg, dict):
                self.music_directory = cfg.get("music_directory")
            elif self.conn.addr.is_socket is False:
                self.music_directory = None
            self._pl_version = None
            self._refresh_all()
        else:
            self.status = {}
            self._poll.stop()
            self.statusChanged.emit()
        self.connectionChanged.emit(ok)

    def _on_idle(self, subsystems: set):
        if "*" in subsystems:
            self._refresh_all()
            return
        if "playlist" in subsystems:
            self._refresh_queue()
        if subsystems & {"player", "mixer", "options", "playlist"}:
            self._refresh_status()
        if "stored_playlist" in subsystems:
            self.storedPlaylistsChanged.emit()
        if "database" in subsystems:
            self.databaseChanged.emit()
        if "update" in subsystems:
            self._refresh_status()
        if "output" in subsystems:
            self.outputsChanged.emit()

    def _refresh_all(self):
        self._refresh_queue()
        self._refresh_status(force_song=True)

    def _refresh_queue(self):
        st = self.conn.call("status", default=None)
        if st is None:
            return
        version = _i(st.get("playlist"), -1)
        length = _i(st.get("playlistlength"))
        if self._pl_version is None:
            songs = self.conn.call("playlistinfo", default=None)
            if songs is None:
                return
            self.queue = list(songs)
        elif version != self._pl_version:
            changes = self.conn.call("plchanges", self._pl_version, default=None)
            if changes is None:
                return
            q = self.queue[:length]
            if len(q) < length:
                q.extend({} for _ in range(length - len(q)))
            for s in changes:
                pos = _i(s.get("pos"), -1)
                if 0 <= pos < length:
                    q[pos] = s
            self.queue = q
            if any(not s for s in self.queue):
                # Should not happen, but never show holes.
                songs = self.conn.call("playlistinfo", default=[])
                self.queue = list(songs)
        else:
            return
        self._pl_version = version
        self.queueChanged.emit()

    def _refresh_status(self, force_song=False):
        st = self.conn.call("status", default=None)
        if st is None:
            return
        old = self.status
        self.status = st
        self._elapsed = _f(st.get("elapsed"))
        self._elapsed_ts = time.monotonic()
        upd = "updating_db" in st
        if upd != self.updating:
            self.updating = upd
            self.updatingChanged.emit(upd)
        if force_song or st.get("songid") != old.get("songid") or \
                st.get("playlist") != old.get("playlist"):
            song = self.conn.call("currentsong", default={}) or {}
            if song != self.song or force_song:
                self.song = song
                self._clear_played_prio()
                self.songChanged.emit()
        if (old.get("volume") != st.get("volume")):
            self.volumeChanged.emit()
        opts = ("random", "repeat", "single", "consume", "xfade")
        if any(old.get(k) != st.get(k) for k in opts):
            self.optionsChanged.emit()
        if self.state == "play":
            if not self._poll.isActive():
                self._poll.start()
        else:
            self._poll.stop()
        self.statusChanged.emit()

    # ------------------------------------------------------------ state
    @property
    def state(self) -> str:
        return self.status.get("state", "stop")

    @property
    def elapsed(self) -> float:
        if self.state == "play":
            e = self._elapsed + (time.monotonic() - self._elapsed_ts)
            d = self.duration
            return min(e, d) if d > 0 else e
        return self._elapsed if self.state == "pause" else 0.0

    @property
    def duration(self) -> float:
        d = _f(self.status.get("duration"))
        if d <= 0:
            d = song_duration(self.song)
        return d

    @property
    def volume(self) -> int:
        if self._vol_pending is not None:
            return self._vol_pending
        return _i(self.status.get("volume"), -1)

    @property
    def bitrate(self) -> int:
        br = _i(self.status.get("bitrate"))
        if br <= 0 and self.state in ("play", "pause"):
            # synthesised formats (game music .spc/.nsf/.vgm, MIDI, trackers…)
            # report 0: show the generated PCM rate like Winamp does for WAV
            rate, bits, ch = self.audio
            a = self.status.get("audio", "")
            if not bits and ":f:" in a:
                bits = 32
            if rate and bits and ch:
                br = rate * bits * ch // 1000
        return br

    @property
    def audio(self) -> tuple[int, int, int]:
        a = self.status.get("audio", "")
        parts = a.split(":") if a else []
        if len(parts) == 3:
            rate = _i(parts[0])
            bits = _i(parts[1]) if parts[1].isdigit() else 0
            ch = _i(parts[2])
            return rate, bits, ch
        return 0, 0, 0

    @property
    def current_pos(self) -> int:
        return _i(self.status.get("song"), -1)

    @property
    def random(self) -> bool:
        return self.status.get("random") == "1"

    @property
    def repeat(self) -> bool:
        return self.status.get("repeat") == "1"

    @property
    def single(self) -> bool:
        return self.status.get("single") == "1"

    @property
    def consume(self) -> bool:
        return self.status.get("consume") == "1"

    @property
    def crossfade(self) -> int:
        return _i(self.status.get("xfade"))

    # --------------------------------------------------------- playback
    def play(self, pos: int | None = None):
        if pos is None:
            if self.state == "pause":
                self.conn.call("pause", 0)
            elif self.state == "play":
                # Winamp restarts the current track when Play is pressed.
                self.conn.call("seekcur", 0)
            else:
                self.conn.call("play")
        else:
            self.conn.call("play", pos)

    def play_id(self, songid):
        self.conn.call("playid", songid)

    def pause(self):
        if self.state == "play":
            self.conn.call("pause", 1)
        elif self.state == "pause":
            self.conn.call("pause", 0)

    def toggle_play(self):
        if self.state == "play":
            self.conn.call("pause", 1)
        else:
            self.play()

    def stop(self):
        self.conn.call("stop")

    def next(self):
        if self.state == "stop":
            pos = self.current_pos
            if pos + 1 < len(self.queue):
                self.conn.call("play", pos + 1)
                self.conn.call("stop")
            return
        self.conn.call("next")

    def previous(self):
        if self.state == "stop":
            pos = self.current_pos
            if pos > 0:
                self.conn.call("play", pos - 1)
                self.conn.call("stop")
            return
        self.conn.call("previous")

    def seek(self, seconds: float):
        if self.state == "stop":
            return
        seconds = max(0.0, seconds)
        if self.conn.call("seekcur", f"{seconds:.3f}", default="err") != "err":
            self._elapsed = seconds
            self._elapsed_ts = time.monotonic()

    def seek_relative(self, delta: float):
        if self.state != "stop":
            self.seek(max(0.0, self.elapsed + delta))

    def set_volume(self, vol: int):
        vol = max(0, min(100, int(vol)))
        self._vol_pending = vol
        if not self._vol_timer.isActive():
            self._vol_timer.start()
        self.volumeChanged.emit()

    def _flush_volume(self):
        if self._vol_pending is None:
            return
        v = self._vol_pending
        self.conn.call("setvol", v)
        self.status["volume"] = str(v)
        self._vol_pending = None

    def toggle_random(self):
        self.conn.call("random", 0 if self.random else 1)

    def toggle_repeat(self):
        """off -> all -> track -> off (MPD single+repeat repeats a track)."""
        if not self.repeat:
            self.conn.batch([("repeat", 1), ("single", 0)])
        elif not self.single:
            self.conn.batch([("single", 1)])
        else:
            self.conn.batch([("repeat", 0), ("single", 0)])

    def set_repeat_mode(self, mode: str):
        if mode == "off":
            self.conn.batch([("repeat", 0), ("single", 0)])
        elif mode == "all":
            self.conn.batch([("repeat", 1), ("single", 0)])
        elif mode == "track":
            self.conn.batch([("repeat", 1), ("single", 1)])

    def set_option(self, name: str, on: bool):
        self.conn.call(name, 1 if on else 0)

    def set_crossfade(self, seconds: int):
        self.conn.call("crossfade", max(0, int(seconds)))

    # ------------------------------------------------------------ queue
    def add(self, uris: list[str], play_first=False, replace=False,
            position: int | None = None):
        if not uris:
            return None
        cmds = []
        if replace:
            cmds.append(("clear",))
        for i, u in enumerate(uris):
            if position is not None:
                cmds.append(("add", u, position + i))
            else:
                cmds.append(("add", u))
        ok = self.conn.batch(cmds)
        if ok and (play_first or replace):
            if replace:
                self.conn.call("play", 0)
            else:
                st = self.conn.call("status", default={}) or {}
                n = _i(st.get("playlistlength"))
                start = position if position is not None else max(0, n - len(uris))
                self.conn.call("play", start)
        return ok

    # ------------------------------------------------------ play next
    def add_next(self, uris: list[str]) -> bool:
        """Queue songs to play right after the current one (in order)."""
        if not uris:
            return False
        ids = []
        for u in uris:
            sid = self.conn.call("addid", u, default=None)
            if sid is None:
                break
            ids.append(str(sid))
        if not ids:
            return False
        self.queue_next_ids(ids)
        return True

    def queue_next_ids(self, ids: list[str]):
        """Make queued songs (by id) play next.

        In random mode MPD ignores queue order, so moving the song after the
        current one is not enough: a high priority makes MPD pick it next
        (and keeps the given order).  The priority is cleared once it plays."""
        st = self.conn.call("status", default={}) or {}
        cur = _i(st.get("song"), -1)
        random_on = st.get("random") == "1"
        cmds = []
        if cur >= 0:
            # "+0" = right after the current song (relative positions, MPD >= 0.23);
            # in reverse so the given order is kept
            for sid in reversed(ids):
                cmds.append(("moveid", sid, "+0"))
        else:
            for i, sid in enumerate(ids):
                cmds.append(("moveid", sid, i))
        if random_on:
            for i, sid in enumerate(ids):
                cmds.append(("prioid", max(1, 255 - i), sid))
            self._prio_ids = set(getattr(self, "_prio_ids", set())) | set(ids)
        if not self.conn.batch(cmds) and cur >= 0:
            # old MPD without relative positions: absolute fallback
            target = cur + 1
            for sid in ids:
                self.conn.call("moveid", sid, target)
                target += 1
            if random_on:
                for i, sid in enumerate(ids):
                    self.conn.call("prioid", max(1, 255 - i), sid)
        if st.get("state") == "stop":
            self.conn.call("playid", ids[0])

    def _clear_played_prio(self):
        pend = getattr(self, "_prio_ids", None)
        sid = str(self.song.get("id", "")) if self.song else ""
        if pend and sid in pend:
            pend.discard(sid)
            self.conn.call("prioid", 0, sid)

    def add_paths(self, paths: list[str], **kw):
        """Add local filesystem paths (files or folders)."""
        uris = []
        md = (self.music_directory or "").rstrip("/")
        for p in paths:
            p = os.path.abspath(p)
            if md and (p == md or p.startswith(md + "/")):
                uris.append(os.path.relpath(p, md) if p != md else "")
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    dirs.sort()
                    for f in sorted(files):
                        if _is_audio(f):
                            uris.append("file://" + os.path.join(root, f))
            else:
                uris.append("file://" + p)
        return self.add([u for u in uris if u is not None], **kw)

    def delete_positions(self, positions):
        pos = sorted({int(p) for p in positions}, reverse=True)
        if not pos:
            return
        # Collapse into contiguous ranges, deleting from the end first.
        cmds = []
        start = end = pos[0]
        for p in [*pos[1:], None]:
            if p is not None and p == start - 1:
                start = p
                continue
            cmds.append(("delete", f"{start}:{end + 1}"))
            if p is not None:
                start = end = p
        self.conn.batch(cmds)

    def crop(self, keep_positions):
        keep = {int(p) for p in keep_positions}
        self.delete_positions([i for i in range(len(self.queue)) if i not in keep])

    def clear(self):
        self.conn.call("clear")

    def move(self, positions: list[int], target: int):
        """Move the selected rows so the first lands at `target`."""
        positions = sorted(positions)
        if not positions:
            return
        n = len(self.queue)
        ids = [self.queue[p].get("id") for p in positions if p < n]
        target = max(0, min(n - len(ids), target))
        cmds = [("moveid", sid, target + i) for i, sid in enumerate(ids)]
        self.conn.batch(cmds)

    def apply_order(self, ids: list[str]):
        """Reorder the queue to match `ids` (a permutation of song ids)."""
        cmds = [("moveid", sid, i) for i, sid in enumerate(ids)]
        self.conn.batch(cmds)

    def apply_order_range(self, ids: list[str], lo: int, hi: int):
        """Make queue[lo..hi] match ids[lo..hi]; prefix before lo is unchanged."""
        cmds = [("moveid", ids[i], i) for i in range(lo, hi + 1)]
        self.conn.batch(cmds)

    def sort_queue(self, key, positions=None):
        idx = list(range(len(self.queue))) if not positions else sorted(positions)
        songs = [self.queue[i] for i in idx]
        songs_sorted = sorted(songs, key=key)
        cmds = [("moveid", s.get("id"), idx[k]) for k, s in enumerate(songs_sorted)]
        self.conn.batch(cmds)

    def reverse_queue(self):
        ids = [s.get("id") for s in reversed(self.queue)]
        self.apply_order(ids)

    def shuffle_queue(self):
        self.conn.call("shuffle")

    def randomize(self):
        ids = [s.get("id") for s in self.queue]
        random.shuffle(ids)
        self.apply_order(ids)

    # ------------------------------------------------------ playlists
    def stored_playlists(self) -> list[str]:
        pls = self.conn.call("listplaylists", default=[]) or []
        return sorted((p.get("playlist", "") for p in pls), key=str.lower)

    def load_playlist(self, name: str, replace=True):
        cmds = [("clear",)] if replace else []
        cmds.append(("load", name))
        if self.conn.batch(cmds) and replace:
            self.conn.call("play", 0)

    def save_playlist(self, name: str, overwrite=True) -> bool:
        if overwrite and name in self.stored_playlists():
            self.conn.call("rm", name)
        return self.conn.call("save", name, default="err") != "err"

    def delete_playlist(self, name: str):
        self.conn.call("rm", name)

    def update_database(self, path: str = ""):
        if path:
            self.conn.call("update", path)
        else:
            self.conn.call("update")

    def outputs(self) -> list[dict]:
        return self.conn.call("outputs", default=[]) or []

    def toggle_output(self, out_id):
        self.conn.call("toggleoutput", out_id)

    def album_art(self, uri: str) -> bytes | None:
        """Embedded picture first, then cover.* in the folder (MPD >= 0.22)."""
        for cmd in ("readpicture", "albumart"):
            try:
                r = self.conn.call(cmd, uri, default=None)
            except Exception:
                r = None
            if isinstance(r, dict) and r.get("binary"):
                return r["binary"]
        return None


AUDIO_EXT = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav",
             ".wv", ".ape", ".mpc", ".wma", ".aiff", ".aif", ".dsf", ".dff",
             ".mod", ".xm", ".s3m", ".it", ".spc", ".nsf", ".vgm", ".vgz",
             ".gbs", ".sid", ".mid", ".midi", ".alac", ".tta", ".mka", ".webm",
             ".mp4", ".m4b", ".nsfe", ".hes", ".kss", ".ay", ".sap", ".gym"}


def _is_audio(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in AUDIO_EXT


def read_playlist_file(path: str) -> list[str]:
    """Entries of an .m3u/.m3u8/.pls file: absolute paths or URLs."""
    uris = []
    base = os.path.dirname(os.path.abspath(path))
    is_pls = path.lower().endswith(".pls")
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(("#", "[")):
                continue
            if is_pls:
                if not line.lower().startswith("file") or "=" not in line:
                    continue
                line = line.split("=", 1)[1].strip()
            if "://" in line:
                uris.append(line)
            else:
                uris.append(line if os.path.isabs(line) else os.path.normpath(os.path.join(base, line)))
    return uris
