"""Desktop notification with the album cover when the song changes."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil

from PySide6.QtCore import QObject, QProcess, QTimer, Qt
from PySide6.QtGui import QImage

from .player import first, fmt_time

log = logging.getLogger(__name__)

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                     "zebamp", "covers")
_COVER_NAMES = re.compile(r"^(cover|folder|front|album)[^/]*\.(jpe?g|png|webp|bmp)$", re.I)
_IMAGE = re.compile(r"\.(jpe?g|png|webp|bmp)$", re.I)
MIN_ONLINE_SIDE = 200       # pixels: smaller downloads are not accepted as covers


def cover_path(uri: str) -> str:
    return os.path.join(CACHE, hashlib.md5(uri.encode("utf-8", "replace")).hexdigest() + ".png")


def is_picture(data: bytes) -> bool:
    """A download is only a cover if it decodes and is not a thumbnail."""
    img = QImage.fromData(data)
    return not img.isNull() and min(img.width(), img.height()) >= MIN_ONLINE_SIDE


def cover_job(app, song: dict, force=False):
    """The job that finds the cover of `song` the way the user set it up
    (with or without looking on the Internet)."""
    return fetch_cover_job(song.get("file", ""), song, bool(app.cfg["cover_online"]), force,
                           app.cfg["acoustid_key"] or "")


def _music_directory(client) -> str | None:
    """MPD's music folder (it only tells local clients)."""
    try:
        return (client.config() or {}).get("music_directory") if hasattr(client, "config") else None
    except Exception:
        return None


def fetch_cover_job(uri: str, song: dict | None = None, online=False, force=False, acoustid_key=""):
    """Worker-thread job: embedded picture, MPD's cover.*, then the folder
    and, if asked to and there is nothing local, the Internet (`force`
    searches even if a recent search found nothing)."""

    def job(client):
        local = _local_cover(client)
        if local is None and online and song:
            return _online_cover(client)
        return local

    def _online_cover(client):
        """Search with the best names known; if the tags did not have them
        and nothing turned up, recognise the song by its sound and try again."""
        from . import songid
        from .coverfind import online_cover
        music_dir = _music_directory(client)
        path = online_cover(songid.described(song, music_dir), is_picture, force=force)
        audio = songid.can_identify(song, music_dir, acoustid_key) if path is None else None
        if audio is None:
            return path
        try:
            identified = songid.identify(audio, acoustid_key)
        except songid.BadKey:
            log.warning("AcoustID does not accept the application key")
            return None
        return online_cover(songid.described(song, music_dir), is_picture, force=force) if identified else None

    def _local_cover(client):
        out = cover_path(uri)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        data = None
        for cmd in ("readpicture", "albumart"):
            try:
                r = getattr(client, cmd)(uri)
                if isinstance(r, dict) and r.get("binary"):
                    data = r["binary"]
                    break
            except Exception:
                continue
        img = QImage.fromData(data) if data else QImage()
        if img.isNull() and "://" not in uri:
            # like ncmpcpp's helper: any image in the album folder
            music = _music_directory(client)
            if music:
                d = os.path.join(music, os.path.dirname(uri))
                try:
                    files = [f for f in os.listdir(d) if _IMAGE.search(f)]
                except OSError:
                    files = []
                named = [f for f in files if _COVER_NAMES.match(f)]
                pick = named[0] if named else (max(files, key=lambda f: os.path.getsize(os.path.join(d, f)))
                                                if files else None)
                if pick:
                    img = QImage(os.path.join(d, pick))
        if img.isNull():
            return None
        if max(img.width(), img.height()) > 512:
            img = img.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        os.makedirs(CACHE, exist_ok=True)
        tmp = out + ".tmp.png"
        if img.save(tmp, "PNG"):
            os.replace(tmp, out)
            return out
        return None
    return job


class SongNotifier(QObject):
    """Sends "now playing" notifications through notify-send (libnotify)."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.available = shutil.which("notify-send") is not None
        self._last_uri = None
        self._startup = True
        self._notif_id = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)       # coalesce song+status bursts
        self._timer.timeout.connect(self._fire)
        p = app.player
        p.songChanged.connect(self._timer.start)
        p.statusChanged.connect(self._timer.start)
        QTimer.singleShot(2500, self._end_startup)

    def _end_startup(self):
        # Don't announce the song that was already playing when Zebamp opened.
        self._last_uri = self._key(self.app.player.song) if self.app.player.state == "play" else None
        self._startup = False

    def _fire(self):
        if self._startup or not self.available or not self.app.cfg["notify_song"]:
            return
        pl = self.app.player
        song = pl.song or {}
        uri = song.get("file")
        key = self._key(song)
        if pl.state != "play" or not uri or key == self._last_uri:
            return
        self._last_uri = key
        pl.conn.run_async(cover_job(self.app, song), lambda path, s=dict(song): self._send(s, path))

    @staticmethod
    def _key(song):
        song = song or {}
        # streams keep their URI while the title changes
        return (song.get("file"), first(song.get("title")))

    def _send(self, song, cover):
        if (self.app.player.song or {}).get("file") != song.get("file"):
            return     # skipped past it while the cover was loading
        title = first(song.get("title")) or os.path.basename(song.get("file", ""))
        artist = first(song.get("artist")) or first(song.get("albumartist")) or ""
        album = first(song.get("album")) or ""
        date = (first(song.get("date")) or "")[:4]
        # two short lines: "Artist · 3:45" and "Album (1975)", so long titles
        # still fit in the notification box
        line1 = artist
        dur = song.get("duration") or song.get("time")
        try:
            if dur:
                line1 += ("  ·  " if line1 else "") + fmt_time(float(dur))
        except (TypeError, ValueError):
            pass
        line2 = album + (f" ({date})" if album and date else "")
        body = "\n".join(x for x in (line1, line2) if x)
        args = ["-a", "Zebamp", "-p", "-t", str(int(self.app.cfg["notify_timeout"]) * 1000),
                "-h", "string:desktop-entry:zebamp"]
        # never combine -r (replace) with x-canonical-private-synchronous: that
        # crashes mako 1.11 (double free)
        if self._notif_id:
            args += ["-r", self._notif_id]
        icon = cover or os.path.join(os.path.dirname(__file__), "data", "zebamp.png")
        if cover:
            args += ["-h", f"string:image-path:{cover}"]
        if icon and os.path.exists(icon):
            args += ["-i", icon]
        args += ["--", title, _escape(body)]
        proc = QProcess(self)
        proc.finished.connect(lambda *_a, pr=proc: self._done(pr))
        proc.start("notify-send", args)

    def _done(self, proc):
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace").strip()
        if out.isdigit():
            self._notif_id = out
        proc.deleteLater()


def _escape(text: str) -> str:
    # notification bodies may be interpreted as markup
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
