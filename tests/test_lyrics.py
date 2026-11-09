"""Tests for lyrics: LRC parsing, source order, version choice, timing fixes."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zebamp import lyricsfind as F
from zebamp import lyricsync as S

LRC = """[ar:Artista]
[ti:Canción]
[length: 03:00]
[00:10.00]Primera
[00:20.50]Segunda <00:21.00>con <00:21.50>palabras
[00:30:25]Tercera (dos puntos)
[01:00.00][02:00.00]Estribillo
"""


class ParseTest(unittest.TestCase):
    def test_stamps_tags_and_repeats(self):
        lines, length = S.parse_lrc(LRC)
        self.assertEqual(length, 180.0)
        self.assertEqual([t for t, _ in lines], [10.0, 20.5, 30.25, 60.0, 120.0])
        self.assertEqual(lines[1][1], "Segunda con palabras")       # word stamps removed
        self.assertEqual(lines[4][1], "Estribillo")

    def test_offset_tag(self):
        lines, _ = S.parse_lrc("[offset:+500]\n[00:10.00]a\n[00:20.00]b\n[00:30.00]c")
        self.assertEqual(lines[0][0], 9.5)                           # positive = earlier

    def test_looks_synced(self):
        self.assertTrue(S.looks_synced(LRC))
        self.assertFalse(S.looks_synced("solo texto\nsin tiempos"))


class QueryTest(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(S.song_query({"artist": "A", "title": "T", "album": "B"}), ("A", "T", "B"))

    def test_stream_title(self):
        self.assertEqual(S.song_query({"title": "A - T", "file": "http://x"})[:2], ("A", "T"))

    def test_untagged_file_names(self):
        self.assertEqual(S.song_query({"file": "Musica/Queen - Bohemian Rhapsody.flac"})[:2],
                         ("Queen", "Bohemian Rhapsody"))
        # track number stripped, artist from Artist/Album/track
        self.assertEqual(S.song_query({"file": "Soda Stereo/Canción Animal/05 - Te hacen falta vitaminas.mp3"})[:2],
                         ("Soda Stereo", "Te hacen falta vitaminas"))


class ChooseTest(unittest.TestCase):
    def test_closest_duration_synced_preferred(self):
        hits = [
            {"id": 1, "duration": 150, "syncedLyrics": "x"},     # sped-up edit
            {"id": 2, "duration": 181, "syncedLyrics": "x"},     # our version
            {"id": 3, "duration": 180, "plainLyrics": "x"},      # exact length but unsynced
        ]
        self.assertEqual(F.choose_candidate(hits, 180)["id"], 2)
        self.assertIsNone(F.choose_candidate([{"id": 4}], 180))


class TimingTest(unittest.TestCase):
    def test_auto_speed_for_sped_up_release(self):
        t = S.auto_timing(lyrics_duration=200, song_duration=170)
        self.assertAlmostEqual(t.speed, 200 / 170)
        self.assertIn("velocidad", t.reason)
        # a few seconds apart: ambiguous, left alone but explained
        t = S.auto_timing(185, 180)
        self.assertEqual((t.speed, t.offset), (1.0, 0.0))
        self.assertIn("Mayús+clic", t.reason)
        self.assertEqual(S.auto_timing(None, 180).speed, 1.0)

    def test_one_tap_fixes_late_start(self):
        t = S.Timing()
        t.add_anchor(song_t=25.0, lyric_t=10.0)       # intro is 15 s longer here
        self.assertAlmostEqual(t.lyric_time(25.0), 10.0)
        self.assertAlmostEqual(t.song_time(60.0), 75.0)

    def test_two_taps_fix_speed_and_offset(self):
        t = S.Timing()
        # real relation: lyric = 1.2 * song - 6
        t.add_anchor(30.0, 1.2 * 30 - 6)
        t.add_anchor(120.0, 1.2 * 120 - 6)
        self.assertAlmostEqual(t.speed, 1.2, places=6)
        self.assertAlmostEqual(t.offset, -6.0, places=6)

    def test_bad_taps_rejected(self):
        t = S.Timing()
        t.add_anchor(30.0, 10.0)
        t.add_anchor(60.0, 200.0)                     # absurd: speed 6.3
        self.assertEqual(t.speed, 1.0)                 # falls back to offset only

    def test_shift_and_storage(self):
        t = S.Timing()
        t.shift(0.5)                                   # show lyrics later
        self.assertAlmostEqual(t.lyric_time(10.0), 9.5)
        path = os.path.join(tempfile.mkdtemp(), "sync.json")
        store = S.SyncStore(path)
        store.put("a.flac", t)
        self.assertAlmostEqual(S.SyncStore(path).get("a.flac").offset, -0.5)
        store.put("a.flac", None)
        self.assertIsNone(S.SyncStore(path).get("a.flac"))

    def test_current_line(self):
        lines = [(10.0, "a"), (20.0, "b"), (30.0, "c")]
        self.assertEqual([S.current_line(lines, t) for t in (5, 10, 25, 99)], [-1, 0, 1, 2])


class StateTest(unittest.TestCase):
    def test_state_follows_timing(self):
        lyr = S.Lyrics(lines=[(10.0, "a"), (20.0, "b"), (30.0, "c")], synced=True, source="x")
        st = S.LyricsState(uri="u", lyrics=lyr)
        self.assertEqual(st.line_at(21.0), 1)
        st.tap(0, song_t=25.0)                         # first line heard at 25 s
        self.assertEqual(st.line_at(26.0), 0)
        self.assertAlmostEqual(st.seek_target(2), 45.0)
        self.assertIn("sincronizada a mano", st.info())


class FindTest(unittest.TestCase):
    def setUp(self):
        self.music = tempfile.mkdtemp()

    def test_sidecar_lrc_wins(self):
        os.makedirs(os.path.join(self.music, "A"))
        with open(os.path.join(self.music, "A", "song.lrc"), "w") as fh:
            fh.write(LRC)
        with mock.patch.object(F, "http_json", side_effect=AssertionError("no network expected")):
            lyr = F.find_lyrics({"file": "A/song.flac", "title": "T"}, self.music, 180)
        self.assertTrue(lyr.synced)
        self.assertEqual(lyr.source, "archivo .lrc")

    def test_embedded_tags_via_mpd(self):
        client = mock.Mock()
        client.readcomments.return_value = {"LYRICS": "[00:01.00]a\n[00:02.00]b\n[00:03.00]c"}
        with mock.patch.object(F, "http_json", side_effect=AssertionError("no network expected")):
            lyr = F.find_lyrics({"file": "x.flac", "title": "T"}, None, 180, client=client)
        self.assertEqual(lyr.source, "etiquetas del archivo")
        self.assertTrue(lyr.synced)

    def test_not_found_is_cached(self):
        calls = []

        def fake(url, timeout=12):
            calls.append(url)
            if "/get?" in url:
                raise OSError("HTTP Error 404: Not Found")
            return []
        with mock.patch.object(F, "http_json", side_effect=fake):
            song = {"file": "z.flac", "artist": "Nadie", "title": "Sin letra"}
            self.assertFalse(F.find_lyrics(song, None, 100).found)
            n = len(calls)
            self.assertFalse(F.find_lyrics(song, None, 100).found)
        self.assertEqual(len(calls), n)                # second time: from cache

    def test_offline_is_reported(self):
        with mock.patch.object(F, "http_json", side_effect=OSError("Network is unreachable")), \
                self.assertRaises(F.LyricsUnavailable):
            F.find_lyrics({"file": "q.flac", "artist": "A", "title": "Q"}, None, 100)

    def test_picks_matching_version(self):
        def fake(url, timeout=12):
            if "/get?" in url:
                raise OSError("HTTP Error 404: Not Found")
            return [{"duration": 150, "syncedLyrics": "[00:01.00]rápida\n[00:02.00]b\n[00:03.00]c"},
                    {"duration": 200, "syncedLyrics": "[00:01.00]buena\n[00:02.00]b\n[00:03.00]c"}]
        with mock.patch.object(F, "http_json", side_effect=fake):
            lyr = F.find_lyrics({"file": "v.flac", "artist": "A", "title": "V"}, None, 199)
        self.assertEqual(lyr.lines[0][1], "buena")
        self.assertEqual(lyr.duration, 200)


    def test_malformed_remote_data(self):
        def fake(url, timeout=12):
            if "/get?" in url:
                return ["not", "a", "record"]
            return [42, {"duration": "??", "syncedLyrics": "[00:01.00]ok\n[00:02.00]b\n[00:03.00]c"}]
        with mock.patch.object(F, "http_json", side_effect=fake):
            lyr = F.find_lyrics({"file": "m.flac", "artist": "A", "title": "M"}, None, 100)
        self.assertEqual(lyr.lines[0][1], "ok")


if __name__ == "__main__":
    unittest.main()
