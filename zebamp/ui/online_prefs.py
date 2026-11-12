"""Preferences page for what Zebamp looks up on the Internet about the
music: covers, and recognising songs by their sound (AcoustID)."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from .. import songid
from ..i18n import tr
from ..threads import run_bg


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    return label


class OnlinePage(QWidget):
    def __init__(self, app):
        super().__init__()
        cfg = app.cfg
        lay = QVBoxLayout(self)

        box = QGroupBox(tr("Carátulas"))
        inner = QVBoxLayout(box)
        self.covers = QCheckBox(tr("Buscar en Internet las carátulas que la música no trae"))
        self.covers.setChecked(bool(cfg["cover_online"]))
        inner.addWidget(self.covers)
        inner.addWidget(_note(tr("Se busca por las etiquetas; si faltan, por el nombre del archivo "
                                 "(«Artista - Título.mp3») y, si lo activas abajo, por el sonido de la canción.")))
        lay.addWidget(box)

        box = QGroupBox(tr("Reconocer canciones por su sonido"))
        form = QFormLayout(box)
        self.key = QLineEdit(cfg["acoustid_key"])
        self.state = QLabel()
        check = QPushButton(tr("Comprobar"))
        check.clicked.connect(self._check)
        form.addRow(tr("Clave de AcoustID:"), self.key)
        form.addRow(check, self.state)
        if not songid.available():
            form.addRow(_note(tr("Falta el programa «fpcalc» (paquete «chromaprint»): "
                                 "instálalo para usar esta función.")))
        form.addRow(_note(tr('Zebamp escucha el archivo, calcula su huella de audio y pregunta a AcoustID qué canción '
                             'es. Hace falta Internet y una clave gratuita de aplicación: créala en '
                             '<a href="https://acoustid.org/new-application">acoustid.org/new-application</a> '
                             'y pégala aquí. Sin clave solo se usan las etiquetas y el nombre del archivo.')))
        lay.addWidget(box)
        lay.addStretch(1)

    def _check(self):
        key = self.key.text().strip()
        if not key:
            self.state.setText(tr("Falta la clave"))
            return
        self.state.setText(tr("Comprobando…"))
        run_bg(lambda: songid.key_accepted(key), self._checked)

    def _checked(self, accepted):
        if accepted is True:
            self.state.setText(tr("Clave aceptada"))
        elif accepted is False:
            self.state.setText(tr("AcoustID no acepta esa clave"))
        else:
            self.state.setText(tr("No se pudo comprobar"))

    def save(self, cfg):
        cfg["cover_online"] = self.covers.isChecked()
        cfg["acoustid_key"] = self.key.text().strip()
