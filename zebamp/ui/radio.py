"""Internet radio directory (radio-browser.info, the free SHOUTcast-like
directory) with favourites."""
from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from ..threads import http_json, run_bg
from ..i18n import tr

API = "https://all.api.radio-browser.info/json"
ROLE = Qt.ItemDataRole.UserRole


class RadioDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(tr("Radio por Internet - Zebamp"))
        self.setPalette(getattr(app, "dialog_palette", self.palette()))
        self.resize(860, 540)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems([tr("Nombre"), tr("Género / etiqueta"), tr("País"), tr("Idioma"),
                            tr("Más escuchadas"), tr("Más votadas"), tr("Favoritas")])
        self.mode.currentIndexChanged.connect(self._mode_changed)
        top.addWidget(self.mode)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Escribe y pulsa Enter (p. ej. jazz, rock, salsa, España, BBC…)"))
        self.edit.returnPressed.connect(self.search)
        top.addWidget(self.edit, 1)
        b = QPushButton(tr("Buscar"))
        b.clicked.connect(self.search)
        top.addWidget(b)
        lay.addLayout(top)
        self.list = QTreeWidget()
        self.list.setHeaderLabels([tr("Emisora"), tr("Género"), tr("País"), tr("Calidad"), tr("Votos")])
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        h = self.list.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in ((1, 220), (2, 110), (3, 90), (4, 60)):
            h.resizeSection(i, w)
        self.list.itemDoubleClicked.connect(lambda *_: self.play())
        lay.addWidget(self.list, 1)
        self.status = QLabel("")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        for text, fn in ((tr("Escuchar"), self.play), (tr("Añadir a la lista"), self.enqueue),
                         (tr("★ Favorita"), self.toggle_fav), (tr("Cerrar"), self.reject)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        lay.addLayout(row)
        QTimer.singleShot(0, lambda: self._load("topclick"))

    # ---------------------------------------------------------------- data
    def _mode_changed(self, i):
        if i == 4:
            self._load("topclick")
        elif i == 5:
            self._load("topvote")
        elif i == 6:
            self._show(list(self.app.cfg["radio_favorites"] or []), fav=True)

    def search(self):
        q = self.edit.text().strip()
        i = self.mode.currentIndex()
        if i >= 4:
            self._mode_changed(i)
            return
        if not q:
            return
        field = ("name", "tag", "country", "language")[i]
        self._load(f"search?{field}={quote(q)}&hidebroken=true&order=clickcount&reverse=true&limit=300")

    def _load(self, what):
        if what in ("topclick", "topvote"):
            url = f"{API}/stations/{what}/200?hidebroken=true"
        else:
            url = f"{API}/stations/{what}"
        self.status.setText(tr("Buscando emisoras…"))
        run_bg(lambda: http_json(url), self._loaded)

    def _loaded(self, res):
        if isinstance(res, Exception) or not isinstance(res, list):
            self.status.setText(tr("No se pudo consultar el directorio de radios: {0}").format(res))
            return
        self._show(res)

    def _show(self, stations, fav=False):
        self.list.clear()
        items = []
        for st in stations:
            url = st.get("url_resolved") or st.get("url")
            if not url:
                continue
            br = st.get("bitrate") or 0
            q = f"{st.get('codec', '')} {br} kbps".strip() if br else (st.get("codec") or "")
            it = QTreeWidgetItem([(st.get("name") or "").strip(), (st.get("tags") or "").replace(",", ", ")[:80],
                                  st.get("country") or st.get("countrycode") or "", q,
                                  str(st.get("votes") or "")])
            it.setData(0, ROLE, {"name": (st.get("name") or "").strip(), "url": url,
                                 "tags": st.get("tags") or "", "country": st.get("country") or "",
                                 "codec": st.get("codec") or "", "bitrate": br,
                                 "votes": st.get("votes") or 0, "stationuuid": st.get("stationuuid", "")})
            it.setToolTip(0, url)
            items.append(it)
        self.list.addTopLevelItems(items)
        count = (tr("{0} emisoras favoritas") if fav else tr("{0} emisoras")).format(len(items))
        self.status.setText(count + tr(". Doble clic o Enter para escuchar."))

    def _selected(self):
        return [it.data(0, ROLE) for it in self.list.selectedItems()] or \
            ([self.list.currentItem().data(0, ROLE)] if self.list.currentItem() else [])

    # ------------------------------------------------------------- actions
    def play(self):
        st = self._selected()
        if st:
            self.app.player.add([s["url"] for s in st], play_first=True)
            uuid = st[0].get("stationuuid")
            if uuid:   # radio-browser asks clients to report plays (popularity)
                run_bg(lambda: http_json(f"{API}/url/{uuid}"))

    def enqueue(self):
        st = self._selected()
        if st:
            self.app.player.add([s["url"] for s in st])
            self.status.setText(tr("Añadidas {0} emisoras a la lista.").format(len(st)))

    def toggle_fav(self):
        favs = list(self.app.cfg["radio_favorites"] or [])
        urls = {f.get("url") for f in favs}
        for s in self._selected():
            if s["url"] in urls:
                favs = [f for f in favs if f.get("url") != s["url"]]
            else:
                favs.append(s)
        self.app.cfg["radio_favorites"] = favs
        self.app.cfg.save()
        self.status.setText(tr("{0} emisoras favoritas.").format(len(favs)))
        if self.mode.currentIndex() == 6:
            self._show(favs, fav=True)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.list.hasFocus():
            self.play()
            return
        super().keyPressEvent(ev)
