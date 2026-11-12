"""MPRIS 2 (org.mpris.MediaPlayer2) so media keys, playerctl, waybar and
desktop widgets can see and control Zebamp/MPD.

Uses dbus-python on the GLib main loop, which Qt's event loop drives on Linux.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

IFACE = "org.mpris.MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"
PROPS = "org.freedesktop.DBus.Properties"
PATH = "/org/mpris/MediaPlayer2"


def start(app):
    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
    except ImportError:
        log.info("dbus-python missing: no MPRIS")
        return None
    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        name = dbus.service.BusName("org.mpris.MediaPlayer2.zebamp", bus,
                                    allow_replacement=True, replace_existing=True, do_not_queue=True)
    except Exception as e:
        log.warning("MPRIS unavailable: %s", e)
        return None
    return _make_service(app, bus, name)


def _make_service(app, bus, name):
    import dbus
    import dbus.service
    from .player import first

    class Mpris(dbus.service.Object):
        def __init__(self):
            super().__init__(name, PATH)
            self.app = app
            self.pl = app.player
            self._last = {}
            self._art = ""
            self._art_uri = None
            p = self.pl
            p.statusChanged.connect(self._changed)
            p.songChanged.connect(self._song)
            p.volumeChanged.connect(self._changed)
            p.optionsChanged.connect(self._changed)
            self._song()

        # -------------------------------------------------- properties
        def _status(self):
            return {"play": "Playing", "pause": "Paused"}.get(self.pl.state, "Stopped")

        def _loop(self):
            p = self.pl
            if not p.repeat:
                return "None"
            return "Track" if p.single else "Playlist"

        def _metadata(self):
            s = self.pl.song or {}
            sid = s.get("id") or "0"
            md = {"mpris:trackid": dbus.ObjectPath(f"/org/zebamp/track/{sid}")}
            if not s:
                md["mpris:trackid"] = dbus.ObjectPath("/org/mpris/MediaPlayer2/TrackList/NoTrack")
                return dbus.Dictionary(md, signature="sv")
            title = first(s.get("title")) or first(s.get("name")) or os.path.basename(s.get("file", ""))
            md["xesam:title"] = title
            for key, tag in (("xesam:artist", "artist"), ("xesam:albumArtist", "albumartist"),
                             ("xesam:genre", "genre"), ("xesam:composer", "composer")):
                v = s.get(tag)
                if v:
                    md[key] = dbus.Array(v if isinstance(v, list) else [v], signature="s")
            if s.get("album"):
                md["xesam:album"] = first(s.get("album"))
            try:
                if s.get("track"):
                    md["xesam:trackNumber"] = dbus.Int32(int(str(first(s.get("track"))).split("/")[0]))
            except ValueError:
                pass
            d = self.pl.duration
            if d > 0:
                md["mpris:length"] = dbus.Int64(int(d * 1e6))
            f = s.get("file", "")
            md["xesam:url"] = f if "://" in f else "file://" + os.path.join(self.pl.music_directory or "", f)
            if self._art:
                md["mpris:artUrl"] = "file://" + self._art
            stats = getattr(self.app, "stats", None)
            if stats is not None:
                r = stats.rating(f)
                if r:
                    md["xesam:userRating"] = dbus.Double(r / 5.0)
                n = stats.playcount(f)
                if n:
                    md["xesam:useCount"] = dbus.Int32(n)
            return dbus.Dictionary(md, signature="sv")

        def _player_props(self):
            p = self.pl
            has = bool(p.queue)
            return {
                "PlaybackStatus": self._status(), "LoopStatus": self._loop(),
                "Rate": dbus.Double(1.0), "MinimumRate": dbus.Double(1.0), "MaximumRate": dbus.Double(1.0),
                "Shuffle": dbus.Boolean(bool(p.random)), "Metadata": self._metadata(),
                "Volume": dbus.Double(max(0, p.volume) / 100.0),
                "Position": dbus.Int64(int(p.elapsed * 1e6)),
                "CanGoNext": dbus.Boolean(has), "CanGoPrevious": dbus.Boolean(has),
                "CanPlay": dbus.Boolean(has), "CanPause": dbus.Boolean(True),
                "CanSeek": dbus.Boolean(p.duration > 0), "CanControl": dbus.Boolean(True),
            }

        def _root_props(self):
            return {
                "CanQuit": dbus.Boolean(True), "CanRaise": dbus.Boolean(True),
                "CanSetFullscreen": dbus.Boolean(False), "Fullscreen": dbus.Boolean(False),
                "HasTrackList": dbus.Boolean(False), "Identity": "Zebamp",
                "DesktopEntry": "zebamp",
                "SupportedUriSchemes": dbus.Array(["file", "http", "https"], signature="s"),
                "SupportedMimeTypes": dbus.Array(["audio/mpeg", "audio/flac", "audio/ogg",
                                                  "audio/x-wav", "audio/mp4", "audio/x-mpegurl"],
                                                 signature="s"),
            }

        # ------------------------------------------------------ signals
        def _changed(self):
            import time as _t
            now, el = _t.monotonic(), self.pl.elapsed
            sid = (self.pl.song or {}).get("id")
            prev = getattr(self, "_pos_ref", None)
            if prev is not None and prev[2] == sid and self.pl.state in ("play", "pause"):
                expected = prev[1] + ((now - prev[0]) if self.pl.state == "play" else 0)
                if abs(el - expected) > 2.5:
                    self.seeked()          # position jumped (seek from any client)
            self._pos_ref = (now, el, sid)
            props = self._player_props()
            props.pop("Position", None)
            diff = {k: v for k, v in props.items() if self._last.get(k) != v}
            self._last.update(props)
            if diff:
                self.PropertiesChanged(PLAYER, dbus.Dictionary(diff, signature="sv"), [])

        def _song(self):
            s = self.pl.song or {}
            uri = s.get("file")
            if uri != self._art_uri:
                self._art_uri = uri
                self._art = ""
                if uri:
                    from .notify import cover_job
                    self.pl.conn.run_async(cover_job(self.app, s), lambda path, u=uri: self._got_art(u, path))
            self._changed()

        def _got_art(self, uri, path):
            if uri == self._art_uri and path:
                self._art = path
                self._last.pop("Metadata", None)
                self._changed()

        def seeked(self):
            self.Seeked(dbus.Int64(int(self.pl.elapsed * 1e6)))

        # ------------------------------------------- org.mpris.MediaPlayer2
        @dbus.service.method(IFACE)
        def Raise(self):
            self.app.show()

        @dbus.service.method(IFACE)
        def Quit(self):
            self.app.quit()

        # ------------------------------------ org.mpris.MediaPlayer2.Player
        @dbus.service.method(PLAYER)
        def Next(self):
            self.pl.next()

        @dbus.service.method(PLAYER)
        def Previous(self):
            self.pl.previous()

        @dbus.service.method(PLAYER)
        def Pause(self):
            if self.pl.state == "play":
                self.pl.pause()

        @dbus.service.method(PLAYER)
        def PlayPause(self):
            self.pl.toggle_play()

        @dbus.service.method(PLAYER)
        def Stop(self):
            self.pl.stop()

        @dbus.service.method(PLAYER)
        def Play(self):
            if self.pl.state != "play":
                self.pl.toggle_play() if self.pl.state == "pause" else self.pl.play()

        @dbus.service.method(PLAYER, in_signature="x")
        def Seek(self, offset):
            self.pl.seek_relative(offset / 1e6)
            self.seeked()

        @dbus.service.method(PLAYER, in_signature="ox")
        def SetPosition(self, track_id, position):
            sid = str(track_id).rsplit("/", 1)[-1]
            if sid == str((self.pl.song or {}).get("id")):
                self.pl.seek(position / 1e6)
                self.seeked()

        @dbus.service.method(PLAYER, in_signature="s")
        def OpenUri(self, uri):
            if uri.startswith("file://"):
                from urllib.parse import unquote
                self.pl.add_paths([unquote(uri[7:])], replace=True)
            else:
                self.pl.add([uri], replace=True)

        @dbus.service.signal(PLAYER, signature="x")
        def Seeked(self, position):
            pass

        # -------------------------------------- org.freedesktop.DBus.Properties
        @dbus.service.method(PROPS, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            return self.GetAll(interface)[prop]

        @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface == PLAYER:
                return dbus.Dictionary(self._player_props(), signature="sv")
            if interface == IFACE:
                return dbus.Dictionary(self._root_props(), signature="sv")
            return dbus.Dictionary({}, signature="sv")

        @dbus.service.method(PROPS, in_signature="ssv")
        def Set(self, interface, prop, value):
            p = self.pl
            if interface != PLAYER:
                return
            if prop == "Volume":
                p.set_volume(int(round(max(0.0, min(1.0, float(value))) * 100)))
            elif prop == "Shuffle":
                if bool(value) != bool(p.random):
                    p.toggle_random()
            elif prop == "LoopStatus":
                p.set_repeat_mode({"None": "off", "Playlist": "all", "Track": "track"}.get(str(value), "off"))

        @dbus.service.signal(PROPS, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

    return Mpris()
