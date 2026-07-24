# ui/dialogs/target_config_dialog.py
"""Dialog per configurare forma e colore predefiniti dei bersagli IPSC.

Ogni tipo bersaglio ha un colore e un SVG associato, definiti
centralmente e non modificabili per singolo item.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QColorDialog, QFrame, QScrollArea,
    QWidget, QGridLayout, QSizePolicy,
)

from core.models import ItemType
from ui.editor.target_images import TargetSvgManager

# Tipi bersaglio mostrati nel pannello (ordine)
_CONFIGURABLE_TARGETS: list[ItemType] = [
    ItemType.PAPER_TARGET,
    ItemType.MINI_TARGET,
    ItemType.MICRO_TARGET,
    ItemType.STEEL_TARGET,
    ItemType.POPPER,
    ItemType.METAL_PLATE,
    ItemType.NO_SHOOT,
    ItemType.SWINGER,
    ItemType.DROP_TURNER,
    ItemType.MOVER,
]

_LABELS: dict[ItemType, str] = {
    ItemType.PAPER_TARGET:  "Paper Target",
    ItemType.MINI_TARGET:   "Mini Target",
    ItemType.MICRO_TARGET:  "Micro Target",
    ItemType.STEEL_TARGET:  "Steel Target",
    ItemType.POPPER:        "Popper",
    ItemType.METAL_PLATE:   "Metal Plate",
    ItemType.NO_SHOOT:      "No-Shoot",
    ItemType.SWINGER:       "Swinger",
    ItemType.DROP_TURNER:   "Drop Turner",
    ItemType.MOVER:         "Mover",
}


class _TargetColorRow(QFrame):
    """Riga per un tipo bersaglio: anteprima SVG + colore + pulsante reset."""

    def __init__(self, item_type: ItemType, parent=None):
        super().__init__(parent)
        self._item_type = item_type
        self._manager = TargetSvgManager.instance()
        self._original_color = self._manager.get_color(item_type)
        self._current_color = QColor(self._original_color)

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Anteprima SVG
        self._preview = QLabel()
        self._preview.setFixedSize(40, 40)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._preview)

        # Nome
        label = QLabel(_LABELS.get(item_type, item_type.name))
        label.setMinimumWidth(120)
        label.setStyleSheet("font-weight: 600; color: #0f172a; border: none;")
        layout.addWidget(label)

        # Bottone colore
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(36, 36)
        self._color_btn.clicked.connect(self._pick_color)
        self._update_color_style()
        layout.addWidget(self._color_btn)

        # Valore hex
        self._hex_label = QLabel(self._current_color.name().upper())
        self._hex_label.setStyleSheet("font-family: monospace; color: #475569; border: none;")
        self._hex_label.setFixedWidth(70)
        layout.addWidget(self._hex_label)

        layout.addStretch()

        # Reset al default
        reset_btn = QPushButton("↺")
        reset_btn.setFixedSize(30, 30)
        reset_btn.setToolTip("Ripristina colore IPSC predefinito")
        reset_btn.clicked.connect(self._reset_default)
        layout.addWidget(reset_btn)

        self._refresh_preview()

    def _refresh_preview(self):
        """Aggiorna anteprima SVG colorata."""
        pixmap = self._manager.get_pixmap(self._item_type, 36, 36)
        if pixmap is not None:
            self._preview.setPixmap(pixmap)
        else:
            self._preview.setText("N/A")

    def _update_color_style(self):
        c = self._current_color.name()
        self._color_btn.setStyleSheet(
            f"background-color: {c}; border: 2px solid #cbd5e1; border-radius: 4px;"
        )
        self._hex_label.setText(c.upper())

    def _pick_color(self):
        color = QColorDialog.getColor(
            self._current_color, self, f"Colore — {_LABELS.get(self._item_type)}"
        )
        if color.isValid():
            self._current_color = color
            self._manager.set_color(self._item_type, color)
            self._update_color_style()
            self._refresh_preview()

    def _reset_default(self):
        self._manager.set_color(self._item_type, QColor(self._original_color))
        self._current_color = QColor(self._original_color)
        self._manager.set_color(self._item_type, self._current_color)
        self._update_color_style()
        self._refresh_preview()

    def apply_changes(self):
        """Applica il colore corrente al manager (già fatto in tempo reale)."""
        self._manager.set_color(self._item_type, self._current_color)


class TargetConfigDialog(QDialog):
    """Dialog modale per configurare l'aspetto dei bersagli IPSC."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Aspetto Bersagli")
        self.setMinimumSize(500, 550)
        self.setModal(True)

        self._manager = TargetSvgManager.instance()
        self._rows: list[_TargetColorRow] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Titolo
        title = QLabel("Aspetto Bersagli IPSC")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Configura il colore predefinito per ogni tipo di bersaglio. "
            "Il colore sarà applicato a tutti i bersagli di quel tipo."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Area scrollabile con le righe
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        grid = QVBoxLayout(container)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        for item_type in _CONFIGURABLE_TARGETS:
            row = _TargetColorRow(item_type)
            self._rows.append(row)
            grid.addWidget(row)

        grid.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Pulsanti in basso
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_all_btn = QPushButton("Ripristina Default IPSC")
        reset_all_btn.setStyleSheet(
            "QPushButton { color: #dc2626; border-color: #fecaca; }"
            "QPushButton:hover { background: #fef2f2; }"
        )
        reset_all_btn.clicked.connect(self._reset_all)
        btn_layout.addWidget(reset_all_btn)

        close_btn = QPushButton("Chiudi")
        close_btn.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none; font-weight: 600; }"
            "QPushButton:hover { background: #2563eb; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _reset_all(self):
        """Ripristina tutti i colori ai default IPSC."""
        self._manager.reset_to_defaults()
        for row in self._rows:
            original = self._manager.get_color(row._item_type)
            row._current_color = QColor(original)
            row._original_color = QColor(original)
            row._update_color_style()
            row._refresh_preview()
