"""Single instance + remote commands (for global hotkeys in the WM).

`zebamp --siguiente`, `zebamp --buscar`... talk to the running Zebamp through
a local socket; launching Zebamp again just brings the open one forward.
"""
from __future__ import annotations

import json
import logging
import os

from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)


def server_name() -> str:
    return f"zebamp-{os.getuid()}"


def send_to_running(msg: dict, timeout=600) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(timeout):
        return False
    sock.write(json.dumps(msg).encode() + b"\n")
    sock.flush()
    sock.waitForBytesWritten(timeout)
    sock.disconnectFromServer()
    return True


def start_server(app) -> QLocalServer | None:
    srv = QLocalServer()
    QLocalServer.removeServer(server_name())   # stale socket from a crash
    if not srv.listen(server_name()):
        log.warning("IPC server failed: %s", srv.errorString())
        return None

    def on_conn():
        while srv.hasPendingConnections():
            s = srv.nextPendingConnection()
            buf = bytearray()

            def ready(s=s, buf=buf):
                buf.extend(bytes(s.readAll()))
                if b"\n" in buf:
                    line = bytes(buf).split(b"\n", 1)[0]
                    try:
                        app.run_command(json.loads(line.decode("utf-8", "replace")))
                    except (ValueError, TypeError) as e:
                        log.warning("bad IPC message: %s", e)
                    s.disconnectFromServer()
            s.readyRead.connect(ready)
            s.disconnected.connect(s.deleteLater)
    srv.newConnection.connect(on_conn)
    return srv
