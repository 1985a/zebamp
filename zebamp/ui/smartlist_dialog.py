"""Editor for a smart list: name, rules, order and limit."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..smartlist import FIELDS, ORDERS, clean_smart_list, ops_for
from ..i18n import tr

DEFAULT_RULE = {"field": "genre", "op": "contains", "value": ""}


class _RuleRow(QWidget):
    """One rule: field, comparison and value."""

    def __init__(self, rule: dict, on_remove):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.field = QComboBox()
        for key, label in FIELDS.items():
            self.field.addItem(label, key)
        self.op = QComboBox()
        self.value = QLineEdit()
        remove = QPushButton(tr("Quitar"))
        remove.clicked.connect(lambda: on_remove(self))
        for widget in (self.field, self.op, self.value, remove):
            lay.addWidget(widget)
        self.field.setCurrentIndex(max(0, self.field.findData(rule.get("field"))))
        self._fill_ops()
        self.op.setCurrentIndex(max(0, self.op.findData(rule.get("op"))))
        value = rule.get("value", "")
        self.value.setText(f"{value:g}" if isinstance(value, float) else str(value))
        self.field.currentIndexChanged.connect(self._fill_ops)

    def _fill_ops(self):
        """Text and number fields are compared in different ways."""
        self.op.clear()
        for key, label in ops_for(self.field.currentData()).items():
            self.op.addItem(label, key)

    def rule(self) -> dict:
        return {"field": self.field.currentData(), "op": self.op.currentData(),
                "value": self.value.text().replace(",", ".").strip()}


class SmartListDialog(QDialog):
    """Returns the edited list in `result_list` when accepted."""

    def __init__(self, app, smart: dict | None = None):
        super().__init__(None)
        from .dialogs import _style
        _style(self, app)
        self.setWindowTitle(tr("Lista inteligente"))
        self.resize(560, 360)
        self.result_list: dict | None = None
        smart = smart or {"name": "", "match": "all", "rules": [dict(DEFAULT_RULE)], "order": "artist",
                          "limit": 0}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(smart["name"])
        self.match = QComboBox()
        self.match.addItem(tr("todas las reglas"), "all")
        self.match.addItem(tr("alguna de las reglas"), "any")
        self.match.setCurrentIndex(max(0, self.match.findData(smart["match"])))
        form.addRow(tr("Nombre:"), self.name)
        form.addRow(tr("Canciones que cumplen:"), self.match)
        lay.addLayout(form)
        self.rules_box = QVBoxLayout()
        lay.addLayout(self.rules_box)
        self.rows: list[_RuleRow] = []
        for rule in smart["rules"]:
            self._add_row(rule)
        add = QPushButton(tr("Añadir regla"))
        add.clicked.connect(lambda: self._add_row(dict(DEFAULT_RULE)))
        lay.addWidget(add)
        form = QFormLayout()
        self.order = QComboBox()
        for key, label in ORDERS.items():
            self.order.addItem(label, key)
        self.order.setCurrentIndex(max(0, self.order.findData(smart["order"])))
        self.limit = QSpinBox()
        self.limit.setRange(0, 100000)
        self.limit.setSpecialValueText(tr("sin límite"))
        self.limit.setValue(int(smart["limit"]))
        form.addRow(tr("Orden:"), self.order)
        form.addRow(tr("Máximo de canciones:"), self.limit)
        lay.addLayout(form)
        self.problem = QLabel()
        lay.addWidget(self.problem)
        lay.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _add_row(self, rule: dict):
        row = _RuleRow(rule, self._remove_row)
        self.rows.append(row)
        self.rules_box.addWidget(row)

    def _remove_row(self, row: _RuleRow):
        if len(self.rows) > 1:              # a list without rules selects nothing useful
            self.rows.remove(row)
            row.deleteLater()

    def edited(self) -> dict | None:
        """What the dialog holds now, or None while it is incomplete."""
        return clean_smart_list({"name": self.name.text(), "match": self.match.currentData(),
                                 "rules": [row.rule() for row in self.rows],
                                 "order": self.order.currentData(), "limit": self.limit.value()})

    def _accept(self):
        smart = self.edited()
        if smart is None:
            self.problem.setText(tr("Falta el nombre o alguna regla tiene el valor vacío o no es un número."))
            return
        if len(smart["rules"]) < len(self.rows):
            self.problem.setText(tr("Alguna regla tiene el valor vacío o no es un número."))
            return
        self.result_list = smart
        self.accept()
