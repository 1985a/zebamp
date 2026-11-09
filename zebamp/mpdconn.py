"""MPD connection handling.

* `MpdConnection` – synchronous command connection used from the GUI thread.
  MPD answers in well under a millisecond on a local socket, so ordinary
  commands are issued directly; anything potentially slow (whole-database
  listings) goes through `run_async`, which uses its own connection in a
  worker thread.
* `IdleThread` – a second connection parked in MPD's `idle` command that
  reports subsystem changes, so the UI never needs to poll for events.
"""
from __future__ import annotations

import logging
import os
import select
import socket
import threading
from dataclasses import dataclass

import mpd
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, QTimer, Signal

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5


@dataclass
class MpdAddress:
    host: str = ""
    port: int = 6600
    password: str = ""

    @property
    def is_socket(self) -> bool:
        return self.host.startswith("/") or self.host.startswith("@")

    def describe(self) -> str:
        return self.host if self.is_socket else f"{self.host}:{self.port}"


def _mpd_conf_socket() -> str | None:
    """Find `bind_to_address` pointing at a unix socket in the user's mpd.conf."""
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    for conf in (os.path.join(xdg, "mpd", "mpd.conf"),
                 os.path.join(home, ".mpdconf"),
                 os.path.join(home, ".mpd", "mpd.conf"), "/etc/mpd.conf"):
        try:
            with open(conf, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("bind_to_address"):
                        val = s.split(None, 1)[1].strip().strip('"')
                        val = os.path.expanduser(val)
                        if val.startswith("/") and os.path.exists(val):
                            return val
        except OSError:
            continue
    return None


def autodetect_address(cfg_host: str = "", cfg_port: int = 0,
                       cfg_password: str = "") -> MpdAddress:
    """Resolve the MPD address like other clients do (MPD_HOST/MPD_PORT)."""
    if cfg_host:
        return MpdAddress(os.path.expanduser(cfg_host), cfg_port or 6600, cfg_password)
    host = os.environ.get("MPD_HOST", "")
    port = int(os.environ.get("MPD_PORT", "6600") or 6600)
    password = cfg_password
    if host and "@" in host and not host.startswith("@"):
        password, host = host.split("@", 1)
    if host:
        return MpdAddress(os.path.expanduser(host), port, password)
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    # systemd socket activation first, then whatever mpd.conf says, then the
    # usual spots.  Socket files can be stale, so each one is test-connected.
    candidates = [os.path.join(runtime, "mpd", "socket")] if runtime else []
    conf_sock = _mpd_conf_socket()
    if conf_sock:
        candidates.append(conf_sock)
    candidates += [os.path.expanduser("~/.mpd/socket"),
                   os.path.expanduser("~/.config/mpd/socket"), "/run/mpd/socket"]
    for c in candidates:
        if c and os.path.exists(c) and _socket_alive(c):
            return MpdAddress(c, port, password)
    return MpdAddress("localhost", port, password)


def _socket_alive(path: str) -> bool:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(path)
        return s.recv(16).startswith(b"OK MPD")
    except OSError:
        return False
    finally:
        s.close()


class _Client(mpd.MPDClient):
    """python-mpd2 leaves the socket open when connecting to a Unix socket
    fails (MPD down/restarting): with a reconnect every 2 s that leaked a
    file descriptor each time."""

    def _connect_unix(self, path: str) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(path)
        except BaseException:
            sock.close()
            raise
        return sock


def open_client(addr: MpdAddress, timeout=CONNECT_TIMEOUT) -> mpd.MPDClient:
    c = _Client()
    c.timeout = timeout
    c.idletimeout = None
    try:
        if addr.is_socket:
            c.connect(addr.host)
        else:
            c.connect(addr.host, addr.port)
        if addr.password:
            c.password(addr.password)
    except BaseException:
        try:
            c.disconnect()
        except Exception:
            pass
        raise
    return c


class MpdConnection(QObject):
    connectionChanged = Signal(bool)
    error = Signal(str)

    def __init__(self, addr: MpdAddress, parent=None):
        super().__init__(parent)
        self.addr = addr
        self._client: mpd.MPDClient | None = None
        self._connected = False
        self._lock = threading.Lock()
        self._retry = QTimer(self)
        self._retry.setInterval(2000)
        self._retry.timeout.connect(self.connect_now)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.last_error = ""

    @property
    def connected(self) -> bool:
        return self._connected

    def set_address(self, addr: MpdAddress):
        self.addr = addr
        self.disconnect_now()
        self.connect_now()

    def connect_now(self):
        if self._connected:
            return True
        try:
            self._client = open_client(self.addr)
        except (OSError, mpd.MPDError) as e:
            self._client = None
            if str(e) != self.last_error:
                log.warning("MPD connect to %s failed: %s", self.addr.describe(), e)
            self.last_error = str(e)
            if not self._retry.isActive():
                self._retry.start()
            return False
        self._retry.stop()
        self._connected = True
        self.last_error = ""
        self.connectionChanged.emit(True)
        return True

    def disconnect_now(self):
        if self._client is not None:
            try:
                self._client.close()
                self._client.disconnect()
            except Exception:
                pass
        self._client = None
        if self._connected:
            self._connected = False
            self.connectionChanged.emit(False)

    def _lost(self, err):
        log.warning("MPD connection lost: %s", err)
        self.disconnect_now()
        if not self._retry.isActive():
            self._retry.start()

    def _ensure(self) -> bool:
        if self._connected:
            return True
        if self._retry.isActive():
            # MPD is down: the retry timer reconnects; don't block the GUI
            # with a connection attempt on every call meanwhile
            return False
        return self.connect_now()

    def call(self, cmd: str, *args, default=None):
        """Run one MPD command; returns `default` on failure."""
        if not self._ensure():
            return default
        try:
            with self._lock:
                return getattr(self._client, cmd)(*args)
        except mpd.CommandError as e:
            log.info("MPD %s%r: %s", cmd, args, e)
            self.error.emit(str(e))
            return default
        except (TimeoutError, mpd.ConnectionError, OSError, mpd.ProtocolError) as e:
            self._lost(e)
            # one retry on a fresh connection for idempotent-enough commands
            if self.connect_now():
                try:
                    with self._lock:
                        return getattr(self._client, cmd)(*args)
                except Exception as e2:
                    self._lost(e2)
            return default

    def batch(self, commands: list[tuple]) -> bool:
        """Run several commands in one command list (atomic for MPD)."""
        if not commands:
            return True
        if not self._ensure():
            return False
        try:
            with self._lock:
                c = self._client
                c.command_list_ok_begin()
                for cmd in commands:
                    getattr(c, cmd[0])(*cmd[1:])
                c.command_list_end()
            return True
        except mpd.CommandError as e:
            log.info("MPD batch failed: %s", e)
            self.error.emit(str(e))
            # The client library leaves the list open on errors; reconnect.
            self.disconnect_now()
            self.connect_now()
            return False
        except (TimeoutError, mpd.ConnectionError, OSError, mpd.ProtocolError) as e:
            self._lost(e)
            return False

    def run_async(self, fn, on_done=None):
        """Run fn(client) on a private connection in a worker thread.

        `on_done(result)` is invoked in the GUI thread (result is None if the
        call failed).
        """
        # The signal object lives in the GUI thread and stays referenced until
        # its result is delivered (a QRunnable-owned QObject could be freed
        # while the queued signal is still pending -> crash).
        sig = _JobSignals(self)
        jobs = self.__dict__.setdefault("_jobs", set())
        jobs.add(sig)

        def finish(result, sig=sig):
            jobs.discard(sig)
            sig.deleteLater()
            if on_done is not None:
                on_done(result)
        sig.done.connect(finish)
        job = _AsyncJob(self.addr, fn, sig)
        self.pool.start(job)
        return job


class _JobSignals(QObject):
    done = Signal(object)


class _AsyncJob(QRunnable):
    def __init__(self, addr, fn, signals):
        super().__init__()
        self.addr = addr
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        result = None
        client = None
        try:
            client = open_client(self.addr, timeout=60)
            result = self.fn(client)
        except Exception as e:
            log.warning("async MPD job failed: %s", e)
        finally:
            if client is not None:
                try:
                    client.close()
                    client.disconnect()
                except Exception:
                    pass
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass  # receiver went away during shutdown


class IdleThread(QThread):
    """Parks a raw protocol connection in MPD's `idle` command.

    A tiny hand-written client is used (instead of python-mpd2) so the wait
    can be interrupted cleanly with `noidle` when the app quits.
    """

    changed = Signal(object)   # set of subsystem names
    connected = Signal(bool)

    def __init__(self, addr: MpdAddress, parent=None):
        super().__init__(parent)
        self.addr = addr
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        self.wait(3000)

    def _open(self) -> socket.socket:
        if self.addr.is_socket:
            path = self.addr.host
            if path.startswith("@"):
                path = "\0" + path[1:]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(CONNECT_TIMEOUT)
            try:
                sock.connect(path)
            except OSError:
                sock.close()
                raise
        else:
            sock = socket.create_connection((self.addr.host, self.addr.port), CONNECT_TIMEOUT)
        return sock

    @staticmethod
    def _read_response(f) -> list[str]:
        lines = []
        while True:
            line = f.readline()
            if not line:
                raise ConnectionError("MPD closed the connection")
            line = line.decode("utf-8", "replace").rstrip("\n")
            if line == "OK":
                return lines
            if line.startswith("ACK"):
                raise ConnectionError(line)
            lines.append(line)

    def run(self):
        backoff = 0.5
        while not self._stop.is_set():
            sock = None
            try:
                sock = self._open()
                f = sock.makefile("rb")
                hello = f.readline()
                if not hello.startswith(b"OK MPD"):
                    raise ConnectionError("not an MPD server")
                if self.addr.password:
                    sock.sendall(f'password "{self.addr.password}"\n'.encode())
                    self._read_response(f)
                sock.settimeout(None)
                self.connected.emit(True)
                backoff = 0.5
                self.changed.emit({"*"})
                while not self._stop.is_set():
                    sock.sendall(b"idle\n")
                    ready = False
                    while not self._stop.is_set():
                        r, _, _ = select.select([sock], [], [], 0.5)
                        if r:
                            ready = True
                            break
                    if not ready:
                        try:
                            sock.sendall(b"noidle\n")
                            sock.settimeout(2)
                            self._read_response(f)
                        except (OSError, ConnectionError):
                            pass
                        break
                    lines = self._read_response(f)
                    subs = {ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("changed:")}
                    if subs:
                        self.changed.emit(subs)
            except (OSError, ConnectionError) as e:
                log.debug("idle connection error: %s", e)
                self.connected.emit(False)
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if self._stop.wait(backoff):
                break
            backoff = min(5.0, backoff * 2)
