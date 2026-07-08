# ui/editor/generator_panel.py
"""Pannello laterale per configurare e lanciare la generazione procedurale."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QProgressBar, QGroupBox,
    QFrame, QScrollArea
)

from core.generator import GeneratorConfig


class GeneratorPanel(QWidget):
    """Pannello di configurazione per la generazione procedurale."""
    generateRequested = Signal(GeneratorConfig)
    stopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Titolo
        title = QLabel("🎲 Generazione Procedurale")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        subtitle = QLabel("Genera automaticamente uno stage IPSC valido")
        subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(subtitle)

        # Gruppo Dimensioni
        dim_group = QGroupBox("Dimensioni Stage")
        dim_layout = QFormLayout(dim_group)
        dim_layout.setSpacing(8)

        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(5, 50)
        self._width_spin.setDecimals(1)
        self._width_spin.setValue(20.0)
        self._width_spin.setSuffix(" m")
        dim_layout.addRow("Larghezza:", self._width_spin)

        self._depth_spin = QDoubleSpinBox()
        self._depth_spin.setRange(5, 50)
        self._depth_spin.setDecimals(1)
        self._depth_spin.setValue(15.0)
        self._depth_spin.setSuffix(" m")
        dim_layout.addRow("Profondità:", self._depth_spin)

        layout.addWidget(dim_group)

        # Gruppo Bersagli
        tgt_group = QGroupBox("Bersagli")
        tgt_layout = QFormLayout(tgt_group)
        tgt_layout.setSpacing(8)

        self._total_spin = QSpinBox()
        self._total_spin.setRange(2, 30)
        self._total_spin.setValue(8)
        tgt_layout.addRow("Bersagli totali:", self._total_spin)

        self._steel_spin = QSpinBox()
        self._steel_spin.setRange(0, 10)
        self._steel_spin.setValue(2)
        tgt_layout.addRow("Di cui Steel:", self._steel_spin)

        self._moving_spin = QSpinBox()
        self._moving_spin.setRange(0, 5)
        self._moving_spin.setValue(1)
        tgt_layout.addRow("Mobili:", self._moving_spin)

        self._no_shoot_check = QCheckBox("Includi No-Shoot")
        self._no_shoot_check.setChecked(True)
        tgt_layout.addRow(self._no_shoot_check)

        layout.addWidget(tgt_group)

        # Gruppo Ostacoli
        obs_group = QGroupBox("Ostacoli")
        obs_layout = QFormLayout(obs_group)
        obs_layout.setSpacing(8)

        self._walls_spin = QSpinBox()
        self._walls_spin.setRange(0, 15)
        self._walls_spin.setValue(4)
        obs_layout.addRow("Muri:", self._walls_spin)

        self._barriers_spin = QSpinBox()
        self._barriers_spin.setRange(0, 10)
        self._barriers_spin.setValue(2)
        obs_layout.addRow("Barriere:", self._barriers_spin)

        self._fault_check = QCheckBox("Includi Fault Lines")
        self._fault_check.setChecked(True)
        obs_layout.addRow(self._fault_check)

        layout.addWidget(obs_group)

        # Gruppo Difficoltà
        diff_group = QGroupBox("Parametri")
        diff_layout = QFormLayout(diff_group)

        self._diff_combo = QComboBox()
        self._diff_combo.addItems(["Facile", "Medio", "Difficile"])
        self._diff_combo.setCurrentIndex(1)
        diff_layout.addRow("Difficoltà:", self._diff_combo)

        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 999999)
        self._seed_spin.setSpecialValueText("Casuale")
        self._seed_spin.setValue(0)
        diff_layout.addRow("Seed:", self._seed_spin)

        layout.addWidget(diff_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # Indeterminato
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Bottoni
        btn_row = QHBoxLayout()
        self._btn_generate = QPushButton("▶ Genera Stage")
        self._btn_generate.setProperty("class", "primary")
        self._btn_generate.clicked.connect(self._on_generate)
        btn_row.addWidget(self._btn_generate)

        self._btn_stop = QPushButton("⏹ Ferma")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stopRequested.emit)
        btn_row.addWidget(self._btn_stop)

        layout.addLayout(btn_row)

        # Spacer
        layout.addStretch()

    def _on_generate(self):
        config = self._build_config()
        self._btn_generate.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setVisible(True)
        self.generateRequested.emit(config)

    def _build_config(self) -> GeneratorConfig:
        diff_map = {0: "easy", 1: "medium", 2: "hard"}
        seed = self._seed_spin.value() if self._seed_spin.value() > 0 else None
        return GeneratorConfig(
            stage_width=self._width_spin.value(),
            stage_depth=self._depth_spin.value(),
            num_targets=self._total_spin.value(),
            num_steel=self._steel_spin.value(),
            num_moving=self._moving_spin.value(),
            num_walls=self._walls_spin.value(),
            num_barriers=self._barriers_spin.value(),
            include_fault_lines=self._fault_check.isChecked(),
            include_no_shoots=self._no_shoot_check.isChecked(),
            difficulty=diff_map[self._diff_combo.currentIndex()],
            seed=seed,
        )

    @Slot()
    def on_generation_finished(self):
        self._btn_generate.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setVisible(False)

    @Slot(str)
    def on_generation_error(self, message: str):
        self._btn_generate.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setVisible(False)
