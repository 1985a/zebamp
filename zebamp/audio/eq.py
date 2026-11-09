"""Equalizer model: bands, presets (built-in, user, Winamp .eqf) and backend."""
from __future__ import annotations

import json
import logging
import os

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

PRESET_KEYS = ["hz60", "hz170", "hz310", "hz600", "hz1000", "hz3000", "hz6000",
               "hz12000", "hz14000", "hz16000"]
EQF_HEADER = b"Winamp EQ library file v1.1\x1a!--"


def winamp_to_db(v: float) -> float:
    """Winamp preset scale 1..64 (33 = 0 dB) -> dB."""
    return round(max(-12.0, min(12.0, (v - 33) / 31 * 12)), 1)


def db_to_winamp(db: float) -> int:
    return int(round(max(1, min(64, db / 12 * 31 + 33))))


def builtin_presets() -> dict[str, dict]:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "eq_presets.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for p in data.get("presets", []):
        out[p["name"]] = {"bands": [winamp_to_db(p[k]) for k in PRESET_KEYS],
                          "preamp": winamp_to_db(p["preamp"])}
    return out


def read_eqf(path: str) -> dict[str, dict]:
    """Parse a Winamp .eqf / winamp.q1 preset library."""
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(EQF_HEADER[:27]):
        raise ValueError("no es un archivo .eqf de Winamp")
    pos = len(EQF_HEADER)
    out = {}
    while pos + 257 + 11 <= len(data):
        name = data[pos:pos + 257].split(b"\0", 1)[0].decode("latin-1").strip()
        vals = data[pos + 257:pos + 268]
        pos += 268
        # eqf stores 0 = +12 dB (top) ... 63 = -12 dB
        bands = [winamp_to_db(64 - v) for v in vals[:10]]
        out[name or os.path.basename(path)] = {"bands": bands,
                                               "preamp": winamp_to_db(64 - vals[10])}
    return out


def write_eqf(path: str, presets: dict[str, dict]):
    with open(path, "wb") as fh:
        fh.write(EQF_HEADER)
        for name, p in presets.items():
            raw = name.encode("latin-1", "replace")[:256]
            fh.write(raw + b"\0" * (257 - len(raw)))
            vals = [64 - db_to_winamp(b) for b in p["bands"]] + [64 - db_to_winamp(p["preamp"])]
            fh.write(bytes(max(0, min(63, v)) for v in vals))


class Equalizer(QObject):
    changed = Signal()

    def __init__(self, cfg, backend, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.backend = backend
        self.bands = [float(b) for b in cfg["eq_bands"]]
        self.preamp = float(cfg["eq_preamp"])
        self.enabled = bool(cfg["eq_enabled"])
        self.builtin = builtin_presets()
        self._push = QTimer(self)
        self._push.setSingleShot(True)
        self._push.setInterval(30)
        self._push.timeout.connect(self._apply)
        if self.enabled:
            self._apply()

    @property
    def user_presets(self) -> dict:
        return self.cfg["eq_user_presets"] or {}

    def _apply(self):
        if self.backend is not None:
            self.backend.set_eq(self.enabled, self.bands, self.preamp)

    def _changed(self, persist=False):
        self.changed.emit()
        if not self._push.isActive():
            self._push.start()
        if persist:
            self.commit()

    def commit(self):
        self.cfg["eq_bands"] = list(self.bands)
        self.cfg["eq_preamp"] = self.preamp
        self.cfg["eq_enabled"] = self.enabled
        self.cfg.save()

    def toggle(self):
        self.set_enabled(not self.enabled)

    def set_enabled(self, on: bool):
        self.enabled = on
        self._changed(persist=True)

    def set_band(self, i: int, db: float):
        self.bands[i] = max(-12.0, min(12.0, db))
        self._changed()

    def set_preamp(self, db: float):
        self.preamp = max(-12.0, min(12.0, db))
        self._changed()

    def set_all(self, db: float):
        self.bands = [float(db)] * 10
        self._changed(persist=True)

    def load_preset(self, p: dict):
        self.bands = [float(b) for b in p["bands"]][:10]
        self.preamp = float(p.get("preamp", 0.0))
        self._changed(persist=True)

    def save_preset(self, name: str):
        presets = dict(self.user_presets)
        presets[name] = {"bands": list(self.bands), "preamp": self.preamp}
        self.cfg["eq_user_presets"] = presets
        self.cfg.save()

    def delete_preset(self, name: str):
        presets = dict(self.user_presets)
        presets.pop(name, None)
        self.cfg["eq_user_presets"] = presets
        self.cfg.save()

    def import_eqf(self, path: str) -> int:
        found = read_eqf(path)
        presets = dict(self.user_presets)
        presets.update(found)
        self.cfg["eq_user_presets"] = presets
        self.cfg.save()
        if len(found) == 1:
            self.load_preset(next(iter(found.values())))
        return len(found)

    def export_eqf(self, path: str, name: str = "Zebamp"):
        write_eqf(path, {name: {"bands": self.bands, "preamp": self.preamp}})
