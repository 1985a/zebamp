"""Tests for the features added after 1.0.0rc1: sleep timer, drag and drop,
server profiles, scrobbling, smart lists, album art, translations."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

QAPP = QApplication.instance() or QApplication([])

from test_core import _start_mpd


def wait(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class SleepTimerLogicTest(unittest.TestCase):
    def test_album_ends_when_the_next_song_is_from_another_album(self):
        from zebamp.sleeptimer import ends_album
        a1 = {"file": "x/1.flac", "album": "Uno", "albumartist": "Ana"}
        a2 = {"file": "x/2.flac", "album": "Uno", "albumartist": "Ana"}
        b1 = {"file": "y/1.flac", "album": "Dos", "albumartist": "Ana"}
        self.assertFalse(ends_album(a1, a2))
        self.assertTrue(ends_album(a2, b1))
        self.assertTrue(ends_album(a2, None))          # end of the queue
        self.assertFalse(ends_album({}, a1))           # nothing playing

    def test_untagged_files_use_their_folder_as_album(self):
        from zebamp.sleeptimer import ends_album
        self.assertFalse(ends_album({"file": "x/1.wav"}, {"file": "x/2.wav"}))
        self.assertTrue(ends_album({"file": "x/2.wav"}, {"file": "y/1.wav"}))

    def test_remaining_text(self):
        from zebamp.sleeptimer import remaining_text
        self.assertEqual(remaining_text(20), "menos de 1 min")
        self.assertEqual(remaining_text(12 * 60 + 59), "12 min")
        self.assertEqual(remaining_text(65 * 60), "1 h 05 min")


@unittest.skipUnless(shutil.which("mpd") and shutil.which("mpc"), "mpd not installed")
class SleepTimerWithMpdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="zebamp-extras-")
        cls.conf = _start_mpd(cls.tmp)
        from zebamp.mpdconn import MpdAddress
        from zebamp.player import Player
        cls.player = Player(MpdAddress(f"{cls.tmp}/sock"))
        cls.player.conn.connect_now()

    @classmethod
    def tearDownClass(cls):
        cls.player.conn.disconnect_now()
        subprocess.run(["mpd", "--kill", cls.conf], capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        p = self.player
        p.conn.batch([("clear",), ("single", 0), ("add", "A")])
        p._pl_version = None
        p._refresh_all()

    def refresh(self):
        self.player._refresh_all()

    def test_minutes_pause_the_music_once(self):
        from zebamp.sleeptimer import SleepTimer
        p = self.player
        p.play(0)
        self.refresh()
        timer = SleepTimer(p)
        fired = []
        timer.fired.connect(lambda: fired.append(1))
        timer.start_minutes(0.2 / 60)                  # 0.2 s
        self.assertTrue(timer.active)
        self.assertIn("Quedan", timer.describe())
        wait(500)
        self.refresh()
        self.assertEqual(p.state, "pause")
        self.assertEqual(fired, [1])
        self.assertFalse(timer.active)

    def test_cancel_leaves_the_music_playing(self):
        from zebamp.sleeptimer import SleepTimer
        p = self.player
        p.play(0)
        self.refresh()
        timer = SleepTimer(p)
        timer.start_minutes(0.2 / 60)
        timer.cancel()
        wait(400)
        self.refresh()
        self.assertEqual(p.state, "play")

    def test_album_mode_lets_the_last_song_finish(self):
        from zebamp.sleeptimer import SleepTimer
        p = self.player
        last = len(p.queue) - 1
        p.play(3)
        self.refresh()
        timer = SleepTimer(p)
        fired = []
        timer.fired.connect(lambda: fired.append(1))
        timer.start_album()
        self.assertNotEqual(p.conn.call("status")["single"], "oneshot")   # more of the album follows
        p.play(last)
        self.refresh()
        self.assertEqual(p.conn.call("status")["single"], "oneshot")
        p.conn.call("seekcur", 3.5)                    # songs last 4 s
        deadline = time.monotonic() + 5
        while timer.active and time.monotonic() < deadline:
            wait(150)
            self.refresh()
        self.assertEqual(fired, [1])
        self.assertNotEqual(p.state, "play")
        self.assertFalse(timer.active)

    def test_cancelling_album_mode_disarms_mpd(self):
        from zebamp.sleeptimer import SleepTimer
        p = self.player
        p.play(len(p.queue) - 1)
        self.refresh()
        timer = SleepTimer(p)
        timer.start_album()
        self.assertEqual(p.conn.call("status")["single"], "oneshot")
        timer.cancel()
        self.assertEqual(p.conn.call("status")["single"], "0")


class ProfilesTest(unittest.TestCase):
    def test_hand_edited_settings_are_cleaned(self):
        from zebamp.profiles import clean_profiles
        raw = [{"name": " Casa ", "host": "192.168.1.5", "port": "6601", "password": "x"},
               {"name": "casa", "host": "otro"},                 # same name: dropped
               {"name": "", "host": "sin-nombre"}, {"name": "sin host"}, "texto", None,
               {"name": "Puerto raro", "host": "h", "port": 99999}]
        self.assertEqual(clean_profiles(raw), [
            {"name": "Casa", "host": "192.168.1.5", "port": 6601, "password": "x"},
            {"name": "Puerto raro", "host": "h", "port": 6600, "password": ""}])
        self.assertEqual(clean_profiles(None), [])
        self.assertEqual(clean_profiles({"name": "x"}), [])

    def test_add_replace_remove_and_address(self):
        from zebamp.profiles import find_profile, profile_address, with_profile, without_profile
        ps = with_profile([], {"name": "Casa", "host": "10.0.0.2", "port": 6600, "password": ""})
        ps = with_profile(ps, {"name": "PC", "host": "/run/mpd/socket", "port": 6600, "password": ""})
        ps = with_profile(ps, {"name": "casa", "host": "10.0.0.9", "port": 6601, "password": "p"})
        self.assertEqual([p["name"] for p in ps], ["PC", "casa"])
        addr = profile_address(find_profile(ps, "CASA"))
        self.assertEqual((addr.host, addr.port, addr.password), ("10.0.0.9", 6601, "p"))
        self.assertIsNone(find_profile(ps, "no existe"))
        self.assertEqual([p["name"] for p in without_profile(ps, "pc")], ["casa"])


SONG = {"file": "A/01.flac", "artist": "Ana", "title": "Uno", "album": "Disco", "albumartist": "Ana",
        "track": "3/12", "duration": "241.5", "musicbrainz_trackid": "mbid-1"}


class ScrobbleLogicTest(unittest.TestCase):
    def test_what_is_scrobbled(self):
        from zebamp.scrobble import listen_from_song
        self.assertEqual(listen_from_song(SONG, 1700000000), {
            "artist": "Ana", "title": "Uno", "album": "Disco", "albumartist": "Ana", "track": 3,
            "duration": 241, "mbid": "mbid-1", "started_at": 1700000000})
        self.assertIsNone(listen_from_song({**SONG, "file": "http://radio/stream"}, 1))   # stream
        self.assertIsNone(listen_from_song({**SONG, "artist": ""}, 1))                    # untagged
        self.assertIsNone(listen_from_song({**SONG, "duration": "20"}, 1))                # too short
        self.assertIsNotNone(listen_from_song({**SONG, "duration": "x", "track": ["x"]}, 1))  # odd tags
        self.assertEqual(listen_from_song({**SONG, "artist": ["Ana", "Bea"]}, 1)["artist"], "Ana")

    def test_listenbrainz_payload(self):
        from zebamp.scrobble import listen_from_song, listenbrainz_payload
        listen = listen_from_song(SONG, 1700000000)
        one = listenbrainz_payload([listen])
        self.assertEqual(one["listen_type"], "single")
        item = one["payload"][0]
        self.assertEqual(item["listened_at"], 1700000000)
        self.assertEqual(item["track_metadata"]["artist_name"], "Ana")
        self.assertEqual(item["track_metadata"]["release_name"], "Disco")
        self.assertEqual(item["track_metadata"]["additional_info"]["recording_mbid"], "mbid-1")
        self.assertEqual(listenbrainz_payload([listen, listen])["listen_type"], "import")
        now = listenbrainz_payload([listen], now_playing=True)
        self.assertEqual(now["listen_type"], "playing_now")
        self.assertNotIn("listened_at", now["payload"][0])

    def test_lastfm_signature_matches_the_documented_recipe(self):
        import hashlib
        from zebamp.scrobble import lastfm_scrobble_params, lastfm_signature, lastfm_signed, listen_from_song
        params = {"method": "auth.getSession", "api_key": "KEY", "token": "TOK", "format": "json"}
        expect = hashlib.md5(b"api_keyKEYmethodauth.getSessiontokenTOKSECRET").hexdigest()
        self.assertEqual(lastfm_signature(params, "SECRET"), expect)       # `format` is not signed
        self.assertEqual(lastfm_signed(params, "SECRET")["api_sig"], expect)
        p = lastfm_scrobble_params([listen_from_song(SONG, 5), listen_from_song(SONG, 9)], "KEY", "SK")
        self.assertEqual((p["artist[0]"], p["track[1]"], p["timestamp[0]"], p["timestamp[1]"]),
                         ("Ana", "Uno", "5", "9"))
        self.assertEqual(p["trackNumber[0]"], "3")

    def test_retry_delay_grows_up_to_an_hour(self):
        from zebamp.scrobble import retry_delay
        self.assertEqual([retry_delay(n) for n in (1, 2, 3, 10)], [60, 120, 240, 3600])

    def test_queue_survives_restarts_and_bad_files(self):
        from zebamp.scrobble import BATCH, ListenQueue, listen_from_song
        path = os.path.join(tempfile.mkdtemp(prefix="zebamp-queue-"), "q.json")
        q = ListenQueue(path)
        for i in range(BATCH + 5):
            q.add("listenbrainz", listen_from_song(SONG, i))
        again = ListenQueue(path)
        self.assertEqual(again.count("listenbrainz"), BATCH + 5)
        self.assertEqual(len(again.batch("listenbrainz")), BATCH)
        again.done("listenbrainz", BATCH)
        self.assertEqual([x["started_at"] for x in ListenQueue(path).batch("listenbrainz")],
                         list(range(BATCH, BATCH + 5)))
        with open(path, "w") as fh:
            fh.write('{"listenbrainz": [{"artist": "x"}, 3], "lastfm": "no"}')     # damaged by hand
        self.assertEqual(ListenQueue(path).count("listenbrainz"), 0)
        with open(path, "w") as fh:
            fh.write("not json")
        self.assertEqual(ListenQueue(path).pending, {})


class _FakeServices:
    """Local stand-in for ListenBrainz and Last.fm: records what it is sent."""

    def __init__(self):
        import http.server
        import json as _json
        import threading
        import urllib.parse
        fake = self
        self.requests = []
        self.status = 200
        self.lastfm_error = None

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, body):
                data = _json.dumps(body).encode()
                self.send_response(fake.status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.requests.append(("GET", self.path, self.headers.get("Authorization"), None))
                self._reply({"valid": self.headers.get("Authorization") == "Token good", "user_name": "ana"})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path.startswith("/1/"):
                    body = _json.loads(raw)
                else:
                    body = dict(urllib.parse.parse_qsl(raw.decode()))
                fake.requests.append(("POST", self.path, self.headers.get("Authorization"), body))
                if self.path.startswith("/1/"):
                    self._reply({"status": "ok"})
                elif fake.lastfm_error:
                    self._reply({"error": fake.lastfm_error, "message": "x"})
                elif body.get("method") == "auth.getToken":
                    self._reply({"token": "TOK"})
                elif body.get("method") == "auth.getSession":
                    self._reply({"session": {"key": "SK", "name": "ana"}})
                else:
                    self._reply({"scrobbles": {}})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class ScrobbleNetworkTest(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeServices()
        self.addCleanup(self.fake.close)

    def test_listenbrainz_submit_check_and_errors(self):
        from zebamp.scrobble import AUTH, OK, RETRY, ListenBrainz, listen_from_song
        lb = ListenBrainz("good", self.fake.url)
        self.assertEqual(lb.check(), (True, "ana"))
        self.assertEqual(ListenBrainz("bad", self.fake.url).check()[0], False)
        self.assertEqual(lb.submit([listen_from_song(SONG, 7)]), OK)
        method, path, auth, body = self.fake.requests[-1]
        self.assertEqual((method, path, auth), ("POST", "/1/submit-listens", "Token good"))
        self.assertEqual(body["payload"][0]["listened_at"], 7)
        self.fake.status = 401
        self.assertEqual(lb.submit([listen_from_song(SONG, 7)]), AUTH)
        self.fake.status = 503
        self.assertEqual(lb.submit([listen_from_song(SONG, 7)]), RETRY)
        self.assertEqual(ListenBrainz("good", "http://127.0.0.1:9").submit([listen_from_song(SONG, 7)]), RETRY)
        # a server address that is not http(s) (a local file, say) is never opened
        self.assertEqual(ListenBrainz("good", "file:///etc").check()[0], False)
        self.assertEqual(ListenBrainz("good", "file:///etc").submit([listen_from_song(SONG, 7)]), RETRY)

    def test_lastfm_sign_in_and_scrobble(self):
        from zebamp.scrobble import AUTH, OK, RETRY, LastFm, lastfm_signature, listen_from_song
        fm = LastFm("KEY", "SECRET", url=self.fake.url + "/2.0/")
        token = fm.request_token()
        self.assertEqual(token, "TOK")
        self.assertIn("token=TOK", fm.approval_url(token))
        self.assertEqual(fm.open_session(token), ("SK", "ana"))
        fm.session_key = "SK"
        self.assertEqual(fm.submit([listen_from_song(SONG, 7)]), OK)
        body = self.fake.requests[-1][3]
        self.assertEqual((body["method"], body["sk"], body["artist[0]"]), ("track.scrobble", "SK", "Ana"))
        unsigned = {k: v for k, v in body.items() if k != "api_sig"}
        self.assertEqual(body["api_sig"], lastfm_signature(unsigned, "SECRET"))
        self.fake.lastfm_error = 9                       # invalid session
        self.assertEqual(fm.submit([listen_from_song(SONG, 7)]), AUTH)
        self.fake.lastfm_error = 29                      # rate limit
        self.assertEqual(fm.submit([listen_from_song(SONG, 7)]), RETRY)
        self.assertEqual(fm.open_session("x"), ("", ""))

    def test_scrobbler_queues_offline_and_sends_when_back(self):
        from PySide6.QtCore import QObject, Signal
        from zebamp.scrobble import ListenQueue, Scrobbler

        class FakePlayer(QObject):
            songChanged = Signal()
            statusChanged = Signal()
            state = "play"
            song = SONG

        class FakeStats(QObject):
            played = Signal(dict, int)

        cfg = {"listenbrainz_enabled": True, "listenbrainz_token": "good", "listenbrainz_url": self.fake.url,
               "lastfm_enabled": False, "lastfm_api_key": "", "lastfm_secret": "", "lastfm_session": "",
               "lastfm_url": ""}
        queue = ListenQueue(os.path.join(tempfile.mkdtemp(prefix="zebamp-queue-"), "q.json"))
        player, stats = FakePlayer(), FakeStats()
        scrobbler = Scrobbler(cfg, player, stats, queue)
        self.fake.status = 503                           # service down
        stats.played.emit(SONG, 100)
        wait(600)
        self.assertEqual(queue.count("listenbrainz"), 1)
        self.assertTrue(scrobbler._retry.isActive())     # will try again by itself
        self.assertIn("1 en espera", scrobbler.describe("listenbrainz"))
        self.fake.status = 200                           # back
        stats.played.emit(SONG, 200)
        wait(800)
        self.assertEqual(queue.count("listenbrainz"), 0)
        sent = [r[3]["payload"] for r in self.fake.requests if r[0] == "POST" and r[3]["listen_type"] != "playing_now"]
        self.assertEqual([x["listened_at"] for x in sent[-1]], [100, 200])
        player.statusChanged.emit()                      # now playing is announced once per song
        player.statusChanged.emit()
        wait(500)
        now = [r for r in self.fake.requests if r[0] == "POST" and r[3]["listen_type"] == "playing_now"]
        self.assertEqual(len(now), 1)
        scrobbler._retry.stop()

    def test_disabled_scrobbler_sends_nothing(self):
        from PySide6.QtCore import QObject, Signal
        from zebamp.scrobble import ListenQueue, Scrobbler

        class FakePlayer(QObject):
            songChanged = Signal()
            statusChanged = Signal()
            state = "play"
            song = SONG

        class FakeStats(QObject):
            played = Signal(dict, int)

        cfg = dict.fromkeys(("listenbrainz_enabled", "listenbrainz_token", "listenbrainz_url", "lastfm_enabled",
                             "lastfm_api_key", "lastfm_secret", "lastfm_session", "lastfm_url"), "")
        queue = ListenQueue(os.path.join(tempfile.mkdtemp(prefix="zebamp-queue-"), "q.json"))
        player, stats = FakePlayer(), FakeStats()
        Scrobbler(cfg, player, stats, queue)
        stats.played.emit(SONG, 100)
        player.statusChanged.emit()
        wait(300)
        self.assertEqual(self.fake.requests, [])
        self.assertEqual(queue.pending, {})


#        file            title     artist  album     albumartist genre        secs   date
ROWS = [["a/1.flac",    "Uno",    "Ana",  "Disco",  "Ana",      "Rock",      "200", "1999"],
        ["a/2.flac",    "Dos",    "Ana",  "Disco",  "Ana",      "Rock",      "400", "1999-05-01"],
        ["b/1.flac",    "Canción", "Bea", "Otro",   "",         "Pop Rock",  "100", "2010"],
        ["c/1.flac",    "Tres",   "Cid",  "Más",    "Cid",      "Jazz",      "",    ""]]
NOW = 1_800_000_000
RATINGS = {"a/1.flac": 10, "a/2.flac": 7, "b/1.flac": 4}             # stored 0..10 -> 5, 4 and 2 stars
COUNTS = {"a/1.flac": 9, "b/1.flac": 2}
LAST = {"a/1.flac": NOW - 2 * 86400, "b/1.flac": NOW - 60 * 86400}


def smart(rules, **kw):
    return {"name": "t", "match": "all", "rules": rules, "order": "artist", "limit": 0, **kw}


def files(smart_list):
    from zebamp.smartlist import evaluate
    return [r[0] for r in evaluate(smart_list, ROWS, RATINGS, COUNTS, LAST, NOW)]


class SmartListTest(unittest.TestCase):
    def test_text_rules_ignore_case_and_accents(self):
        self.assertEqual(files(smart([{"field": "genre", "op": "contains", "value": "ROCK"}])),
                         ["a/1.flac", "a/2.flac", "b/1.flac"])
        self.assertEqual(files(smart([{"field": "genre", "op": "is", "value": "rock"}])), ["a/1.flac", "a/2.flac"])
        self.assertEqual(files(smart([{"field": "title", "op": "contains", "value": "cancion"}])), ["b/1.flac"])
        self.assertEqual(files(smart([{"field": "file", "op": "starts", "value": "c/"}])), ["c/1.flac"])
        self.assertEqual(files(smart([{"field": "artist", "op": "is_not", "value": "ana"},
                                      {"field": "genre", "op": "not_contains", "value": "jazz"}])), ["b/1.flac"])

    def test_number_rules(self):
        self.assertEqual(files(smart([{"field": "rating", "op": "ge", "value": 4.0}])), ["a/1.flac", "a/2.flac"])
        self.assertEqual(files(smart([{"field": "plays", "op": "eq", "value": 0.0}])), ["a/2.flac", "c/1.flac"])
        self.assertEqual(files(smart([{"field": "year", "op": "le", "value": 1999.0}])),
                         ["a/1.flac", "a/2.flac", "c/1.flac"])            # unknown year counts as 0
        self.assertEqual(files(smart([{"field": "minutes", "op": "ge", "value": 5.0}])), ["a/2.flac"])

    def test_not_heard_in_a_month_includes_never_played(self):
        rule = {"field": "days_since_played", "op": "ge", "value": 30.0}
        self.assertEqual(files(smart([rule])), ["a/2.flac", "b/1.flac", "c/1.flac"])
        self.assertEqual(files(smart([{"field": "days_since_played", "op": "le", "value": 7.0}])), ["a/1.flac"])

    def test_all_any_order_and_limit(self):
        rules = [{"field": "genre", "op": "contains", "value": "rock"}, {"field": "rating", "op": "ge", "value": 4.0}]
        self.assertEqual(files(smart(rules)), ["a/1.flac", "a/2.flac"])
        self.assertEqual(len(files(smart([*rules, {"field": "genre", "op": "is", "value": "jazz"}], match="any"))), 4)
        every = [{"field": "plays", "op": "ge", "value": 0.0}]
        self.assertEqual(files(smart(every, order="most_played"))[:2], ["a/1.flac", "b/1.flac"])
        self.assertEqual(files(smart(every, order="best_rated"))[0], "a/1.flac")
        self.assertEqual(files(smart(every, order="recently_played"))[0], "a/1.flac")
        self.assertEqual(files(smart(every, order="longest_unheard"))[-1], "a/1.flac")
        self.assertEqual(sorted(files(smart(every, order="random"))), sorted(r[0] for r in ROWS))
        self.assertEqual(files(smart(every, limit=2)), ["a/1.flac", "a/2.flac"])

    def test_rows_from_an_older_index_have_no_date(self):
        from zebamp.smartlist import evaluate
        old_rows = [r[:7] for r in ROWS]
        got = evaluate(smart([{"field": "year", "op": "ge", "value": 1990.0}]), old_rows, {}, {}, {}, NOW)
        self.assertEqual(got, [])

    def test_hand_edited_settings_are_cleaned(self):
        from zebamp.smartlist import clean_smart_lists
        raw = [{"name": " Rock ", "match": "raro", "order": "x", "limit": "-3",
                "rules": [{"field": "genre", "op": "contains", "value": " rock "},
                          {"field": "rating", "op": "ge", "value": "4"},
                          {"field": "rating", "op": "contains", "value": "4"},      # wrong comparison
                          {"field": "plays", "op": "ge", "value": "muchas"},        # not a number
                          {"field": "genre", "op": "is", "value": "  "}, {"field": "nope"}, 7]},
               {"name": "rock", "rules": [{"field": "genre", "op": "is", "value": "x"}]},   # duplicate name
               {"name": "Vacía", "rules": []}, {"rules": [{"field": "genre", "op": "is", "value": "x"}]},
               "texto", None]
        self.assertEqual(clean_smart_lists(raw), [{
            "name": "Rock", "match": "all", "order": "artist", "limit": 0,
            "rules": [{"field": "genre", "op": "contains", "value": "rock"},
                      {"field": "rating", "op": "ge", "value": 4.0}]}])
        self.assertEqual(clean_smart_lists("no"), [])

    def test_edit_replaces_in_place_and_describe(self):
        from zebamp.smartlist import describe, with_smart_list, without_smart_list
        a, b = smart([{"field": "genre", "op": "is", "value": "x"}], name="A"), \
            smart([{"field": "genre", "op": "is", "value": "y"}], name="B")
        renamed = smart([{"field": "rating", "op": "ge", "value": 4.0}], name="Z")
        self.assertEqual([x["name"] for x in with_smart_list([a, b], renamed, replacing="A")], ["Z", "B"])
        self.assertEqual([x["name"] for x in with_smart_list([a, b], renamed)], ["A", "B", "Z"])
        self.assertEqual([x["name"] for x in without_smart_list([a, b], "a")], ["B"])
        both = smart([{"field": "genre", "op": "contains", "value": "rock"},
                      {"field": "rating", "op": "ge", "value": 4.0}])
        self.assertEqual(describe(both), "Género contiene rock y Valoración (estrellas) al menos 4")

    def test_fast_enough_for_a_big_library(self):
        from zebamp.smartlist import evaluate
        rows = [[f"d{i % 900}/{i}.flac", f"Título {i}", f"Artista {i % 3000}", f"Álbum {i % 9000}", "",
                 ("Rock", "Pop", "Jazz")[i % 3], "200", "2001"] for i in range(100_000)]
        rules = smart([{"field": "genre", "op": "contains", "value": "rock"},
                       {"field": "rating", "op": "ge", "value": 4.0},
                       {"field": "days_since_played", "op": "ge", "value": 30.0}])
        ratings = {r[0]: 8 for r in rows[::7]}
        t = time.monotonic()
        got = evaluate(rules, rows, ratings, {}, {}, NOW)
        self.assertLess(time.monotonic() - t, 3.0)
        self.assertEqual(len(got), len([r for r in rows[::7] if r[5] == "Rock"]))


class ArtFitTest(unittest.TestCase):
    def test_picture_keeps_its_proportions_and_is_centred(self):
        from PySide6.QtCore import QRect
        from zebamp.ui.artpanel import fit_rect
        box = QRect(10, 20, 200, 100)
        wide = fit_rect(400, 100, box)
        self.assertEqual((wide.x(), wide.y(), wide.width(), wide.height()), (10, 45, 200, 50))
        square = fit_rect(50, 50, box)                    # small images are enlarged to fit
        self.assertEqual((square.x(), square.y(), square.width(), square.height()), (60, 20, 100, 100))
        self.assertTrue(fit_rect(0, 50, box).isEmpty())   # broken image


@unittest.skipUnless(shutil.which("mpd") and shutil.which("mpc"), "mpd not installed")
class AppFeaturesTest(unittest.TestCase):
    """The new features inside the real application (private MPD, offscreen)."""

    @classmethod
    def setUpClass(cls):
        import argparse
        import importlib
        from PySide6.QtGui import QColor, QImage
        cls.tmp = tempfile.mkdtemp(prefix="zebamp-app-")
        cls.conf = _start_mpd(cls.tmp)
        cover = QImage(40, 20, QImage.Format.Format_RGB32)
        cover.fill(QColor("#c02020"))
        cover.save(os.path.join(cls.tmp, "music", "A", "cover.png"))
        os.environ["XDG_CONFIG_HOME"] = os.path.join(cls.tmp, "cfg")
        os.environ["XDG_DATA_HOME"] = os.path.join(cls.tmp, "data")
        os.environ["XDG_CACHE_HOME"] = os.path.join(cls.tmp, "cache")
        import zebamp.config
        importlib.reload(zebamp.config)
        import zebamp.app
        importlib.reload(zebamp.app)
        args = argparse.Namespace(host=f"{cls.tmp}/sock", port=0, skin=None, debug=False, files=[])
        cls.app = zebamp.app.ZebampApp(QAPP, args)
        cls.app.shell.setFixedSize(2560, 1400)           # room for every window
        cls.app.show()
        wait(500)
        cls.app.player.add(["A"], replace=True)
        wait(300)

    @classmethod
    def tearDownClass(cls):
        cls.app.player.stop()
        wait(100)
        cls.app.quit()
        subprocess.run(["mpd", "--kill", cls.conf], capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_art_panel_docks_and_shows_the_cover(self):
        app = self.app
        self.assertNotIn(app.art_panel, app.visible_panels())
        app.toggle_art_panel()
        wait(700)
        self.assertIn(app.art_panel, app.visible_panels())
        self.assertFalse(app.art_panel._cover.isNull())
        self.assertEqual((app.art_panel._cover.width(), app.art_panel._cover.height()), (40, 20))
        # it appears docked under the stack, so it travels with the main window
        from PySide6.QtCore import QPoint
        main = app.main_panel
        app._drag_begin(main, QPoint(main.x() + 30, main.y() + 5))
        self.assertIn(app.art_panel, app._drag[1])
        app.drag_end()
        app.toggle_art_panel()
        self.assertNotIn(app.art_panel, app.visible_panels())

    def test_art_panel_resizes_in_steps(self):
        app = self.app
        app.cfg["art_width"], app.cfg["art_height"] = 2, 3
        app.art_panel.rebuild()
        self.assertEqual(app.art_panel.logical_size(), (275 + 50, 116 + 87))
        self.assertEqual(app.ly_panel.logical_size(), (275 + 25 * app.cfg["ly_width"], 116 + 29 * app.cfg["ly_height"]))

    def test_dropping_files_on_the_main_window_plays_them(self):
        from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PySide6.QtGui import QDropEvent
        app = self.app
        app.player.clear()
        wait(200)
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(os.path.join(self.tmp, "music", "A", "03.wav")),
                      QUrl.fromLocalFile(os.path.join(self.tmp, "music", "A", "05.wav"))])
        drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
        app.main_panel.dropEvent(drop)
        wait(400)
        self.assertEqual([s["file"] for s in app.player.queue], ["A/03.wav", "A/05.wav"])
        self.assertEqual(app.player.state, "play")
        app.player.add(["A"], replace=True)
        wait(200)

    def test_sleep_timer_menu(self):
        app = self.app
        app.player.play(0)
        wait(200)
        app.start_sleep(30)
        menu = app.build_sleep_menu(None)                # keep the menu alive while reading it
        labels = [a.text() for a in menu.actions()]
        self.assertIn("Quedan 29 min", labels)
        self.assertIn("Cancelar", labels)
        app.sleep.cancel()
        menu = app.build_sleep_menu(None)
        self.assertNotIn("Cancelar", [a.text() for a in menu.actions()])

    def test_profiles_switch_servers(self):
        app = self.app
        app.cfg["mpd_profiles"] = [{"name": "Pruebas", "host": f"{self.tmp}/sock", "port": 6600, "password": ""},
                                   {"name": "Apagado", "host": "/nonexistent/sock", "port": 6600, "password": ""}]
        app.use_profile("Apagado")
        wait(300)
        self.assertFalse(app.player.connected)
        self.assertEqual(app.cfg["mpd_profile"], "Apagado")
        app.use_profile("Pruebas")
        wait(500)
        self.assertTrue(app.player.connected)
        self.assertEqual(len(app.player.queue), 12)
        menu = app.build_profiles_menu(None)
        checked = [a.text() for a in menu.actions() if a.isChecked()]
        self.assertEqual(checked, ["Pruebas"])
        app.use_profile("no existe")                     # unknown name: nothing changes
        self.assertEqual(app.cfg["mpd_profile"], "Pruebas")
        app.remove_profile("Pruebas")
        self.assertEqual([p["name"] for p in app.profiles()], ["Apagado"])
        self.assertTrue(app.player.connected)

    def test_smart_list_in_the_library(self):
        app = self.app
        app.library_index.refresh()
        deadline = time.monotonic() + 5
        while not app.library_index.is_ready and time.monotonic() < deadline:
            wait(100)
        self.assertEqual(len(app.library_index.rows), 12)
        app.stats.ratings["A/04.wav"] = 10
        app.save_smart_lists([{"name": "Favoritas", "match": "all", "order": "artist", "limit": 0,
                               "rules": [{"field": "rating", "op": "ge", "value": 5.0}]}])
        from zebamp.ui.library import LibraryWindow
        lib = LibraryWindow(app)
        root = lib._roots["smartlists"]
        root.setExpanded(True)
        self.assertEqual([root.child(i).text(0) for i in range(root.childCount())],
                         ["Favoritas", "＋ Nueva lista inteligente…"])
        lib.tree.setCurrentItem(root.child(0))
        wait(500)
        self.assertEqual(lib.table.uris(selected_only=False), ["A/04.wav"])
        lib.delete_smart_list("Favoritas")
        self.assertEqual(app.smart_lists(), [])
        lib.deleteLater()

    def test_smart_list_editor_validates(self):
        from zebamp.ui.smartlist_dialog import SmartListDialog
        dialog = SmartListDialog(self.app)
        self.assertIsNone(dialog.edited())               # no name, empty value
        dialog.name.setText("Rock bueno")
        dialog.rows[0].value.setText("rock")
        dialog._add_row({"field": "rating", "op": "ge", "value": 4.0})
        self.assertEqual([c.currentData() for c in (dialog.rows[1].field, dialog.rows[1].op)], ["rating", "ge"])
        self.assertEqual(dialog.edited()["rules"], [{"field": "genre", "op": "contains", "value": "rock"},
                                                    {"field": "rating", "op": "ge", "value": 4.0}])
        dialog.rows[1].value.setText("muchas")           # not a number: refused, dialog stays open
        dialog._accept()
        self.assertIsNone(dialog.result_list)
        dialog.rows[1].value.setText("4,5")              # decimal comma is understood
        dialog._accept()
        self.assertEqual(dialog.result_list["rules"][1]["value"], 4.5)
        dialog.deleteLater()

    def test_preferences_save_scrobbling_settings(self):
        from zebamp.ui.dialogs import PreferencesDialog
        app = self.app
        dialog = PreferencesDialog(app)
        dialog.scrobble.lb_on.setChecked(True)
        dialog.scrobble.lb_token.setText(" tok ")
        dialog.scrobble.lb_url.setText("http://127.0.0.1:9")
        dialog._save()
        self.assertEqual((app.cfg["listenbrainz_enabled"], app.cfg["listenbrainz_token"]), (True, "tok"))
        self.assertEqual([s.name for s in app.scrobbler.services], ["listenbrainz"])
        app.cfg["listenbrainz_enabled"] = False
        app.scrobbler.configure()
        self.assertEqual(app.scrobbler.services, [])
        dialog.deleteLater()


class CompositorTest(unittest.TestCase):
    def test_detection(self):
        from zebamp import compositor
        self.assertEqual(compositor.detect({"SWAYSOCK": "/run/sway.sock"}).name, "sway")
        self.assertEqual(compositor.detect({"HYPRLAND_INSTANCE_SIGNATURE": "abc"}).name, "hyprland")
        self.assertEqual(compositor.detect({"XDG_CURRENT_DESKTOP": "KDE"}).name, "generic")
        generic = compositor.Generic()
        self.assertEqual((generic.workspace_rects(), generic.focus_command("x")), ([], []))
        generic.move_window("x", 1, 2)                   # nothing to do, must not fail

    def test_sway_workspaces_focused_first_and_bad_data(self):
        from PySide6.QtCore import QRect
        from zebamp.compositor import sway_workspace_rects
        data = [{"visible": True, "focused": False, "rect": {"x": 0, "y": 76, "width": 1920, "height": 1004}},
                {"visible": False, "focused": False, "rect": {"x": 0, "y": 76, "width": 1920, "height": 1004}},
                {"visible": True, "focused": True, "rect": {"x": 1920, "y": 76, "width": 2560, "height": 1364}}]
        self.assertEqual(sway_workspace_rects(data), [QRect(1920, 76, 2560, 1364), QRect(0, 76, 1920, 1004)])
        self.assertEqual(sway_workspace_rects([{"visible": True}]), [])
        self.assertEqual(sway_workspace_rects({"error": "x"}), [])
        self.assertEqual(sway_workspace_rects(None), [])

    def test_sway_finds_our_floating_window(self):
        from zebamp.compositor import sway_find_window
        ours = {"id": 7, "pid": 42, "name": "Zebamp", "type": "floating_con", "rect": {"x": 5, "y": 6}}
        tree = {"nodes": [{"type": "output", "nodes": [{"type": "workspace", "nodes": [
            {"id": 3, "pid": 42, "name": "Zebamp", "type": "con"}],            # tiled namesake: not it
            "floating_nodes": [{"id": 9, "pid": 1, "name": "Zebamp", "type": "floating_con"}, ours]}]}]}
        self.assertIs(sway_find_window(tree, 42, "Zebamp"), ours)
        self.assertIsNone(sway_find_window(tree, 42, "Otro"))
        self.assertIsNone(sway_find_window(None, 42, "Zebamp"))

    def test_hyprland_monitors_scale_rotation_and_bars(self):
        from PySide6.QtCore import QRect
        from zebamp.compositor import hypr_monitor_rects
        data = [{"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0, "transform": 0,
                 "reserved": [0, 30, 0, 0], "focused": False},
                {"x": 1920, "y": 0, "width": 3840, "height": 2160, "scale": 2.0, "transform": 1,
                 "reserved": [0, 0, 0, 0], "focused": True}]
        self.assertEqual(hypr_monitor_rects(data), [QRect(1920, 0, 1080, 1920), QRect(0, 30, 1920, 1050)])
        self.assertEqual(hypr_monitor_rects([{"x": 0, "y": 0, "width": 800, "height": 600}]), [QRect(0, 0, 800, 600)])
        self.assertEqual(hypr_monitor_rects([{"x": 0}]), [])
        self.assertEqual(hypr_monitor_rects("no"), [])

    def test_hyprland_finds_our_client(self):
        from zebamp.compositor import hypr_find_client
        clients = [{"pid": 1, "title": "Zebamp", "address": "0x1"}, {"pid": 42, "title": "Zebamp", "address": "0x2"}]
        self.assertEqual(hypr_find_client(clients, 42, "Zebamp")["address"], "0x2")
        self.assertIsNone(hypr_find_client(clients, 42, "Otro"))
        self.assertIsNone(hypr_find_client(None, 42, "Zebamp"))

    def test_missing_tool_is_not_an_error(self):
        from unittest import mock
        from zebamp import compositor
        with mock.patch.object(compositor.subprocess, "run", side_effect=FileNotFoundError("hyprctl")):
            hypr = compositor.Hyprland()
            self.assertEqual(hypr.workspace_rects(), [])
            hypr.move_window("Zebamp", 0, 0)
            self.assertEqual(compositor.Sway().workspace_rects(), [])

    def test_hyprland_moves_and_floats_the_canvas(self):
        import json
        from unittest import mock
        from zebamp import compositor
        calls = []

        def fake_run(command, **kw):
            calls.append(command)
            out = json.dumps([{"pid": os.getpid(), "title": "Zebamp", "address": "0xabc", "floating": False,
                               "at": [10, 10]}])
            return mock.Mock(stdout=out)
        with mock.patch.object(compositor.subprocess, "run", side_effect=fake_run):
            compositor.Hyprland().move_window("Zebamp", 1920, 30)
        self.assertEqual(calls[1:], [["hyprctl", "dispatch", "setfloating", "address:0xabc"],
                                     ["hyprctl", "dispatch", "movewindowpixel", "exact 1920 30,address:0xabc"]])


REPO = os.path.join(os.path.dirname(__file__), "..")


def translatable_texts() -> dict:
    """Every literal passed to tr() in the code -> the file it is in."""
    import ast
    import glob
    texts = {}
    for path in sorted(glob.glob(os.path.join(REPO, "zebamp", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                arg = node.args[0] if node.args else None
                # tr() must get the text itself: a variable cannot be collected for translation
                assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (path, node.lineno)
                texts.setdefault(arg.value, os.path.relpath(path, REPO))
    return texts


class TranslationTest(unittest.TestCase):
    def test_english_catalogue_is_complete_and_has_nothing_stale(self):
        from zebamp import i18n
        english = i18n.load_catalog("en")
        texts = translatable_texts()
        self.assertGreater(len(texts), 500)
        self.assertEqual(sorted(set(texts) - set(english)), [], "texts without an English translation")
        self.assertEqual(sorted(set(english) - set(texts)), [], "translations of texts that no longer exist")

    def test_translations_keep_placeholders_and_layout(self):
        import re
        from zebamp import i18n
        placeholder = re.compile(r"\{[^{}]*\}")
        for spanish, english in i18n.load_catalog("en").items():
            self.assertEqual(sorted(placeholder.findall(spanish)), sorted(placeholder.findall(english)), spanish)
            # menu shortcuts after a tab, and the spaces/newlines texts are glued with
            self.assertEqual(spanish.count("\t"), english.count("\t"), spanish)
            lead = len(spanish) - len(spanish.lstrip())
            trail = len(spanish) - len(spanish.rstrip())
            self.assertEqual(spanish[:lead], english[:lead], spanish)
            self.assertEqual(spanish[len(spanish) - trail:], english[len(english) - trail:], spanish)
            english.format(*range(5))                    # must be a valid template

    def test_english_help_matches_the_spanish_one(self):
        import re
        from zebamp.ui import help as spanish
        from zebamp.ui import help_en as english
        self.assertEqual([k for k, _t, _b in english.SECTIONS], [k for k, _t, _b in spanish.SECTIONS])
        link = re.compile(r"href=[\"']#([\w-]+)")
        shortcut = re.compile(r"<kbd>([^<]+)</kbd>")
        same_everywhere = re.compile(r"^(Ctrl|Alt|Shift|Super|F\d|[A-Z/]$|[←→↑↓…])")
        for (key, title, body), (_k, _t, spanish_body) in zip(english.SECTIONS, spanish.SECTIONS):
            self.assertTrue(title and body.strip(), key)
            self.assertEqual(sorted(link.findall(body)), sorted(link.findall(spanish_body)), key)
            # the same shortcuts are documented (key names such as Supr/Del differ by language)
            def keys(text):
                found = [k.replace("Supr", "Del") for k in shortcut.findall(text)]
                return sorted(k for k in found if same_everywhere.match(k))
            self.assertEqual(keys(body), keys(spanish_body), key)
            self.assertNotRegex(body, r"[áéíóúñ¿¡«»]", key)      # no Spanish left behind

    def test_language_choice(self):
        from zebamp import i18n
        self.assertEqual(i18n.pick_language("es"), "es")
        self.assertEqual(i18n.pick_language("en"), "en")
        self.assertEqual(i18n.pick_language("klingon"), "es")          # unknown setting: the source language
        self.assertEqual(i18n.pick_language("auto", {"LANG": "es_DO.UTF-8"}), "es")
        self.assertEqual(i18n.pick_language("auto", {"LANG": "en_US.UTF-8"}), "en")
        self.assertEqual(i18n.pick_language("auto", {"LANG": "fr_FR.UTF-8"}), "en")
        self.assertEqual(i18n.pick_language("auto", {"LC_ALL": "es_ES", "LANG": "en_US"}), "es")
        self.assertEqual(i18n.pick_language("auto", {}), "en")

    def test_tr_and_numbers_follow_the_language(self):
        from zebamp import i18n
        self.addCleanup(i18n.setup, "es")
        self.assertEqual(i18n.tr("Reproducir"), "Reproducir")
        self.assertEqual(i18n.number(1234567), "1.234.567")
        self.assertEqual(i18n.setup("en"), "en")
        self.assertEqual(i18n.tr("Reproducir"), "Play")
        self.assertEqual(i18n.tr("texto sin traducir"), "texto sin traducir")
        self.assertEqual(i18n.number(1234567), "1,234,567")
        self.assertEqual(i18n.load_catalog("zz"), {})                  # missing file: Spanish, no error

    def test_english_interface_builds_every_menu_and_window(self):
        """Tables are translated when modules are imported, so English needs
        its own process -- exactly how `zebamp --lang en` starts."""
        code = r"""
import argparse, os, sys, tempfile
home = tempfile.mkdtemp(prefix="zebamp-en-")
os.environ.update(ZEBAMP_TESTING="1", QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=home + "/c",
                  XDG_CACHE_HOME=home + "/k", XDG_DATA_HOME=home + "/d")
from zebamp import i18n
assert i18n.setup("en") == "en"
from PySide6.QtWidgets import QApplication
qapp = QApplication([])
from zebamp.app import ZebampApp
app = ZebampApp(qapp, argparse.Namespace(host=home + "/nosock", port=0, skin=None, debug=False, files=[]))
menu = app.build_main_menu()
labels = []
def walk(m):
    for a in m.actions():
        labels.append(a.text())
        if a.menu() is not None:
            walk(a.menu())
walk(menu)
for wanted in ("Play file…", "Playlist", "Options", "Sleep timer", "Language", "Quit", "Media library"):
    assert wanted in labels, (wanted, labels[:40])
spanish = [t for t in labels if t in ("Reproducir", "Opciones", "Salir", "Lista de reproducción")]
assert not spanish, spanish
from zebamp.smartlist import FIELDS, describe
assert FIELDS["genre"] == "Genre"
rule = {"field": "rating", "op": "ge", "value": 4.0}
assert describe({"match": "all", "rules": [rule]}) == "Rating (stars) at least 4"
from zebamp.ui.dialogs import PreferencesDialog
from zebamp.ui.help import HelpWindow, sections
from zebamp.ui.library import LibraryWindow
from zebamp.ui.smartlist_dialog import SmartListDialog
prefs = PreferencesDialog(app)
assert prefs.windowTitle() == "Zebamp Preferences"
lib = LibraryWindow(app); SmartListDialog(app); HelpWindow(app)
assert sections()[0][1] == "Welcome", sections()[0][1]
assert app.art_panel.title == "ALBUM ART"
app.toggle_art_panel(); app.toggle_lyrics_panel()
for panel in app.panels():
    panel.grab()                                  # paints every classic window
print("english ok", flush=True)
os._exit(0)
"""
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                                cwd=REPO, env=env)
        self.assertIn("english ok", result.stdout, result.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
