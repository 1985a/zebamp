"""Entry point: python -m zebamp"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="zebamp", description="Reproductor estilo Winamp para MPD")
    ap.add_argument("--host", help="servidor MPD o ruta del socket")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--skin", help="skin .wsz/.wal a cargar")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--buscar", "--search", dest="cmd", action="append_const", const="search",
                    help="abrir la búsqueda de canciones (en la instancia abierta)")
    ap.add_argument("--saltar", "--jump", dest="cmd", action="append_const", const="jump",
                    help="abrir «saltar a archivo»")
    for name, alias, help_ in (("play", "reproducir", "reproducir"), ("pause", "pausa", "pausar"),
                               ("toggle", "play-pausa", "reproducir/pausar"), ("stop", "detener", "detener"),
                               ("next", "siguiente", "siguiente canción"),
                               ("prev", "anterior", "canción anterior"),
                               ("milkdrop", "milkdrop", "abrir/cerrar la visualización MilkDrop"),
                               ("lyrics", "letras", "abrir la ventana de letras"),
                               ("radio", "radio", "abrir la radio por Internet"),
                               ("help", "ayuda", "abrir la ayuda de Zebamp")):
        flags = [f"--{alias}"]
        if name == "help":
            flags.append("--manual")        # --help is argparse's own
        elif name != alias:
            flags.append(f"--{name}")
        ap.add_argument(*flags, dest="cmd", action="append_const", const=name, help=help_)
    ap.add_argument("files", nargs="*", help="archivos o URLs a reproducir")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setDesktopFileName("zebamp")
    qapp = QApplication(sys.argv[:1])
    from .ipc import send_to_running, start_server
    msg = {"cmd": args.cmd or ["show"],
           "files": [f if "://" in f else os.path.abspath(f) for f in args.files]}
    if send_to_running(msg):
        return 0
    qapp.setApplicationName("zebamp")
    qapp.setApplicationDisplayName("Zebamp")
    qapp.setQuitOnLastWindowClosed(False)
    from PySide6.QtGui import QIcon
    icon_path = os.path.join(os.path.dirname(__file__), "data", "zebamp.png")
    qapp.setWindowIcon(QIcon.fromTheme("zebamp", QIcon(icon_path)))
    from .app import ZebampApp

    app = ZebampApp(qapp, args)
    app.show()
    app.ipc = start_server(app)
    from .mpris import start as start_mpris
    app.mpris = start_mpris(app)
    from .tray import Tray
    app.tray = Tray(app)
    if args.cmd:
        QTimer.singleShot(800, lambda: app.run_command({"cmd": args.cmd, "files": []}))
    if args.files:
        files = [f if "://" in f else os.path.abspath(f) for f in args.files]
        QTimer.singleShot(300, lambda: app.open_paths(files))
    # Let Ctrl+C in a terminal quit cleanly.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    t = QTimer()
    t.start(500)
    t.timeout.connect(lambda: None)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
