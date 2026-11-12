"""Album art as a classic skinned window (GEN.BMP frame).

Docks/snaps like the other windows.  The picture comes from the same cache
the notifications use (embedded art, MPD's cover.*, then the album folder)
and is only looked up while the window is shown."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

from ..notify import fetch_cover_job
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
    def load(self):
        """Fetch the current song's cover (off the GUI thread) if it changed."""
        if not self.isVisible():
            return
        uri = (self.app.player.song or {}).get("file")
        if uri == self._uri:
            return
        self._uri = uri
        if not uri:
            self._set_cover(uri, None)
            return
        self.app.player.conn.run_async(fetch_cover_job(uri), lambda path: self._set_cover(uri, path))

    def _set_cover(self, uri, path):
        if uri != self._uri:
            return                  # the song changed while this one was loading
        self._cover = QPixmap(path) if isinstance(path, str) else QPixmap()
        self.update()

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
        m.addAction(tr("Información del archivo…"), self.app.show_file_info)
        m.addAction(tr("Cerrar carátula"), self.app.toggle_art_panel)
        self.app._last_menu = m
        m.popup(gp)
