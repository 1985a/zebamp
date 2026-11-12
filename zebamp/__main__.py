"""Entry point: python -m zebamp"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys


def _language_argument(argv) -> str | None:
    """`--lang xx` read by hand: the language is needed before the argument
    parser (whose own help is translated) exists."""
    args = list(sys.argv[1:] if argv is None else argv)
    for i, arg in enumerate(args):
        if arg == "--lang" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def main(argv=None):
    from . import i18n
    from .config import Config
    # first of all: every module imported from here on already speaks the language
    i18n.setup(_language_argument(argv) or Config()["language"])
    tr = i18n.tr
    ap = argparse.ArgumentParser(prog="zebamp", description=tr("Reproductor estilo Winamp para MPD"))
    ap.add_argument("--host", help=tr("servidor MPD o ruta del socket"))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--skin", help=tr("skin .wsz/.wal a cargar"))
    ap.add_argument("--lang", choices=[*i18n.LANGUAGES, "auto"],
                    help=tr("idioma de la interfaz solo para esta vez"))
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--buscar", "--search", dest="cmd", action="append_const", const="search",
                    help=tr("abrir la búsqueda de canciones (en la instancia abierta)"))
    ap.add_argument("--saltar", "--jump", dest="cmd", action="append_const", const="jump",
                    help=tr("abrir «saltar a archivo»"))
    for name, alias, help_ in (("play", "reproducir", tr("reproducir")), ("pause", "pausa", tr("pausar")),
                               ("toggle", "play-pausa", tr("reproducir/pausar")),
                               ("stop", "detener", tr("detener")),
                               ("next", "siguiente", tr("siguiente canción")),
                               ("prev", "anterior", tr("canción anterior")),
                               ("milkdrop", "milkdrop", tr("abrir/cerrar la visualización MilkDrop")),
                               ("lyrics", "letras", tr("abrir la ventana de letras")),
                               ("radio", "radio", tr("abrir la radio por Internet")),
                               ("help", "ayuda", tr("abrir la ayuda de Zebamp"))):
        flags = [f"--{alias}"]
        if name == "help":
            flags.append("--manual")        # --help is argparse's own
        elif name != alias:
            flags.append(f"--{name}")
        ap.add_argument(*flags, dest="cmd", action="append_const", const=name, help=help_)
    ap.add_argument("files", nargs="*", help=tr("archivos o URLs a reproducir"))
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
