"""Notices when MPD says "playing" but the song does not advance, and keeps
a snapshot of the audio system at that moment.

That stall is rare and does not show up on demand, so the only way to learn
its cause is to look at PipeWire while it happens.  `StallDetector` is pure
(fed with what MPD reports once a second); `StallWatch` connects it to the
player and writes the snapshot off the GUI thread.  Snapshots stay on this
computer, in ~/.cache/zebamp/atascos/.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time

from PySide6.QtCore import QObject, Signal

from .i18n import tr
from .threads import run_bg

log = logging.getLogger(__name__)

STALL_SECONDS = 3.0         # playing without advancing for this long is a stall
KEEP_SNAPSHOTS = 10
SNAPSHOT_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "zebamp", "atascos")
AUDIO_NODE_CLASSES = ("Audio/Sink", "Stream/Output/Audio", "Stream/Input/Audio")
TOOL_TIMEOUT = 4


class StallDetector:
    """Fed with MPD's state once a second; says when a stall begins."""

    def __init__(self, threshold: float = STALL_SECONDS):
        self.threshold = threshold
        self._key = None            # (song id, elapsed) last seen while playing
        self._since = 0.0
        self._reported = False

    def feed(self, state: str, elapsed, song_id, now: float) -> bool:
        """True exactly once per stall: playing, same song, same position
        for `threshold` seconds."""
        if state != "play":
            self._key = None
            return False
        key = (song_id, elapsed)
        if key != self._key:
            self._key, self._since, self._reported = key, now, False
            return False
        if not self._reported and now - self._since >= self.threshold:
            self._reported = True
            return True
        return False


# ------------------------------------------------------------- snapshot
def _run(command: list[str]) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=TOOL_TIMEOUT).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def audio_graph(dump: list) -> dict:
    """The part of a pw-dump that explains where audio flows: audio nodes
    (state, error, format), the links between them and stream targets."""
    names, nodes = {}, []
    for obj in dump:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        info = obj.get("info") or {}
        props = info.get("props") or {}
        names[obj.get("id")] = props.get("node.name")
        if props.get("media.class") not in AUDIO_NODE_CLASSES:
            continue
        params = info.get("params") or {}
        nodes.append({"id": obj.get("id"), "name": props.get("node.name"), "class": props.get("media.class"),
                      "app": props.get("application.name"), "state": info.get("state"), "error": info.get("error"),
                      "passive": props.get("node.passive"), "rate": props.get("node.rate"),
                      "latency": props.get("node.latency"), "format": params.get("Format"),
                      "ports": [info.get("n-input-ports"), info.get("n-output-ports")]})
    links = []
    for obj in dump:
        if obj.get("type") != "PipeWire:Interface:Link":
            continue
        info = obj.get("info") or {}
        links.append({"id": obj.get("id"), "from": names.get(info.get("output-node-id")),
                      "to": names.get(info.get("input-node-id")), "state": info.get("state"),
                      "error": info.get("error"), "format": info.get("format")})
    targets = []
    for obj in dump:
        if obj.get("type") != "PipeWire:Interface:Metadata":
            continue
        for item in obj.get("metadata") or []:
            key = str(item.get("key") or "")
            if key.startswith(("target.", "default.audio", "clock.")):
                targets.append({"subject": names.get(item.get("subject"), item.get("subject")), "key": key,
                                "value": item.get("value")})
    return {"nodes": nodes, "links": links, "metadata": targets}


def take_snapshot(status: dict, song: dict, directory: str = SNAPSHOT_DIR) -> str | None:
    """Write what is known about the stall; returns the file path."""
    try:
        dump = json.loads(_run(["pw-dump"]) or "[]")
    except ValueError:
        dump = []
    journal = _run(["journalctl", "--user", "-u", "pipewire", "-u", "wireplumber", "-u", "pipewire-pulse",
                    "--since", "-2min", "--no-pager", "-o", "short-precise"])
    snapshot = {"when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mpd_status": status,
                "song": {k: song.get(k) for k in ("file", "format", "duration")},
                "pipewire": audio_graph(dump),
                "journal": journal.splitlines()[-60:]}
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, time.strftime("atasco-%Y%m%d-%H%M%S.json"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=1)
        for old in sorted(f for f in os.listdir(directory) if f.startswith("atasco-"))[:-KEEP_SNAPSHOTS]:
            os.unlink(os.path.join(directory, old))
    except OSError as e:
        log.warning("stall snapshot not written: %s", e)
        return None
    return path


class StallWatch(QObject):
    stalled = Signal(str)       # text for the title display

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.detector = StallDetector()
        # MPD is polled once a second while it plays: no timer of our own
        player.statusChanged.connect(self._check)

    def _check(self):
        player = self.player
        song = player.song or {}
        if "://" in song.get("file", ""):
            return                  # a radio that is still connecting is not a stall
        status = player.status
        if not self.detector.feed(player.state, status.get("elapsed"), status.get("songid"), time.monotonic()):
            return
        log.warning("MPD is playing but not advancing; saving a snapshot of the audio system")
        snapshot_status, snapshot_song = dict(status), dict(song)
        run_bg(lambda: take_snapshot(snapshot_status, snapshot_song), self._saved)

    def _saved(self, path):
        if isinstance(path, str):
            self.stalled.emit(tr("MPD no avanza: diagnóstico guardado"))
