"""MilkDrop configuration window (like Winamp's MilkDrop config panel)."""
from __future__ import annotations

import glob
import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)
from ..i18n import tr


def count_presets(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    return len(glob.glob(os.path.join(folder, "**", "*.milk"), recursive=True)) + \
        len(glob.glob(os.path.join(folder, "**", "*.prjm"), recursive=True))


class MilkdropConfig(QDialog):
    QUALITIES = [("low", tr("Baja (más ligera)")), ("medium", tr("Media")), ("high", tr("Alta")),
                 ("custom", tr("Personalizada"))]

    def __init__(self, app):
        super().__init__(None)
        self.app = app
        cfg = app.cfg
        self.setWindowTitle(tr("Configuración de MilkDrop - Zebamp"))
        self.setPalette(getattr(app, "dialog_palette", self.palette()))
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # ------------------------------------------------------- presets
        w = QWidget()
        f = QFormLayout(w)
        from ..milkdrop import preset_dirs
        row = QHBoxLayout()
        self.folder = QLineEdit(cfg["milkdrop_presets"] or "")
        self.folder.setPlaceholderText(preset_dirs({"milkdrop_presets": ""}) or tr("(presets de "
                                                                                   "projectM del "
                                                                                   "sistema)"))
        self.folder.textChanged.connect(self._count)
        row.addWidget(self.folder, 1)
        b = QPushButton(tr("Elegir…"))
        b.clicked.connect(self._pick)
        row.addWidget(b)
        b2 = QPushButton(tr("Sistema"))
        b2.setToolTip(tr("Usar los presets que trae projectM"))
        b2.clicked.connect(lambda: self.folder.setText(""))
        row.addWidget(b2)
        f.addRow(tr("Carpeta de presets:"), row)
        self.count = QLabel("")
        f.addRow("", self.count)
        self.duration = QSpinBox()
        self.duration.setRange(5, 600)
        self.duration.setSuffix(" s")
        self.duration.setValue(int(cfg["milkdrop_duration"]))
        f.addRow(tr("Cambiar de preset cada:"), self.duration)
        self.smooth = QSpinBox()
        self.smooth.setRange(0, 30)
        self.smooth.setSuffix(" s")
        self.smooth.setValue(int(cfg["milkdrop_smooth"]))
        f.addRow(tr("Duración de la transición suave:"), self.smooth)
        self.shuffle = QCheckBox(tr("Orden aleatorio de presets (también al pulsar «siguiente»)"))
        self.shuffle.setChecked(bool(cfg["milkdrop_shuffle"]))
        f.addRow(self.shuffle)
        self.hardcut = QCheckBox(tr("Cortes bruscos con los golpes fuertes de la música"))
        self.hardcut.setChecked(bool(cfg["milkdrop_hardcut"]))
        f.addRow(self.hardcut)
        self.hardmin = QSpinBox()
        self.hardmin.setRange(1, 600)
        self.hardmin.setSuffix(" s")
        self.hardmin.setValue(int(cfg["milkdrop_hardcut_min"]))
        f.addRow(tr("Tiempo mínimo entre cortes bruscos:"), self.hardmin)
        self.hardsens = QDoubleSpinBox()
        self.hardsens.setRange(0.5, 50.0)
        self.hardsens.setSingleStep(0.5)
        self.hardsens.setValue(float(cfg["milkdrop_hardcut_sens"]))
        f.addRow(tr("Umbral de corte brusco (menor = más cortes):"), self.hardsens)
        tabs.addTab(w, "Presets")

        # ------------------------------------------------------- visual
        w = QWidget()
        f = QFormLayout(w)
        self.quality = QComboBox()
        for k, label in self.QUALITIES:
            self.quality.addItem(label, k)
        self.quality.setCurrentIndex([k for k, _ in self.QUALITIES].index(cfg["milkdrop_quality"])
                                     if cfg["milkdrop_quality"] in [k for k, _ in self.QUALITIES] else 1)
        self.quality.currentIndexChanged.connect(self._quality_changed)
        f.addRow(tr("Calidad:"), self.quality)
        self.mesh_x = QSpinBox()
        self.mesh_x.setRange(8, 192)
        self.mesh_x.setValue(int(cfg["milkdrop_mesh_x"]))
        self.mesh_y = QSpinBox()
        self.mesh_y.setRange(6, 144)
        self.mesh_y.setValue(int(cfg["milkdrop_mesh_y"]))
        mrow = QHBoxLayout()
        mrow.addWidget(self.mesh_x)
        mrow.addWidget(QLabel("×"))
        mrow.addWidget(self.mesh_y)
        f.addRow(tr("Malla (detalle de los efectos):"), mrow)
        self.texture = QComboBox()
        for t in (256, 512, 1024, 2048, 4096):
            self.texture.addItem(f"{t} × {t}", t)
        self.texture.setCurrentIndex(max(0, [256, 512, 1024, 2048, 4096].index(int(cfg["milkdrop_texture"]))
                                         if int(cfg["milkdrop_texture"]) in (256, 512, 1024, 2048, 4096) else 2))
        f.addRow(tr("Textura interna:"), self.texture)
        self.fps = QSpinBox()
        self.fps.setRange(15, 144)
        self.fps.setValue(int(cfg["milkdrop_fps"]))
        f.addRow(tr("Fotogramas por segundo:"), self.fps)
        self.beat = QDoubleSpinBox()
        self.beat.setRange(0.1, 5.0)
        self.beat.setSingleStep(0.1)
        self.beat.setValue(float(cfg["milkdrop_beat"]))
        f.addRow(tr("Sensibilidad al ritmo:"), self.beat)
        self.aspect = QCheckBox(tr("Corregir la proporción de las figuras"))
        self.aspect.setChecked(bool(cfg["milkdrop_aspect"]))
        f.addRow(self.aspect)
        self.title = QCheckBox(tr("Mostrar el título al cambiar de canción"))
        self.title.setChecked(bool(cfg["milkdrop_title"]))
        f.addRow(self.title)
        self.fullscreen = QCheckBox(tr("Abrir directamente a pantalla completa"))
        self.fullscreen.setChecked(bool(cfg["milkdrop_fullscreen"]))
        f.addRow(self.fullscreen)
        note = QLabel(tr("Más malla, textura y fotogramas = más detalle, pero más trabajo para la "
                         "tarjeta gráfica y la CPU."))
        note.setWordWrap(True)
        f.addRow(note)
        tabs.addTab(w, tr("Imagen"))

        # --------------------------------------------------------- keys
        w = QWidget()
        v = QVBoxLayout(w)
        keys = QLabel(
            tr("<table cellspacing=4><tr><td><b>Espacio / N</b></td><td>siguiente preset (con "
               "transición)</td></tr><tr><td><b>H</b></td><td>corte brusco a otro "
               "preset</td></tr><tr><td><b>Retroceso / P</b></td><td>preset "
               "anterior</td></tr><tr><td><b>L</b></td><td>elegir preset (con "
               "búsqueda)</td></tr><tr><td><b>K / Bloq Despl</b></td><td>bloquear el preset "
               "actual</td></tr><tr><td><b>R</b></td><td>orden aleatorio "
               "sí/no</td></tr><tr><td><b>T</b></td><td>mostrar el "
               "título</td></tr><tr><td><b>C</b></td><td>esta configuración</td></tr><tr><td><b>Enter / "
               "F / F11 / doble clic</b></td><td>pantalla "
               "completa</td></tr><tr><td><b>Esc</b></td><td>salir de pantalla completa / "
               "cerrar</td></tr><tr><td><b>Clic derecho</b></td><td>menú</td></tr></table>"))
        v.addWidget(keys)
        v.addStretch(1)
        tabs.addTab(w, tr("Teclas"))

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel |
                              QDialogButtonBox.StandardButton.Apply)
        bb.accepted.connect(lambda: (self._apply(), self.accept()))
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        lay.addWidget(bb)
        self._count()
        self._quality_changed()

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de presets de MilkDrop"),
                                             self.folder.text() or os.path.expanduser("~"))
        if d:
            self.folder.setText(d)

    def _count(self, *_):
        from ..milkdrop import preset_dirs
        folder = self.folder.text().strip() or preset_dirs({"milkdrop_presets": ""}) or ""
        n = count_presets(folder)
        self.count.setText(tr("{0} presets encontrados").format(n) if n
                           else tr("No se encontraron presets .milk en esa carpeta"))

    def _quality_changed(self, *_):
        custom = self.quality.currentData() == "custom"
        for wdg in (self.mesh_x, self.mesh_y, self.texture):
            wdg.setEnabled(custom)

    def _apply(self):
        cfg = self.app.cfg
        new = {
            "milkdrop_presets": self.folder.text().strip(),
            "milkdrop_duration": self.duration.value(), "milkdrop_smooth": self.smooth.value(),
            "milkdrop_shuffle": self.shuffle.isChecked(), "milkdrop_hardcut": self.hardcut.isChecked(),
            "milkdrop_hardcut_min": self.hardmin.value(), "milkdrop_hardcut_sens": self.hardsens.value(),
            "milkdrop_quality": self.quality.currentData(), "milkdrop_mesh_x": self.mesh_x.value(),
            "milkdrop_mesh_y": self.mesh_y.value(), "milkdrop_texture": self.texture.currentData(),
            "milkdrop_fps": self.fps.value(), "milkdrop_beat": round(self.beat.value(), 2),
            "milkdrop_aspect": self.aspect.isChecked(), "milkdrop_title": self.title.isChecked(),
            "milkdrop_fullscreen": self.fullscreen.isChecked(),
        }
        # settings projectM only reads when it starts
        restart_keys = {"milkdrop_presets", "milkdrop_smooth", "milkdrop_hardcut", "milkdrop_hardcut_min",
                        "milkdrop_hardcut_sens", "milkdrop_quality", "milkdrop_mesh_x", "milkdrop_mesh_y",
                        "milkdrop_texture", "milkdrop_beat", "milkdrop_aspect"}
        changed = {k for k, v in new.items() if cfg[k] != v}
        for k, v in new.items():
            cfg[k] = v
        cfg.save()
        md = getattr(self.app, "milkdrop", None)
        if md is None or not changed:
            return
        if changed & restart_keys and md.isVisible():
            self.app.restart_milkdrop()
            return
        if "milkdrop_duration" in changed:
            md.set_duration(new["milkdrop_duration"])
        if "milkdrop_shuffle" in changed and md.pm:
            md.lib.zpm_shuffle(md.pm, 1 if new["milkdrop_shuffle"] else 0)
        if "milkdrop_fps" in changed and md.isVisible():
            md.start()
