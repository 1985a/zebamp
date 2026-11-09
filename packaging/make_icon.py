"""Draws the Zebamp application icon (original artwork)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen, QPolygonF

app = QGuiApplication([])
size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
img = QImage(size, size, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
s = size / 256
g = QLinearGradient(0, 0, 0, size)
g.setColorAt(0, QColor(70, 78, 98))
g.setColorAt(1, QColor(22, 25, 32))
p.setBrush(g)
p.setPen(QPen(QColor(120, 130, 155), 6 * s))
p.drawRoundedRect(QRectF(12 * s, 12 * s, 232 * s, 232 * s), 44 * s, 44 * s)
bolt = QPolygonF([QPointF(x * s, y * s) for x, y in
                  [(70, 62), (186, 62), (118, 136), (172, 136), (84, 204), (116, 150), (66, 150), (126, 84), (70, 84)]])
p.setPen(QPen(QColor(10, 40, 36), 5 * s))
p.setBrush(QColor(62, 240, 200))
p.drawPolygon(bolt)
p.end()
img.save(sys.argv[1])
