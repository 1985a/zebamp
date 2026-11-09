"""Tests for: vector skin, Scale2x/3x, MAKI division, vis pacing, search query,
fifo sharing detection, notifications key, docking of modern containers."""
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
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

QAPP = QApplication.instance() or QApplication([])


class TestVectorSkin(unittest.TestCase):
    def test_sheets_at_resolution(self):
        from zebamp.skin import sprites as SP
        from zebamp.skin.zebamp_skin import zebamp_skin
        for res in (1, 2, 3):
            sk = zebamp_skin(res)
            self.assertEqual(sk.res, res)
            for sheet in ("MAIN", "CBUTTONS", "TITLEBAR", "EQMAIN", "PLEDIT", "TEXT"):
                w, _h = sk.sheet_size(sheet)
                self.assertGreater(w, 0)
                self.assertEqual(sk.sheet(sheet).width(), w * res)
            pm = sk.sprite("CBUTTONS", "PLAY")
            self.assertEqual(pm.width(), SP.S["CBUTTONS"]["PLAY"][2] * res)
            self.assertAlmostEqual(pm.devicePixelRatio(), res)
            # pixel() samples in classic coordinates
            self.assertTrue(sk.pixel("EQMAIN", 115, 294).isValid())
            self.assertTrue(sk.has_volume_thumb())


class TestPixelScale(unittest.TestCase):
    def test_scale2x_rounds_diagonal(self):
        from zebamp.skin.pixelscale import scale2x, scale3x, upscale
        a = np.array([[1, 0], [0, 1]], dtype=np.uint32) * 0xFFFFFFFF
        b = scale2x(a)
        self.assertEqual(b.shape, (4, 4))
        c = scale3x(np.zeros((3, 5), np.uint32))
        self.assertEqual(c.shape, (9, 15))
        img = QImage(7, 5, QImage.Format.Format_ARGB32)
        img.fill(0xFF336699)
        out = upscale(img, 3)
        self.assertEqual((out.width(), out.height()), (21, 15))
        self.assertEqual(out.pixel(10, 7), 0xFF336699)


class TestMakiDivision(unittest.TestCase):
    def test_int_division_is_real(self):
        from zebamp.modern.maki import VM, Var
        vm = VM(engine=None)

        class P:
            commands = [(1, 0), (1, 1), (67, None), (1, 2), (66, None), (1, 3), (64, None), (33, None)]
            vars = [Var("INT", 51), Var("INT", 255), Var("INT", 70), Var("INT", 5)]
            methods = []
            classes = []
            id = "t"
        stack = []
        vm._run(P, 0, stack)
        self.assertAlmostEqual(stack[-1].value, 51 / 255 * 70 + 5)


class TestVisPacing(unittest.TestCase):
    def test_window_advances_between_bursts(self):
        from zebamp.vis import FifoReader
        r = FifoReader("/nonexistent", "44100:16:2", keep=1024)
        r._push(np.arange(4096, dtype=np.float32))
        r.resync()
        t = 100.0
        w1 = r.window(t).copy()
        # one burst of 1000 samples arrives; successive frames must differ
        r._push(np.arange(4096, 5096, dtype=np.float32))
        w2 = r.window(t + 0.008).copy()
        w3 = r.window(t + 0.016).copy()
        self.assertFalse(np.array_equal(w2, w3))
        self.assertGreaterEqual(w3[-1], w2[-1])
        self.assertLessEqual(w3[-1], 5095)
        self.assertEqual(len(w1), 1024)


class TestFifoReaders(unittest.TestCase):
    def test_detects_other_reader(self):
        import subprocess
        from zebamp.vis import fifo_other_readers
        d = tempfile.mkdtemp()
        f = os.path.join(d, "x.fifo")
        os.mkfifo(f)
        self.assertEqual(fifo_other_readers(f), [])
        pr = subprocess.Popen([sys.executable, "-c",
                               f"import os,time; os.open({f!r}, os.O_RDONLY|os.O_NONBLOCK); time.sleep(5)"])
        try:
            for _ in range(50):
                if fifo_other_readers(f):
                    break
                time.sleep(0.05)
            self.assertTrue(fifo_other_readers(f))
        finally:
            pr.kill()
            pr.wait()


class TestSearchQuery(unittest.TestCase):
    def test_query(self):
        from zebamp.ui.dialogs import SearchLibraryDialog
        q = SearchLibraryDialog.build_query
        self.assertEqual(q("abc"), '(any contains "abc")')
        self.assertEqual(q("a b", "file"), '((file contains "a") AND (file contains "b"))')
        self.assertIn('\\"', q('x"y'))
        self.assertIsNone(q("   "))


class TestRebrand(unittest.TestCase):
    def test_rebrand(self):
        from zebamp.modern.gui import rebrand
        self.assertEqual(rebrand("WINAMP"), "ZEBAMP")
        self.assertEqual(rebrand("Winamp Library"), "Zebamp Library")
        self.assertEqual(rebrand("winamp5"), "winamp5")


if __name__ == "__main__":
    unittest.main()


class TestLibraryIndex(unittest.TestCase):
    def test_search_and_narrowing(self):
        from zebamp import libindex
        idx = libindex.LibraryIndex.__new__(libindex.LibraryIndex)
        rows = [["a/Canción de amor.mp3", "Canción de amor", "Ana", "Uno", "", "Pop", "200"],
                ["b/Love you.flac", "Love You", "Bob", "Dos", "", "Rock", "180"],
                ["c/Lovely.ogg", "Lovely", "Cleo", "Tres", "", "Pop", "150"]]
        idx.rows = rows
        idx.hay = [libindex._hay(r) for r in rows]
        idx._last_q = None
        self.assertEqual(idx.search("cancion"), [0])          # accents ignored
        self.assertEqual(idx.search("lo"), [1, 2])
        self.assertEqual(idx.search("love"), [1, 2])           # narrowed from "lo"
        self.assertEqual(idx.search("love bob"), [1])
        self.assertEqual(idx.search("pop"), [0, 2])            # full rescan
        self.assertEqual(idx.search("zz"), [])


class TestSupersampledUpscale(unittest.TestCase):
    def test_aa_sizes(self):
        from zebamp.skin.pixelscale import upscale
        img = QImage(9, 7, QImage.Format.Format_ARGB32)
        img.fill(0x00000000)
        for x in range(9):
            img.setPixel(x, x * 6 // 8, 0xFFFFFFFF)
        for k in (2, 3, 4):
            out = upscale(img, k)
            self.assertEqual((out.width(), out.height()), (9 * k, 7 * k))
        out = upscale(img, 3)
        alphas = {(out.pixel(x, y) >> 24) for x in range(27) for y in range(21)}
        self.assertTrue(any(0 < a < 255 for a in alphas))   # antialiased edges


class TestNewFeatures(unittest.TestCase):
    def test_gamma(self):
        from PySide6.QtGui import QColor
        from zebamp.modern.skin import apply_gamma_color, apply_gamma_image
        self.assertLess(apply_gamma_color(QColor(255, 255, 255), (-3897, -3774, -2394, 0, 0)).red(), 20)
        self.assertEqual(apply_gamma_color(QColor(0, 0, 0), (4095, 4095, 4095, 0, 1)).red(), 254)
        img = QImage(4, 4, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(200, 100, 50))
        out = apply_gamma_image(img, (0, 0, 0, 1, 0))         # grayscale
        c = QColor(out.pixel(1, 1))
        self.assertEqual(c.red(), c.green())

    def test_playlist_file(self):
        from zebamp.player import read_playlist_file
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.pls")
        with open(p, "w") as fh:
            fh.write("[playlist]\nFile1=a.mp3\nTitle1=A\nFile2=http://r/s\nNumberOfEntries=2\n")
        self.assertEqual(read_playlist_file(p), [os.path.join(d, "a.mp3"), "http://r/s"])
        m = os.path.join(d, "y.m3u")
        with open(m, "w") as fh:
            fh.write("#EXTM3U\n#EXTINF:1,x\n/abs/b.flac\nsub/c.ogg\n")
        self.assertEqual(read_playlist_file(m), ["/abs/b.flac", os.path.join(d, "sub/c.ogg")])

    def test_tagedit_roundtrip(self):
        import shutil
        import subprocess
        from zebamp import tagedit
        if not tagedit.available() or not shutil.which("ffmpeg"):
            self.skipTest("mutagen/ffmpeg missing")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "t.flac")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", p], check=True)
        tagedit.write_tags(p, {"title": "Hola", "genre": "A; B"})
        self.assertEqual(tagedit.read_tags(p)["genre"], "A; B")
        tagedit.write_tags(p, {"genre": ""})
        self.assertNotIn("genre", tagedit.read_tags(p))

    def test_stats_rating_scale(self):
        from zebamp.stats import Stats
        st = Stats.__new__(Stats)
        st.ratings = {"a": 10, "b": 7, "c": 1}
        self.assertEqual([st.rating(x) for x in "abcd"], [5, 4, 1, 0])

    def test_lrc(self):
        from zebamp.lyricsync import parse_lrc, song_query
        self.assertEqual(parse_lrc("[00:01.50]hola\n[01:02]adios")[0], [(1.5, "hola"), (62.0, "adios")])
        self.assertEqual(song_query({"title": "Art - Song"})[:2], ("Art", "Song"))


class TestConfigPersistence(unittest.TestCase):
    def test_keeps_skin_state_and_unknown_keys(self):
        from zebamp.config import Config
        d = tempfile.mkdtemp()
        p = os.path.join(d, "config.json")
        c = Config(p)
        c["modern_store"] = {"priv:winamp5|draweropen": "1"}
        c["modern_positions"] = {"/x": {"main": [1, 2]}}
        c["some_future_key"] = 42
        c.save()
        c2 = Config(p)
        self.assertEqual(c2["modern_store"], {"priv:winamp5|draweropen": "1"})
        self.assertEqual(c2["modern_positions"], {"/x": {"main": [1, 2]}})
        self.assertEqual(c2.get("some_future_key"), 42)


class DragFrameTest(unittest.TestCase):
    def test_click_is_not_drag_and_stale_events_translated(self):
        from PySide6.QtCore import QPointF
        from zebamp.canvas import DragFrame
        f = DragFrame(QPointF(100, 10))
        f.fix(QPointF(102, 11))
        self.assertFalse(f.moved)                 # jitter: still a click
        f.fix(QPointF(110, 10))
        self.assertTrue(f.moved)
        f.shift(1920, 0)                          # canvas moved 1920 px left
        p = f.fix(QPointF(114, 10))               # queued event, old frame
        self.assertEqual((p.x(), p.y()), (2034, 10))
        p = f.fix(QPointF(2040, 10))              # new frame
        self.assertEqual((p.x(), p.y()), (2040, 10))


class HelpTest(unittest.TestCase):
    def test_links_and_context_targets_exist(self):
        import re
        from zebamp.ui import help as H
        keys = {k for k, _t, _h in H.SECTIONS}
        for k, _t, body in H.SECTIONS:
            for target in re.findall(r"href=[\"']#([\w-]+)", body):
                self.assertIn(target, keys, f"broken link #{target} in section {k}")
        self.assertTrue(set(H.CONTEXT.values()) <= keys)
        import zebamp.milkdrop as md
        import zebamp.ui.dialogs as dl
        import zebamp.ui.library as lib
        import zebamp.ui.lyrics as ly
        import zebamp.ui.milkdrop_config as mc
        import zebamp.ui.radio as ra
        mods = (md, dl, lib, ly, mc, ra)
        for cls in H.CONTEXT:
            self.assertTrue(any(hasattr(m, cls) for m in mods), cls)


class ReachesMonitorTest(unittest.TestCase):
    def test_only_when_touching_an_uncovered_monitor(self):
        from PySide6.QtCore import QRect
        from zebamp.canvas import reaches_other_monitor
        canvas = QRect(0, 0, 2560, 1417)                   # right monitor
        screens = [QRect(0, 0, 2560, 1417), QRect(-1920, 0, 1920, 1057)]
        self.assertFalse(reaches_other_monitor([QRect(500, 300, 550, 232)], canvas, screens))
        self.assertFalse(reaches_other_monitor([QRect(2300, 300, 550, 232)], canvas, screens))  # outer edge
        self.assertTrue(reaches_other_monitor([QRect(-5, 300, 550, 232)], canvas, screens))


class FollowBottomEdgesTest(unittest.TestCase):
    def test_shading_drags_the_stack_below(self):
        from PySide6.QtCore import QRect
        from zebamp.canvas import follow_bottom_edges
        rects = {"main": QRect(0, 0, 275, 116), "pl": QRect(0, 116, 275, 203),
                 "ly": QRect(0, 319, 275, 174), "apart": QRect(400, 116, 275, 100)}
        # main shaded (116 -> 14): playlist and lyrics move up 102, the loose one stays
        self.assertEqual(follow_bottom_edges(rects, {"main": 14}), {"pl": -102, "ly": -102})
        # playlist grows by 29: only the lyrics below it move
        self.assertEqual(follow_bottom_edges(rects, {"pl": 232}), {"ly": 29})
        self.assertEqual(follow_bottom_edges(rects, {}), {})


class MpdConfTargetTest(unittest.TestCase):
    def test_target_preferred_sink_as_fallback(self):
        from unittest import mock

        from zebamp.audio import pipewire as pw
        d = tempfile.mkdtemp()
        conf = os.path.join(d, "mpd", "mpd.conf")
        os.makedirs(os.path.dirname(conf))
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}), \
                mock.patch.object(os.path, "expanduser", lambda p: d if p == "~" else p):
            with open(conf, "w") as fh:
                fh.write('audio_output {\n type "pipewire"\n name "p"\n target "duck"\n}\n')
            self.assertEqual(pw.mpd_conf_sink(), "duck")
            with open(conf, "w") as fh:          # old configs: pulse-style "sink"
                fh.write('audio_output {\n type "pipewire"\n sink "old"\n}\n# target "x"\n')
            self.assertEqual(pw.mpd_conf_sink(), "old")


class DeadEndSinkTest(unittest.TestCase):
    def test_null_sink_is_never_a_target(self):
        from zebamp.audio import pipewire as pw
        node = lambda i, name, factory: {"id": i, "type": "PipeWire:Interface:Node",
                                         "info": {"props": {"node.name": name, "factory.name": factory}}}
        dump = [node(1, "duck", "support.null-audio-sink"), node(2, "card", "api.alsa.pcm.sink")]
        self.assertTrue(pw.is_dead_end(dump, "duck"))
        self.assertFalse(pw.is_dead_end(dump, "card"))
        self.assertFalse(pw.is_dead_end(dump, "missing"))
