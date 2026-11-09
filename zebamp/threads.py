"""Run blocking work (HTTP, file I/O) off the GUI thread."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)
_pool = QThreadPool()
_pool.setMaxThreadCount(4)
_alive: set = set()


class _Sig(QObject):
    done = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn, sig):
        super().__init__()
        self.fn = fn
        self.sig = sig
        self.setAutoDelete(True)

    def run(self):
        try:
            res = self.fn()
        except Exception as e:
            log.warning("background job failed: %s", e)
            res = e
        try:
            self.sig.done.emit(res)
        except RuntimeError:
            pass


def run_bg(fn, on_done=None):
    """fn() runs in a worker; on_done(result or Exception) in the GUI thread."""
    sig = _Sig()
    _alive.add(sig)

    def finish(res, sig=sig):
        _alive.discard(sig)
        sig.deleteLater()
        if on_done is not None:
            on_done(res)
    sig.done.connect(finish)
    _pool.start(_Job(fn, sig))


USER_AGENT = "Zebamp/1.0 (MPD client)"


def http_json(url: str, timeout=12):
    import json
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
