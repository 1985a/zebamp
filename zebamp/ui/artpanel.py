"""Album art as a classic skinned window (GEN.BMP frame).

Docks/snaps like the other windows.  The picture comes from the same cache
the notifications use (embedded art, MPD's cover.*, then the album folder)
and is only looked up while the window is shown."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

from ..coverfind import CoverCache
from ..notify import cover_job, cover_query
from .genpanel import GenPanel
from ..i18n import tr

MARGIN = 3      # skin pixels between the frame and the picture


def fit_rect(image_w: int, image_h: int, box: QRect) -> QRectF:
    """Largest rectangle with the image's proportions centred in `box`."""
    if image_w <= 0 or image_h <= 0 or box.width() <= 0 or box.height() <= 0:
        return QRectF()
    scale = min(box.width() / image_w, box.height() / image_h)
    w, h = image_w * scale, image_h * scale
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)


class ArtPanel(GenPanel):
    cfg_prefix = "art"
    title = tr("CARÁTULA")
    close_tooltip = tr("Cerrar carátula")

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self._uri = None            # song the picture belongs to
        self._path = None           # file the picture was read from
        self._cover = QPixmap()
        app.player.songChanged.connect(self.load)
        self.rebuild()

    def build(self):
        self.build_frame()

    def close_panel(self):
        self.app.toggle_art_panel()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.load()

    # ----------------------------------------------------------- loading
    def load(self, force=False):
        """Fetch the current song's cover (off the GUI thread) if it changed;
        `force` looks again, on the Internet too, for the same song."""
        if not self.isVisible():
            return
        song = dict(self.app.player.song or {})
        uri = song.get("file")
        if uri == self._uri and not force:
            return
        self._uri = uri
        if not uri:
            self._set_cover(uri, None)
            return
        self.app.player.conn.run_async(cover_job(self.app, song, force), lambda path: self._set_cover(uri, path))

    def _set_cover(self, uri, path):
        if uri != self._uri:
            return                  # the song changed while this one was loading
        self._path = path if isinstance(path, str) else None
        self._cover = QPixmap(self._path) if self._path else QPixmap()
        self.update()

    # ------------------------------------------ covers from the Internet
    def _query(self):
        return cover_query(self.app, self.app.player.song or {})

    def shows_online_cover(self) -> bool:
        query = self._query()
        return bool(self._path and query and self._path == CoverCache().image_path(query))

    def search_online(self):
        """Look on the Internet now, even if a recent search found nothing."""
        query = self._query()
        if query is not None:
            CoverCache().forget(query)
            self.load(force=True)

    def reject_cover(self, give_up=False):
        """The downloaded cover is not this album's: drop it and look for
        another one (or, with `give_up`, leave the album without cover)."""
        query = self._query()
        if query is not None:
            CoverCache().reject(query, give_up=give_up)
            self._uri = None            # show the result even though the song is the same
            self.load(force=not give_up)

    # ------------------------------------------------------------- paint
    def picture_rect(self) -> QRect:
        return self.content_rect().adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)

    def paint_background(self, p: QPainter):
        self.paint_frame(p)
        colors = self.skin.genex_colors or {}
        p.fillRect(self.content_rect(), colors.get("item_bg") or QColor(10, 15, 18))
        if self._cover.isNull():
            p.setPen(colors.get("item_fg") or QColor(160, 170, 180))
            p.drawText(self.content_rect(), Qt.AlignmentFlag.AlignCenter, tr("Sin carátula"))
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawPixmap(fit_rect(self._cover.width(), self._cover.height(), self.picture_rect()),
                     self._cover, QRectF(self._cover.rect()))
        p.restore()

    def context_menu(self, pt, gp):
        m = QMenu()
        m.setPalette(getattr(self.app, "dialog_palette", m.palette()))
        if self.shows_online_cover():
            m.addAction(tr("No es esta carátula: buscar otra"), self.reject_cover)
            m.addAction(tr("Dejar este álbum sin carátula"), lambda: self.reject_cover(give_up=True))
        elif self._cover.isNull() and self._query() is not None:
            m.addAction(tr("Buscar la carátula en Internet"), self.search_online)
        self.app._act(m, tr("Buscar carátulas en Internet"), self.app.toggle_cover_online,
                      checked=bool(self.app.cfg["cover_online"]))
        m.addSeparator()
        m.addAction(tr("Información del archivo…"), self.app.show_file_info)
        m.addAction(tr("Cerrar carátula"), self.app.toggle_art_panel)
        self.app._last_menu = m
        m.popup(gp)
