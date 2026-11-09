"""Classic equalizer window."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QPainter

from .base import Area, Button, SkinPanel, Slider, Toggle

W, H = 275, 116
BAND_X = [78, 96, 114, 132, 150, 168, 186, 204, 222, 240]
FREQS = ["60", "170", "310", "600", "1K", "3K", "6K", "12K", "14K", "16K"]
GRAPH = QRect(86, 17, 113, 19)


def db_to_v(db: float) -> float:
    return (max(-12.0, min(12.0, db)) + 12.0) / 24.0


def v_to_db(v: float) -> float:
    return round((v * 24.0 - 12.0) * 10) / 10.0


def spline(xs, ys, out_x):
    """Natural cubic spline through (xs, ys) evaluated at out_x."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    alpha = [0.0] * n
    for i in range(1, n - 1):
        alpha[i] = 3 / h[i] * (ys[i + 1] - ys[i]) - 3 / h[i - 1] * (ys[i] - ys[i - 1])
    diag, mu, z = [1.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n - 1):
        diag[i] = 2 * (xs[i + 1] - xs[i - 1]) - h[i - 1] * mu[i - 1]
        mu[i] = h[i] / diag[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / diag[i]
    c, b, d = [0.0] * n, [0.0] * (n - 1), [0.0] * (n - 1)
    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (ys[j + 1] - ys[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3
        d[j] = (c[j + 1] - c[j]) / (3 * h[j])
    out = []
    for x in out_x:
        j = min(n - 2, max(0, next((k for k in range(n - 1) if x < xs[k + 1]), n - 2)))
        dx = x - xs[j]
        out.append(ys[j] + b[j] * dx + c[j] * dx * dx + d[j] * dx ** 3)
    return out


class EqPanel(SkinPanel):
    default_cursor = "eqnormal"

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        app.eq.changed.connect(self.update)
        app.player.volumeChanged.connect(self.update)
        self.rebuild()

    @property
    def shaded(self) -> bool:
        return bool(self.app.cfg["eq_shade"])

    def logical_size(self):
        return (W, 14) if self.shaded else (W, H)

    def region_path(self):
        return self.skin.region_path("equalizerws" if self.shaded else "equalizer")

    def build(self):
        a = self.app
        eq = a.eq
        self.add(Area((0, 0, W, 14), on_press=self.start_move,
                      on_double=a.toggle_eq_shade, cursor="eqtitle"))
        if self.shaded:
            self.add(Button((254, 3, 9, 9), lambda: (None, self.skin.sprite("EQ_EX", "EQ_MAXIMIZE_D")),
                            draw_normal=False, on_click=a.toggle_eq_shade))
            self.add(Button((264, 3, 9, 9), lambda: (self.skin.sprite("EQ_EX", "EQS_CLOSE"),
                                                     self.skin.sprite("EQ_EX", "EQS_CLOSE_D")),
                            on_click=a.toggle_eq_window, cursor="eqclose"))

            def vthumb(pr, v):
                n = "EQS_VOL_L" if v < 0.33 else "EQS_VOL_C" if v < 0.66 else "EQS_VOL_R"
                return self.skin.sprite("EQ_EX", n)

            def bthumb(pr, v):
                n = "EQS_BAL_L" if v < 0.4 else "EQS_BAL_C" if v < 0.6 else "EQS_BAL_R"
                return self.skin.sprite("EQ_EX", n)
            main = a.main_panel
            self.add(Slider((61, 4, 97, 7), thumb_size=(3, 7), thumb=vthumb,
                            value=lambda: max(0, a.player.volume) / 100.0,
                            on_change=lambda v: main._volume_change(v),
                            on_release=lambda v: main._volume_release(v)))
            self.add(Slider((164, 4, 43, 7), thumb_size=(3, 7), thumb=bthumb,
                            value=lambda: (a.balance + 100) / 200.0,
                            on_change=lambda v: main._balance_change(v),
                            on_release=lambda v: main._balance_release(v)))
            return
        self.add(Button((254, 3, 9, 9), lambda: (None, self.skin.sprite("EQ_EX", "EQ_MINIMIZE_D")
                                                if self.skin.has_own("EQ_EX") else
                                                self.skin.sprite("EQMAIN", "EQ_SHADE_BTN_FALLBACK")),
                        draw_normal=False, on_click=a.toggle_eq_shade))
        self.add(Button((264, 3, 9, 9), lambda: (None, self.skin.sprite("EQMAIN", "EQ_CLOSE_D")),
                        draw_normal=False, on_click=a.toggle_eq_window, cursor="eqclose"))
        self.add(Toggle((14, 18, 26, 12),
                        lambda: tuple(self.skin.sprite("EQMAIN", n) for n in
                                      ("EQ_ON", "EQ_ON_D", "EQ_ON_SEL", "EQ_ON_SEL_D")),
                        selected=lambda: eq.enabled, on_click=eq.toggle,
                        tooltip="Activar ecualizador"))
        self.add(Toggle((40, 18, 32, 12),
                        lambda: tuple(self.skin.sprite("EQMAIN", n) for n in
                                      ("EQ_AUTO", "EQ_AUTO_D", "EQ_AUTO_SEL", "EQ_AUTO_SEL_D")),
                        selected=lambda: a.cfg["eq_auto"], on_click=a.toggle_eq_auto,
                        tooltip="Cargar preajuste automáticamente por canción"))
        self.add(Button((217, 18, 44, 12), lambda: (self.skin.sprite("EQMAIN", "EQ_PRESETS"),
                                                    self.skin.sprite("EQMAIN", "EQ_PRESETS_D")),
                        on_click=lambda: a.show_eq_presets_menu(self._global(QPoint(217, 30)))))

        def band_bg(p, r, v):
            p.drawPixmap(r.topLeft(), self.skin.eq_band_frame(int(round(v * 27))))

        def band_thumb(pr, v):
            return self.skin.sprite("EQMAIN", "EQ_THUMB_SEL" if pr else "EQ_THUMB")

        self.add(Slider((21, 38, 14, 63), thumb_size=(11, 11), thumb_offset=1,
                        background=band_bg, thumb=band_thumb, vertical=True,
                        track_length=62, cursor="eqslid",
                        value=lambda: db_to_v(eq.preamp),
                        on_change=lambda v: self._set_preamp(v),
                        on_release=lambda v: eq.commit(), wheel_step=1 / 24))
        for i, x in enumerate(BAND_X):
            self.add(Slider((x, 38, 14, 63), thumb_size=(11, 11), thumb_offset=1,
                            background=band_bg, thumb=band_thumb, vertical=True,
                            track_length=62, cursor="eqslid",
                            value=lambda i=i: db_to_v(eq.bands[i]),
                            on_change=lambda v, i=i: self._set_band(i, v),
                            on_release=lambda v: eq.commit(), wheel_step=1 / 24,
                            tooltip=f"{FREQS[i]} Hz"))
        # +12 / 0 / -12 labels reset all bands like Winamp
        self.add(Area((45, 36, 22, 8), on_click=lambda: eq.set_all(12)))
        self.add(Area((45, 64, 22, 8), on_click=lambda: eq.set_all(0)))
        self.add(Area((45, 95, 22, 8), on_click=lambda: eq.set_all(-12)))

    def _set_band(self, i, v):
        db = v_to_db(v)
        self.app.eq.set_band(i, db)
        self.app.main_panel.set_temp_text(f"EQ: {FREQS[i]}HZ {db:+.1f} DB")

    def _set_preamp(self, v):
        db = v_to_db(v)
        self.app.eq.set_preamp(db)
        self.app.main_panel.set_temp_text(f"Preamp: {db:+.1f} DB")

    def _global(self, logical: QPoint) -> QPoint:
        return self.mapToGlobal(QPoint(logical.x() * self.scale, logical.y() * self.scale))

    def paint_background(self, p: QPainter):
        sk = self.skin
        active = self.is_active()
        if self.shaded:
            if sk.has_own("EQ_EX") or not sk.has_own("EQMAIN"):
                p.drawPixmap(0, 0, sk.sprite("EQ_EX", "EQS_BG_SEL" if active else "EQS_BG"))
            else:
                p.drawPixmap(0, 0, sk.sprite("EQMAIN", "EQ_TITLE_SEL" if active else "EQ_TITLE"))
            return
        p.drawPixmap(0, 0, sk.sprite("EQMAIN", "EQ_BG"))
        p.drawPixmap(0, 0, sk.sprite("EQMAIN", "EQ_TITLE_SEL" if active else "EQ_TITLE"))
        self._paint_graph(p)

    def _paint_graph(self, p: QPainter):
        sk = self.skin
        eq = self.app.eq
        p.drawPixmap(GRAPH.topLeft(), sk.sprite("EQMAIN", "EQ_GRAPH_BG"))
        gh = GRAPH.height()
        py = int(round((1 - db_to_v(eq.preamp)) * (gh - 1)))
        p.drawPixmap(GRAPH.left(), GRAPH.top() + py, sk.sprite("EQMAIN", "EQ_PREAMP_LINE"))
        colors = [sk.pixel("EQMAIN", 115, 294 + y) for y in range(19)]
        xs = [i * 108 / 9 for i in range(10)]
        ys = [(1 - db_to_v(b)) * (gh - 1) for b in eq.bands]
        pts = spline(xs, ys, list(range(109)))
        prev = None
        for x, y in enumerate(pts):
            yi = max(0, min(gh - 1, int(round(y))))
            lo, hi = (yi, yi) if prev is None else (min(prev, yi), max(prev, yi))
            for yy in range(lo, hi + 1):
                p.fillRect(GRAPH.left() + 2 + x, GRAPH.top() + yy, 1, 1, colors[yy])
            prev = yi
