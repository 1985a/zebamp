"""Modern skin engine tests (XML parser, MAKI loader/VM, engine smoke tests)."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import glob
import os
import sys
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

QAPP = QApplication.instance() or QApplication([])

from zebamp.modern import maki
from zebamp.modern.xmlparse import parse

SKIN_DIRS = [os.environ.get("ZEBAMP_TEST_SKINS", ""),
             os.path.expanduser("~/.local/share/zebamp/skins")]


def wal_files():
    out = []
    for d in SKIN_DIRS:
        if d and os.path.isdir(d):
            out += glob.glob(os.path.join(d, "*.wal"))
            out += [os.path.dirname(x) for x in glob.glob(os.path.join(d, "*", "skin.xml"))]
    return out


class TestXml(unittest.TestCase):
    def test_malformed(self):
        txt = ('﻿<?xml version="1.0"?><WasabiXML><!-- c --><elements>'
               '<bitmap id="a" file="x & y.png" w=10 h="5"/>'
               '<bitmap id="b" file="z.png"></elements>'
               '<container id=main><layout id="normal"><layer id="l" image="a"/>'
               '</layout></containr></container><stray></nomatch>')
        root = parse(txt)
        wx = root.children[0]
        self.assertEqual(wx.tag, "wasabixml")
        el = wx.children[0]
        bm = list(el.iter("bitmap"))
        self.assertEqual(bm[0].get("file"), "x & y.png")
        self.assertEqual(bm[0].get("w"), "10")
        cont = list(root.iter("container"))
        self.assertEqual(len(cont), 1)
        self.assertEqual(cont[0].get("id"), "main")
        self.assertEqual(next(iter(cont[0].iter("layer"))).get("image"), "a")

    def test_entities_and_case(self):
        root = parse('<Text ID="t" Text="a &amp; b &#65;"/>')
        t = root.children[0]
        self.assertEqual(t.tag, "text")
        self.assertEqual(t.get("text"), "a & b A")


class TestMaki(unittest.TestCase):
    def test_guid_format(self):
        # System class GUID as stored in .maki files vs objects.json key
        self.assertEqual(maki.class_name(maki.format_guid("d6f50f6449b793fa66baf193983eaeef")),
                         "System")

    def test_method_lookup_inherits(self):
        g = maki._BY_NAME["Button"]
        arity, _res = maki.find_method(g, "show")   # from GuiObject
        self.assertEqual(arity, 0)
        self.assertIsNotNone(maki.find_method(g, "setactivated"))

    def test_all_scripts_parse(self):
        files = wal_files()
        if not files:
            self.skipTest("no .wal skins installed")
        n = 0
        for f in files:
            if os.path.isdir(f):
                for name in glob.glob(os.path.join(f, "**", "*.maki"), recursive=True):
                    with open(name, "rb") as fh:
                        p = maki.Program(fh.read(), name)
                    self.assertTrue(p.commands)
                    n += 1
                continue
            with zipfile.ZipFile(f) as z:
                for name in z.namelist():
                    if name.lower().endswith(".maki"):
                        p = maki.Program(z.read(name), name)
                        self.assertTrue(p.commands)
                        n += 1
        self.assertGreater(n, 0)

    def test_vm_never_raises(self):
        class Dummy:
            def maki_call(self, name, args):
                raise RuntimeError("boom")
        files = wal_files()
        if not files:
            self.skipTest("no .wal skins installed")
        vm = maki.VM(engine=None)
        files = [f for f in files if not os.path.isdir(f)]
        if not files:
            self.skipTest("no .wal archives")
        with zipfile.ZipFile(files[0]) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".maki"))
            prog = maki.Program(z.read(name), name)
        prog.vars[0].value = Dummy()
        vm.add(prog)
        # dispatching onscriptloaded on a hostile object must not raise
        vm.dispatch(prog.vars[0].value, "onscriptloaded")


@unittest.skipUnless(wal_files(), "no .wal skins installed")
class TestEngineSmoke(unittest.TestCase):
    """Loads every installed .wal against a stub app and paints each layout."""

    def test_load_and_paint(self):
        import argparse
        import tempfile
        from PySide6.QtGui import QImage, QPainter
        tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = tmp
        from zebamp.app import ZebampApp
        args = argparse.Namespace(host=os.path.join(tmp, "nosock"), port=0, skin=None,
                                  debug=False, files=[])
        app = ZebampApp(QAPP, args)
        try:
            for f in wal_files():
                self.assertTrue(app.load_skin(f, save=False, quiet=True), f)
                eng = app.modern
                eng.start()
                for c in eng.containers:
                    for lay in c.layouts:
                        img = QImage(max(1, lay.rect.width()), max(1, lay.rect.height()),
                                     QImage.Format.Format_ARGB32_Premultiplied)
                        p = QPainter(img)
                        lay.paint(p)
                        p.end()
                # simulate pressing every button: actions must not raise
                for c in eng.containers:
                    for lay in c.layouts:
                        for o in list(lay.walk()):
                            if type(o).__name__ == "Button" and (o.p("action") or "").lower() in (
                                    "switch", "toggle"):
                                o.click()
                app.use_default_skin()
        finally:
            app._stop_modern()
            app.player.shutdown()


if __name__ == "__main__":
    unittest.main()
