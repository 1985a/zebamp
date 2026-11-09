"""Spectrum analyser / oscilloscope fed by MPD's fifo output."""
from __future__ import annotations

import errno
import logging
import os
import re
import time

import numpy as np
from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter

log = logging.getLogger(__name__)


def mpd_fifo_outputs() -> list[tuple[str, str, str]] | None:
    """(path, format, name) of every fifo audio_output in mpd.conf.

    None when no mpd.conf could be read (then nothing is known)."""
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    for conf in (os.path.join(xdg, "mpd", "mpd.conf"),
                 os.path.join(home, ".mpdconf"),
                 os.path.join(home, ".mpd", "mpd.conf"), "/etc/mpd.conf"):
        try:
            with open(conf, encoding="utf-8", errors="replace") as fh:
                text = re.sub(r"#[^\n]*", "", fh.read())
        except OSError:
            continue
        found = []
        for block in re.findall(r"audio_output\s*\{(.*?)\}", text, re.S):
            props = dict(re.findall(r'(\w+)\s+"([^"]*)"', block))
            if props.get("type") == "fifo" and props.get("path"):
                found.append((os.path.expanduser(props["path"]), props.get("format", "44100:16:2"),
                              props.get("name", "")))
        return found
    return None


def find_fifo_output() -> tuple[str, str] | None:
    """The fifo audio_output (path, format) Zebamp should read, if any."""
    found = mpd_fifo_outputs() or []
    if not found:
        return None
    # A fifo shared with another visualiser (ncmpcpp, cava...) splits the
    # data between readers, so prefer one reserved for Zebamp.
    found.sort(key=lambda f: 0 if "zebamp" in (f[0] + f[2]).lower() else 1)
    for path, fmt, _name in found:
        if os.path.exists(path):
            return path, fmt
    return found[0][0], found[0][1]


class FifoReader:
    """Non-blocking reader that keeps the most recent PCM frames."""

    def __init__(self, path: str, fmt: str = "44100:16:2", keep: int = 2048):
        self.path = path
        self.keep = keep
        try:
            rate, bits, ch = fmt.split(":")
            self.rate = int(rate) if rate != "*" else 44100
            self.bits = int(bits) if bits not in ("*", "f") else 16
            self.channels = int(ch) if ch != "*" else 2
        except ValueError:
            self.rate, self.bits, self.channels = 44100, 16, 2
        if self.bits not in (8, 16, 24, 32):
            self.bits = 16
        self.dtype = {8: np.int8, 16: np.int16, 24: None, 32: np.int32}[self.bits]
        self.frame_bytes = (self.bits // 8) * self.channels
        self.fd = None
        self.buf = np.zeros(keep, dtype=np.float32)
        self._partial = b""
        self.got_data = False
        # MPD writes the fifo in bursts (~1000 frames every ~23 ms).  Keep a
        # history ring and read it with a cursor that advances in real time, so
        # every frame shows fresh audio whatever the frame rate.
        self.ring_len = 16384
        self.ring = np.zeros(self.ring_len, dtype=np.float32)
        self.total = 0           # samples ever written into the ring
        self.cursor = 0.0        # playback position (samples) shown on screen
        self._last_t = None
        self.extra = []          # extra consumers (e.g. MilkDrop) get raw samples

    def open(self) -> bool:
        if self.fd is not None:
            return True
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            return True
        except OSError as e:
            log.debug("cannot open fifo %s: %s", self.path, e)
            self.fd = None
            return False

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None

    def drain(self):
        """Discard anything buffered (stale audio)."""
        if self.fd is None:
            return
        try:
            while os.read(self.fd, 65536):
                pass
        except OSError:
            pass
        self._partial = b""

    def poll(self) -> bool:
        """Read everything available; return True if new data arrived."""
        if self.fd is None and not self.open():
            return False
        chunks = []
        total = 0
        try:
            while True:
                d = os.read(self.fd, 65536)
                if not d:
                    break
                chunks.append(d)
                total += len(d)
                if total > 1 << 20:
                    break
        except BlockingIOError:
            pass
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                self.close()
            return False
        if not chunks:
            return False
        data = self._partial + b"".join(chunks)
        usable = len(data) - (len(data) % self.frame_bytes)
        self._partial = data[usable:]
        # Only the tail matters.
        tail_bytes = self.keep * self.frame_bytes
        data = data[max(0, usable - tail_bytes):usable]
        if self.bits == 24:
            raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
            vals = (raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8)
                    | (raw[:, 2].astype(np.int32) << 16))
            vals = np.where(vals & 0x800000, vals - 0x1000000, vals)
            samples = vals.astype(np.float32) / float(1 << 23)
        else:
            samples = np.frombuffer(data, dtype=self.dtype).astype(np.float32)
            samples /= float(1 << (self.bits - 1))
        if self.channels > 1:
            samples = samples.reshape(-1, self.channels).mean(axis=1)
        self._push(samples)
        self.got_data = True
        return True

    def _push(self, samples: np.ndarray):
        n = len(samples)
        if n == 0:
            return
        for cb in self.extra:
            try:
                cb(samples)
            except Exception:
                log.exception("vis consumer failed")
        if n >= self.ring_len:
            samples = samples[-self.ring_len:]
            n = self.ring_len
        i = self.total % self.ring_len
        first = min(n, self.ring_len - i)
        self.ring[i:i + first] = samples[:first]
        if first < n:
            self.ring[:n - first] = samples[first:]
        self.total += n

    def resync(self):
        self.cursor = float(self.total)
        self._last_t = None

    def window(self, now: float, n: int | None = None) -> np.ndarray:
        """The `n` samples ending at the paced cursor (updates self.buf)."""
        n = n or self.keep
        if self._last_t is not None:
            self.cursor += (now - self._last_t) * self.rate
        self._last_t = now
        # Stay one burst behind the writer: never run past the data we have and
        # never lag more than ~70 ms (resync after stalls or pauses).
        burst = 1100
        if self.cursor > self.total:
            self.cursor = float(self.total)
        elif self.cursor < self.total - 3 * burst:
            self.cursor = float(self.total - burst)
        end = int(self.cursor)
        start = end - n
        if start < 0 or end <= 0 or self.total - start > self.ring_len:
            out = np.zeros(n, dtype=np.float32)
            avail = min(end, n, self.ring_len)
            if avail > 0:
                idx = np.arange(end - avail, end) % self.ring_len
                out[-avail:] = self.ring[idx]
            self.buf = out
            return out
        a = start % self.ring_len
        if a + n <= self.ring_len:
            self.buf = self.ring[a:a + n].copy()
        else:
            self.buf = np.concatenate((self.ring[a:], self.ring[:a + n - self.ring_len]))
        return self.buf


def fifo_other_readers(path: str) -> list[str]:
    """Names of other processes that have `path` open (e.g. ncmpcpp)."""
    try:
        real = os.path.realpath(path)
        os.stat(real)
    except OSError:
        return []
    me = os.getpid()
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        fd_dir = f"/proc/{pid}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    if os.path.realpath(os.path.join(fd_dir, fd)) == real:
                        with open(f"/proc/{pid}/comm") as fh:
                            out.append(fh.read().strip())
                        raise StopIteration
                except OSError:
                    continue
        except StopIteration:
            continue
        except OSError:
            continue
    return out


class PipeWireCapture(FifoReader):
    """Reads MPD's PipeWire stream with pw-record (no fifo needed).

    Used when the fifo is already read by another visualiser: two readers of
    one fifo each get only part of the data, so both would stutter.
    """

    def __init__(self, keep: int = 2048):
        super().__init__("pipewire:mpd", "44100:16:2", keep)
        self.proc = None
        self._retry_at = 0.0

    @staticmethod
    def available() -> bool:
        import shutil
        return shutil.which("pw-record") is not None and shutil.which("pw-dump") is not None

    @staticmethod
    def _target() -> str | None:
        import json
        import subprocess
        try:
            dump = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True,
                                             timeout=3).stdout or "[]")
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        from .audio.pipewire import _props, find_mpd_stream
        o = find_mpd_stream(dump)
        if o is None:
            return None
        p = _props(o)
        return str(p.get("object.serial") or o.get("id"))

    def open(self) -> bool:
        if self.proc is not None and self.proc.poll() is None:
            return True
        self.close()
        if time.monotonic() < self._retry_at:
            return False
        target = getattr(self, "_found_target", None)
        if target is None:
            # pw-dump is slow: look the stream up off the GUI thread
            if not getattr(self, "_looking", False):
                self._looking = True
                from .threads import run_bg

                def found(t):
                    self._looking = False
                    self._found_target = t if isinstance(t, str) else None
                    if self._found_target is None:
                        self._retry_at = time.monotonic() + 3
                run_bg(self._target, found)
            return False
        self._found_target = None      # re-resolve next time (MPD may recreate it)
        import subprocess
        try:
            self.proc = subprocess.Popen(
                ["pw-record", "--target", target, "--format", "s16", "--rate", "44100",
                 "--channels", "2", "--latency", "512",
                 "-P", "{ node.passive=true node.dont-reconnect=true media.name=\"Zebamp vis\" "
                       "node.description=\"Zebamp (visualizador)\" }", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except OSError as e:
            log.debug("pw-record failed: %s", e)
            self.proc = None
            self._retry_at = time.monotonic() + 10
            return False
        self.fd = self.proc.stdout.fileno()
        os.set_blocking(self.fd, False)
        return True

    def poll(self) -> bool:
        if self.proc is not None and self.proc.poll() is not None:
            self.close()          # stream went away (MPD restarted…); retry later
            self._retry_at = time.monotonic() + 2
        return super().poll()

    def close(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            try:
                self.proc.stdout.close()
            except Exception:
                pass
        self.proc = None
        self.fd = None


FALLOFF = [0.25, 0.5, 1.0, 1.6, 2.6]          # px per frame at 50 fps
PEAK_FALLOFF = [1.03, 1.06, 1.12, 1.25, 1.45]  # acceleration


class Analyzer:
    """Computes classic-looking bar heights (0..16) and scope samples."""

    def __init__(self, width=75, height=16):
        self.width = width
        self.height = height
        self.bars = np.zeros(width, dtype=np.float32)
        self.peaks = np.zeros(width, dtype=np.float32)
        self.peak_vel = np.zeros(width, dtype=np.float32)
        self.window = np.hanning(1024).astype(np.float32)
        self._edges = self._make_edges(width)
        self.scope = np.zeros(width, dtype=np.float32)

    @staticmethod
    def _make_edges(width):
        """Column -> FFT bin boundaries: mostly logarithmic with a linear blend
        (the same feel as Winamp's analyser)."""
        n = 512
        x = np.arange(width + 1) / width
        log_idx = np.power(10.0, x * np.log10(n))
        lin_idx = x * (n - 1)
        idx = 0.91 * log_idx + 0.09 * lin_idx
        return np.clip(idx, 1, n - 1)

    def process(self, samples: np.ndarray, falloff_idx=2, peak_idx=1,
                thick=True, fps=50):
        frame_scale = 50.0 / max(10, fps)
        x = samples[-1024:]
        if len(x) < 1024:
            x = np.pad(x, (1024 - len(x), 0))
        spec = np.abs(np.fft.rfft(x * self.window))[:512]
        e = self._edges
        vals = np.empty(self.width, dtype=np.float32)
        for i in range(self.width):
            a = int(e[i])
            b = max(a + 1, int(np.ceil(e[i + 1])))
            vals[i] = spec[a:b].max()
        # dB scale -> 0..16 rows; slight high-frequency tilt like Winamp.
        tilt = np.geomspace(1.0, 7.0, self.width).astype(np.float32)
        db = 20 * np.log10(vals * tilt + 1e-9)
        h = np.clip((db - 4.0) / 2.4, 0, self.height)
        if thick:
            n = self.width // 4 * 4
            g = h[:n].reshape(-1, 4).mean(axis=1)
            h = np.repeat(g, 4)
            if len(h) < self.width:
                h = np.pad(h, (0, self.width - len(h)))
        fall = FALLOFF[max(0, min(4, falloff_idx))] * frame_scale
        self.bars = np.maximum(h, self.bars - fall)
        # peaks
        rising = self.bars >= self.peaks
        self.peaks = np.where(rising, self.bars, self.peaks)
        self.peak_vel = np.where(rising, 0.0, self.peak_vel)
        acc = PEAK_FALLOFF[max(0, min(4, peak_idx))]
        self.peak_vel = np.where(rising, 0.0,
                                 np.maximum(0.05, self.peak_vel * acc + 0.02) * frame_scale)
        self.peaks = np.where(rising, self.peaks,
                              np.maximum(self.bars, self.peaks - self.peak_vel))
        # oscilloscope: 75 points spread over ~ 11 ms
        seg = samples[-576:]
        idx = np.linspace(0, len(seg) - 1, self.width).astype(int)
        self.scope = np.clip(seg[idx] * 2.2, -1.0, 1.0)

    def decay(self, falloff_idx=2):
        fall = FALLOFF[max(0, min(4, falloff_idx))]
        self.bars = np.maximum(0, self.bars - fall)
        self.peaks = np.maximum(0, self.peaks - 0.5)
        self.scope *= 0.5
        return bool(self.bars.any() or self.peaks.any())


class VisRenderer:
    """Draws analyser output with the skin's viscolor palette (numpy based)."""

    def __init__(self):
        self.pal = np.zeros(24, dtype=np.uint32)
        self._bg_cache: dict = {}

    def set_colors(self, colors: list[QColor]):
        self.pal = np.array([0xFF000000 | (c.red() << 16) | (c.green() << 8) | c.blue()
                             for c in colors[:24]] + [0xFF000000] * (24 - len(colors[:24])),
                            dtype=np.uint32)
        self._bg_cache.clear()

    def _bg(self, w, h, dotted):
        key = (w, h, dotted)
        bg = self._bg_cache.get(key)
        if bg is None:
            bg = np.full((h, w), self.pal[0], dtype=np.uint32)
            if dotted:
                bg[1::2, 1::2] = self.pal[1]
            self._bg_cache[key] = bg
        return bg

    def render(self, w: int, h: int, analyzer: Analyzer, mode: str, cfg,
               small=False) -> np.ndarray:
        pal = self.pal
        img = self._bg(w, h, not small).copy()
        rows = np.arange(h)[:, None]
        if mode == "spectrum":
            bars = analyzer.bars[:w]
            n = len(bars)
            H = np.clip(np.round(bars * (h / 16.0 if not small else h / 5.0)), 0, h).astype(int)
            if small:
                H = np.clip(np.round(bars), 0, h).astype(int)
            top = h - H
            mask = rows >= top[None, :]
            if cfg["vis_bands"] == "thick" and not small:
                mask[:, 3::4] = False
            coloring = cfg["vis_coloring"]
            if coloring == "fire":
                idx = 2 + np.clip((rows - top[None, :]) * 16 // h, 0, 15)
                colors = pal[idx]
            elif coloring == "line":
                idx = 2 + np.clip(16 - (H * 16 // h), 0, 15)
                colors = np.broadcast_to(pal[idx][None, :], (h, n))
            else:
                idx = 2 + np.clip(rows * 16 // h, 0, 15)
                colors = np.broadcast_to(pal[idx], (h, n))
            sub = img[:, :n]
            sub[mask] = colors[mask]
            if cfg["vis_peaks"]:
                P = np.clip(np.round(analyzer.peaks[:n] * (h / 16.0 if not small else 1.0)), 0, h).astype(int)
                if small:
                    P = np.clip(np.round(analyzer.peaks[:n]), 0, h).astype(int)
                cols = np.nonzero(P > 0)[0]
                if cfg["vis_bands"] == "thick" and not small:
                    cols = cols[(cols % 4) != 3]
                sub[h - P[cols], cols] = pal[23]
        elif mode == "oscilloscope":
            sc = analyzer.scope[:w]
            n = len(sc)
            mid = (h - 1) / 2.0
            y = np.clip(np.round(mid - sc * mid), 0, h - 1).astype(int)
            dist = np.abs(y - mid) / max(1.0, mid)
            colidx = 18 + np.clip((dist * 5).astype(int), 0, 4)
            style = cfg["vis_osc_style"]
            if style == "dots":
                mask = rows == y[None, :]
            elif style == "solid":
                m = int(round(mid))
                lo = np.minimum(y, m)
                hi = np.maximum(y, m)
                mask = (rows >= lo[None, :]) & (rows <= hi[None, :])
            else:
                prev = np.concatenate(([y[0]], y[:-1]))
                lo = np.minimum(prev, y)
                hi = np.maximum(prev, y)
                mask = (rows >= lo[None, :]) & (rows <= hi[None, :])
            colors = np.broadcast_to(pal[colidx][None, :], (h, n))
            sub = img[:, :n]
            sub[mask] = colors[mask]
        return img

    def paint(self, p: QPainter, rect: QRect, analyzer: Analyzer, mode: str,
              cfg, small=False):
        arr = self.render(rect.width(), rect.height(), analyzer, mode, cfg, small)
        arr = np.ascontiguousarray(arr)
        qimg = QImage(arr.data, arr.shape[1], arr.shape[0], arr.shape[1] * 4,
                      QImage.Format.Format_RGB32)
        p.drawImage(rect.topLeft(), qimg)


class Visualizer(QObject):
    """Drives the fifo reader and analyser at the configured frame rate."""

    frame = Signal()

    def __init__(self, cfg, player, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.player = player
        self.analyzer = Analyzer()
        self.small = Analyzer(width=38, height=5)
        self.renderer = VisRenderer()
        self.reader: FifoReader | None = None
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self._active_views = 0
        self._next_share_check = 0.0
        self.shared_with: list[str] = []
        self._decaying = False
        self.available = False
        # set by the app: is any window showing the visualiser?  When Zebamp
        # is hidden in the tray nothing is analysed (MilkDrop excepted).
        self.shown = lambda: True
        self.configure()
        player.statusChanged.connect(self._on_state)

    def _check_shared(self):
        """A visualiser such as ncmpcpp may open the shared fifo later on."""
        r = self.reader
        if self.cfg["vis_source"] != "auto" or type(r) is not FifoReader \
                or "zebamp" in r.path.lower() or not PipeWireCapture.available():
            return
        if getattr(self, "_checking", False):
            return
        self._checking = True
        from .threads import run_bg
        path = r.path
        run_bg(lambda: fifo_other_readers(path), lambda res, r=r: self._shared_result(r, res))

    def _shared_result(self, r, others):
        self._checking = False
        if r is not self.reader or not isinstance(others, list):
            return
        if others:
            log.info("fifo %s also read by %s: switching to PipeWire capture", r.path, others)
            extra = r.extra
            r.close()
            self.shared_with = others
            self.reader = PipeWireCapture()
            self.reader.extra = extra
            self.reader.open()

    def configure(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        path = self.cfg["vis_fifo"]
        fmt = self.cfg["vis_fifo_format"]
        source = self.cfg["vis_source"]
        if not path:
            found = find_fifo_output()
            if found:
                path, f2 = found
                fmt = fmt or f2
        self.shared_with = []
        use_pw = source == "pipewire"
        if source == "auto" and path:
            # MPD's fifo outputs can hold back the other outputs when playback
            # resumes (up to ~1.3 s of silence), so users may remove them: a
            # fifo no longer declared in mpd.conf is stale, capture PipeWire.
            declared = mpd_fifo_outputs()
            if declared is not None and path not in [p for p, _f, _n in declared]:
                path = ""
        if source == "auto" and path and os.path.exists(path) and "zebamp" not in path.lower():
            # don't steal a fifo another visualiser (ncmpcpp, cava…) is reading
            self.shared_with = fifo_other_readers(path)
            use_pw = bool(self.shared_with)
        if source == "auto" and not (path and os.path.exists(path)):
            use_pw = True
        if use_pw and PipeWireCapture.available():
            self.reader = PipeWireCapture()
            self.available = True
        elif path and os.path.exists(path):
            self.reader = FifoReader(path, fmt or "44100:16:2")
            self.available = True
        else:
            self.available = False
        self.timer.setInterval(int(1000 / max(10, min(120, self.cfg["vis_fps"]))))
        self._on_state()

    @property
    def mode(self) -> str:
        return self.cfg["vis_mode"]

    def _on_state(self):
        want = (self.player.state == "play" and self.mode != "off"
                and self.reader is not None
                and (self.shown() or bool(self.reader.extra)))
        if want:
            if not self.timer.isActive() or self._decaying:
                self.reader.open()
                self.reader.drain()
                self.reader.resync()
            # Re-enabling during the fade-out must resume live drawing.
            self._decaying = False
            if not self.timer.isActive():
                self.timer.start()
        elif self.timer.isActive() and not self._decaying:
            self._decaying = True

    def _tick(self):
        cfg = self.cfg
        if self._decaying:
            if self.reader is not None:
                # keep consuming (other consumers such as MilkDrop still want it)
                self.reader.poll()
            alive = self.analyzer.decay(cfg["vis_falloff"])
            self.small.decay(cfg["vis_falloff"])
            self.frame.emit()
            if not alive:
                self.timer.stop()
                self._decaying = False
                if isinstance(self.reader, PipeWireCapture) and not self.reader.extra:
                    self.reader.close()      # no capture process while idle
            return
        if self.reader is None:
            return
        now = time.monotonic()
        if now >= self._next_share_check:
            self._next_share_check = now + 5
            self._check_shared()
        self.reader.poll()
        buf = self.reader.window(now)
        fps = cfg["vis_fps"]
        self.analyzer.process(buf, cfg["vis_falloff"], cfg["vis_peak_falloff"],
                              cfg["vis_bands"] == "thick", fps)
        self.small.bars = self.analyzer.bars[::2][:38] * (5 / 16)
        self.small.peaks = self.analyzer.peaks[::2][:38] * (5 / 16)
        self.small.scope = self.analyzer.scope[::2][:38]
        self.frame.emit()

    def shutdown(self):
        self.timer.stop()
        if self.reader is not None:
            self.reader.close()
