"""Dialogs: file info, jump to file, preferences, skin browser, playlists."""
from __future__ import annotations

import os
import shutil
import time

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..config import SKIN_DIR
from ..mpdconn import autodetect_address
from ..player import fmt_time, song_duration, song_title


def _style(dlg: QDialog, app):
    pal = getattr(app, "dialog_palette", None)
    if pal is not None:
        dlg.setPalette(pal)
    dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)


def install_skin(path: str) -> str | None:
    """Copy a skin into the skins folder (unless it's already there)."""
    try:
        os.makedirs(SKIN_DIR, exist_ok=True)
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(SKIN_DIR):
            return path
        dest = os.path.join(SKIN_DIR, os.path.basename(path))
        if os.path.isdir(path):
            if not os.path.exists(dest):
                shutil.copytree(path, dest)
        else:
            shutil.copy2(path, dest)
        return dest
    except OSError:
        return None


# ------------------------------------------------------------- file info
TAGS = [("title", "Título"), ("artist", "Artista"), ("album", "Álbum"),
        ("albumartist", "Artista del álbum"), ("date", "Año"), ("track", "Pista"),
        ("disc", "Disco"), ("genre", "Género"), ("composer", "Compositor"),
        ("performer", "Intérprete"), ("comment", "Comentario"), ("name", "Nombre"),
        ("label", "Sello")]


class FileInfoDialog(QDialog):
    """File info like Winamp's (Alt+3): tags are editable when the file is
    reachable locally; saving asks for confirmation first."""

    def __init__(self, app, song: dict):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.song = song
        self.setWindowTitle("Información del archivo")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        from .. import tagedit
        self.tagedit = tagedit
        f = song.get("file", "")
        self.uri = f
        self.path = tagedit.local_path(app.player, f) if tagedit.available() else None
        self.orig = {}
        self.edits = {}
        self.new_cover: bytes | None = None
        self.remove_cover = False
        if self.path:
            try:
                self.orig = tagedit.read_tags(self.path)
            except Exception as e:
                self.path = None
                self._why = str(e)
        lay = QHBoxLayout(self)
        form = QFormLayout()
        path = QLineEdit(self.path or f)
        path.setReadOnly(True)
        path.setMinimumWidth(400)
        form.addRow("Archivo:", path)
        if self.path:
            for key, label in tagedit.FIELDS:
                e = QLineEdit(self.orig.get(key, ""))
                e.textChanged.connect(self._dirty)
                self.edits[key] = e
                form.addRow(label + ":", e)
            hint = QLabel("Varios valores: sepáralos con «;». Los cambios se escriben en el archivo.")
            hint.setWordWrap(True)
            form.addRow(hint)
        else:
            for key, label in TAGS:
                v = song.get(key)
                if v:
                    val = ", ".join(v) if isinstance(v, list) else str(v)
                    e = QLineEdit(val)
                    e.setReadOnly(True)
                    form.addRow(label + ":", e)
            why = getattr(self, "_why", "")
            if "://" in f:
                why = "es una emisión por Internet"
            elif not tagedit.available():
                why = "falta el módulo «mutagen» de Python"
            elif not why:
                why = "el archivo no está en este equipo (MPD remoto)"
            note = QLabel(f"Solo lectura: {why}.")
            note.setWordWrap(True)
            form.addRow(note)
        st = app.player.status if song.get("id") == app.player.song.get("id") else {}
        info = []
        d = song_duration(song)
        if d:
            info.append(f"Duración: {fmt_time(d)}")
        if st.get("audio"):
            rate, bits, ch = app.player.audio
            info.append(f"{rate} Hz, {bits or '?'} bits, {'mono' if ch == 1 else f'{ch} canales'}")
        if st.get("bitrate"):
            info.append(f"{st.get('bitrate')} kbps")
        fmt = song.get("format")
        if fmt:
            info.append(f"Formato: {fmt}")
        if song.get("last-modified"):
            info.append(f"Modificado: {song['last-modified']}")
        stats = getattr(app, "stats", None)
        if stats is not None and f:
            n = stats.playcount(f)
            info.append(f"Valoración: {'★' * stats.rating(f) or '—'}   Escuchada: {n} {'vez' if n == 1 else 'veces'}")
        form.addRow(QLabel("\n".join(info)))
        lay.addLayout(form)
        side = QVBoxLayout()
        self.art = QLabel()
        self.art.setFixedSize(220, 220)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setText("(sin carátula)")
        side.addWidget(self.art)
        if self.path:
            b1 = QPushButton("Cambiar carátula…")
            b1.clicked.connect(self._pick_cover)
            side.addWidget(b1)
            b2 = QPushButton("Quitar carátula incrustada")
            b2.clicked.connect(self._drop_cover)
            side.addWidget(b2)
        side.addStretch(1)
        lay.addLayout(side)
        if f:
            QTimer.singleShot(0, lambda: self._load_art(f))
        if self.path:
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
            self.save_btn = bb.button(QDialogButtonBox.StandardButton.Save)
            self.save_btn.setText("Guardar cambios…")
            self.save_btn.setEnabled(False)
            bb.accepted.connect(self._save)
        else:
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.close)
        form.addRow(bb)

    # ------------------------------------------------------------ editing
    def _changes(self):
        out = {}
        for k, e in self.edits.items():
            new = e.text().strip()
            if new != self.orig.get(k, "").strip():
                out[k] = new
        return out

    def _dirty(self, *_):
        if hasattr(self, "save_btn"):
            self.save_btn.setEnabled(bool(self._changes()) or self.new_cover is not None or self.remove_cover)

    def _pick_cover(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Elegir carátula", os.path.dirname(self.path or ""),
                                            "Imágenes (*.jpg *.jpeg *.png)")
        if not fn:
            return
        try:
            with open(fn, "rb") as fh:
                data = fh.read()
        except OSError as e:
            QMessageBox.warning(self, "Carátula", str(e))
            return
        img = QImage.fromData(data)
        if img.isNull():
            QMessageBox.warning(self, "Carátula", "No es una imagen válida.")
            return
        self.new_cover, self.remove_cover = data, False
        self.art.setPixmap(QPixmap.fromImage(img).scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
        self._dirty()

    def _drop_cover(self):
        self.new_cover, self.remove_cover = None, True
        self.art.setPixmap(QPixmap())
        self.art.setText("(se quitará la carátula)")
        self._dirty()

    def _save(self):
        changes = self._changes()
        labels = dict(self.tagedit.FIELDS)
        lines = [f"• {labels[k]}: «{self.orig.get(k, '') or '—'}» → «{v or '(vacío)'}»"
                 for k, v in changes.items()]
        if self.new_cover is not None:
            lines.append("• Carátula: se incrusta la imagen elegida")
        if self.remove_cover:
            lines.append("• Carátula: se quita la imagen incrustada")
        if not lines:
            return
        msg = (f"Se modificará el archivo:\n{self.path}\n\n" + "\n".join(lines) +
               "\n\n¿Guardar estos cambios?")
        ok = QMessageBox.question(self, "Confirmar cambios", msg,
                                  QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                                  QMessageBox.StandardButton.Cancel)
        if ok != QMessageBox.StandardButton.Save:
            return
        try:
            if changes:
                self.tagedit.write_tags(self.path, changes)
            if self.new_cover is not None or self.remove_cover:
                self.tagedit.write_cover(self.path, self.new_cover)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo guardar", f"{self.path}\n\n{e}")
            return
        # forget cached covers and let MPD re-read the file
        from ..notify import cover_path
        try:
            os.unlink(cover_path(self.uri))
        except OSError:
            pass
        self.app.player.update_database(os.path.dirname(self.uri) or self.uri)
        self.orig.update(changes)
        self.new_cover, self.remove_cover = None, False
        self._dirty()
        QMessageBox.information(self, "Guardado", "Cambios guardados. MPD está releyendo el archivo.")

    def _load_art(self, uri):
        app = self.app

        def job(client):
            for cmd in ("readpicture", "albumart"):
                try:
                    r = getattr(client, cmd)(uri)
                    if isinstance(r, dict) and r.get("binary"):
                        return r["binary"]
                except Exception:
                    continue
            return None

        def done(data):
            try:
                if data:
                    img = QImage.fromData(data)
                    if not img.isNull():
                        pm = QPixmap.fromImage(img).scaled(
                            220, 220, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        self.art.setPixmap(pm)
            except RuntimeError:
                pass  # dialog already closed
        app.player.conn.run_async(job, done)


# ---------------------------------------------------------- jump to file
class JumpToFileDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.setWindowTitle("Saltar a archivo")
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Escribe para buscar en la lista…")
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._play)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Reproducir", self._play), ("Encolar a continuación", self._queue_next),
                         ("Cerrar", self.reject)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        lay.addLayout(row)
        self._entries = [(i, f"{i + 1}. {song_title(s)}", (song_title(s) + " " + s.get("file", "")).lower())
                         for i, s in enumerate(app.player.queue)]
        self._filter("")

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress and ev.key() in (
                Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            self.list.setFocus()
            self.list.keyPressEvent(ev)
            self.edit.setFocus()
            return True
        return super().eventFilter(obj, ev)

    def _filter(self, text):
        words = text.lower().split()
        self.list.clear()
        for i, label, hay in self._entries:
            if all(w in hay for w in words):
                it = QListWidgetItem(label)
                it.setData(Qt.ItemDataRole.UserRole, i)
                self.list.addItem(it)
                if self.list.count() > 5000:
                    break
        if self.list.count():
            self.list.setCurrentRow(0)

    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _play(self, *_):
        i = self._current()
        if i is not None:
            self.app.player.play(i)
            self.accept()

    def _queue_next(self):
        i = self._current()
        if i is None:
            return
        sid = self.app.player.queue[i].get("id")
        if sid is not None:
            self.app.player.queue_next_ids([str(sid)])
        self.accept()


class _ResultModel(QAbstractTableModel):
    HEAD = ["Título", "Artista", "Álbum", "Duración"]

    def __init__(self):
        super().__init__()
        self.rows: list = []      # row lists (see libindex.FIELDS)
        self.idx: list[int] = []

    def set(self, rows, idx):
        self.beginResetModel()
        self.rows, self.idx = rows, idx
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.idx)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, section, orient, role=Qt.ItemDataRole.DisplayRole):
        if orient == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEAD[section]
        return None

    def row(self, r):
        return self.rows[self.idx[r]]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[self.idx[index.row()]]
        c = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                return row[1] or os.path.basename(row[0])
            if c == 1:
                return row[2] or row[4]
            if c == 2:
                return row[3]
            try:
                return fmt_time(float(row[6])) if row[6] else ""
            except (TypeError, ValueError):
                return ""
        if role == Qt.ItemDataRole.ToolTipRole and c == 0:
            return row[0]
        if role == Qt.ItemDataRole.TextAlignmentRole and c == 3:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class SearchLibraryDialog(QDialog):
    """Instant search over the whole MPD library (Ctrl+F / F3 / /).

    Uses the in-memory LibraryIndex (100k+ songs filter in a few ms; more
    letters narrow the previous result).  Enter plays the song now,
    Ctrl+Enter plays it next, Shift+Enter or Insert appends it.
    """

    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.index = app.library_index
        self.setWindowTitle("Buscar canciones")
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Artista, título, álbum, género, archivo…  (sin importar tildes)")
        self.edit.setClearButtonEnabled(True)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        from PySide6.QtWidgets import QHeaderView, QTreeView
        self.model = _ResultModel()
        self.list = QTreeView()
        self.list.setModel(self.model)
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hv = self.list.header()
        hv.setStretchLastSection(False)
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2):
            hv.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            hv.resizeSection(c, 200)
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hv.resizeSection(3, 70)
        self.list.activated.connect(lambda *_: self._play())
        lay.addWidget(self.list)
        self.status = QLabel("")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        for text, fn in (("Reproducir (Enter)", self._play),
                         ("A continuación (Ctrl+Enter)", self._play_next),
                         ("Añadir a la lista (Insert)", self._enqueue),
                         ("Cerrar", self.reject)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        lay.addLayout(row)
        # coalesce bursts of keystrokes into one search per event-loop turn
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._search)
        self.edit.textChanged.connect(lambda _t: self._timer.start())
        self.index.ready.connect(self._on_ready)
        if not self.index.is_ready:
            self.index.refresh()
        self._on_ready()

    def _on_ready(self):
        if self.index.is_ready:
            self.status.setText(f"{len(self.index.rows):,} canciones en la biblioteca.".replace(",", "."))
            if self.edit.text().strip():
                self._search()
        else:
            self.status.setText("Preparando el índice de la biblioteca…")

    @staticmethod
    def build_query(text: str, tag="any"):
        """MPD filter expression (used by tests and as a fallback)."""
        words = [w for w in text.split() if w]
        if not words:
            return None

        def q(w):
            return '"' + w.replace("\\", "\\\\").replace('"', '\\"') + '"'
        expr = " AND ".join(f"({tag} contains {q(w)})" for w in words)
        return f"({expr})" if len(words) > 1 else expr

    def _search(self):
        text = self.edit.text()
        if not self.index.is_ready:
            return
        t = time.perf_counter()
        res = self.index.search(text) if text.strip() else []
        self.model.set(self.index.rows, res)
        if res:
            self.list.setCurrentIndex(self.model.index(0, 0))
        ms = (time.perf_counter() - t) * 1000
        n = len(res)
        if not text.strip():
            self._on_ready()
        else:
            self.status.setText("Sin resultados." if not n else
                                f"{n:,} canciones ({ms:.0f} ms). ".replace(",", ".") +
                                "Enter: reproducir · Ctrl+Enter: a continuación · Insert: añadir")

    def _uris(self):
        rows = sorted({i.row() for i in self.list.selectionModel().selectedRows()})
        if not rows and self.list.currentIndex().isValid():
            rows = [self.list.currentIndex().row()]
        return [self.model.row(r)[0] for r in rows]

    def _play(self):
        uris = self._uris()
        if uris:
            self.app.player.add(uris, play_first=True)
            self.accept()

    def _play_next(self):
        uris = self._uris()
        if not uris:
            return
        self.app.player.add_next(uris)
        self.accept()

    def _enqueue(self):
        uris = self._uris()
        if uris:
            self.app.player.add(uris)
            self.status.setText(f"Añadidas {len(uris)} a la lista.")

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.KeyPress:
            k = ev.key()
            mods = ev.modifiers()
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._timer.isActive():
                    self._timer.stop()
                    self._search()
                if mods & Qt.KeyboardModifier.ControlModifier:
                    self._play_next()
                elif mods & Qt.KeyboardModifier.ShiftModifier:
                    self._enqueue()
                else:
                    self._play()
                return True
            if k == Qt.Key.Key_Insert:
                self._enqueue()
                return True
            if obj is self.edit and k in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                                          Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                self.list.setFocus()
                self.list.keyPressEvent(ev)
                self.edit.setFocus()
                return True
        return super().eventFilter(obj, ev)


# ---------------------------------------------------------- playlists
def save_playlist_dialog(app):
    names = app.player.stored_playlists()
    name, ok = QInputDialog.getItem(None, "Guardar lista", "Nombre de la lista en MPD:",
                                    names or [""], 0, True)
    name = (name or "").strip()
    if not ok or not name:
        return
    if name in names:
        r = QMessageBox.question(None, "Guardar lista", f"¿Sobrescribir «{name}»?")
        if r != QMessageBox.StandardButton.Yes:
            return
    if not app.player.save_playlist(name):
        QMessageBox.warning(None, "Zebamp", "MPD no pudo guardar la lista.")


class PlaylistsDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.setWindowTitle("Listas guardadas en MPD")
        self.resize(380, 420)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda *_: self._load(True))
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Cargar", lambda: self._load(True)), ("Añadir", lambda: self._load(False)),
                         ("Borrar", self._delete), ("Renombrar", self._rename),
                         ("Importar .m3u…", self._import), ("Cerrar", self.reject)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        for n in self.app.player.stored_playlists():
            self.list.addItem(n)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _name(self):
        it = self.list.currentItem()
        return it.text() if it else None

    def _load(self, replace):
        n = self._name()
        if n:
            self.app.player.load_playlist(n, replace=replace)
            self.accept()

    def _delete(self):
        n = self._name()
        if n and QMessageBox.question(self, "Borrar", f"¿Borrar la lista «{n}» de MPD?") == \
                QMessageBox.StandardButton.Yes:
            self.app.player.delete_playlist(n)
            self._refresh()

    def _rename(self):
        n = self._name()
        if not n:
            return
        new, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=n)
        if ok and new.strip() and new.strip() != n:
            self.app.player.conn.call("rename", n, new.strip())
            self._refresh()

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importar lista", os.path.expanduser("~"),
                                           "Listas (*.m3u *.m3u8 *.pls);;Todos (*)")
        if not f:
            return
        from ..player import read_playlist_file
        uris = read_playlist_file(f)
        local = [u for u in uris if "://" not in u]
        remote = [u for u in uris if "://" in u]
        if local:
            self.app.player.add_paths(local)
        if remote:
            self.app.player.add(remote)
        self.accept()


# ------------------------------------------------------------- skins
def render_preview(app, path: str, size=QSize(275, 116)) -> QPixmap | None:
    from ..skin.classic import is_classic_skin, load_classic
    try:
        if not is_classic_skin(path):
            return None
        skin = load_classic(path, fallback=app.base_skin)
    except Exception:
        return None
    pm = QPixmap(275, 116)
    p = QPainter(pm)
    p.drawPixmap(0, 0, skin.sprite("MAIN", "MAIN_WINDOW_BACKGROUND"))
    p.drawPixmap(0, 0, skin.sprite("TITLEBAR", "TITLE_SEL"))
    for name, x, y in (("PREV", 16, 88), ("PLAY", 39, 88), ("PAUSE", 62, 88), ("STOP", 85, 88),
                       ("NEXT", 108, 88), ("EJECT", 136, 89)):
        p.drawPixmap(x, y, skin.sprite("CBUTTONS", name))
    p.drawPixmap(16, 72, skin.sprite("POSBAR", "POS_BG"))
    p.drawPixmap(107, 57, skin.volume_frame(20))
    p.drawPixmap(177, 57, skin.balance_frame(0))
    p.drawPixmap(164, 89, skin.sprite("SHUFREP", "SHUFFLE"))
    p.drawPixmap(210, 89, skin.sprite("SHUFREP", "REPEAT"))
    p.drawPixmap(219, 58, skin.sprite("SHUFREP", "EQ_SEL"))
    p.drawPixmap(242, 58, skin.sprite("SHUFREP", "PL_SEL"))
    p.end()
    return pm


class SkinBrowser(QDialog):
    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.setWindowTitle("Explorador de skins")
        self.resize(640, 460)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._preview)
        self.list.itemActivated.connect(lambda *_: self._apply())
        left.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Añadir skin…", self._add), ("Borrar", self._delete),
                         ("Carpeta", self._folder)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        left.addLayout(row)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(275 * 2, 116 * 2)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.preview)
        self.info = QLabel()
        self.info.setWordWrap(True)
        right.addWidget(self.info)
        right.addStretch(1)
        self.random_cb = QCheckBox("Skin aleatorio al iniciar")
        self.random_cb.setChecked(bool(app.cfg.get("random_skin", False)))
        self.random_cb.toggled.connect(self._random)
        right.addWidget(self.random_cb)
        bb = QDialogButtonBox()
        apply_b = bb.addButton("Aplicar", QDialogButtonBox.ButtonRole.AcceptRole)
        apply_b.clicked.connect(self._apply)
        close_b = bb.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        close_b.clicked.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right, 2)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        it = QListWidgetItem("<Zebamp (predeterminado)>")
        it.setData(Qt.ItemDataRole.UserRole, "")
        self.list.addItem(it)
        cur = self.app.cfg["skin"]
        sel = 0
        for i, f in enumerate(self.app.skin_files(), start=1):
            it = QListWidgetItem(os.path.splitext(os.path.basename(f))[0] +
                                 ("  [moderno]" if f.lower().endswith(".wal") else ""))
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.list.addItem(it)
            if cur and os.path.abspath(f) == os.path.abspath(cur):
                sel = i
        self.list.setCurrentRow(sel)

    def _path(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _preview(self, *_):
        path = self._path()
        if path is None:
            return
        if path == "":
            pm = self._builtin_preview()
            self.info.setText("Skin original incluido con Zebamp.")
        elif path.lower().endswith(".wal") or (os.path.isdir(path) and \
                os.path.exists(os.path.join(path, "skin.xml"))):
            from ..modern.skin import ModernSkin
            pm = None
            try:
                ms = ModernSkin(path)
                pm = ms.preview()
                ms.vfs.close()
            except Exception:
                pm = None
            self.info.setText(path + "\n\nSkin moderno (Winamp 3/5): compatibilidad parcial "
                              "con scripts MAKI.")
        else:
            pm = render_preview(self.app, path)
            self.info.setText(path)
        if pm is not None:
            self.preview.setPixmap(pm.scaled(550, 232, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.FastTransformation))
        else:
            self.preview.setText("(sin vista previa)")

    def _builtin_preview(self):
        sk = self.app.base_skin
        pm = QPixmap(275, 116)
        p = QPainter(pm)
        p.drawPixmap(0, 0, sk.sprite("MAIN", "MAIN_WINDOW_BACKGROUND"))
        p.drawPixmap(0, 0, sk.sprite("TITLEBAR", "TITLE_SEL"))
        for name, x, y in (("PREV", 16, 88), ("PLAY", 39, 88), ("PAUSE", 62, 88), ("STOP", 85, 88),
                           ("NEXT", 108, 88), ("EJECT", 136, 89)):
            p.drawPixmap(x, y, sk.sprite("CBUTTONS", name))
        p.drawPixmap(16, 72, sk.sprite("POSBAR", "POS_BG"))
        p.end()
        return pm

    def _apply(self):
        path = self._path()
        if path is None:
            return
        if path == "":
            self.app.use_default_skin()
        else:
            self.app.load_skin(path)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Añadir skins", os.path.expanduser("~/Downloads"),
                                                "Skins de Winamp (*.wsz *.wal *.zip);;Todos (*)")
        for f in files:
            install_skin(f)
        self._refresh()

    def _delete(self):
        path = self._path()
        if not path or os.path.dirname(os.path.abspath(path)) != os.path.abspath(SKIN_DIR):
            return
        if QMessageBox.question(self, "Borrar skin", f"¿Borrar {os.path.basename(path)}?") == \
                QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)
            except OSError as e:
                QMessageBox.warning(self, "Zebamp", str(e))
            self._refresh()

    def _folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(SKIN_DIR))

    def _random(self, on):
        self.app.cfg["random_skin"] = bool(on)
        self.app.cfg.save()


# --------------------------------------------------------- preferences
class PreferencesDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        cfg = app.cfg
        self.setWindowTitle("Preferencias de Zebamp")
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # MPD
        w = QWidget()
        f = QFormLayout(w)
        self.host = QLineEdit(cfg["mpd_host"])
        self.host.setPlaceholderText(f"automático ({app.player.conn.addr.describe()})")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(cfg["mpd_port"] or 6600))
        self.password = QLineEdit(cfg["mpd_password"])
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("Servidor o socket:", self.host)
        f.addRow("Puerto:", self.port)
        f.addRow("Contraseña:", self.password)
        st = QLabel("Conectado" if app.player.connected else
                    f"Sin conexión: {app.player.conn.last_error or '—'}")
        f.addRow("Estado:", st)
        stats = app.player.conn.call("stats", default={}) or {}
        if stats:
            f.addRow("Biblioteca:", QLabel(f"{stats.get('artists', '?')} artistas, "
                                           f"{stats.get('albums', '?')} álbumes, "
                                           f"{stats.get('songs', '?')} canciones"))
        tabs.addTab(w, "MPD")

        # Display
        w = QWidget()
        f = QFormLayout(w)
        self.scale = QComboBox()
        self.scale.addItems(["1x", "2x", "3x"])
        self.scale.setCurrentIndex(app.scale - 1)
        f.addRow("Tamaño:", self.scale)
        self.bitmap = QCheckBox("Usar la fuente del skin para el título")
        self.bitmap.setChecked(cfg["use_bitmap_font"])
        f.addRow(self.bitmap)
        self.scroll = QCheckBox("Desplazar el título")
        self.scroll.setChecked(cfg["marquee_scroll"])
        f.addRow(self.scroll)
        self.speed = QComboBox()
        self.speed.addItems(["Lento", "Normal", "Rápido"])
        self.speed.setCurrentIndex(int(cfg["marquee_speed"]))
        f.addRow("Velocidad del título:", self.speed)
        self.plfont = QSpinBox()
        self.plfont.setRange(7, 20)
        self.plfont.setValue(int(cfg["pl_font_size"]))
        f.addRow("Letra de la lista (px):", self.plfont)
        tabs.addTab(w, "Pantalla")

        # Vis
        w = QWidget()
        f = QFormLayout(w)
        self.fifo = QLineEdit(cfg["vis_fifo"])
        self.fifo.setPlaceholderText("automático (salida fifo de mpd.conf)")
        self.fifo_fmt = QLineEdit(cfg["vis_fifo_format"])
        self.fifo_fmt.setPlaceholderText("automático, p. ej. 44100:16:2")
        f.addRow("FIFO de MPD:", self.fifo)
        f.addRow("Formato:", self.fifo_fmt)
        f.addRow(QLabel("Visualización: " + ("recibiendo datos" if app.vis.available
                                             else "no hay salida fifo configurada")))
        tabs.addTab(w, "Visualización")

        # EQ
        w = QWidget()
        f = QFormLayout(w)
        from ..audio import pipewire as pw
        self.eq_backend = QComboBox()
        self.eq_backend.addItems(["pipewire", "none"])
        self.eq_backend.setCurrentText(cfg["eq_backend"])
        f.addRow("Motor del ecualizador:", self.eq_backend)
        f.addRow(QLabel("PipeWire disponible" if pw.available() else "PipeWire no encontrado"))
        self.bal = QCheckBox("Aplicar el balance al stream de MPD en PipeWire")
        self.bal.setChecked(cfg["balance_backend"])
        f.addRow(self.bal)
        note = QLabel("El EQ inserta un filtro «Zebamp EQ» entre MPD y la salida que ya usaba. "
                      "Al apagarlo o cerrar Zebamp, MPD vuelve a su salida original.")
        note.setWordWrap(True)
        f.addRow(note)
        tabs.addTab(w, "Ecualizador")

        # MPD audio options (live server settings)
        w = QWidget()
        f = QFormLayout(w)
        st = app.player.status or {}
        conn = app.player.conn
        from PySide6.QtWidgets import QDoubleSpinBox
        self.xfade = QSpinBox()
        self.xfade.setRange(0, 30)
        self.xfade.setSuffix(" s")
        self.xfade.setValue(int(float(st.get("xfade", 0) or 0)))
        f.addRow("Fundido entre canciones:", self.xfade)
        self.mixramp_on = QCheckBox("Usar MixRamp (fundido según el volumen real, "
                                    "si las canciones tienen etiquetas MixRamp)")
        mdelay = str(st.get("mixrampdelay", "nan"))
        self.mixramp_on.setChecked(mdelay.lower() not in ("nan", "", "0"))
        f.addRow(self.mixramp_on)
        self.mixdb = QDoubleSpinBox()
        self.mixdb.setRange(-60.0, 0.0)
        self.mixdb.setSuffix(" dB")
        try:
            self.mixdb.setValue(float(st.get("mixrampdb", -17)))
        except ValueError:
            self.mixdb.setValue(-17.0)
        f.addRow("Umbral MixRamp:", self.mixdb)
        self.mixdelay = QDoubleSpinBox()
        self.mixdelay.setRange(0.0, 30.0)
        self.mixdelay.setSuffix(" s")
        try:
            self.mixdelay.setValue(float(mdelay) if self.mixramp_on.isChecked() else 2.0)
        except ValueError:
            self.mixdelay.setValue(2.0)
        f.addRow("Retardo MixRamp:", self.mixdelay)
        self.rg = QComboBox()
        rg_modes = [("off", "Desactivado"), ("track", "Por pista"), ("album", "Por álbum"),
                    ("auto", "Automático (álbum en modo aleatorio desactivado)")]
        for k, label in rg_modes:
            self.rg.addItem(label, k)
        rg = conn.call("replay_gain_status", default="off") or "off"
        if isinstance(rg, dict):
            rg = rg.get("replay_gain_mode", "off")
        rg = str(rg).strip()
        self.rg.setCurrentIndex(max(0, [k for k, _ in rg_modes].index(rg) if rg in [k for k, _ in rg_modes] else 0))
        f.addRow("ReplayGain (igualar volumen):", self.rg)
        note = QLabel("Estas opciones se guardan en MPD y afectan a todos sus clientes (ncmpcpp incluido).")
        note.setWordWrap(True)
        f.addRow(note)
        self._audio_initial = (self.xfade.value(), self.mixramp_on.isChecked(), self.mixdb.value(),
                               self.mixdelay.value(), self.rg.currentData())
        tabs.addTab(w, "Audio (MPD)")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        app = self.app
        cfg = app.cfg
        host, port, pwd = self.host.text().strip(), self.port.value(), self.password.text()
        conn_changed = (host, port, pwd) != (cfg["mpd_host"], int(cfg["mpd_port"] or 6600), cfg["mpd_password"])
        cfg["mpd_host"], cfg["mpd_port"], cfg["mpd_password"] = host, port, pwd
        cfg["use_bitmap_font"] = self.bitmap.isChecked()
        cfg["marquee_scroll"] = self.scroll.isChecked()
        cfg["marquee_speed"] = self.speed.currentIndex()
        cfg["pl_font_size"] = self.plfont.value()
        fifo_changed = (self.fifo.text().strip(), self.fifo_fmt.text().strip()) != \
            (cfg["vis_fifo"], cfg["vis_fifo_format"])
        cfg["vis_fifo"] = self.fifo.text().strip()
        cfg["vis_fifo_format"] = self.fifo_fmt.text().strip()
        cfg["eq_backend"] = self.eq_backend.currentText()
        cfg["balance_backend"] = self.bal.isChecked()
        cfg.save()
        audio = (self.xfade.value(), self.mixramp_on.isChecked(), self.mixdb.value(),
                 self.mixdelay.value(), self.rg.currentData())
        if audio != self._audio_initial:
            c = app.player.conn
            c.call("crossfade", self.xfade.value())
            c.call("mixrampdb", f"{self.mixdb.value():.1f}")
            c.call("mixrampdelay", f"{self.mixdelay.value():.1f}" if self.mixramp_on.isChecked() else "nan")
            c.call("replay_gain_mode", self.rg.currentData())
        if conn_changed:
            app.player.set_address(autodetect_address(host, port, pwd))
        if fifo_changed:
            app.vis.configure()
        app.main_panel.marquee.set_speed(cfg["marquee_speed"])
        app.main_panel.marquee._cache_key = None
        if self.scale.currentIndex() + 1 != app.scale:
            app.set_scale(self.scale.currentIndex() + 1)
        else:
            for p in app.panels():
                p.rebuild()
            app.relayout()
        self.accept()


class BookmarksDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        _style(self, app)
        self.app = app
        self.setWindowTitle("Marcadores")
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemDoubleClicked.connect(lambda it: self._play())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Reproducir", self._play), ("Subir", lambda: self._move(-1)),
                         ("Bajar", lambda: self._move(1)), ("Quitar", self._remove),
                         ("Cerrar", self.accept)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        lay.addLayout(row)
        self._fill()

    def _bms(self):
        return list(self.app.cfg["bookmarks"] or [])

    def _fill(self, sel=None):
        self.list.clear()
        for b in self._bms():
            pos = int(b.get("pos") or 0)
            t = (b.get("title") or b.get("file", "")) + (f"   [{pos // 60}:{pos % 60:02d}]" if pos else "")
            it = QListWidgetItem(t)
            it.setToolTip(b.get("file", ""))
            self.list.addItem(it)
        if sel is not None and 0 <= sel < self.list.count():
            self.list.setCurrentRow(sel)

    def _save(self, bms):
        self.app.cfg["bookmarks"] = bms
        self.app.cfg.save()

    def _play(self):
        r = self.list.currentRow()
        bms = self._bms()
        if 0 <= r < len(bms):
            self.app.play_bookmark(bms[r])

    def _remove(self):
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}, reverse=True)
        bms = self._bms()
        for r in rows:
            if 0 <= r < len(bms):
                del bms[r]
        self._save(bms)
        self._fill()

    def _move(self, d):
        r = self.list.currentRow()
        bms = self._bms()
        t = r + d
        if 0 <= r < len(bms) and 0 <= t < len(bms):
            bms[r], bms[t] = bms[t], bms[r]
            self._save(bms)
            self._fill(t)


def about_dialog(app):
    QMessageBox.about(None, "Acerca de Zebamp",
                      f"<b>Zebamp {__version__}</b><br>"
                      "Reproductor estilo Winamp para MPD.<br><br>"
                      "Compatible con skins clásicos (.wsz) y modernos (.wal).<br>"
                      "Winamp es una marca de sus respectivos propietarios; "
                      "Zebamp no está afiliado a ella.<br><br>"
                      f"MPD: {app.player.conn.addr.describe()}")
