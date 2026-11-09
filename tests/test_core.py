"""Core tests.  Run: python -m unittest discover -s tests

Tests that need MPD start a private instance (null output) in a temp dir, so
they never touch the user's MPD.
"""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from PySide6.QtWidgets import QApplication

QAPP = QApplication.instance() or QApplication([])

from zebamp.audio import eq as eqmod
from zebamp.audio import pipewire as pw
from zebamp.skin import classic
from zebamp.skin.default_skin import default_skin
from zebamp.ui.eqwin import spline
from zebamp.vis import Analyzer, VisRenderer

DL = os.path.expanduser("~/Downloads")


class TestParsers(unittest.TestCase):
    def test_ini(self):
        d = classic.parse_ini("[Text]\r\nNormal=#00FF00\nCurrent = FFFFFF ; c\n;x=1\nFont=\"Arial\"\n")
        self.assertEqual(d["text"]["normal"], "#00FF00")
        self.assertEqual(d["text"]["font"], "Arial")
        self.assertNotIn(";x", d["text"])

    def test_region(self):
        txt = ("[Normal]\nNumPoints=4, 3\nPointList=0,0, 275,0, 275,116, 0,116  1 1 2 2 3 3\n"
               "[Bad]\nNumPoints=2\nPointList=1,1,2,2\n")
        r = classic.parse_region(txt)
        self.assertEqual(len(r["normal"]), 2)
        self.assertEqual(r["normal"][0][2], (275, 116))
        self.assertNotIn("bad", r)

    def test_viscolors(self):
        cols = classic.parse_viscolors("0,0,0 // bg\n 255, 10 ,3\n300,1,1\n")
        self.assertEqual(cols[1].getRgb()[:3], (255, 10, 3))
        self.assertEqual(cols[2].red(), 255)  # clamped
        self.assertEqual(len(cols), 24)

    def test_bitmap_text(self):
        bt = classic.ClassicSkin.bitmap_text
        self.assertEqual(bt("Canción Á"), "Cancion A")
        self.assertEqual(bt("a–b"), "a-b")
        self.assertIsNone(bt("ノイズ"))


class TestSkins(unittest.TestCase):
    def test_default_complete(self):
        sk = default_skin()
        for sheet in ("MAIN", "CBUTTONS", "TITLEBAR", "PLEDIT", "EQMAIN", "GEN"):
            self.assertIsNotNone(sk.sheet(sheet))
        pm = sk.sprite("CBUTTONS", "PLAY")
        self.assertEqual((pm.width(), pm.height()), (23, 18))
        self.assertEqual(len(sk.viscolors), 24)

    def test_user_skins_load(self):
        files = [os.path.join(DL, f) for f in os.listdir(DL)] if os.path.isdir(DL) else []
        wsz = [f for f in files if f.lower().endswith(".wsz")]
        if not wsz:
            self.skipTest("no .wsz files")
        for f in wsz:
            sk = classic.load_classic(f, fallback=default_skin())
            self.assertFalse(sk.sprite("MAIN", "MAIN_WINDOW_BACKGROUND").isNull(), f)
            self.assertEqual(sk.volume_frame(27).height(), 13)
            for ch in "0123456789- ":
                self.assertFalse(sk.digit(ch).isNull(), (f, ch))

    def test_missing_sheet_falls_back(self):
        d = tempfile.mkdtemp()
        try:
            img = default_skin().sheet("MAIN")
            img.save(os.path.join(d, "MAIN.BMP"), "BMP")
            sk = classic.load_classic(d, fallback=default_skin())
            self.assertIsNotNone(sk.sheet("CBUTTONS"))
            self.assertTrue(classic.is_classic_skin(d))
        finally:
            shutil.rmtree(d)


class TestEq(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(eqmod.winamp_to_db(33), 0.0)
        self.assertEqual(eqmod.winamp_to_db(64), 12.0)
        self.assertEqual(eqmod.db_to_winamp(0), 33)

    def test_eqf_roundtrip(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "x.eqf")
            bands = [12, 6, 0, -6, -12, 3, -3, 1.5, -1.5, 0]
            eqmod.write_eqf(p, {"Test": {"bands": bands, "preamp": 2}})
            r = eqmod.read_eqf(p)["Test"]
            for a, b in zip(r["bands"], bands):
                self.assertAlmostEqual(a, b, delta=0.4)
        finally:
            shutil.rmtree(d)

    def test_builtin_presets(self):
        pr = eqmod.builtin_presets()
        self.assertIn("Rock", pr)
        self.assertEqual(len(pr["Rock"]["bands"]), 10)

    def test_spline_passes_points(self):
        xs = [0, 12, 24, 36]
        ys = [1.0, 5.0, 2.0, 8.0]
        out = spline(xs, ys, xs)
        for a, b in zip(out, ys):
            self.assertAlmostEqual(a, b, places=6)

    def test_pw_conf(self):
        conf = pw.eq_conf("sink_x", [1] * 10, -2)
        self.assertIn('target.object = "sink_x"', conf)
        self.assertEqual(conf.count("bq_peaking"), 10)


class TestVis(unittest.TestCase):
    def test_analyzer_sine(self):
        a = Analyzer()
        t = np.arange(2048) / 44100
        x = (0.05 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        for _ in range(3):
            a.process(x, thick=False)
        self.assertGreater(a.bars.max(), 6)
        peak_col = int(np.argmax(a.bars))
        self.assertTrue(20 < peak_col < 60, peak_col)

    def test_silence_decays(self):
        a = Analyzer()
        a.bars[:] = 16
        for _ in range(200):
            alive = a.decay(2)
        self.assertFalse(alive)

    def test_render_shapes(self):
        r = VisRenderer()
        r.set_colors(default_skin().viscolors)
        a = Analyzer()
        a.bars[:] = 8
        a.peaks[:] = 12
        cfg = {"vis_bands": "thick", "vis_coloring": "normal", "vis_peaks": True,
               "vis_osc_style": "lines"}
        for mode in ("spectrum", "oscilloscope"):
            for col in ("normal", "fire", "line"):
                cfg["vis_coloring"] = col
                img = r.render(76, 16, a, mode, cfg)
                self.assertEqual(img.shape, (16, 76))


def _start_mpd(tmp):
    music = os.path.join(tmp, "music", "A")
    os.makedirs(music)
    for i in range(12):
        # minimal valid WAV files (silence) are enough for queue tests
        path = os.path.join(music, f"{i:02d}.wav")
        n = 44100 * 4  # 4 s, long enough not to auto-advance during UI tests
        import struct
        with open(path, "wb") as fh:
            fh.write(b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt " +
                     struct.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16) +
                     b"data" + struct.pack("<I", n * 2) + b"\0" * (n * 2))
    conf = os.path.join(tmp, "mpd.conf")
    with open(conf, "w") as fh:
        fh.write(f'''music_directory "{tmp}/music"
playlist_directory "{tmp}"
db_file "{tmp}/db"
pid_file "{tmp}/pid"
log_file "{tmp}/log"
bind_to_address "{tmp}/sock"
audio_output {{
  type "null"
  name "null"
  mixer_type "software"
}}
''')
    subprocess.run(["mpd", conf], check=True, capture_output=True)
    for _ in range(50):
        if os.path.exists(f"{tmp}/sock"):
            break
        time.sleep(0.1)
    subprocess.run(["mpc", "-h", f"{tmp}/sock", "update", "--wait"], capture_output=True)
    return conf


@unittest.skipUnless(shutil.which("mpd") and shutil.which("mpc"), "mpd not installed")
class TestPlayerWithMpd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="zebamp-test-")
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
        p.conn.call("clear")
        p.conn.call("add", "A")
        p._pl_version = None
        p._refresh_queue()

    def files(self):
        return [s["file"] for s in self.player.conn.call("playlistinfo")]

    def sync(self):
        self.player._refresh_queue()
        self.assertEqual([s["file"] for s in self.player.queue], self.files())

    def test_delete_ranges(self):
        before = self.files()
        self.player.delete_positions([0, 1, 2, 5, 9, 11])
        expect = [f for i, f in enumerate(before) if i not in {0, 1, 2, 5, 9, 11}]
        self.assertEqual(self.files(), expect)
        self.sync()

    def test_crop(self):
        before = self.files()
        self.player.crop([3, 4, 7])
        self.assertEqual(self.files(), [before[3], before[4], before[7]])

    def test_apply_order_range_random(self):
        rnd = random.Random(42)
        for _ in range(30):
            q = self.player.conn.call("playlistinfo")
            ids = [s["id"] for s in q]
            n = len(ids)
            lo = rnd.randrange(n)
            hi = rnd.randrange(lo, n)
            seg = ids[lo:hi + 1]
            rnd.shuffle(seg)
            target = ids[:lo] + seg + ids[hi + 1:]
            self.player.apply_order_range(target, lo, hi)
            got = [s["id"] for s in self.player.conn.call("playlistinfo")]
            self.assertEqual(got, target)
            self.sync()

    def test_sort_and_reverse(self):
        self.player.reverse_queue()
        self.assertEqual(self.files(), sorted(self.files(), reverse=True))
        self.sync()
        self.player.sort_queue(lambda s: s["file"])
        self.assertEqual(self.files(), sorted(self.files()))
        self.sync()

    def test_plchanges_incremental(self):
        rnd = random.Random(7)
        for _ in range(25):
            op = rnd.choice(["del", "add", "move", "shuffle"])
            n = len(self.files())
            if op == "del" and n > 2:
                self.player.conn.call("delete", rnd.randrange(n))
            elif op == "add":
                self.player.conn.call("add", f"A/{rnd.randrange(12):02d}.wav")
            elif op == "move" and n > 1:
                self.player.conn.call("move", rnd.randrange(n), rnd.randrange(n))
            else:
                self.player.conn.call("shuffle")
            self.sync()

    def test_add_paths_inside_music_dir(self):
        self.player.music_directory = f"{self.tmp}/music"
        self.player.conn.call("clear")
        self.player.add_paths([f"{self.tmp}/music/A/03.wav"])
        self.assertEqual(self.files(), ["A/03.wav"])

    def test_move_selection_block(self):
        from zebamp.ui import plwin  # noqa: F401
        ids = [s["id"] for s in self.player.conn.call("playlistinfo")]
        # emulate PlaylistPanel.move_selection for rows 2 and 4 moved down by 3
        rows, delta = [2, 4], 3
        n = len(ids)
        new = [None] * n
        for r in rows:
            new[r + delta] = ids[r]
        rest = iter(i for k, i in enumerate(ids) if k not in rows)
        new = [x if x is not None else next(rest) for x in new]
        self.player.apply_order_range(new, min(rows), max(rows) + delta)
        self.assertEqual([s["id"] for s in self.player.conn.call("playlistinfo")], new)

    def test_repeat_cycle(self):
        p = self.player
        p.set_repeat_mode("off")
        p._refresh_status()
        p.toggle_repeat()
        p._refresh_status()
        self.assertTrue(p.repeat and not p.single)
        p.toggle_repeat()
        p._refresh_status()
        self.assertTrue(p.repeat and p.single)
        p.toggle_repeat()
        p._refresh_status()
        self.assertFalse(p.repeat or p.single)

    def test_bad_command_does_not_raise(self):
        self.assertEqual(self.player.conn.call("play", 9999, default="x"), "x")
        self.assertTrue(self.player.connected)
        self.assertFalse(self.player.conn.batch([("add", "no/such/file.wav")]))
        self.assertTrue(self.player.connected)


if __name__ == "__main__":
    unittest.main()
