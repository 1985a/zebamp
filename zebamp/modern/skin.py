"""Loads a Winamp 3/5 modern skin (.wal archive or folder)."""
from __future__ import annotations

import logging
import os
import posixpath
import zipfile

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFontDatabase, QImage, QPixmap

from .xmlparse import Node, parse
from ..i18n import tr

log = logging.getLogger(__name__)


class Vfs:
    """Case-insensitive read-only view of a zip archive or folder."""

    def __init__(self, path: str):
        self.path = path
        self.files: dict[str, str] = {}
        self.zip = None
        if os.path.isdir(path):
            for root, _d, files in os.walk(path):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, path).replace(os.sep, "/")
                    self.files[rel.lower()] = full
        else:
            self.zip = zipfile.ZipFile(path)
            names = self.zip.namelist()
            # Some archives wrap everything in a single top folder.
            prefix = ""
            if not any(n.lower() == "skin.xml" for n in names):
                for n in names:
                    if n.lower().endswith("/skin.xml") and n.count("/") == 1:
                        prefix = n[: n.index("/") + 1]
                        break
            for n in names:
                if n.endswith("/"):
                    continue
                rel = n[len(prefix):] if prefix and n.startswith(prefix) else n
                self.files[rel.replace("\\", "/").lower()] = n

    @staticmethod
    def norm(p: str) -> str:
        p = p.replace("\\", "/").strip()
        p = posixpath.normpath(p) if p else p
        return p.lstrip("./").lower() if p not in (".", "") else ""

    def exists(self, p: str) -> bool:
        return self.norm(p) in self.files

    def read(self, p: str) -> bytes | None:
        key = self.files.get(self.norm(p))
        if key is None:
            return None
        try:
            if self.zip is not None:
                return self.zip.read(key)
            with open(key, "rb") as fh:
                return fh.read()
        except (OSError, KeyError, zipfile.BadZipFile):
            return None

    def text(self, p: str) -> str | None:
        d = self.read(p)
        if d is None:
            return None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return d.decode(enc)
            except UnicodeDecodeError:
                continue
        return None

    def close(self):
        if self.zip is not None:
            self.zip.close()


class BitmapDef:
    __slots__ = ("file", "gamma", "h", "id", "src_dir", "w", "x", "y")

    def __init__(self, node: Node):
        self.id = node.get("id", "")
        self.file = node.get("file", "")
        self.src_dir = node.src_dir
        self.x = _int(node.get("x"), 0)
        self.y = _int(node.get("y"), 0)
        self.w = _int(node.get("w"), -1)
        self.h = _int(node.get("h"), -1)
        self.gamma = (node.get("gammagroup") or "").strip().lower()


class BitmapFont:
    def __init__(self, image: QImage, cw: int, ch: int, hs: int, vs: int):
        self.image = image
        self.cw, self.ch, self.hs, self.vs = cw, ch, hs, vs
        self._glyphs: dict[str, QPixmap] = {}

    def glyph(self, c: str) -> QPixmap:
        from ..skin.sprites import FONT_LOOKUP
        pm = self._glyphs.get(c)
        if pm is None:
            pos = FONT_LOOKUP.get(c) or FONT_LOOKUP.get(c.lower()) or FONT_LOOKUP[" "]
            r, col = pos
            pm = QPixmap.fromImage(self.image.copy(col * self.cw, r * self.ch, self.cw, self.ch))
            self._glyphs[c] = pm
        return pm


def _int(v, default=0) -> int:
    if v is None or v == "":
        return default
    try:
        return int(float(str(v).strip()))
    except ValueError:
        return default


def parse_color(v: str | None, colors: dict | None = None) -> QColor | None:
    if not v:
        return None
    v = v.strip()
    if colors is not None and v.lower() in colors:
        return colors[v.lower()]
    if v.startswith("#"):
        c = QColor(v)
        return c if c.isValid() else None
    parts = [p for p in v.replace(";", ",").split(",") if p.strip()]
    try:
        nums = [max(0, min(255, int(float(p)))) for p in parts]
    except ValueError:
        c = QColor(v)
        return c if c.isValid() else None
    if len(nums) >= 3:
        return QColor(nums[0], nums[1], nums[2], nums[3] if len(nums) > 3 else 255)
    return None


class ModernSkin:
    MAX_INCLUDE_DEPTH = 16

    def __init__(self, path: str, freeform: str | None = None):
        self.path = path
        self.vfs = Vfs(path)
        self.ff = Vfs(freeform) if freeform and os.path.isdir(freeform) else None
        self.bitmaps: dict[str, BitmapDef] = {}
        self.colors: dict[str, QColor] = {}
        self.fonts: dict[str, object] = {}     # id -> family name or BitmapFont
        self.groupdefs: dict[str, Node] = {}
        self.xuitags: dict[str, Node] = {}
        self.containers: list[Node] = []
        self.scripts: list[Node] = []           # global <script> nodes
        self.info: dict[str, str] = {}
        self._images: dict[str, QImage | None] = {}
        self._pix: dict[str, QPixmap | None] = {}
        self.base_colors: dict[str, QColor] = {}
        self.color_gamma: dict[str, str] = {}
        self.gammasets: dict[str, dict] = {}
        self.gamma_name: str | None = None
        self.tree: Node | None = None
        self.name = os.path.splitext(os.path.basename(path.rstrip("/")))[0]

    # ------------------------------------------------------------ loading
    def load(self) -> bool:
        text = self.vfs.text("skin.xml")
        if text is None:
            return False
        # Winamp 5 loads its "Freeform" library (standard frames, menus,
        # wasabi objects) first; the skin then overrides what it redefines.
        if self.ff is not None:
            entries = ["@ff/xml/wasabi/wasabi.xml"]
            subdirs = sorted({k.split("/")[1] for k in self.ff.files if k.startswith("xml/") and k.count("/") >= 2})
            for d in subdirs:
                if d not in ("wasabi",) and self.ff.exists(f"xml/{d}/{d}.xml"):
                    entries.append(f"@ff/xml/{d}/{d}.xml")
            for e in entries:
                try:
                    self._collect(self._load_file(e, depth=0, seen=set()))
                except Exception as ex:
                    log.warning("freeform %s: %s", e, ex)
            base_containers = len(self.containers)
        else:
            base_containers = 0
        self.tree = self._load_file("skin.xml", depth=0, seen=set())
        self._collect(self.tree, toplevel=True)
        return len(self.containers) > base_containers

    # paths starting with "@ff/" live in the Freeform library
    def _exists(self, rel: str) -> bool:
        if rel.startswith("@fs/"):
            return os.path.isfile(rel[4:])
        if rel.startswith("@ff/"):
            return self.ff is not None and self.ff.exists(rel[4:])
        return self.vfs.exists(rel)

    def _read(self, rel: str) -> bytes | None:
        if rel.startswith("@fs/"):
            try:
                with open(rel[4:], "rb") as fh:
                    return fh.read()
            except OSError:
                return None
        if rel.startswith("@ff/"):
            return self.ff.read(rel[4:]) if self.ff is not None else None
        return self.vfs.read(rel)

    def _text(self, rel: str) -> str | None:
        d = self._read(rel)
        if d is None:
            return None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return d.decode(enc)
            except UnicodeDecodeError:
                continue
        return None

    def _load_file(self, rel: str, depth: int, seen: set) -> Node:
        text = self._text(rel) or ""
        ff = rel.startswith("@ff/")
        src_dir = posixpath.dirname(Vfs.norm(rel[4:] if ff else rel))
        if ff:
            src_dir = "@ff/" + src_dir
        root = parse(text, src_dir)
        self._expand_includes(root, depth, seen | {rel.lower()})
        return root

    def _sibling(self, f: str) -> str | None:
        """"../Big Bento/x.png": Bento borrows art from its sibling skin."""
        base = self.path.rstrip("/")
        parent = os.path.dirname(base)
        rel = posixpath.normpath(f)
        if not rel.startswith("../"):
            return None
        target = os.path.normpath(os.path.join(base, rel))
        if not target.startswith(parent + os.sep):
            return None
        if os.path.isfile(target):
            return "@fs/" + target
        # case-insensitive match (skins are written on Windows)
        d, parts = parent, os.path.relpath(target, parent).split(os.sep)
        for part in parts:
            try:
                hit = next((e for e in os.listdir(d) if e.lower() == part.lower()), None)
            except OSError:
                return None
            if hit is None:
                return None
            d = os.path.join(d, hit)
        return "@fs/" + d if os.path.isfile(d) else None

    def _resolve(self, src_dir: str, f: str) -> str | None:
        f = f.replace("\\", "/").strip()
        if not f:
            return None
        if f.startswith("../") or "/../" in f:
            sib = self._sibling(f)
            if sib:
                return sib
        if src_dir.startswith("@ff/"):
            d = src_dir[4:]
            cands = [("@ff/" + posixpath.join(d, f)) if d else "@ff/" + f, "@ff/" + f, f]
        else:
            cands = [posixpath.join(src_dir, f) if src_dir else f, f, "@ff/" + f]
        for c in cands:
            if self._exists(c):
                return c
        # Freeform paths are often written relative to Winamp's folder
        # (e.g. "wacs/xml/..."): fall back to the longest matching suffix.
        if self.ff is not None:
            parts = Vfs.norm(f).split("/")
            for i in range(1, len(parts)):
                suf = "/".join(parts[i:])
                for k in self.ff.files:
                    if k == suf or k.endswith("/" + suf):
                        return "@ff/" + k
        return None

    def _expand_includes(self, node: Node, depth: int, seen: set):
        out = []
        for c in node.children:
            if c.tag == "include":
                f = c.get("file", "")
                rel = self._resolve(c.src_dir, f) if f else None
                if rel and depth < self.MAX_INCLUDE_DEPTH and rel.lower() not in seen:
                    sub = self._load_file(rel, depth + 1, seen)
                    for sc in sub.children:
                        sc.parent = node
                        out.append(sc)
                elif f:
                    log.debug("include not found: %s (from %s)", f, c.src_dir)
                continue
            self._expand_includes(c, depth, seen)
            out.append(c)
        node.children = out

    def _collect(self, node: Node, toplevel=False):
        for c in node.children:
            t = c.tag
            if t == "elements":
                self._collect_elements(c)
            elif t == "groupdef":
                gid = (c.get("id") or "").lower()
                if gid:
                    self.groupdefs[gid] = c
                xt = (c.get("xuitag") or "").lower()
                if xt:
                    self.xuitags[xt] = c
                # groupdefs may also carry <elements>
                for e in c.children:
                    if e.tag == "elements":
                        self._collect_elements(e)
            elif t == "container":
                self.containers.append(c)
                self._collect_nested(c)
            elif t == "scripts":
                for s in c.children:
                    if s.tag == "script":
                        self.scripts.append(s)
            elif t == "script" and node.tag in ("root", "wasabixml", "winampabstractionlayer"):
                self.scripts.append(c)
            elif t == "skininfo":
                for i in c.children:
                    self.info[i.tag] = ""
            elif t in ("wasabixml", "winampabstractionlayer", "root"):
                self._collect(c)
            elif t in ("bitmap", "color", "bitmapfont", "truetypefont"):
                self._collect_elements(Node("elements", children=[c]))
            elif t == "gammaset":
                name = c.get("id") or tr("Tema {0}").format(len(self.gammasets) + 1)
                groups = {}
                for g in c.children:
                    if g.tag != "gammagroup":
                        continue
                    vals = [_int(v.strip(), 0) for v in (g.get("value") or "0,0,0").split(",")[:3]]
                    vals += [0] * (3 - len(vals))
                    groups[(g.get("id") or "").strip().lower()] = (
                        vals[0], vals[1], vals[2], _int(g.get("gray"), 0), _int(g.get("boost"), 0))
                self.gammasets[name] = groups
            elif t in ("accelerators", "cursor", "elementalias"):
                pass

    def _collect_nested(self, node: Node):
        """groupdefs/elements may live inside containers and layouts too."""
        for c in node.children:
            if c.tag == "groupdef":
                gid = (c.get("id") or "").lower()
                if gid:
                    self.groupdefs[gid] = c
                xt = (c.get("xuitag") or "").lower()
                if xt:
                    self.xuitags[xt] = c
            elif c.tag == "elements":
                self._collect_elements(c)
            self._collect_nested(c)

    def _collect_elements(self, el: Node):
        for c in el.children:
            t = c.tag
            cid = (c.get("id") or "").lower()
            if not cid:
                continue
            if t == "bitmap":
                self.bitmaps[cid] = BitmapDef(c)
            elif t == "color":
                col = parse_color(c.get("value"))
                if col is not None:
                    self.colors[cid] = col
                    self.base_colors[cid] = QColor(col)
                    gg = (c.get("gammagroup") or "").strip().lower()
                    if gg:
                        self.color_gamma[cid] = gg
            elif t == "truetypefont":
                rel = self._resolve(c.src_dir, c.get("file", ""))
                data = self._read(rel) if rel else None
                if data:
                    fid = QFontDatabase.addApplicationFontFromData(data)
                    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                    if fams:
                        self.fonts[cid] = fams[0]
                elif c.get("file"):
                    # system font name, e.g. file="Arial"
                    self.fonts[cid] = os.path.splitext(c.get("file"))[0]
            elif t == "bitmapfont":
                rel = self._resolve(c.src_dir, c.get("file", ""))
                img = self._image(rel) if rel else None
                if img is not None:
                    self.fonts[cid] = BitmapFont(img, _int(c.get("charwidth"), 5),
                                                 _int(c.get("charheight"), 6),
                                                 _int(c.get("hspacing"), 0),
                                                 _int(c.get("vspacing"), 0))
            elif t in ("elementalias",):
                pass

    # ------------------------------------------------------------ images
    def _image(self, rel: str) -> QImage | None:
        key = rel.lower()
        if key in self._images:
            return self._images[key]
        img = None
        data = self._read(rel)
        if data:
            img = QImage.fromData(data)
            if img.isNull():
                from ..skin.classic import decode_image
                img = decode_image(data)
            elif img.format() != QImage.Format.Format_ARGB32_Premultiplied:
                img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self._images[key] = img
        return img

    def bitmap(self, bid: str | None) -> QPixmap | None:
        """Pixmap for a bitmap id (or a direct file name)."""
        if not bid:
            return None
        key = bid.lower()
        if key in self._pix:
            return self._pix[key]
        pm = None
        d = self.bitmaps.get(key)
        if d is not None:
            rel = self._resolve(d.src_dir, d.file) or self._resolve("", d.file)
            img = self._image(rel) if rel else None
            if img is not None:
                w = d.w if d.w > 0 else img.width() - d.x
                h = d.h if d.h > 0 else img.height() - d.y
                if d.x or d.y or w != img.width() or h != img.height():
                    img = img.copy(QRect(d.x, d.y, w, h))
                g = self._gamma(d.gamma)
                if g is not None:
                    img = apply_gamma_image(img, g)
                pm = QPixmap.fromImage(img)
        else:
            rel = self._resolve("", bid)
            img = self._image(rel) if rel else None
            if img is not None:
                pm = QPixmap.fromImage(img)
        if pm is not None and _is_brand(key):
            pm = _brand_pixmap(pm)
        self._pix[key] = pm
        return pm

    # --------------------------------------------------------- colour themes
    def _gamma(self, group: str):
        if not group or not self.gamma_name:
            return None
        g = self.gammasets.get(self.gamma_name, {}).get(group)
        if g is None or g == (0, 0, 0, 0, 0):
            return None
        return g

    def set_gamma(self, name: str | None):
        """Apply a <gammaset> (Winamp 5 colour theme)."""
        if name not in self.gammasets:
            name = None
        self.gamma_name = name
        self._pix.clear()
        for cid, base in self.base_colors.items():
            g = self._gamma(self.color_gamma.get(cid, ""))
            self.colors[cid] = apply_gamma_color(base, g) if g is not None else QColor(base)

    def default_gamma(self) -> str | None:
        if not self.gammasets:
            return None
        for n in self.gammasets:
            if n.lower() == "default":
                return n
        return next(iter(self.gammasets))

    def image_of(self, bid: str | None) -> QImage | None:
        pm = self.bitmap(bid)
        return pm.toImage() if pm is not None else None

    def color(self, v: str | None, default: QColor | None = None) -> QColor | None:
        c = parse_color(v, self.colors)
        return c if c is not None else default

    def script_data(self, node: Node) -> bytes | None:
        rel = self._resolve(node.src_dir, node.get("file", ""))
        return self._read(rel) if rel else None

    def preview(self) -> QPixmap | None:
        for cand in ("screenshot.png", "skinshot.png", "preview.png", "screenshot.jpg"):
            d = self.vfs.read(cand)
            if d:
                img = QImage.fromData(d)
                if not img.isNull():
                    return QPixmap.fromImage(img)
        return None


# ------------------------------------------------------------- branding
_BRAND_IDS = ("titlebar.text.winamp", "infocomp.branding")


def _is_brand(key: str) -> bool:
    return any(b in key for b in _BRAND_IDS)


def _brand_pixmap(pm: QPixmap) -> QPixmap:
    """Redraw a "WINAMP" wordmark bitmap as "ZEBAMP", in the original colours."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont, QFontMetricsF, QLinearGradient, QPainter
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    # dominant bright colours of the original lettering (top / bottom halves)
    def avg(y0, y1):
        r = g = b = n = 0
        for y in range(y0, y1):
            for x in range(0, w, max(1, w // 64)):
                c = QColor.fromRgba(img.pixel(x, y))
                if c.alpha() > 160 and c.value() > 90:
                    r += c.red()
                    g += c.green()
                    b += c.blue()
                    n += 1
        return QColor(r // n, g // n, b // n) if n else QColor(235, 235, 235)
    top, bot = avg(0, max(1, h // 2)), avg(h // 2, h)
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    text = "ZEBAMP"
    f = QFont("DejaVu Sans")
    f.setBold(True)
    size = h * 0.95
    while size > 4:
        f.setPixelSize(int(size))
        if QFontMetricsF(f).horizontalAdvance(text) <= w * 0.96:
            break
        size -= 0.5
    p.setFont(f)
    fm = QFontMetricsF(f)
    tw = fm.horizontalAdvance(text)
    x = (w - tw) / 2
    y = (h + fm.capHeight()) / 2
    if h >= 24:
        # big logo: shadow + vertical gradient like Winamp's wordmark
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(QRectF(x + 1.5, 0 + 1.5, tw, h), int(Qt.AlignmentFlag.AlignVCenter), text)
        g = QLinearGradient(0, y - fm.capHeight(), 0, y)
        g.setColorAt(0, top.lighter(130))
        g.setColorAt(1, bot)
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addText(x, y, f, text)
        p.fillPath(path, g)
    else:
        p.setPen(top)
        p.drawText(QRectF(0, 0, w, h), int(Qt.AlignmentFlag.AlignCenter), text)
    p.end()
    return QPixmap.fromImage(out)


# ---------------------------------------------------------- gamma (themes)
def _gamma_channels(arr, g):
    """Wasabi colour filter on float rgb arrays (0..255): optional grayscale,
    then each channel scaled by (4096 + value) / 4096, or with boost, pulled
    towards white by value / 4096."""
    import numpy as np
    r, gr, b, gray, boost = g
    if gray:
        if gray == 2:
            lum = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
        else:
            lum = arr[..., :3].mean(axis=-1)
        arr[..., 0] = arr[..., 1] = arr[..., 2] = lum
    for i, v in enumerate((r, gr, b)):
        ch = arr[..., i]
        if boost:
            ch += (255.0 - ch) * (v / 4096.0) if v >= 0 else ch * (v / 4096.0)
        else:
            ch *= (4096.0 + v) / 4096.0
        np.clip(ch, 0, 255, out=ch)
    return arr


def apply_gamma_image(img: QImage, g) -> QImage:
    import numpy as np
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = src.width(), src.height()
    a = np.frombuffer(src.constBits(), dtype=np.uint8, count=h * src.bytesPerLine())
    a = a.reshape(h, src.bytesPerLine())[:, :w * 4].reshape(h, w, 4).astype(np.float32)
    # memory order of ARGB32 on little endian: B, G, R, A
    rgb = a[..., [2, 1, 0]].copy()
    rgb = _gamma_channels(rgb, g)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[..., 0] = rgb[..., 2]
    out[..., 1] = rgb[..., 1]
    out[..., 2] = rgb[..., 0]
    out[..., 3] = a[..., 3]
    res = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
    return res.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def apply_gamma_color(c: QColor, g) -> QColor:
    import numpy as np
    arr = np.array([[c.red(), c.green(), c.blue()]], dtype=np.float32)
    arr = _gamma_channels(arr, g)
    return QColor(int(arr[0, 0]), int(arr[0, 1]), int(arr[0, 2]), c.alpha())
