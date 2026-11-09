"""PipeWire helpers: 10-band EQ (filter-chain) and balance for MPD's stream.

MPD itself has no equalizer, so Zebamp inserts a filter-chain sink
(`zebamp_eq`) between MPD's PipeWire stream and the sink it was playing to,
and adjusts the biquad gains live with `pw-cli set-param`.  Balance is applied
as per-channel volume on MPD's stream node.  All PipeWire commands run in a
worker thread so the UI never blocks on them.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time

log = logging.getLogger(__name__)

EQ_NODE = "zebamp_eq"
FREQS = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]
Q = 1.41
RUNTIME = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "zebamp")
PIDFILE = os.path.join(RUNTIME, "eq.pid")


def available() -> bool:
    return all(shutil.which(b) for b in ("pipewire", "pw-dump", "pw-cli", "pw-metadata"))


def _run(args, timeout=5.0, input_=None) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           input=input_)
        return r.stdout
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("%s failed: %s", args[0], e)
        return ""


def pw_dump() -> list:
    out = _run(["pw-dump"], timeout=5)
    try:
        return json.loads(out) if out else []
    except ValueError:
        return []


def _props(o) -> dict:
    return (o.get("info") or {}).get("props") or {}


def find_mpd_stream(dump: list, match: str = "Music Player Daemon"):
    for o in dump:
        if o.get("type") != "PipeWire:Interface:Node":
            continue
        p = _props(o)
        if p.get("media.class") != "Stream/Output/Audio":
            continue
        if p.get("application.name") == match:
            return o
        if match == "Music Player Daemon" and p.get("node.name", "").startswith("mpd."):
            return o
    return None


def find_node(dump: list, name: str):
    for o in dump:
        if o.get("type") == "PipeWire:Interface:Node" and _props(o).get("node.name") == name:
            return o
    return None


def is_dead_end(dump: list, name: str) -> bool:
    """A null sink swallows what it receives: never send the music there
    (e.g. a leftover "ducking" sink from a disabled setup)."""
    node = find_node(dump, name)
    return node is not None and _props(node).get("factory.name") == "support.null-audio-sink"


def linked_sink(dump: list, node_id: int) -> str | None:
    """Name of the node that `node_id`'s output is linked to."""
    nodes = {o["id"]: o for o in dump if o.get("type") == "PipeWire:Interface:Node"}
    for o in dump:
        if o.get("type") != "PipeWire:Interface:Link":
            continue
        info = o.get("info") or {}
        if info.get("output-node-id") == node_id:
            peer = nodes.get(info.get("input-node-id"))
            if peer:
                return _props(peer).get("node.name")
    return None


def stream_target(dump: list, node_id: int) -> str | None:
    for o in dump:
        if o.get("type") != "PipeWire:Interface:Metadata":
            continue
        name = (o.get("props") or {}).get("metadata.name") or _props(o).get("metadata.name")
        if name != "default":
            continue
        for m in o.get("metadata") or []:
            if m.get("subject") == node_id and m.get("key") in ("target.object", "target.node"):
                v = m.get("value")
                if isinstance(v, str):
                    try:
                        v = json.loads(v)
                    except ValueError:
                        pass
                if isinstance(v, dict):
                    v = v.get("name") or v.get("value")
                return str(v) if v is not None else None
    return None


def mpd_conf_sink() -> str | None:
    """Where mpd.conf sends its pipewire audio_output, if it says so.

    The pipewire plugin's option is `target`; `sink` belongs to the pulse
    plugin (MPD ignores it on pipewire) but old configs carry it over, so it is
    accepted as a fallback."""
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    for conf in (os.path.join(xdg, "mpd", "mpd.conf"), os.path.join(home, ".mpdconf"),
                 os.path.join(home, ".mpd", "mpd.conf"), "/etc/mpd.conf"):
        try:
            with open(conf, encoding="utf-8", errors="replace") as fh:
                text = re.sub(r"#[^\n]*", "", fh.read())
        except OSError:
            continue
        for block in re.findall(r"audio_output\s*\{(.*?)\}", text, re.S):
            props = dict(re.findall(r'(\w+)\s+"([^"]*)"', block))
            if props.get("type") == "pipewire" and (props.get("target") or props.get("sink")):
                return props.get("target") or props["sink"]
    return None


def eq_conf(target: str | None, bands, preamp) -> str:
    nodes = [f'{{ type = builtin name = pre label = bq_highshelf '
             f'control = {{ "Freq" = 0.0 "Q" = 1.0 "Gain" = {preamp:.2f} }} }}']
    for i, (f, g) in enumerate(zip(FREQS, bands)):
        nodes.append(f'{{ type = builtin name = b{i} label = bq_peaking '
                     f'control = {{ "Freq" = {f}.0 "Q" = {Q} "Gain" = {g:.2f} }} }}')
    links = ['{ output = "pre:Out" input = "b0:In" }'] + [
        f'{{ output = "b{i}:Out" input = "b{i + 1}:In" }}' for i in range(9)]
    target_line = f'target.object = "{target}"' if target else ""
    return f"""
context.properties = {{ log.level = 0 }}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-rt flags = [ ifexists nofail ] }}
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "Zebamp EQ"
            media.name       = "Zebamp EQ"
            filter.graph = {{
                nodes = [ {' '.join(nodes)} ]
                links = [ {' '.join(links)} ]
                inputs  = [ "pre:In" ]
                outputs = [ "b9:Out" ]
            }}
            audio.channels = 2
            audio.position = [ FL FR ]
            capture.props = {{
                node.name   = "{EQ_NODE}"
                media.class = Audio/Sink
                node.virtual = true
            }}
            playback.props = {{
                node.name    = "{EQ_NODE}.output"
                node.passive = true
                {target_line}
                node.dont-reconnect = false
            }}
        }}
    }}
]
"""


class PipeWireAudio:
    """Serialises PipeWire operations on a worker thread."""

    def __init__(self, stream_match="Music Player Daemon"):
        self.stream_match = stream_match
        self.q: queue.Queue = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.eq_on = False
        self.bands = [0.0] * 10
        self.preamp = 0.0
        self.balance = 0
        self._balance_applied = 0
        self._eq_node_id = None
        self._routed_stream = None
        self.target = None
        self.status = ""
        # keep the EQ filter (and balance) running when Zebamp closes, so the
        # music is never re-routed (no audible gap); the next start adopts it
        self.keep_on_exit = True
        self._thread = threading.Thread(target=self._loop, name="zebamp-pw", daemon=True)
        self._thread.start()
        atexit.register(self.shutdown_sync)

    # public API (non-blocking) ------------------------------------------
    def set_eq(self, enabled: bool, bands, preamp):
        self.q.put(("eq", enabled, list(bands), float(preamp)))

    def set_balance(self, balance: int):
        self.q.put(("balance", int(balance)))

    def ensure(self):
        """Re-check routing (MPD recreates its stream after stop/start)."""
        self.q.put(("ensure",))

    def cleanup_stale(self):
        self.q.put(("cleanup",))

    def shutdown(self):
        self.q.put(("quit",))

    # worker ---------------------------------------------------------------
    def _loop(self):
        while True:
            item = self.q.get()
            # coalesce bursts (slider drags): keep only the last eq/balance
            items = [item]
            try:
                while True:
                    items.append(self.q.get_nowait())
            except queue.Empty:
                pass
            last = {}
            order = []
            for it in items:
                if it[0] not in last:
                    order.append(it[0])
                last[it[0]] = it
            try:
                for kind in order:
                    it = last[kind]
                    if kind == "quit":
                        if self.keep_on_exit:
                            self._detach()
                        else:
                            self._stop_eq()
                            self._apply_balance(0, force=self._balance_applied != 0)
                        return
                    if kind == "eq":
                        self._do_eq(*it[1:])
                    elif kind == "balance":
                        self.balance = it[1]
                        self._apply_balance(self.balance)
                    elif kind == "ensure":
                        if self.eq_on:
                            self._route()
                        if self.balance:
                            self._apply_balance(self.balance, force=True)
                    elif kind == "cleanup":
                        self._cleanup()
            except Exception:
                log.exception("pipewire worker error")

    def _do_eq(self, enabled, bands, preamp):
        changed_gains = bands != self.bands or preamp != self.preamp
        self.bands, self.preamp = bands, preamp
        if enabled and not self.eq_on:
            self._start_eq()
        elif not enabled and self.eq_on:
            self._stop_eq()
        elif enabled and changed_gains:
            self._set_gains()

    def _start_eq(self):
        dump = pw_dump()
        stream = find_mpd_stream(dump, self.stream_match)
        # where the equalised audio goes: the destination configured in
        # mpd.conf first (the user's choice), else where MPD plays right now
        target = mpd_conf_sink()
        if not target or not find_node(dump, target) or is_dead_end(dump, target):
            target = None
            if stream is not None:
                cur = linked_sink(dump, stream["id"])
                if cur and cur != EQ_NODE and not is_dead_end(dump, cur):
                    target = cur
        self.target = target
        os.makedirs(RUNTIME, exist_ok=True)
        path = os.path.join(RUNTIME, "eq.conf")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(eq_conf(target, self.bands, self.preamp))
        existing = find_node(dump, EQ_NODE)
        if existing is not None and target:
            # a filter left running by an earlier session may point elsewhere
            out = find_node(dump, EQ_NODE + ".output")
            if out is not None and linked_sink(dump, out["id"]) not in (None, target):
                log.info("EQ filter sends to %s, wanted %s: recreating it",
                         linked_sink(dump, out["id"]), target)
                self._kill()
                existing = None
                time.sleep(0.2)
        if existing is None:
            try:
                self.proc = subprocess.Popen(["pipewire", "-c", path],
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True)
                with open(PIDFILE, "w") as fh:
                    fh.write(str(self.proc.pid))
            except OSError as e:
                self.status = f"No se pudo iniciar PipeWire EQ: {e}"
                log.warning(self.status)
                return
        node = None
        for _ in range(40):
            dump = pw_dump()
            node = find_node(dump, EQ_NODE)
            if node is not None:
                break
            time.sleep(0.1)
        if node is None:
            self.status = "El filtro EQ de PipeWire no apareció"
            log.warning(self.status)
            self._kill()
            return
        self._eq_node_id = node["id"]
        self.eq_on = True
        self.status = f"EQ activo → {target or 'salida por defecto'}"
        if existing is not None:
            self._set_gains()
        self._route(dump)

    def _route(self, dump=None):
        dump = dump if dump is not None else pw_dump()
        node = find_node(dump, EQ_NODE)
        if node is None:
            # filter process died; restart it
            self.eq_on = False
            self._kill()
            self._start_eq()
            return
        self._eq_node_id = node["id"]
        stream = find_mpd_stream(dump, self.stream_match)
        if stream is None:
            return
        sid = stream["id"]
        if stream_target(dump, sid) != EQ_NODE or linked_sink(dump, sid) != EQ_NODE:
            _run(["pw-metadata", str(sid), "target.object", EQ_NODE])
            self._routed_stream = sid

    def _set_gains(self):
        if self._eq_node_id is None:
            return
        params = [f'"pre:Gain" {self.preamp:.2f}']
        params += [f'"b{i}:Gain" {g:.2f}' for i, g in enumerate(self.bands)]
        _run(["pw-cli", "set-param", str(self._eq_node_id), "Props",
              "{ params = [ " + " ".join(params) + " ] }"])

    def _stop_eq(self):
        if self.eq_on or self.proc is not None:
            dump = pw_dump()
            stream = find_mpd_stream(dump, self.stream_match)
            if stream is not None and stream_target(dump, stream["id"]) == EQ_NODE:
                _run(["pw-metadata", "-d", str(stream["id"]), "target.object"])
            self._kill()
        self.eq_on = False
        self._eq_node_id = None
        self.status = "EQ apagado"

    def _detach(self):
        """Leave the running filter alone (no routing change at exit)."""
        self.proc = None
        self.eq_on = False

    def _kill(self):
        if self.proc is None:
            # a filter left running by a previous session: stop it by pid
            pids = []
            try:
                with open(PIDFILE) as fh:
                    pids.append(int(fh.read().strip()))
            except (OSError, ValueError):
                # older sessions didn't write a pid file: find it by command line
                want = os.path.join(RUNTIME, "eq.conf").encode()
                for d in os.listdir("/proc"):
                    if d.isdigit():
                        try:
                            with open(f"/proc/{d}/cmdline", "rb") as fh:
                                if want in fh.read():
                                    pids.append(int(d))
                        except OSError:
                            pass
            for pid in pids:
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as fh:
                        if b"eq.conf" in fh.read():
                            os.kill(pid, 15)
                except OSError:
                    pass
            try:
                os.unlink(PIDFILE)
            except OSError:
                pass
            return
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                try:
                    self.proc.kill()
                except OSError:
                    pass
            self.proc = None

    def _cleanup(self):
        """Undo leftovers of a previous crashed session."""
        dump = pw_dump()
        stream = find_mpd_stream(dump, self.stream_match)
        if stream is not None and stream_target(dump, stream["id"]) == EQ_NODE \
                and find_node(dump, EQ_NODE) is None:
            _run(["pw-metadata", "-d", str(stream["id"]), "target.object"])

    def _apply_balance(self, bal: int, force=False):
        if bal == self._balance_applied and not force:
            return
        dump = pw_dump()
        stream = find_mpd_stream(dump, self.stream_match)
        if stream is None:
            return
        left = 1.0 if bal <= 0 else max(0.0, 1 - bal / 100)
        right = 1.0 if bal >= 0 else max(0.0, 1 + bal / 100)
        _run(["pw-cli", "set-param", str(stream["id"]), "Props",
              f"{{ channelVolumes = [ {left:.3f} {right:.3f} ] }}"])
        self._balance_applied = bal

    def shutdown_sync(self):
        """Called at interpreter exit: make sure MPD is routed back."""
        if self.keep_on_exit:
            return
        if self.proc is not None or self.eq_on:
            try:
                dump = pw_dump()
                stream = find_mpd_stream(dump, self.stream_match)
                if stream is not None and stream_target(dump, stream["id"]) == EQ_NODE:
                    _run(["pw-metadata", "-d", str(stream["id"]), "target.object"], timeout=2)
            except Exception:
                pass
            self._kill()
            self.eq_on = False
