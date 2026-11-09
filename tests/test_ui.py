"""UI interaction tests: real mouse/keyboard events against a private MPD."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

QAPP = QApplication.instance() or QApplication([])

from test_core import _start_mpd


def wait(ms=300):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@unittest.skipUnless(shutil.which("mpd") and shutil.which("mpc"), "mpd not installed")
class TestClassicUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="zebamp-ui-")
        cls.conf = _start_mpd(cls.tmp)
        subprocess.run(["mpc", "-h", f"{cls.tmp}/sock", "-q", "add", "A"])
        os.environ["XDG_CONFIG_HOME"] = os.path.join(cls.tmp, "cfg")
        os.environ["XDG_DATA_HOME"] = os.path.join(cls.tmp, "data")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["mpd", "--kill", cls.conf], capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_interactions(self):
        import importlib
        import zebamp.config
        importlib.reload(zebamp.config)
        import zebamp.app
        importlib.reload(zebamp.app)
        args = argparse.Namespace(host=f"{self.tmp}/sock", port=0, skin=None, debug=False, files=[])
        app = zebamp.app.ZebampApp(QAPP, args)
        app.show()
        wait(500)
        pl = app.player
        pl.set_volume(70)
        wait()
        fails = []

        def check(name, cond):
            if not cond:
                fails.append(name)
        try:
            mp = app.main_panel
            def click(panel, x, y, dbl=False):
                s = app.scale
                if dbl: QTest.mouseDClick(panel, Qt.MouseButton.LeftButton, pos=QPoint(x*s+1, y*s+1))
                else: QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=QPoint(x*s+1, y*s+1))
                wait()
            click(mp, 45, 95); check("play button", pl.state == "play")
            click(mp, 68, 95); check("pause button", pl.state == "pause")
            click(mp, 68, 95); check("pause again resumes", pl.state == "play")
            click(mp, 114, 95); wait(); check("next button", pl.current_pos >= 1)
            click(mp, 90, 95); check("stop button", pl.state == "stop")
            r0 = pl.random; click(mp, 180, 95); check("shuffle toggles", pl.random != r0); click(mp, 180, 95)
            # volume drag to the far left then right
            QTest.mousePress(mp, Qt.MouseButton.LeftButton, pos=QPoint(110, 63))
            QTest.mouseMove(mp, QPoint(108, 63))
            QTest.mouseRelease(mp, Qt.MouseButton.LeftButton, pos=QPoint(108, 63))
            wait(400)
            check("volume to 0", pl.volume <= 3)
            QTest.mousePress(mp, Qt.MouseButton.LeftButton, pos=QPoint(170, 63))
            QTest.mouseRelease(mp, Qt.MouseButton.LeftButton, pos=QPoint(170, 63))
            wait(400)
            check("volume to max", pl.volume >= 95)
            pl.set_volume(70); wait(200)
            eqv = app.cfg["show_eq"]
            click(mp, 225, 62)
            check("EQ toggle hides/shows", app.cfg["show_eq"] != eqv)
            click(mp, 225, 62)
            # playlist: double click 3rd row plays it
            pp = app.pl_panel; r = pp.list_rect()
            click(pp, r.x() + 20, r.y() + 2 + 2 * pp.row_h + 3, dbl=True)
            wait()
            check("playlist dblclick plays row 3", pl.current_pos == 2 and pl.state == "play")
            # time toggle
            tm = app.cfg["time_remaining"]
            click(mp, 60, 30)
            check("time mode toggles", app.cfg["time_remaining"] != tm)
            click(mp, 60, 30)
            # keyboard
            QTest.keyClick(app.shell, Qt.Key.Key_V); wait(); check("key V stops", pl.state == "stop")
            QTest.keyClick(app.shell, Qt.Key.Key_X); wait(); check("key X plays", pl.state == "play")
            QTest.keyClick(app.shell, Qt.Key.Key_C); wait(); check("key C pauses", pl.state == "pause")
            QTest.keyClick(app.shell, Qt.Key.Key_V); wait()
            # shade via double click title
            click(mp, 120, 6, dbl=True)
            check("dblclick title shades", app.cfg["main_shade"])
            click(mp, 120, 6, dbl=True)
            check("unshade", not app.cfg["main_shade"])
            # file info is non-modal: it must survive garbage collection
            import gc
            pl.play(0)
            wait()
            app.show_file_info()
            gc.collect()
            wait(600)
            check("file info window alive", any(w.isVisible() for w in getattr(app, "_windows", [])))
        finally:
            pl.stop()
            wait()
            app.quit()
        self.assertEqual(fails, [])


if __name__ == "__main__":
    unittest.main()
