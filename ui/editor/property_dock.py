# ui/editor/property_dock.py
"""Dock widget per editare le proprietà dell'oggetto selezionato."""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QLineEdit, QDoubleSpinBox,
    QSpinBox, QLabel, QPushButton, QHBoxLayout, QColorDialog,
    QComboBox, QVBoxLayout, QGroupBox
)

from core.models import StageItem, ItemType
from ui.editor.stage_scene import StageItemWrapper
import math


class PropertyDock(QDockWidget):
    """Dock laterale per editing proprietà oggetto stage."""
    propertyChanged = Signal(int, dict)  # item_id, {field: value}

    def __init__(self, parent=None):
        super().__init__("Proprietà", parent)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self._wrapper: Optional[StageItemWrapper] = None

        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Titolo
        self._title = QLabel("Nessuna selezione")
        self._title.setStyleSheet("font-weight: 700; font-size: 14px; color: #0f172a;")
        layout.addWidget(self._title)

        # Form
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._type_label = QLabel("—")
        form.addRow("Tipo:", self._type_label)

        self._id_label = QLabel("—")
        form.addRow("ID:", self._id_label)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("Nome oggetto")
        self._label_edit.editingFinished.connect(self._on_label_changed)
        form.addRow("Nome:", self._label_edit)

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(-100, 100)
        self._x_spin.setDecimals(2)
        self._x_spin.setSingleStep(0.5)
        self._x_spin.valueChanged.connect(self._on_position_changed)
        form.addRow("X (m):", self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(-100, 100)
        self._y_spin.setDecimals(2)
        self._y_spin.setSingleStep(0.5)
        self._y_spin.valueChanged.connect(self._on_position_changed)
        form.addRow("Y (m):", self._y_spin)

        self._w_spin = QDoubleSpinBox()
        self._w_spin.setRange(0.05, 50)
        self._w_spin.setDecimals(2)
        self._w_spin.setSingleStep(0.1)
        self._w_spin.valueChanged.connect(self._on_size_changed)
        form.addRow("Larghezza (m):", self._w_spin)

        self._h_spin = QDoubleSpinBox()
        self._h_spin.setRange(0.05, 50)
        self._h_spin.setDecimals(2)
        self._h_spin.setSingleStep(0.1)
        self._h_spin.valueChanged.connect(self._on_size_changed)
        form.addRow("Altezza (m):", self._h_spin)

        self._rot_spin = QDoubleSpinBox()
        self._rot_spin.setRange(-360, 360)
        self._rot_spin.setDecimals(1)
        self._rot_spin.setSingleStep(5)
        self._rot_spin.setSuffix("°")
        self._rot_spin.valueChanged.connect(self._on_rotation_changed)
        form.addRow("Rotazione:", self._rot_spin)

        # Colore
        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 28)
        self._color_btn.setStyleSheet("border-radius: 4px; border: 1px solid #e2e8f0;")
        self._color_btn.clicked.connect(self._on_color_pick)
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        form.addRow("Colore:", color_row)

        # Proprietà mobili (dinamiche)
        self._mobility_group = QGroupBox("Parametri movimento")
        self._mobility_layout = QFormLayout(self._mobility_group)
        self._mobility_group.setVisible(False)

        self._amp_spin = QDoubleSpinBox()
        self._amp_spin.setRange(5, 180)
        self._amp_spin.setDecimals(0)
        self._amp_spin.setSuffix("°")
        self._amp_spin.valueChanged.connect(self._on_mobility_changed)
        self._mobility_layout.addRow("Ampiezza:", self._amp_spin)

        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.1, 10.0)
        self._speed_spin.setDecimals(1)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.valueChanged.connect(self._on_mobility_changed)
        self._mobility_layout.addRow("Velocità:", self._speed_spin)

        self._dist_spin = QDoubleSpinBox()
        self._dist_spin.setRange(0.5, 20.0)
        self._dist_spin.setDecimals(1)
        self._dist_spin.setSingleStep(0.5)
        self._dist_spin.setSuffix(" m")
        self._dist_spin.valueChanged.connect(self._on_mobility_changed)
        self._mobility_layout.addRow("Distanza:", self._dist_spin)

        self._fall_spin = QDoubleSpinBox()
        self._fall_spin.setRange(0.1, 5.0)
        self._fall_spin.setDecimals(1)
        self._fall_spin.setSingleStep(0.1)
        self._fall_spin.setSuffix(" s")
        self._fall_spin.valueChanged.connect(self._on_mobility_changed)
        self._mobility_layout.addRow("Tempo caduta:", self._fall_spin)

        layout.addLayout(form)
        layout.addWidget(self._mobility_group)
        layout.addStretch()

        self._block_signals = False
        self.setEnabled(False)

    @Slot(object)
    def set_item(self, wrapper: Optional[StageItemWrapper]):
        self._wrapper = wrapper
        self._block_signals = True
        if wrapper is None:
            self.setEnabled(False)
            self._title.setText("Nessuna selezione")
            self._type_label.setText("—")
            self._id_label.setText("—")
            self._label_edit.clear()
            self._x_spin.setValue(0)
            self._y_spin.setValue(0)
            self._w_spin.setValue(1)
            self._h_spin.setValue(1)
            self._rot_spin.setValue(0)
            self._color_btn.setStyleSheet("background-color: #808080; border-radius: 4px; border: 1px solid #e2e8f0;")
        else:
            it = wrapper.item
            self.setEnabled(True)
            self._title.setText(it.label or f"Oggetto #{it.id}")
            self._type_label.setText(it.item_type.name.replace("_", " ").title())
            self._id_label.setText(str(it.id))
            self._label_edit.setText(it.label)
            self._x_spin.setValue(it.x)
            self._y_spin.setValue(it.y)
            self._w_spin.setValue(it.width)
            self._h_spin.setValue(it.height)
            self._rot_spin.setValue(it.rotation)
            self._update_color_btn(it.color)
            # Mostra/nascondi parametri mobili
            is_mobile = it.item_type in (ItemType.SWINGER, ItemType.MOVER, ItemType.DROP_TURNER)
            self._mobility_group.setVisible(is_mobile)
            if is_mobile:
                self._amp_spin.setValue(it.properties.get("amplitude", 45))
                self._speed_spin.setValue(it.properties.get("speed", 1.0))
                self._dist_spin.setValue(it.properties.get("distance", 3.0))
                self._fall_spin.setValue(it.properties.get("fall_time", 0.5))
                # Mostra solo i campi rilevanti
                self._amp_spin.parentWidget().setVisible(it.item_type == ItemType.SWINGER)
                self._dist_spin.parentWidget().setVisible(it.item_type == ItemType.MOVER)
                self._fall_spin.parentWidget().setVisible(it.item_type == ItemType.DROP_TURNER)
        self._block_signals = False

    def _update_color_btn(self, color: str):
        self._color_btn.setStyleSheet(
            f"background-color: {color}; border-radius: 4px; border: 1px solid #e2e8f0;"
        )

    def _emit(self, **kwargs):
        if self._block_signals or self._wrapper is None:
            return
        self.propertyChanged.emit(self._wrapper.item.id, kwargs)

    def _on_label_changed(self):
        text = self._label_edit.text()
        self._emit(label=text)
        if self._wrapper:
            self._title.setText(text or f"Oggetto #{self._wrapper.item.id}")

    def _on_position_changed(self):
        self._emit(x=self._x_spin.value(), y=self._y_spin.value())

    def _on_size_changed(self):
        self._emit(width=self._w_spin.value(), height=self._h_spin.value())

    def _on_rotation_changed(self):
        self._emit(rotation=self._rot_spin.value())

    def _on_mobility_changed(self):
        if self._wrapper is None:
            return
        it = self._wrapper.item
        props = dict(it.properties)
        if it.item_type == ItemType.SWINGER:
            props["amplitude"] = self._amp_spin.value()
            props["speed"] = self._speed_spin.value()
        elif it.item_type == ItemType.MOVER:
            props["distance"] = self._dist_spin.value()
            props["speed"] = self._speed_spin.value()
        elif it.item_type == ItemType.DROP_TURNER:
            props["fall_time"] = self._fall_spin.value()
        self._emit(properties=props)

    def _on_color_pick(self):
        if self._wrapper is None:
            return
        color = QColorDialog.getColor(QColor(self._wrapper.item.color), self, "Seleziona colore")
        if color.isValid():
            hex_color = color.name()
            self._update_color_btn(hex_color)
            self._emit(color=hex_color)
