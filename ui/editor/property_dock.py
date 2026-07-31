# ui/editor/property_dock.py
"""Dock widget per editare le proprietà dell'oggetto selezionato."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import ItemType
from core.target_designer import CUSTOM_TARGETS_DIR, ensure_custom_dir
from ui.editor.stage_scene import StageItemWrapper, SvgTargetGraphicsItem
from ui.icons import load_icon

# Tipi bersaglio: colore e forma sono definiti centralmente, non modificabili per item
_TARGET_TYPES = {
    ItemType.PAPER_TARGET,
    ItemType.STEEL_TARGET,
    ItemType.POPPER,
    ItemType.METAL_PLATE,
    ItemType.MINI_TARGET,
    ItemType.MICRO_TARGET,
    ItemType.NO_SHOOT,
    ItemType.SWINGER,
    ItemType.DROP_TURNER,
    ItemType.MOVER,
    # Compositi
    ItemType.DOUBLET_SIDE,
    ItemType.DOUBLET_OVERLAP,
    ItemType.DOUBLET_SIDE_HOSTAGE,
    ItemType.DOUBLET_OVERLAP_HOSTAGE,
    ItemType.BOBBER_PLATE,
    ItemType.DOUBLE_BOBBER,
    ItemType.TARGET_PLUS_NOSHOOT,
}


class PropertyDock(QDockWidget):
    """Dock laterale per editing proprietà oggetto stage."""

    propertyChanged = Signal(int, dict)  # item_id, {field: value}
    markerChanged = Signal(dict)  # {field: value}, per marker scene

    def __init__(self, parent=None):
        super().__init__("Proprietà", parent)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._wrapper: Optional[StageItemWrapper] = None
        self._marker_ref: object = None

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

        # Bersaglio personalizzato (solo per tipi target)
        self._custom_svg_widget = QWidget()
        custom_svg_layout = QHBoxLayout(self._custom_svg_widget)
        custom_svg_layout.setContentsMargins(0, 0, 0, 0)
        custom_svg_layout.setSpacing(4)
        self._custom_svg_combo = QComboBox()
        self._custom_svg_combo.setMinimumWidth(100)
        self._custom_svg_combo.currentIndexChanged.connect(self._on_custom_svg_combo_changed)
        custom_svg_layout.addWidget(self._custom_svg_combo)
        self._btn_browse_svg = QPushButton("…")
        self._btn_browse_svg.setFixedWidth(26)
        self._btn_browse_svg.setToolTip("Sfoglia per un file SVG…")
        self._btn_browse_svg.clicked.connect(self._on_browse_custom_svg)
        custom_svg_layout.addWidget(self._btn_browse_svg)
        self._btn_reset_svg = QPushButton(load_icon("close"), "")
        self._btn_reset_svg.setFixedWidth(26)
        self._btn_reset_svg.setToolTip("Ripristina bersaglio default IPSC")
        self._btn_reset_svg.clicked.connect(self._on_reset_custom_svg)
        custom_svg_layout.addWidget(self._btn_reset_svg)
        self._custom_svg_widget.setVisible(False)
        form.addRow("Aspetto:", self._custom_svg_widget)

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
            self._color_btn.setStyleSheet(
                "background-color: #808080; border-radius: 4px; border: 1px solid #e2e8f0;"
            )
            self._custom_svg_widget.setVisible(False)
        else:
            it = wrapper.item
            is_target = it.item_type in _TARGET_TYPES
            self.setEnabled(True)
            self._title.setText(it.label or f"Oggetto #{it.id}")
            self._type_label.setText(it.item_type.name.replace("_", " ").title())
            self._id_label.setText(str(it.id))
            self._label_edit.setText(it.label)
            self._x_spin.setValue(it.x)
            self._y_spin.setValue(it.y)
            self._w_spin.setValue(it.width)
            self._w_spin.setEnabled(True)
            self._h_spin.setValue(it.height)
            self._h_spin.setEnabled(True)
            self._rot_spin.setEnabled(True)
            self._rot_spin.setValue(it.rotation)
            self._update_color_btn(it.color)
            self._color_btn.setEnabled(True)
            self._color_btn.setToolTip("Clicca per cambiare colore")
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
            # Bersaglio personalizzato
            self._custom_svg_widget.setVisible(is_target)
            if is_target:
                custom_path = it.properties.get("custom_svg_path", "")
                self._custom_svg_combo.blockSignals(True)
                self._populate_custom_svg_combo(custom_path)
                self._custom_svg_combo.blockSignals(False)
        self._block_signals = False

    @Slot(object, object)
    def set_marker(self, props, marker_ref):
        """Mostra proprietà di un marker (posizione/ostacolo)."""
        self._wrapper = None
        self._block_signals = True
        self._marker_ref = marker_ref

        if props is None:
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
            self._mobility_group.setVisible(False)
            self._custom_svg_widget.setVisible(False)
        else:
            self.setEnabled(True)
            self._custom_svg_widget.setVisible(False)
            marker_type = props["type"]
            if marker_type == "shooting_position":
                self._title.setText(f"Posizione #{props.get('label', '?')}")
                self._type_label.setText("Posizione di tiro")
                self._id_label.setText("#" + props.get("label", "?"))
                self._label_edit.setText(f"Pos #{props.get('label', '?')}")
                self._x_spin.setValue(props["x"])
                self._y_spin.setValue(props["y"])
                self._w_spin.setEnabled(False)
                self._w_spin.setValue(0.5)
                self._h_spin.setEnabled(False)
                self._h_spin.setValue(0.5)
                self._rot_spin.setEnabled(False)
                self._rot_spin.setValue(0)
                self._color_btn.setEnabled(False)
                self._color_btn.setStyleSheet(
                    "background-color: #22c55e; border-radius: 4px;"
                    if props.get("is_start")
                    else "background-color: #3b82f6; border-radius: 4px;"
                )
                self._mobility_group.setVisible(False)
            elif marker_type == "obstacle":
                tipo = "Muro" if props.get("is_wall") else "Barriera"
                self._title.setText(f"{tipo} {props.get('label', '')}")
                self._type_label.setText(tipo)
                self._id_label.setText("—")
                self._label_edit.setText(tipo)
                self._x_spin.setValue(props["x"])
                self._y_spin.setValue(props["y"])
                self._w_spin.setEnabled(True)
                self._w_spin.setValue(props.get("width", 3.0))
                self._h_spin.setEnabled(False)
                self._h_spin.setValue(0.2)
                self._rot_spin.setEnabled(True)
                self._rot_spin.setValue(props.get("rotation", 0.0))
                self._color_btn.setEnabled(False)
                bg = "#475569" if props.get("is_wall") else "#fbbf24"
                self._color_btn.setStyleSheet(f"background-color: {bg}; border-radius: 4px;")
                self._mobility_group.setVisible(False)
        self._block_signals = False

    def _update_color_btn(self, color: str):
        self._color_btn.setStyleSheet(
            f"background-color: {color}; border-radius: 4px; border: 1px solid #e2e8f0;"
        )

    def _emit(self, **kwargs):
        if self._block_signals:
            return
        if self._wrapper is not None:
            self.propertyChanged.emit(self._wrapper.item.id, kwargs)
        elif hasattr(self, "_marker_ref") and self._marker_ref is not None:
            self.markerChanged.emit(kwargs)

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
        it = self._wrapper.item
        if it.item_type in _TARGET_TYPES:
            return  # bersagli: colore centralizzato, non modificabile
        color = QColorDialog.getColor(QColor(it.color), self, "Seleziona colore")
        if color.isValid():
            hex_color = color.name()
            self._update_color_btn(hex_color)
            self._emit(color=hex_color)

    # ── Bersaglio personalizzato ────────────────────────────────────────

    def _populate_custom_svg_combo(self, current_path: str):
        """Popola la QComboBox con gli SVG disponibili.

        current_path: il percorso attuale (o "" per default).
        Se il percorso non è nella lista, lo aggiunge come "Altro…".
        """
        self._custom_svg_combo.clear()
        self._custom_svg_combo.addItem("Default IPSC", "")

        ensure_custom_dir()
        found = False
        if os.path.isdir(CUSTOM_TARGETS_DIR):
            for fname in sorted(os.listdir(CUSTOM_TARGETS_DIR)):
                if fname.lower().endswith(".svg"):
                    full_path = os.path.join(CUSTOM_TARGETS_DIR, fname)
                    self._custom_svg_combo.addItem(fname, full_path)
                    if current_path and os.path.samefile(full_path, current_path):
                        found = True

        # Se il percorso corrente non è nella lista (file esterno)
        if current_path and not found:
            self._custom_svg_combo.addItem(os.path.basename(current_path), current_path)
            idx = self._custom_svg_combo.count() - 1
        elif current_path:
            # Trova l'indice del percorso corrente
            idx = self._custom_svg_combo.findData(current_path)
        else:
            idx = 0  # Default IPSC

        self._custom_svg_combo.setCurrentIndex(max(0, idx))

    def _on_custom_svg_combo_changed(self, index: int):
        """Cambia il bersaglio personalizzato in base alla selezione combo."""
        if self._block_signals or self._wrapper is None:
            return
        path = self._custom_svg_combo.itemData(index)
        if path is None:
            path = ""
        # Rende il percorso portabile (relativo a resources/ se possibile)
        portable = SvgTargetGraphicsItem._make_path_portable(path) if path else ""
        self._emit(properties={"custom_svg_path": portable})

    def _on_browse_custom_svg(self):
        """Apre un file dialog per selezionare un SVG personalizzato."""
        start_dir = (
            CUSTOM_TARGETS_DIR if os.path.isdir(CUSTOM_TARGETS_DIR) else os.path.expanduser("~")
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona SVG bersaglio", start_dir, "SVG (*.svg);;Tutti i file (*)"
        )
        if not path:
            return
        if self._wrapper is None:
            return
        # Rende il percorso portabile
        portable = SvgTargetGraphicsItem._make_path_portable(path)
        self._custom_svg_combo.blockSignals(True)
        # Aggiunge il file selezionato alla combo (se non già presente)
        idx = self._custom_svg_combo.findData(path)
        if idx < 0:
            self._custom_svg_combo.addItem(os.path.basename(path), path)
            idx = self._custom_svg_combo.count() - 1
        self._custom_svg_combo.setCurrentIndex(idx)
        self._custom_svg_combo.blockSignals(False)
        self._emit(properties={"custom_svg_path": portable})

    def _on_reset_custom_svg(self):
        """Resetta il bersaglio a default IPSC."""
        if self._wrapper is None:
            return
        self._custom_svg_combo.blockSignals(True)
        self._custom_svg_combo.setCurrentIndex(0)  # "Default IPSC"
        self._custom_svg_combo.blockSignals(False)
        self._emit(properties={"custom_svg_path": ""})
