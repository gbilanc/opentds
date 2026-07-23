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
        # Layout principale del widget (solo per contenere la scroll area)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        # Contenitore interno
        content = QWidget()
        layout = QVBoxLayout(content)
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
        self._total_spin.setToolTip("Bersagli cartacei (PAPER_TARGET)")
        tgt_layout.addRow("Paper targets:", self._total_spin)

        self._popper_spin = QSpinBox()
        self._popper_spin.setRange(0, 10)
        self._popper_spin.setValue(1)
        self._popper_spin.setToolTip("Popper calibrati (POPPER, App. C1-C2)")
        tgt_layout.addRow("Popper:", self._popper_spin)

        self._plate_spin = QSpinBox()
        self._plate_spin.setRange(0, 10)
        self._plate_spin.setValue(1)
        self._plate_spin.setToolTip("Piatti metallici (METAL_PLATE, App. C3)")
        tgt_layout.addRow("Metal plates:", self._plate_spin)

        self._mini_spin = QSpinBox()
        self._mini_spin.setRange(0, 5)
        self._mini_spin.setValue(0)
        self._mini_spin.setToolTip("Mini target cartacei (MINI_TARGET, App. B3)")
        tgt_layout.addRow("Mini target:", self._mini_spin)

        self._moving_spin = QSpinBox()
        self._moving_spin.setRange(0, 5)
        self._moving_spin.setValue(1)
        tgt_layout.addRow("Mobili:", self._moving_spin)

        self._no_shoot_check = QCheckBox("Includi No-Shoot")
        self._no_shoot_check.setChecked(True)
        tgt_layout.addRow(self._no_shoot_check)

        self._activator_check = QCheckBox("Attivatori (popper→bersagli)")
        self._activator_check.setChecked(True)
        self._activator_check.setToolTip("Collega popper/plate a bersagli che attivano")
        tgt_layout.addRow(self._activator_check)

        layout.addWidget(tgt_group)

        # Gruppo Ostacoli
        obs_group = QGroupBox("Ostacoli")
        obs_layout = QFormLayout(obs_group)
        obs_layout.setSpacing(8)

        self._walls_spin = QSpinBox()
        self._walls_spin.setRange(0, 15)
        self._walls_spin.setValue(1)
        obs_layout.addRow("Muri:", self._walls_spin)

        self._barriers_spin = QSpinBox()
        self._barriers_spin.setRange(0, 10)
        self._barriers_spin.setValue(4)
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

        # Forma area di tiro (lettera)
        self._shape_combo = QComboBox()
        self._shape_combo.addItems(
            ["Casuale", "L", "T", "U", "C", "H", "F", "O", "Z", "S",
             "X", "Y", "M", "N", "E"])
        self._shape_combo.setCurrentIndex(0)
        diff_layout.addRow("Forma area:", self._shape_combo)

        layout.addWidget(diff_group)

        # Gruppo IPSC
        ipsc_group = QGroupBox("Classificazione IPSC")
        ipsc_layout = QFormLayout(ipsc_group)
        ipsc_layout.setSpacing(8)

        self._course_combo = QComboBox()
        self._course_combo.addItems(["Non specificato", "Short Course",
                                      "Medium Course", "Long Course"])
        self._course_combo.setCurrentIndex(0)
        ipsc_layout.addRow("Tipo corso:", self._course_combo)

        self._div_combo = QComboBox()
        self._div_combo.addItems(["Non specificata", "Open", "Standard",
                                   "Classic", "Production",
                                   "Production Optics", "Revolver"])
        self._div_combo.setCurrentIndex(0)
        ipsc_layout.addRow("Divisione:", self._div_combo)

        layout.addWidget(ipsc_group)

        # Gruppo Opzioni avanzate
        adv_group = QGroupBox("Opzioni Avanzate")
        adv_layout = QFormLayout(adv_group)
        adv_layout.setSpacing(8)

        self._discipline_combo = QComboBox()
        self._discipline_combo.addItems(["IPSC Pistola", "Mini Rifle", "Shotgun"])
        self._discipline_combo.setCurrentIndex(0)
        adv_layout.addRow("Disciplina:", self._discipline_combo)

        self._delim_combo = QComboBox()
        self._delim_combo.addItems(["Fault Lines", "Barriere", "Muri", "Misto"])
        self._delim_combo.setCurrentIndex(0)
        self._delim_combo.setToolTip("Tipo di delimitazione area di tiro")
        adv_layout.addRow("Delimitazione:", self._delim_combo)

        self._auto_dist_check = QCheckBox("Distribuzione automatica")
        self._auto_dist_check.setChecked(True)
        self._auto_dist_check.setToolTip("Calcola bersagli in base al tipo corso (Short/Medium/Long)")
        adv_layout.addRow(self._auto_dist_check)

        layout.addWidget(adv_group)

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

        # Monta scroll area
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    def _on_generate(self):
        config = self._build_config()
        self._btn_generate.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setVisible(True)
        self.generateRequested.emit(config)

    def _build_config(self) -> GeneratorConfig:
        diff_map = {0: "easy", 1: "medium", 2: "hard"}
        shape_map = {"Casuale": "random", "L": "L", "T": "T", "U": "U",
                     "C": "C", "H": "H", "F": "F", "O": "O",
                     "Z": "Z", "S": "S", "X": "X", "Y": "Y",
                     "M": "M", "N": "N", "E": "E"}
        course_map = {"Non specificato": "", "Short Course": "short",
                       "Medium Course": "medium", "Long Course": "long"}
        disc_map = {"IPSC Pistola": "ipsc_pistol", "Mini Rifle": "mini_rifle",
                     "Shotgun": "shotgun"}
        delim_map = {"Fault Lines": "fault_lines", "Barriere": "barriers",
                      "Muri": "walls", "Misto": "mixed"}
        seed = self._seed_spin.value() if self._seed_spin.value() > 0 else None
        return GeneratorConfig(
            stage_width=self._width_spin.value(),
            stage_depth=self._depth_spin.value(),
            num_targets=self._total_spin.value(),
            num_steel=0,
            num_poppers=self._popper_spin.value(),
            num_plates=self._plate_spin.value(),
            num_mini=self._mini_spin.value(),
            num_moving=self._moving_spin.value(),
            num_walls=self._walls_spin.value(),
            num_barriers=self._barriers_spin.value(),
            include_fault_lines=self._fault_check.isChecked(),
            include_no_shoots=self._no_shoot_check.isChecked(),
            include_activators=self._activator_check.isChecked(),
            difficulty=diff_map[self._diff_combo.currentIndex()],
            seed=seed,
            letter_shape=shape_map[self._shape_combo.currentText()],
            course_type=course_map[self._course_combo.currentText()],
            discipline=disc_map[self._discipline_combo.currentText()],
            delimitation=delim_map[self._delim_combo.currentText()],
            auto_distribution=self._auto_dist_check.isChecked(),
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
