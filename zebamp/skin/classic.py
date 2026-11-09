"""Loader for classic Winamp skins (.wsz archives or unpacked folders)."""
from __future__ import annotations

import io
import logging
import os
import re
import struct
import unicodedata
import zipfile
from collections import Counter

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import (QColor, QCursor, QImage, QPainterPath,
                           QPixmap, QPolygonF)

from . import sprites as SP

log = logging.getLogger(__name__)

_INI_SECTION = re.compile(r"^\s*\[(.+?)\]\s*$")
_INI_PROP = re.compile(r"^\s*([^;=][^=]*?)\s*=\s*(.*?)\s*$")


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    section = None
    for line in re.split(r"[\r\n]+", text):
        m = _INI_SECTION.match(line)
        if m:
            section = m.group(1).strip().lower()
            data.setdefault(section, {})
            continue
        m = _INI_PROP.match(line)
        if m and section is not None:
            key = m.group(1).strip().lower()
            value = m.group(2).split("=")[0].strip().strip("\"'")
            data[section][key] = value
    return data


def parse_viscolors(text: str) -> list[QColor]:
    colors = [QColor(*c) for c in SP.DEFAULT_VISCOLORS]
    rx = re.compile(r"^\s*(\d+)\s*,?\s*(\d+)\s*,?\s*(\d+)")
    i = 0
    for line in text.splitlines():
        m = rx.match(line)
        if m and i < 24:
            r, g, b = (min(255, int(v)) for v in m.groups())
            colors[i] = QColor(r, g, b)
            i += 1
    return colors


def parse_region(text: str) -> dict[str, list[list[tuple[int, int]]]]:
    out = {}
    for section, props in parse_ini(text).items():
        counts = [c for c in re.split(r"\s*,\s*", props.get("numpoints", "")) if c]
        nums = [p for p in re.split(r"[\s,]+", props.get("pointlist", "")) if p]
        try:
            pts = [(int(float(nums[i])), int(float(nums[i + 1])))
                   for i in range(0, len(nums) - 1, 2)]
            idx = 0
            polys = []
            for c in counts:
                n = int(c)
                if n >= 3 and idx + n <= len(pts):
                    polys.append(pts[idx:idx + n])
                idx += n
        except ValueError:
            continue
        if polys:
            out[section] = polys
    return out


def _parse_color(value: str | None, default: str) -> QColor:
    if not value:
        return QColor(default)
    v = value.strip()
    if not v.startswith("#"):
        v = "#" + v
    c = QColor(v[:7])
    return c if c.isValid() else QColor(default)


def load_cursor(data: bytes) -> QCursor | None:
    """Load a Windows .cur file (first image) with its hotspot."""
    try:
        if data[:4] == b"RIFF":
            # Animated cursor (.ani): use its first frame.
            i = data.find(b"icon")
            if i < 0 or i + 8 > len(data):
                return None
            n = struct.unpack_from("<I", data, i + 4)[0]
            frame = data[i + 8:i + 8 + n]
            return load_cursor(frame) if frame[:4] != b"RIFF" else None
        _reserved, typ, count = struct.unpack_from("<HHH", data, 0)
        if typ != 2 or count < 1:
            return None
        _w, _h, _cc, _r, hx, hy, _size, _off = struct.unpack_from(
            "<BBBBHHII", data, 6)
        img = QImage.fromData(data, "CUR")
        if img.isNull():
            # A .cur is an .ico with type=2; present it as an icon instead.
            img = QImage.fromData(data[:2] + b"\x01\x00" + data[4:], "ICO")
        if img.isNull():
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(data[:2] + b"\x01\x00" + data[4:])).convert("RGBA")
                buf = io.BytesIO()
                im.save(buf, "PNG")
                img = QImage.fromData(buf.getvalue(), "PNG")
            except Exception:
                return None
        if img.isNull():
            return None
        return QCursor(QPixmap.fromImage(img), hx, hy)
    except Exception:
        return None


class SkinSource:
    """Case-insensitive file access to a skin archive or folder."""

    def __init__(self, path: str):
        self.path = path
        self._files: dict[str, str] = {}
        self._zip = None
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for f in files:
                    full = os.path.join(root, f)
                    self._files.setdefault(f.lower(), full)
        else:
            self._zip = zipfile.ZipFile(path)
            # Prefer files nearest to the archive root.
            names = sorted(self._zip.namelist(), key=lambda n: n.count("/"))
            for n in names:
                if n.endswith("/"):
                    continue
                base = n.replace("\\", "/").rsplit("/", 1)[-1].lower()
                self._files.setdefault(base, n)

    def names(self):
        return list(self._files)

    def read(self, name: str) -> bytes | None:
        key = self._files.get(name.lower())
        if key is None:
            return None
        try:
            if self._zip is not None:
                return self._zip.read(key)
            with open(key, "rb") as fh:
                return fh.read()
        except Exception as e:
            log.warning("cannot read %s from %s: %s", name, self.path, e)
            return None

    def find(self, base: str, exts=("bmp", "png")) -> bytes | None:
        for ext in exts:
            d = self.read(f"{base}.{ext}")
            if d is not None:
                return d
        return None

    def text(self, name: str) -> str | None:
        d = self.read(name)
        if d is None:
            return None
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return d.decode(enc)
            except UnicodeDecodeError:
                continue
        return None

    def close(self):
        if self._zip is not None:
            self._zip.close()


def decode_image(data: bytes) -> QImage | None:
    img = QImage.fromData(data)
    if img.isNull():
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGBA")
            buf = io.BytesIO()
            im.save(buf, "PNG")
            img = QImage.fromData(buf.getvalue(), "PNG")
        except Exception:
            return None
    if img.isNull():
        return None
    return img.convertToFormat(QImage.Format.Format_ARGB32)


class ClassicSkin:
    """A loaded classic skin.  Missing parts fall back to `fallback`."""

    def __init__(self, sheets: dict[str, QImage | None], *, name="",
                 path=None, fallback: ClassicSkin | None = None,
                 viscolors=None, pledit=None, region=None, cursors=None,
                 genex_colors=None, nums_ex=None, res: int = 1, text_colors=None):
        # `res`: sheets are drawn at res x the classic pixel size (vector skins
        # render at the screen zoom so they stay sharp).  Coordinates stay 1x.
        self.res = max(1, int(res))
        self.name = name
        self.path = path
        self.fallback = fallback
        self.sheets = sheets
        self.viscolors = viscolors or [QColor(*c) for c in SP.DEFAULT_VISCOLORS]
        self.pledit = pledit or {k: (QColor(v) if k != "font" else v)
                                 for k, v in SP.DEFAULT_PLEDIT.items()}
        self.region = region or {}
        self.cursors = cursors or {}
        self.genex_colors = genex_colors
        self._cache: dict = {}
        if nums_ex is None:
            nums_ex = sheets.get("NUMBERS") is None and sheets.get("NUMS_EX") is not None
        self.nums_ex = nums_ex
        self._font_glyphs: dict[str, QPixmap] = {}
        self.text_colors_hint = text_colors
        self.text_fg, self.text_bg = text_colors or self._text_colors()

    # -- raw access ---------------------------------------------------
    def _owner(self, sheet: str) -> ClassicSkin | None:
        if self.sheets.get(sheet) is not None:
            return self
        if self.fallback is not None:
            return self.fallback._owner(sheet)
        return None

    def sheet(self, sheet: str) -> QImage | None:
        o = self._owner(sheet)
        return o.sheets.get(sheet) if o is not None else None

    def sheet_res(self, sheet: str) -> int:
        o = self._owner(sheet)
        return o.res if o is not None else 1

    def sheet_size(self, sheet: str) -> tuple[int, int]:
        """Size of a sheet in classic (1x) pixels."""
        img = self.sheet(sheet)
        if img is None:
            return 0, 0
        k = self.sheet_res(sheet)
        return img.width() // k, img.height() // k

    def has_own(self, sheet: str) -> bool:
        return self.sheets.get(sheet) is not None

    def crop(self, sheet: str, rect) -> QPixmap:
        key = (sheet, rect)
        pm = self._cache.get(key)
        if pm is None:
            img = self.sheet(sheet)
            x, y, w, h = rect
            if img is None:
                pm = QPixmap(w, h)
                pm.fill(Qt.GlobalColor.transparent)
            else:
                k = self.sheet_res(sheet)
                pm = QPixmap.fromImage(img.copy(QRect(x * k, y * k, w * k, h * k)))
                if k > 1:
                    pm.setDevicePixelRatio(k)
            self._cache[key] = pm
        return pm

    def sprite(self, sheet: str, name: str) -> QPixmap:
        return self.crop(sheet, SP.S[sheet][name])

    def pixel(self, sheet: str, x: int, y: int) -> QColor:
        img = self.sheet(sheet)
        k = self.sheet_res(sheet)
        # sample the middle of the scaled pixel
        x, y = x * k + k // 2, y * k + k // 2
        if img is None or not img.rect().contains(x, y):
            return QColor(0, 0, 0)
        return QColor(img.pixel(x, y))

    # -- composite helpers --------------------------------------------
    def volume_frame(self, frame: int) -> QPixmap:
        frame = max(0, min(SP.VOLUME_FRAMES - 1, frame))
        return self.crop("VOLUME", (0, frame * 15, 68, 13))

    def balance_frame(self, frame: int) -> QPixmap:
        frame = max(0, min(SP.BALANCE_FRAMES - 1, frame))
        if 0 < self.sheet_size("BALANCE")[0] < 47:
            return self.crop("BALANCE", (0, frame * 15, 38, 13))
        return self.crop("BALANCE", (9, frame * 15, 38, 13))

    def has_volume_thumb(self, sheet="VOLUME") -> bool:
        return self.sheet_size(sheet)[1] > 422

    def eq_band_frame(self, frame: int) -> QPixmap:
        frame = max(0, min(27, frame))
        x = 13 + (frame % 14) * 15
        y = 164 + (frame // 14) * 65
        return self.crop("EQMAIN", (x, y, 14, 63))

    def digit(self, ch: str) -> QPixmap:
        sheet = "NUMS_EX" if self.nums_ex else "NUMBERS"
        if ch == "-":
            if self.nums_ex:
                return self.crop(sheet, (99, 0, 9, 13))
            return self.crop(sheet, (20, 6, 5, 1))
        if ch == " ":
            if self.nums_ex:
                return self.crop(sheet, (90, 0, 9, 13))
            return self.crop(sheet, (9, 6, 5, 1))
        return self.crop(sheet, (int(ch) * 9, 0, 9, 13))

    # -- bitmap font --------------------------------------------------
    def glyph(self, ch: str) -> QPixmap:
        pm = self._font_glyphs.get(ch)
        if pm is None:
            pos = SP.FONT_LOOKUP.get(ch) or SP.FONT_LOOKUP.get(ch.lower())
            if pos is None:
                pos = SP.FONT_LOOKUP[" "]
            r, c = pos
            pm = self.crop("TEXT", (c * SP.CHAR_W, r * SP.CHAR_H,
                                     SP.CHAR_W, SP.CHAR_H))
            self._font_glyphs[ch] = pm
        return pm

    @staticmethod
    def bitmap_text(text: str) -> str | None:
        """Return `text` mapped to the bitmap font, or None if impossible."""
        out = []
        for ch in text:
            if ch in SP.FONT_LOOKUP or ch.lower() in SP.FONT_LOOKUP:
                out.append(ch)
                continue
            base = unicodedata.normalize("NFKD", ch)
            base = "".join(b for b in base if not unicodedata.combining(b))
            if base and all(b in SP.FONT_LOOKUP or b.lower() in SP.FONT_LOOKUP
                            for b in base):
                out.append(base)
            elif ch in "\t":
                out.append(" ")
            elif ch in "‘’`´":
                out.append("'")
            elif ch in "“”":
                out.append('"')
            elif ch in "–—~":
                out.append("-")
            elif ch == "|":
                out.append("/")
            elif ch == ";":
                out.append(",")
            else:
                return None
        return "".join(out)

    def _text_colors(self) -> tuple[QColor, QColor]:
        img = self.sheet("TEXT")
        if img is None:
            return QColor(0, 255, 0), QColor(0, 0, 0)
        bg = QColor(img.pixel(min(img.width() - 1, 152), 2))
        counts = Counter()
        for y in range(min(6, img.height())):
            for x in range(min(130, img.width())):
                p = img.pixel(x, y)
                if QColor(p) != bg:
                    counts[p] += 1
        fg = QColor(counts.most_common(1)[0][0]) if counts else QColor(0, 255, 0)
        return fg, bg

    # -- regions ------------------------------------------------------
    def region_path(self, section: str) -> QPainterPath | None:
        polys = self.region.get(section.lower())
        if not polys:
            return None
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for poly in polys:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
            path.closeSubpath()
        return path

    def cursor(self, name: str) -> QCursor | None:
        return self.cursors.get(name)


CURSOR_NAMES = ["normal", "close", "mainmenu", "min", "posbar", "songname",
                "titlebar", "volbal", "winbut", "wsnormal", "wsposbar",
                "wsclose", "wsmin", "wswinbut", "eqclose", "eqnormal",
                "eqslid", "eqtitle", "pclose", "pnormal", "psize", "ptbar",
                "pvscroll", "pwinbut", "pwsnorm", "pwssize", "volbar"]


def load_classic(path: str, fallback: ClassicSkin | None = None, smooth: int = 1) -> ClassicSkin:
    """`smooth` > 1 enlarges the bitmaps with Scale2x/3x for that zoom."""
    src = SkinSource(path)
    try:
        sheets: dict[str, QImage | None] = {}
        for sheet, fname in SP.SHEET_FILES.items():
            data = src.find(fname)
            sheets[sheet] = decode_image(data) if data else None
        if sheets["NUMBERS"] is None and sheets["NUMS_EX"] is None and fallback:
            sheets["NUMBERS"] = None
        nums_ex = sheets["NUMS_EX"] is not None
        vis_txt = src.text("viscolor.txt")
        viscolors = parse_viscolors(vis_txt) if vis_txt else None
        pl_txt = src.text("pledit.txt")
        pledit = None
        if pl_txt:
            d = parse_ini(pl_txt).get("text", {})
            pledit = {
                k: _parse_color(d.get(k.lower()), SP.DEFAULT_PLEDIT.get(k, "#000000"))
                for k in ("normal", "current", "normalbg", "selectedbg")
            }
            pledit["font"] = d.get("font") or SP.DEFAULT_PLEDIT["font"]
            for k in ("mbfg", "mbbg"):
                if d.get(k):
                    pledit[k] = _parse_color(d.get(k), "#000000")
        reg_txt = src.text("region.txt")
        region = parse_region(reg_txt) if reg_txt else None
        cursors = {}
        for cname in CURSOR_NAMES:
            d = src.read(cname + ".cur")
            if d:
                c = load_cursor(d)
                if c is not None:
                    cursors[cname] = c
        genex_colors = None
        if sheets.get("GENEX") is not None:
            img = sheets["GENEX"]
            names = ["item_bg", "item_fg", "window_bg", "button_text",
                     "window_text", "divider", "playlist_selection",
                     "list_header_bg", "list_header_text",
                     "list_header_frame_tl", "list_header_frame_br",
                     "list_header_frame_pressed", "list_header_dead",
                     "scrollbar_one", "scrollbar_two", "pressed_scrollbar_one",
                     "pressed_scrollbar_two", "scrollbar_dead",
                     "list_text_highlighted", "list_text_highlighted_bg",
                     "list_text_selected", "list_text_selected_bg"]
            genex_colors = {}
            for i, n in enumerate(names):
                x = 48 + i * 2
                if x < img.width():
                    genex_colors[n] = QColor(img.pixel(x, 0))
        name = os.path.splitext(os.path.basename(path.rstrip("/")))[0]
        skin = ClassicSkin(sheets, name=name, path=path, fallback=fallback,
                           viscolors=viscolors, pledit=pledit, region=region,
                           cursors=cursors, genex_colors=genex_colors,
                           nums_ex=nums_ex)
        if smooth > 1:
            from .pixelscale import upscale
            # colours were sampled at 1x above; now swap in the enlarged sheets
            skin.sheets = {k: (upscale(v, smooth) if v is not None else None)
                           for k, v in sheets.items()}
            skin.res = smooth
            skin._cache.clear()
            skin._font_glyphs.clear()
        return skin
    finally:
        src.close()


def is_classic_skin(path: str) -> bool:
    try:
        src = SkinSource(path)
    except Exception:
        return False
    try:
        names = set(src.names())
        return "main.bmp" in names or "main.png" in names
    finally:
        src.close()
