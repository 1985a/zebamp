"""Pixel-art upscalers (Scale2x / Scale3x, a.k.a. AdvMAME) for bitmap skins.

They round off the staircase edges of enlarged skin bitmaps while keeping
them sharp (no blur), which looks much better than plain nearest-neighbour
at 2x/3x.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage


def _to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), dtype=np.uint32, count=h * img.bytesPerLine() // 4)
    return a.reshape(h, img.bytesPerLine() // 4)[:, :w].copy()


def _to_image(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a, dtype=np.uint32)
    h, w = a.shape
    img = QImage(a.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    return img.copy()        # detach from the numpy buffer


def _neighbours(a):
    p = np.pad(a, 1, mode="edge")
    return (p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:],     # A B C
            p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:],  # D E F
            p[2:, :-2], p[2:, 1:-1], p[2:, 2:])        # G H I


def scale2x(a: np.ndarray) -> np.ndarray:
    _A, B, _C, D, E, F, _G, H, _I = _neighbours(a)
    cond = (B != H) & (D != F)
    e0 = np.where(cond & (D == B), D, E)
    e1 = np.where(cond & (B == F), F, E)
    e2 = np.where(cond & (D == H), D, E)
    e3 = np.where(cond & (H == F), F, E)
    h, w = a.shape
    out = np.empty((h * 2, w * 2), dtype=a.dtype)
    out[0::2, 0::2] = e0
    out[0::2, 1::2] = e1
    out[1::2, 0::2] = e2
    out[1::2, 1::2] = e3
    return out


def scale3x(a: np.ndarray) -> np.ndarray:
    # A..I: the 3x3 neighbourhood, named as in the Scale3x description
    A, B, C, D, E, F, G, H, I = _neighbours(a)  # noqa: E741
    cond = (B != H) & (D != F)
    db, bf, dh, hf = cond & (D == B), cond & (B == F), cond & (D == H), cond & (H == F)
    e0 = np.where(db, D, E)
    e1 = np.where((db & (E != C)) | (bf & (E != A)), B, E)
    e2 = np.where(bf, F, E)
    e3 = np.where((db & (E != G)) | (dh & (E != A)), D, E)
    e5 = np.where((bf & (E != I)) | (hf & (E != C)), F, E)
    e6 = np.where(dh, D, E)
    e7 = np.where((dh & (E != I)) | (hf & (E != G)), H, E)
    e8 = np.where(hf, F, E)
    h, w = a.shape
    out = np.empty((h * 3, w * 3), dtype=a.dtype)
    for (dy, dx), e in (((0, 0), e0), ((0, 1), e1), ((0, 2), e2), ((1, 0), e3), ((1, 1), E),
                        ((1, 2), e5), ((2, 0), e6), ((2, 1), e7), ((2, 2), e8)):
        out[dy::3, dx::3] = e
    return out


def _down2(a: np.ndarray) -> np.ndarray:
    """Average 2x2 blocks (in premultiplied space): antialiased edges."""
    ch = np.stack([(a >> s) & 0xFF for s in (24, 16, 8, 0)], axis=-1).astype(np.float32)
    al = ch[..., 0:1] / 255.0
    ch[..., 1:] *= al                       # premultiply rgb
    h, w = a.shape[0] // 2, a.shape[1] // 2
    ch = ch[:h * 2, :w * 2].reshape(h, 2, w, 2, 4).mean(axis=(1, 3))
    alpha = ch[..., 0]
    rgb = np.where(alpha[..., None] > 0, ch[..., 1:] / np.maximum(alpha[..., None] / 255.0, 1e-6), 0)
    out = np.clip(np.rint(np.concatenate([alpha[..., None], rgb], axis=-1)), 0, 255).astype(np.uint32)
    return (out[..., 0] << 24) | (out[..., 1] << 16) | (out[..., 2] << 8) | out[..., 3]


def upscale(img: QImage, k: int, aa: bool = True) -> QImage:
    """Return `img` enlarged k times (k = 2, 3 or 4) with Scale2x/3x.

    With `aa` the image is first enlarged to 2k and averaged back down
    (supersampling): curves and diagonals get smooth antialiased edges while
    flat areas stay perfectly sharp.
    """
    if k <= 1 or img.isNull():
        return img
    a = _to_array(img)
    if k == 2:
        a = _down2(scale2x(scale2x(a))) if aa else scale2x(a)
    elif k == 3:
        a = _down2(scale2x(scale3x(a))) if aa else scale3x(a)
    elif k == 4:
        a = _down2(scale2x(scale2x(scale2x(a)))) if aa else scale2x(scale2x(a))
    else:
        a = np.repeat(np.repeat(a, k, axis=0), k, axis=1)
    out = _to_image(a)
    out.setDevicePixelRatio(k)
    return out
