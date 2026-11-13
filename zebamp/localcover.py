"""Choosing and loading the album picture among the images of a folder.

Album folders often hold scans of the whole package ("…-Back.png",
"…-Gatefold.png", "…-Insert 1.png" next to the front), and they can be huge
(a 600 dpi gatefold is 15000 px wide and hundreds of megabytes).  So the
front is picked by name and shape -- never by file size --, pictures too big
to decode are passed over, and the result is kept small.
"""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from .libindex import fold

IMAGE = re.compile(r"\.(jpe?g|png|webp|bmp)$", re.I)
# "cover.jpg", "folder.png"…: what players and taggers write
COVER_NAME = re.compile(r"^(cover|folder|front|album)[^/]*\.(jpe?g|png|webp|bmp)$", re.I)
_FRONT_WORD = re.compile(r"\b(front|cover|portada|caratula|frontal|delantera)\b")
_OTHER_SIDE = re.compile(r"\b(back|rear|gatefold|insert|inlay|booklet|inside|tray|spine|disc|disk|cd|matrix|label|obi|"
                         r"sticker|contraportada|trasera|interior|libreto|disco|galleta)\b")
SQUARE_SLACK = 0.15         # how far from 1:1 still counts as a front cover shape
FRONT, UNKNOWN, OTHER = 0, 1, 2


def kind(name: str) -> int:
    """What a file name says the picture is: the front, another part of the
    package, or nothing."""
    words = re.sub(r"[^a-z0-9]+", " ", fold(os.path.splitext(name)[0]))
    if COVER_NAME.match(name) or _FRONT_WORD.search(words):
        return FRONT
    return OTHER if _OTHER_SIDE.search(words) else UNKNOWN


def is_square(size: tuple[int, int] | None) -> bool:
    if not size or size[0] <= 0 or size[1] <= 0:
        return False
    return abs(size[0] / size[1] - 1) <= SQUARE_SLACK


def ranked_cover_files(names: list[str], size_of=None) -> list[str]:
    """The images among `names`, the likeliest front cover first.

    Named as the front first; then the ones whose name says nothing, then
    backs and inserts; within each group square pictures before spreads, and
    the shortest name (usually just the album's).  `size_of(name)` gives
    (width, height) or None."""
    size_of = size_of or (lambda name: None)
    images = [n for n in names if IMAGE.search(n)]
    return sorted(images, key=lambda n: (kind(n), not is_square(size_of(n)), len(n), n.lower()))


def pick_cover_file(names: list[str], size_of=None) -> str | None:
    ranked = ranked_cover_files(names, size_of)
    return ranked[0] if ranked else None


def picture_size(path: str) -> tuple[int, int] | None:
    """(width, height) read from the file's header, without decoding it."""
    size = QImageReader(path).size()
    return (size.width(), size.height()) if size.isValid() else None


def load_scaled(path: str, max_side: int) -> QImage:
    """The picture at most `max_side` wide or tall; a null image when it
    cannot be read.  That includes monsters: Qt refuses to decode pictures
    needing more than its allocation limit (256 MB, a 15000 px gatefold),
    and the caller then tries the next image of the folder."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_side:
        reader.setScaledSize(size.scaled(QSize(max_side, max_side), Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


def folder_covers(folder: str) -> list[str]:
    """Paths of the images of `folder`, the likeliest front cover first."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    ranked = ranked_cover_files(names, lambda name: picture_size(os.path.join(folder, name)))
    return [os.path.join(folder, name) for name in ranked]
