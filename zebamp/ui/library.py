"""Media Library window: browses MPD's database inside a gen.bmp frame."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QDrag, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLineEdit, QMenu, QPushButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..player import first, fmt_time, song_duration, song_title
from .plwin import MIME_URIS
from ..i18n import tr

ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_VAL = Qt.ItemDataRole.UserRole + 1
ROLE_LOADED = Qt.ItemDataRole.UserRole + 2

L, T, R, B = 11, 20, 8, 14


def _vals(result, key):
    """python-mpd2 returns list of dicts (or strings for old servers)."""
    out = []
    for r in result or []:
        if isinstance(r, dict):
            v = r.get(key)
            if isinstance(v, list):
                out.extend(v)
            elif v is not None:
                out.append(v)
        else:
            out.append(r)
    seen = set()
    res = []
    for v in out:
        if v not in seen:
            seen.add(v)
            res.append(v)
    return sorted(res, key=lambda s: str(s).lower())


class TrackTable(QTreeWidget):
    COLS = [tr("Artista"), tr("Título"), tr("Álbum"), tr("Duración"), tr("Pista"), tr("Año"), tr("Género"),
            tr("Valoración"), tr("Escuchas")]

    def __init__(self, lib):
        super().__init__()
        self.lib = lib
        self.setColumnCount(len(self.COLS))
        self.setHeaderLabels(self.COLS)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)
        h = self.header()
        h.setStretchLastSection(False)
        for i, w in enumerate((150, 220, 160, 60, 45, 50, 90, 80, 60)):
            self.setColumnWidth(i, w)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.itemDoubleClicked.connect(lambda *_: lib.play_selected())
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def set_songs(self, songs, keep_order=False):
        self.setSortingEnabled(False)
        self.clear()
        items = []
        stats = getattr(self.lib.app, "stats", None)
        for s in songs:
            if "file" not in s:
                continue
            d = song_duration(s)
            it = QTreeWidgetItem([
                str(first(s.get("artist"))), str(first(s.get("title"))) or song_title(s),
                str(first(s.get("album"))), fmt_time(d) if d else "",
                str(first(s.get("track"))).split("/")[0], str(first(s.get("date")))[:4],
                str(first(s.get("genre"))),
                "★" * stats.rating(s["file"]) if stats else "",
                str(stats.playcount(s["file"]) or "") if stats else ""])
            it.setData(0, ROLE_VAL, s["file"])
            if stats:
                it.setData(7, Qt.ItemDataRole.UserRole + 3, stats.rating(s["file"]))
            try:
                it.setData(4, Qt.ItemDataRole.UserRole + 3, int(str(first(s.get("track"))).split("/")[0] or 0))
            except ValueError:
                pass
            items.append(it)
        self.addTopLevelItems(items)
        if not keep_order:
            self.setSortingEnabled(True)

    def uris(self, selected_only=True):
        its = self.selectedItems() if selected_only else [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        if selected_only and not its:
            its = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        return [it.data(0, ROLE_VAL) for it in its if it is not None]

    def startDrag(self, actions):
        uris = self.uris()
        if not uris:
            return
        md = QMimeData()
        md.setData(MIME_URIS, "\n".join(uris).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.CopyAction)

    def _menu(self, pos):
        m = QMenu(self)
        m.addAction(tr("Reproducir"), self.lib.play_selected)
        m.addAction(tr("Encolar"), self.lib.enqueue_selected)
        m.addAction(tr("Encolar a continuación"), self.lib.enqueue_next)
        stats = getattr(self.lib.app, "stats", None)
        if stats is not None:
            r = m.addMenu(tr("Valorar"))
            for n in range(5, -1, -1):
                r.addAction("★" * n if n else tr("Sin valoración"),
                            lambda n=n: self._rate(n))
        m.exec(self.viewport().mapToGlobal(pos))

    def _rate(self, n):
        stats = self.lib.app.stats
        for it in self.selectedItems():
            stats.set_rating(it.data(0, ROLE_VAL), n)
            it.setText(7, "★" * n)


class LibraryWindow(QWidget):
    def __init__(self, app, embedded_in: QWidget | None = None):
        self.embedded = embedded_in is not None
        if self.embedded:
            super().__init__(embedded_in)
        else:
            super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.app = app
        self.setWindowTitle(tr("Biblioteca de medios - Zebamp"))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(275 * 2, 116 * 3)
        self.resize(820, 520)
        self._drag = None
        self._resize = None
        self._close_pressed = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*((2, 2, 2, 2) if self.embedded else (L, T, R, B)))
        lay.setSpacing(3)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Buscar en la biblioteca (artista, título, álbum…)"))
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_search)
        self.search.textChanged.connect(lambda *_: self._search_timer.start())
        top.addWidget(self.search, 1)
        for text, fn in ((tr("Reproducir"), self.play_selected), (tr("Encolar"), self.enqueue_selected),
                         (tr("Actualizar BD"), lambda: app.player.update_database())):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            top.addWidget(b)
        lay.addLayout(top)
        self.split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.currentItemChanged.connect(self._select)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._tree_play(it))
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.split.addWidget(self.tree)
        self.table = TrackTable(self)
        self.split.addWidget(self.table)
        self.split.setStretchFactor(1, 3)
        self.split.setSizes([220, 600])
        lay.addWidget(self.split, 1)
        self._roots = {}
        for key, label in (("artists", tr("Artistas")), ("albumartists", tr("Artistas del álbum")),
                           ("albums", tr("Álbumes")), ("genres", tr("Géneros")), ("dirs", tr("Carpetas")),
                           ("playlists", tr("Listas guardadas")), ("smartlists", tr("Listas inteligentes"))):
            it = QTreeWidgetItem([label])
            it.setData(0, ROLE_KIND, "root:" + key)
            it.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.tree.addTopLevelItem(it)
            self._roots[key] = it
        # smart views (play statistics / ratings kept in MPD stickers)
        for key, label in (("smart:most", tr("★ Más escuchadas")), ("smart:rated", tr("★ Mejor valoradas")),
                           ("smart:recentplay", tr("★ Escuchadas recientemente")),
                           ("smart:added", tr("★ Añadidas recientemente"))):
            it = QTreeWidgetItem([label])
            it.setData(0, ROLE_KIND, key)
            self.tree.addTopLevelItem(it)
        app.player.databaseChanged.connect(self._reset)
        app.player.storedPlaylistsChanged.connect(lambda: self._reload_root("playlists"))
        self.apply_skin()
        geo = app.cfg["library_geometry"]
        if geo and len(geo) == 4 and not self.embedded:
            self.setGeometry(*geo)

    # ---------------------------------------------------------- skin
    EMBED_COLORS = {"window_text": "#d6dad6", "item_bg": "#050505", "item_fg": "#c8d8c8",
                    "divider": "#3a3a3a", "list_text_selected_bg": "#34506e",
                    "list_text_selected": "#ffffff", "list_header_bg": "#262626",
                    "list_header_text": "#d6dad6", "list_header_frame_br": "#111111",
                    "button_text": "#d6dad6", "list_header_frame_pressed": "#111111",
                    "scrollbar_dead": "#101010", "scrollbar_one": "#3a3a3a", "window_bg": "#141414"}

    def apply_skin(self):
        g = self.app.skin.genex_colors or self.app.base_skin.genex_colors or {}
        if self.embedded:
            # inside a modern skin (Bento): neutral dark colours that blend in
            g = {k: QColor(v) for k, v in self.EMBED_COLORS.items()}

        from ..colors import distinct_bg, readable
        g = dict(g)
        base = g.get("item_bg") or QColor("#0a0f12")
        hl = distinct_bg(g.get("list_text_selected_bg") or QColor("#1e465a"), base,
                         g.get("playlist_selection"), g.get("list_text_highlighted_bg"))
        g["list_text_selected_bg"] = hl
        g["list_text_selected"] = readable(g.get("list_text_selected") or QColor("#ffffff"), hl,
                                           g.get("item_fg"), g.get("window_text"))
        g["item_fg"] = readable(g.get("item_fg") or QColor("#3ef0c8"), base, g.get("window_text"))
        hb = g.get("list_header_bg") or QColor("#363c4a")
        g["list_header_text"] = readable(g.get("list_header_text") or QColor("#d0d4dc"), hb)
        g["button_text"] = readable(g.get("button_text") or QColor("#d0d4dc"), hb)

        def c(name, default):
            col = g.get(name) or QColor(default)
            return col.name()
        css = f"""
        QWidget {{ color: {c('window_text', '#d0d4dc')}; }}
        QTreeWidget, QLineEdit {{
            background: {c('item_bg', '#0a0f12')}; color: {c('item_fg', '#3ef0c8')};
            border: 1px solid {c('divider', '#464d5e')};
            selection-background-color: {c('list_text_selected_bg', '#1e465a')};
            selection-color: {c('list_text_selected', '#ffffff')};
            alternate-background-color: {QColor(c('item_bg', '#0a0f12')).lighter(118).name()};
        }}
        QHeaderView::section {{
            background: {c('list_header_bg', '#363c4a')}; color: {c('list_header_text', '#d0d4dc')};
            border: 1px solid {c('list_header_frame_br', '#1a1d24')}; padding: 1px 4px;
        }}
        QPushButton {{
            background: {c('list_header_bg', '#363c4a')}; color: {c('button_text', '#d0d4dc')};
            border: 1px solid {c('list_header_frame_br', '#1a1d24')}; padding: 2px 8px;
        }}
        QPushButton:pressed {{ background: {c('list_header_frame_pressed', '#1a1d24')}; }}
        QSplitter::handle {{ background: {c('divider', '#464d5e')}; }}
        QScrollBar {{ background: {c('scrollbar_dead', '#121418')}; }}
        QScrollBar::handle {{ background: {c('scrollbar_one', '#363c4a')}; }}
        """
        self.setStyleSheet(css)
        self.update()

    def paintEvent(self, ev):
        if self.embedded:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(self.EMBED_COLORS["window_bg"]))
            p.end()
            return
        sk = self.app.skin
        p = QPainter(self)
        w, h = self.width(), self.height()
        active = self.isActiveWindow()
        s = "_SEL" if active else ""
        p.fillRect(QRect(L, T, w - L - R, h - T - B),
                   (sk.genex_colors or {}).get("window_bg", QColor(38, 42, 52)))
        # top row
        title_w = max(100, (len(self.windowTitle()) * 6 + 50) // 25 * 25)
        tx = (w - title_w) // 2
        for x in range(25, w - 25, 25):
            p.drawPixmap(x, 0, sk.sprite("GEN", "TLRF" + s))
        for x in range(tx, tx + title_w, 25):
            p.drawPixmap(x, 0, sk.sprite("GEN", "TC" + s))
        p.drawPixmap(tx - 25, 0, sk.sprite("GEN", "TLE" + s))
        p.drawPixmap(tx + title_w, 0, sk.sprite("GEN", "TRE" + s))
        p.drawPixmap(0, 0, sk.sprite("GEN", "TL" + s))
        p.drawPixmap(w - 25, 0, sk.sprite("GEN", "TR" + s))
        f = QFont()
        f.setPixelSize(9)
        f.setBold(True)
        p.setFont(f)
        p.setPen((sk.genex_colors or {}).get("window_text", QColor(200, 200, 200)))
        p.drawText(QRect(tx, 0, title_w, 20), Qt.AlignmentFlag.AlignCenter, tr("BIBLIOTECA DE MEDIOS"))
        if self._close_pressed:
            p.drawPixmap(w - 11, 3, sk.sprite("GEN", "CLOSE_D"))
        # sides
        for y in range(T, h - B, 29):
            p.drawPixmap(0, y, sk.sprite("GEN", "ML"))
            p.drawPixmap(w - R, y, sk.sprite("GEN", "MR"))
        # bottom
        for x in range(125, w - 125, 25):
            p.drawPixmap(x, h - B, sk.sprite("GEN", "BF"))
        p.drawPixmap(0, h - B, sk.sprite("GEN", "BL"))
        p.drawPixmap(w - 125, h - B, sk.sprite("GEN", "BR"))
        p.end()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == ev.Type.ActivationChange:
            self.update()

    def mousePressEvent(self, ev):
        if self.embedded:
            return super().mousePressEvent(ev)
        pos = ev.position().toPoint()
        w, h = self.width(), self.height()
        if ev.button() != Qt.MouseButton.LeftButton:
            return None
        if QRect(w - 11, 3, 9, 9).contains(pos):
            self._close_pressed = True
            self.update()
            return None
        if QRect(w - 16, h - 16, 16, 16).contains(pos):
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
            return None
        if pos.y() < T:
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()

    def mouseReleaseEvent(self, ev):
        if self.embedded:
            return super().mouseReleaseEvent(ev)
        if self._close_pressed:
            self._close_pressed = False
            self.update()
            if QRect(self.width() - 11, 3, 9, 9).contains(ev.position().toPoint()):
                self.hide()

    def hideEvent(self, ev):
        if self.embedded:
            return super().hideEvent(ev)
        g = self.geometry()
        self.app.cfg["library_geometry"] = [g.x(), g.y(), g.width(), g.height()]
        self.app.cfg.save()
        super().hideEvent(ev)

    def keyPressEvent(self, ev):
        if self.embedded:
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.table.hasFocus():
                self.play_selected()
                return None
            return super().keyPressEvent(ev)
        if ev.key() == Qt.Key.Key_Escape:
            self.hide()
            return None
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.table.hasFocus():
            self.play_selected()
            return None
        if ev.modifiers() & Qt.KeyboardModifier.AltModifier and ev.key() == Qt.Key.Key_L:
            self.hide()
            return None
        super().keyPressEvent(ev)

    # ---------------------------------------------------------- data
    def _async(self, fn, done):
        self.app.player.conn.run_async(fn, lambda r: self._safe(done, r))

    def _safe(self, done, r):
        try:
            done(r)
        except RuntimeError:
            pass  # widgets were deleted

    def _reset(self):
        for key in self._roots:
            self._reload_root(key)

    def _reload_root(self, key):
        it = self._roots.get(key)
        if it is None:
            return
        it.takeChildren()
        it.setData(0, ROLE_LOADED, False)
        if it.isExpanded():
            self._expand(it)

    def _expand(self, item: QTreeWidgetItem):
        if item.data(0, ROLE_LOADED):
            return
        item.setData(0, ROLE_LOADED, True)
        kind = item.data(0, ROLE_KIND) or ""
        val = item.data(0, ROLE_VAL)

        def add_children(names, child_kind, expandable=True, values=None):
            item.takeChildren()
            kids = []
            for i, n in enumerate(names):
                label = str(n) if n not in ("", None) else tr("(desconocido)")
                c = QTreeWidgetItem([label])
                c.setData(0, ROLE_KIND, child_kind)
                c.setData(0, ROLE_VAL, values[i] if values is not None else n)
                if expandable:
                    c.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                kids.append(c)
            item.addChildren(kids)

        if kind == "root:artists":
            self._async(lambda c: _vals(c.list("artist"), "artist"),
                        lambda r: add_children(r or [], "artist"))
        elif kind == "root:albumartists":
            self._async(lambda c: _vals(c.list("albumartist"), "albumartist"),
                        lambda r: add_children(r or [], "albumartist"))
        elif kind == "root:albums":
            self._async(lambda c: _vals(c.list("album"), "album"),
                        lambda r: add_children(r or [], "album", expandable=False))
        elif kind == "root:genres":
            self._async(lambda c: _vals(c.list("genre"), "genre"),
                        lambda r: add_children(r or [], "genre"))
        elif kind == "root:smartlists":
            add_children([s["name"] for s in self.app.smart_lists()], "smartlist", expandable=False)
            create = QTreeWidgetItem([tr("＋ Nueva lista inteligente…")])     # double click opens the editor
            create.setData(0, ROLE_KIND, "smartnew")
            item.addChild(create)
        elif kind == "root:playlists":
            self._async(lambda c: sorted((p.get("playlist") for p in c.listplaylists()), key=str.lower),
                        lambda r: add_children(r or [], "playlist", expandable=False))
        elif kind in ("artist", "albumartist", "genre"):
            tag = kind
            self._async(lambda c: _vals(c.list("album", tag, val), "album"),
                        lambda r: add_children(r or [], f"album@{tag}", expandable=False))
        elif kind in ("root:dirs", "dir"):
            path = "" if kind == "root:dirs" else val

            def job(c):
                return c.lsinfo(path) if path else c.lsinfo()

            def done(r):
                dirs = [d["directory"] for d in (r or []) if "directory" in d]
                add_children([d.rsplit("/", 1)[-1] for d in dirs], "dir", values=dirs)
            self._async(job, done)

    def _filter_for(self, item):
        """MPD filter args for a tree item (used by find/findadd)."""
        kind = item.data(0, ROLE_KIND) or ""
        val = item.data(0, ROLE_VAL)
        if kind in ("artist", "albumartist", "genre"):
            return [kind, val]
        if kind == "album":
            return ["album", val]
        if kind.startswith("album@"):
            parent = item.parent()
            ptag = kind.split("@", 1)[1]
            return [ptag, parent.data(0, ROLE_VAL), "album", val]
        return None

    def _select(self, item, _prev=None):
        if item is None:
            return
        kind = item.data(0, ROLE_KIND) or ""
        val = item.data(0, ROLE_VAL)
        flt = self._filter_for(item)
        if flt:
            self._async(lambda c: c.find(*flt), lambda r: self.table.set_songs(r or []))
        elif kind == "dir":
            self._async(lambda c: [s for s in c.lsinfo(val) if "file" in s],
                        lambda r: self.table.set_songs(r or []))
        elif kind == "playlist":
            self._async(lambda c: c.listplaylistinfo(val), lambda r: self.table.set_songs(r or []))
        elif kind == "smartlist":
            self._show_smart_list(val)
        elif kind.startswith("smart:"):
            self._smart(kind)

    # ------------------------------------------------------ smart lists
    @staticmethod
    def _song_from_row(r) -> dict:
        return {"file": r[0], "title": r[1], "artist": r[2], "album": r[3], "albumartist": r[4],
                "genre": r[5], "duration": r[6], "date": r[7] if len(r) > 7 else ""}

    def _smart_rows(self, name: str, done):
        """Evaluate a smart list off the GUI thread; done(index rows)."""
        from ..smartlist import evaluate
        from ..threads import run_bg
        smart = next((x for x in self.app.smart_lists() if x["name"] == name), None)
        index, stats = self.app.library_index, self.app.stats
        if smart is None or not index.is_ready:
            if not index.is_ready:
                index.refresh()             # still loading: the list fills in on the next click
            done([])
            return
        # snapshots: the worker must not see the dicts change under it
        rows, ratings, counts, last = index.rows, dict(stats.ratings), dict(stats.counts), dict(stats.last)
        run_bg(lambda: evaluate(smart, rows, ratings, counts, last),
               lambda r: self._safe(done, [] if isinstance(r, Exception) else r))

    def _show_smart_list(self, name: str):
        self._smart_rows(name, lambda rows: self.table.set_songs(
            [self._song_from_row(r) for r in rows], keep_order=True))

    def new_smart_list(self):
        self.edit_smart_list(None)

    def edit_smart_list(self, name: str | None):
        from ..smartlist import with_smart_list
        from .smartlist_dialog import SmartListDialog
        current = next((x for x in self.app.smart_lists() if x["name"] == name), None)
        dialog = SmartListDialog(self.app, current)
        if dialog.exec() and dialog.result_list:
            self.app.save_smart_lists(with_smart_list(self.app.smart_lists(), dialog.result_list, name or ""))
            self._reload_root("smartlists")
            self._roots["smartlists"].setExpanded(True)

    def delete_smart_list(self, name: str):
        from ..smartlist import without_smart_list
        self.app.save_smart_lists(without_smart_list(self.app.smart_lists(), name))
        self._reload_root("smartlists")

    def _songs_for(self, uris):
        """Song dicts for URIs, from the in-memory index when it's ready."""
        idx = getattr(self.app, "library_index", None)
        if idx is not None and idx.is_ready:
            by = idx.by_file()
            out = []
            for u in uris:
                r = by.get(u)
                if r is not None:
                    out.append(self._song_from_row(r))
            return out
        return None

    def _smart(self, kind):
        st = getattr(self.app, "stats", None)
        if kind == "smart:added":
            import time as _t
            since = int(_t.time()) - 30 * 86400

            def job(c):
                try:
                    return c.find(f"(modified-since '{since}')", "sort", "-Last-Modified", "window", "0:500")
                except Exception:
                    return c.find(f"(modified-since '{since}')")[:500]
            self._async(job, lambda r: self.table.set_songs(r or [], keep_order=True))
            return
        if st is None:
            return
        uris = {"smart:most": st.most_played, "smart:rated": st.top_rated,
                "smart:recentplay": st.recently_played}[kind]()
        songs = self._songs_for(uris)
        if songs is not None:
            self.table.set_songs(songs, keep_order=True)
            return

        def job(c):
            out = []
            for u in uris[:200]:
                try:
                    out.extend(c.find("file", u))
                except Exception:
                    pass
            return out
        self._async(job, lambda r: self.table.set_songs(r or [], keep_order=True))

    def _do_search(self):
        q = self.search.text().strip()
        if len(q) < 2:
            return

        def job(c):
            # MPD filter expression: any tag contains the text (case-insensitive)
            esc = q.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            try:
                return c.search(f'(any contains "{esc}")', "window", "0:2000")
            except Exception:
                return c.search("any", q)
        self._async(job, lambda r: self.table.set_songs(r or []))

    # ------------------------------------------------------- actions
    def _uris_for_tree(self, item, cb):
        kind = item.data(0, ROLE_KIND) or ""
        val = item.data(0, ROLE_VAL)
        flt = self._filter_for(item)
        if flt:
            self._async(lambda c: [s["file"] for s in c.find(*flt) if "file" in s], cb)
        elif kind == "dir":
            cb([val])
        elif kind == "playlist":
            self._async(lambda c: [s["file"] for s in c.listplaylistinfo(val) if "file" in s], cb)
        elif kind == "smartlist":
            self._smart_rows(val, lambda rows: cb([r[0] for r in rows]))

    def _tree_play(self, item):
        if item.data(0, ROLE_KIND) == "smartnew":
            self.new_smart_list()
            return
        self._uris_for_tree(item, lambda uris: uris and self.app.player.add(uris, replace=True))

    def _tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        kind = (item.data(0, ROLE_KIND) or "") if item is not None else ""
        if kind == "root:smartlists":
            m = QMenu(self)
            m.addAction(tr("Nueva lista inteligente…"), self.new_smart_list)
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        if item is None or kind.startswith("root:") or kind == "smartnew":
            return
        m = QMenu(self)
        m.addAction(tr("Reproducir"), lambda: self._tree_play(item))
        m.addAction(tr("Encolar"), lambda: self._uris_for_tree(item, lambda u: u and self.app.player.add(u)))
        if item.data(0, ROLE_KIND) == "playlist":
            m.addAction(tr("Cargar (reemplazar lista)"),
                        lambda: self.app.player.load_playlist(item.data(0, ROLE_VAL)))
        if kind == "smartlist":
            name = item.data(0, ROLE_VAL)
            m.addSeparator()
            m.addAction(tr("Editar…"), lambda: self.edit_smart_list(name))
            m.addAction(tr("Nueva lista inteligente…"), self.new_smart_list)
            m.addAction(tr("Borrar"), lambda: self.delete_smart_list(name))
        if item.data(0, ROLE_KIND) == "dir":
            m.addAction(tr("Actualizar esta carpeta en la BD"),
                        lambda: self.app.player.update_database(item.data(0, ROLE_VAL)))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def play_selected(self):
        uris = self.table.uris()
        if uris:
            sel = self.table.selectedItems()
            if len(sel) == 1:
                # Winamp-like: play the clicked track, keep the rest of the view queued
                allu = self.table.uris(selected_only=False)
                idx = allu.index(sel[0].data(0, ROLE_VAL))
                self.app.player.add(allu, replace=True)
                self.app.player.play(idx)
            else:
                self.app.player.add(uris, replace=True)

    def enqueue_selected(self):
        uris = self.table.uris()
        if uris:
            self.app.player.add(uris)

    def enqueue_next(self):
        uris = self.table.uris()
        if uris:
            self.app.player.add_next(uris)
