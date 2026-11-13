"""Audio quality window: the spectrogram of a song and what it tells."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from .. import audioquality as Q
from ..i18n import tr
from ..player import fmt_time, song_title
from ..threads import run_bg

LEFT, BOTTOM, TOP, RIGHT = 46, 20, 6, 8         # room around the picture for the scales
LEVEL_COLORS = {Q.FULL: "#3ddc84", Q.HIGH: "#9bdc3d", Q.MEDIUM: "#e8c63a", Q.LOW: "#f08c2e", Q.POOR: "#e8503a"}
SUSPICIOUS_COLOR = "#f08c2e"


def frequency_ticks(top_hz: float) -> list[int]:
    """Round frequencies (Hz) for the scale of a picture reaching `top_hz`."""
    step = next(s for s in (2000, 5000, 10000, 20000, 50000) if top_hz / s <= 12)
    return list(range(0, int(top_hz) + 1, step))


def time_ticks(seconds: float) -> list[int]:
    """Round times (s) for the scale of a picture `seconds` long."""
    if seconds <= 0:
        return []
    step = next((s for s in (5, 10, 15, 30, 60, 120, 300, 600) if seconds / s <= 10), 900)
    return list(range(0, int(seconds) + 1, step))


def info_line(info: Q.AudioInfo) -> str:
    """«FLAC · 44,1 kHz · 16 bits · estéreo · 912 kbps»."""
    parts = [info.codec.upper().replace("PCM_", "PCM ")]
    if info.sample_rate:
        parts.append(f"{info.sample_rate / 1000:g}".replace(".", tr(",")) + " kHz")
    if info.bits:
        parts.append(f"{info.bits} bits")
    if info.channels:
        parts.append({1: "mono", 2: tr("estéreo")}.get(info.channels, tr("{0} canales").format(info.channels)))
    if info.bitrate:
        parts.append(f"{info.bitrate} kbps")
    return " · ".join(p for p in parts if p)


class SpectrogramView(QWidget):
    """The picture with its frequency and time scales and the cut marked."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image: QImage | None = None
        self.top_hz = 0.0
        self.seconds = 0.0
        self.edge_hz: float | None = None
        self.message = ""

    def show_message(self, text: str):
        self.image, self.message = None, text
        self.update()

    def show_analysis(self, analysis: Q.Analysis):
        rgb = np.ascontiguousarray(Q.to_image(analysis.spectrogram_db))
        height, width, _ = rgb.shape
        # copy(): the QImage must own its pixels once `rgb` goes away
        self.image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
        self.top_hz = analysis.info.sample_rate / 2
        self.seconds = analysis.seconds
        self.edge_hz = analysis.edge_hz
        self.message = ""
        self.update()

    def picture_rect(self) -> QRect:
        return QRect(LEFT, TOP, self.width() - LEFT - RIGHT, self.height() - TOP - BOTTOM)

    def paintEvent(self, ev):
        p = QPainter(self)
        box = self.picture_rect()
        p.fillRect(box, QColor(0, 0, 0))
        text_color = self.palette().color(self.foregroundRole())
        font = QFont(p.font())
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(text_color)
        if self.image is None:
            p.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(QRectF(box), self.image)
        for hz in frequency_ticks(self.top_hz):
            y = box.bottom() - round(hz / self.top_hz * box.height())
            p.drawLine(box.left() - 4, y, box.left() - 1, y)
            p.drawText(QRect(0, y - 7, LEFT - 7, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{hz // 1000} kHz")
        for second in time_ticks(self.seconds):
            x = box.left() + round(second / self.seconds * box.width())
            p.drawLine(x, box.bottom() + 1, x, box.bottom() + 4)
            p.drawText(QRect(x - 30, box.bottom() + 5, 60, 14), Qt.AlignmentFlag.AlignHCenter, fmt_time(second))
        if self.edge_hz:
            y = box.bottom() - round(self.edge_hz / self.top_hz * box.height())
            p.setPen(QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine))
            p.drawLine(box.left(), y, box.right(), y)
            label = tr("corte a {0} kHz").format(f"{self.edge_hz / 1000:.1f}".replace(".", tr(",")))
            p.drawText(QRect(box.left() + 6, y - 16, 200, 14), Qt.AlignmentFlag.AlignLeft, label)
        p.end()


class QualityWindow(QWidget):
    def __init__(self, app, song: dict):
        super().__init__(None, Qt.WindowType.Window)
        from .dialogs import _style
        _style(self, app)
        self.app = app
        self.song = dict(song)
        self._closed = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Calidad del audio - Zebamp"))
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        self.title = QLabel(song_title(song))
        title_font = QFont(self.title.font())
        title_font.setBold(True)
        self.title.setFont(title_font)
        self.info = QLabel()
        self.view = SpectrogramView()
        self.verdict = QLabel()
        verdict_font = QFont(title_font)
        verdict_font.setPointSizeF(verdict_font.pointSizeF() * 1.25)
        self.verdict.setFont(verdict_font)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        hint = QLabel(tr("Cada punto es el sonido en un instante (horizontal) y un tono (vertical): cuanto más "
                         "claro, más fuerte. Un borde recto con todo negro por encima delata un formato con pérdida."))
        hint.setWordWrap(True)
        for widget in (self.title, self.info, self.view, self.verdict, self.detail, hint):
            lay.addWidget(widget, 1 if widget is self.view else 0)
        self._start()

    def _start(self):
        if not Q.available():
            self.view.show_message(tr("Hace falta el programa «ffmpeg» para analizar el audio."))
            return
        path = Q.audio_file_of(self.song, self.app.player.music_directory)
        if path is None:
            self.view.show_message(tr("El archivo no está en este equipo (emisora, o MPD en otro equipo)."))
            return
        self.view.show_message(tr("Analizando el audio…"))
        time_range = Q.song_range(self.song)
        run_bg(lambda: Q.analyse(path, time_range, cancelled=lambda: self._closed), self._done)
        if path != os.path.join(self.app.player.music_directory or "", self.song.get("file", "")) and not time_range:
            # a CUE track whose limits MPD did not give: the whole album file is analysed
            self.info.setText(tr("Se analiza el archivo completo del álbum."))

    def _done(self, analysis):
        if self._closed:
            return
        try:
            if not isinstance(analysis, Q.Analysis):
                self.view.show_message(tr("No se pudo leer el audio de este archivo."))
                return
            self.info.setText(info_line(analysis.info))
            self.view.show_analysis(analysis)
            verdict = analysis.verdict
            color = SUSPICIOUS_COLOR if verdict.suspicious else LEVEL_COLORS[verdict.level]
            self.verdict.setText(verdict.title)
            self.verdict.setStyleSheet(f"color: {color};")
            self.detail.setText(verdict.detail)
        except RuntimeError:
            pass                    # closed while the analysis was finishing

    def closeEvent(self, ev):
        self._closed = True         # stops ffmpeg if it is still decoding
        super().closeEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)
