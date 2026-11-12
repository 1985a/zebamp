"""Preferences page for scrobbling (ListenBrainz and Last.fm accounts)."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ..scrobble import LastFm, ListenBrainz
from ..threads import run_bg
from ..i18n import tr


def _secret_edit(text: str) -> QLineEdit:
    edit = QLineEdit(text)
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    return label


class ScrobblePage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        cfg = app.cfg
        lay = QVBoxLayout(self)
        lay.addWidget(_note(tr("Envía lo que escuchas a tu perfil. Una canción cuenta cuando suena más "
                               "de la mitad (o cuatro minutos). Sin conexión se guarda y se envía "
                               "después.")))

        # ListenBrainz: one token, nothing else
        box = QGroupBox("ListenBrainz")
        form = QFormLayout(box)
        self.lb_on = QCheckBox(tr("Enviar a ListenBrainz"))
        self.lb_on.setChecked(bool(cfg["listenbrainz_enabled"]))
        self.lb_token = _secret_edit(cfg["listenbrainz_token"])
        self.lb_url = QLineEdit(cfg["listenbrainz_url"])
        self.lb_url.setPlaceholderText(tr("https://api.listenbrainz.org (o tu servidor compatible)"))
        self.lb_state = QLabel(app.scrobbler.describe("listenbrainz"))
        check = QPushButton(tr("Comprobar"))
        check.clicked.connect(self._check_listenbrainz)
        form.addRow(self.lb_on)
        form.addRow(tr("Token de usuario:"), self.lb_token)
        form.addRow(tr("Servidor:"), self.lb_url)
        form.addRow(check, self.lb_state)
        form.addRow(_note(tr("El token está en <a "
                             "href=\"https://listenbrainz.org/settings/\">listenbrainz.org/settings</a>.")))
        lay.addWidget(box)

        # Last.fm: the user's own API key, then approval in the browser
        box = QGroupBox("Last.fm")
        form = QFormLayout(box)
        self.fm_on = QCheckBox(tr("Enviar a Last.fm"))
        self.fm_on.setChecked(bool(cfg["lastfm_enabled"]))
        self.fm_key = QLineEdit(cfg["lastfm_api_key"])
        self.fm_secret = _secret_edit(cfg["lastfm_secret"])
        self.fm_session = cfg["lastfm_session"]
        self.fm_user = cfg["lastfm_user"]
        self._fm_token = ""
        self.fm_state = QLabel()
        self.fm_button = QPushButton()
        self.fm_button.clicked.connect(self._lastfm_step)
        form.addRow(self.fm_on)
        form.addRow(tr("Clave de API:"), self.fm_key)
        form.addRow(tr("Secreto:"), self.fm_secret)
        form.addRow(self.fm_button, self.fm_state)
        form.addRow(_note(tr("Crea tu clave gratis en <a "
                             "href=\"https://www.last.fm/api/account/create\">last.fm/api/account/create</a> "
                             "y pulsa «Conectar».")))
        lay.addWidget(box)
        lay.addStretch(1)
        self._show_lastfm_state()

    # ------------------------------------------------------- ListenBrainz
    def _check_listenbrainz(self):
        token = self.lb_token.text().strip()
        if not token:
            self.lb_state.setText(tr("Falta el token"))
            return
        self.lb_state.setText(tr("Comprobando…"))
        service = ListenBrainz(token, self.lb_url.text().strip())
        run_bg(service.check, self._listenbrainz_checked)

    def _listenbrainz_checked(self, result):
        if isinstance(result, Exception):
            self.lb_state.setText(tr("No se pudo comprobar"))
            return
        accepted, detail = result
        self.lb_state.setText(tr("Correcto: {0}").format(detail) if accepted else tr("No válido: {0}").format(detail))

    # ------------------------------------------------------------ Last.fm
    def _lastfm(self) -> LastFm:
        return LastFm(self.fm_key.text().strip(), self.fm_secret.text().strip(), url=self.app.cfg["lastfm_url"])

    def _show_lastfm_state(self, message: str = ""):
        if self._fm_token:
            self.fm_button.setText(tr("Ya lo autoricé"))
            self.fm_state.setText(message or tr("Autoriza Zebamp en el navegador y vuelve aquí"))
        elif self.fm_session:
            self.fm_button.setText(tr("Desconectar"))
            self.fm_state.setText(message or tr("Conectado como {0}").format(self.fm_user or '?'))
        else:
            self.fm_button.setText(tr("Conectar…"))
            self.fm_state.setText(message or tr("Sin conectar"))

    def _lastfm_step(self):
        if self._fm_token:
            token, self._fm_token = self._fm_token, ""
            self.fm_state.setText(tr("Comprobando…"))
            run_bg(lambda: self._lastfm().open_session(token), self._lastfm_session_opened)
        elif self.fm_session:
            self.fm_session = self.fm_user = ""
            self._show_lastfm_state()
        elif not self.fm_key.text().strip() or not self.fm_secret.text().strip():
            self._show_lastfm_state(tr("Faltan la clave y el secreto"))
        else:
            self.fm_state.setText(tr("Pidiendo permiso…"))
            run_bg(self._lastfm().request_token, self._lastfm_token_received)

    def _lastfm_token_received(self, token):
        if isinstance(token, Exception) or not token:
            self._show_lastfm_state(tr("Last.fm no aceptó la clave"))
            return
        self._fm_token = token
        QDesktopServices.openUrl(QUrl(self._lastfm().approval_url(token)))
        self._show_lastfm_state()

    def _lastfm_session_opened(self, result):
        if isinstance(result, Exception) or not result[0]:
            self._show_lastfm_state(tr("No se autorizó; pulsa «Conectar» otra vez"))
            return
        self.fm_session, self.fm_user = result
        self._show_lastfm_state()

    # --------------------------------------------------------------- save
    def save(self, cfg):
        cfg["listenbrainz_enabled"] = self.lb_on.isChecked()
        cfg["listenbrainz_token"] = self.lb_token.text().strip()
        cfg["listenbrainz_url"] = self.lb_url.text().strip()
        cfg["lastfm_enabled"] = self.fm_on.isChecked()
        cfg["lastfm_api_key"] = self.fm_key.text().strip()
        cfg["lastfm_secret"] = self.fm_secret.text().strip()
        cfg["lastfm_session"] = self.fm_session
        cfg["lastfm_user"] = self.fm_user
