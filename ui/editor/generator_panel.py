# ui/editor/generator_panel.py
"""Wizard a 2 fasi per la generazione procedurale degli stage IPSC.

Fase 1: dimensioni + forma + rotazione area di tiro
Fase 2: posizioni di tiro + bersagli + auto-place
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QProgressBar, QGroupBox,
    QFrame, QScrollArea, QStackedWidget, QListWidget,
    QListWidgetItem, QAbstractItemView, QMessageBox,
    QSlider,
)

from core.generator import GeneratorConfig, Phase1Config, Phase2Config


class StageWizard(QWidget):
    """Wizard a 2 pagine per la generazione dello stage."""

    # Segnali
    phase1Requested = Signal(Phase1Config)
    phase2Requested = Signal(Phase2Config)
    stopRequested = Signal()
    placeModeToggled = Signal(bool)  # True = attivo, False = disattivo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase1_done = False
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Stack delle pagine
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Pagina 1: Area di Tiro
        self._page1 = self._build_page1()
        self._stack.addWidget(self._page1)

        # Pagina 2: Bersagli e posizioni
        self._page2 = self._build_page2()
        self._stack.addWidget(self._page2)

        # Barra di navigazione
        nav = QHBoxLayout()
        nav.setContentsMargins(12, 4, 12, 8)

        self._btn_back = QPushButton("← Indietro")
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._go_back)
        nav.addWidget(self._btn_back)

        nav.addStretch()

        self._step_label = QLabel("Passo 1 di 2: Area di tiro")
        self._step_label.setStyleSheet("font-size: 12px; color: #64748b; font-weight: 600;")
        nav.addWidget(self._step_label)

        nav.addStretch()

        self._btn_next = QPushButton("Avanti →")
        self._btn_next.setEnabled(False)
        self._btn_next.clicked.connect(self._go_forward)
        nav.addWidget(self._btn_next)

        root.addLayout(nav)

        # Progress bar (Fase 2)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

    # ── Pagina 1: Area di Tiro ────────────────────────────────────────

    def _build_page1(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; }
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        title = QLabel("🎯 Fase 1 — Area di Tiro")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        subtitle = QLabel("Definisci dimensione, forma e rotazione dell'area di tiro")
        subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(subtitle)

        # ── Dimensioni ──
        dim_group = QGroupBox("Dimensioni Stage")
        dim_form = QFormLayout(dim_group)
        dim_form.setSpacing(8)

        self._p1_width = QDoubleSpinBox()
        self._p1_width.setRange(5, 50)
        self._p1_width.setDecimals(1)
        self._p1_width.setValue(20.0)
        self._p1_width.setSuffix(" m")
        dim_form.addRow("Larghezza:", self._p1_width)

        self._p1_depth = QDoubleSpinBox()
        self._p1_depth.setRange(5, 50)
        self._p1_depth.setDecimals(1)
        self._p1_depth.setValue(15.0)
        self._p1_depth.setSuffix(" m")
        dim_form.addRow("Profondità:", self._p1_depth)

        layout.addWidget(dim_group)

        # ── Forma e rotazione ──
        shape_group = QGroupBox("Forma Area di Tiro")
        shape_form = QFormLayout(shape_group)
        shape_form.setSpacing(8)

        self._p1_shape = QComboBox()
        self._p1_shape.addItems(
            ["Casuale", "Quadrato", "Rettangolo", "T", "U", "W", "X", "Y", "Z"]
        )
        self._p1_shape.setCurrentIndex(0)
        shape_form.addRow("Forma:", self._p1_shape)

        rot_row = QHBoxLayout()
        self._p1_rotation = QSpinBox()
        self._p1_rotation.setRange(0, 359)
        self._p1_rotation.setValue(0)
        self._p1_rotation.setSuffix("°")
        self._p1_rotation.setFixedWidth(80)

        self._p1_rot_slider = QSlider(Qt.Orientation.Horizontal)
        self._p1_rot_slider.setRange(0, 359)
        self._p1_rot_slider.setValue(0)
        self._p1_rot_slider.valueChanged.connect(self._p1_rotation.setValue)
        self._p1_rotation.valueChanged.connect(self._p1_rot_slider.setValue)
        rot_row.addWidget(self._p1_rotation)
        rot_row.addWidget(self._p1_rot_slider, 1)
        shape_form.addRow("Rotazione:", rot_row)

        self._p1_delim = QComboBox()
        self._p1_delim.addItems(["Fault Lines", "Barriere", "Muri", "Misto"])
        self._p1_delim.setCurrentIndex(0)
        shape_form.addRow("Delimitazione:", self._p1_delim)

        layout.addWidget(shape_group)

        # ── Bottone Genera Area ──
        self._btn_gen_area = QPushButton("▶ Genera Area di Tiro")
        self._btn_gen_area.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #22c55e; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self._btn_gen_area.clicked.connect(self._on_generate_phase1)
        layout.addWidget(self._btn_gen_area)

        # Stato
        self._p1_status = QLabel("")
        self._p1_status.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(self._p1_status)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _on_generate_phase1(self):
        shape_map = {"Casuale": "random", "Quadrato": "Q",
                     "Rettangolo": "O", "T": "T", "U": "U",
                     "W": "W", "X": "X", "Y": "Y", "Z": "Z"}
        delim_map = {"Fault Lines": "fault_lines", "Barriere": "barriers",
                      "Muri": "walls", "Misto": "mixed"}

        config = Phase1Config(
            stage_width=self._p1_width.value(),
            stage_depth=self._p1_depth.value(),
            letter_shape=shape_map[self._p1_shape.currentText()],
            rotation=float(self._p1_rotation.value()),
            delimitation=delim_map[self._p1_delim.currentText()],
        )
        self._btn_gen_area.setEnabled(False)
        self._btn_gen_area.setText("⏳ Generazione in corso...")
        self._p1_status.setText("Generazione area di tiro in corso...")
        self.phase1Requested.emit(config)

    def on_phase1_complete(self, stage_name: str = "Stage"):
        """Chiamato quando la Fase 1 è completata con successo."""
        self._phase1_done = True
        self._btn_gen_area.setEnabled(True)
        self._btn_gen_area.setText("✅ Area Generata — Rigenera")
        self._btn_gen_area.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #f59e0b; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #d97706; }
        """)
        self._p1_status.setText(f"✅ Area di tiro generata ({stage_name})")
        self._btn_next.setEnabled(True)

    def on_phase1_error(self, message: str):
        self._btn_gen_area.setEnabled(True)
        self._btn_gen_area.setText("▶ Genera Area di Tiro")
        self._btn_gen_area.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #22c55e; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        self._p1_status.setText(f"❌ Errore: {message}")
        self._p1_status.setStyleSheet("font-size: 12px; color: #dc2626;")

    # ── Pagina 2: Bersagli e Posizioni ────────────────────────────────

    def _build_page2(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; }
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        title = QLabel("🎯 Fase 2 — Bersagli e Posizioni")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        # ── Shooting positions ──
        pos_group = QGroupBox("Posizioni di Tiro")
        pos_layout = QVBoxLayout(pos_group)
        pos_layout.setSpacing(8)

        pos_help = QLabel(
            "🖱️ Clicca sulla mappa nell'editor per aggiungere posizioni.\n"
            "Il primo click = posizione di partenza (Start).\n"
            "Click successivi = posizioni intermedie.\n"
            "Click destro su un marker per rimuoverlo."
        )
        pos_help.setWordWrap(True)
        pos_help.setStyleSheet("font-size: 11px; color: #64748b; padding: 4px;")
        pos_layout.addWidget(pos_help)

        # Lista posizioni
        self._pos_list = QListWidget()
        self._pos_list.setAlternatingRowColors(True)
        self._pos_list.setMaximumHeight(120)
        pos_layout.addWidget(self._pos_list)

        btn_row = QHBoxLayout()
        self._btn_place_pos = QPushButton("✏️ Posiziona")
        self._btn_place_pos.setCheckable(True)
        self._btn_place_pos.setToolTip("Clicca sulla mappa per aggiungere posizioni")
        self._btn_place_pos.clicked.connect(self._toggle_place_mode)
        btn_row.addWidget(self._btn_place_pos)

        self._btn_clear_pos = QPushButton("🗑️ Cancella tutte")
        self._btn_clear_pos.clicked.connect(self._clear_positions)
        btn_row.addWidget(self._btn_clear_pos)
        pos_layout.addLayout(btn_row)

        layout.addWidget(pos_group)

        # ── Bersagli ──
        tgt_group = QGroupBox("Bersagli")
        tgt_form = QFormLayout(tgt_group)
        tgt_form.setSpacing(8)

        self._p2_paper = QSpinBox()
        self._p2_paper.setRange(2, 30)
        self._p2_paper.setValue(8)
        tgt_form.addRow("Paper targets:", self._p2_paper)

        self._p2_poppers = QSpinBox()
        self._p2_poppers.setRange(0, 10)
        self._p2_poppers.setValue(1)
        tgt_form.addRow("Popper:", self._p2_poppers)

        self._p2_plates = QSpinBox()
        self._p2_plates.setRange(0, 10)
        self._p2_plates.setValue(1)
        tgt_form.addRow("Metal plates:", self._p2_plates)

        self._p2_mini = QSpinBox()
        self._p2_mini.setRange(0, 5)
        self._p2_mini.setValue(0)
        tgt_form.addRow("Mini target:", self._p2_mini)

        self._p2_moving = QSpinBox()
        self._p2_moving.setRange(0, 5)
        self._p2_moving.setValue(1)
        tgt_form.addRow("Mobili:", self._p2_moving)

        self._p2_noshoot = QCheckBox("Includi No-Shoot")
        self._p2_noshoot.setChecked(True)
        tgt_form.addRow(self._p2_noshoot)

        self._p2_activators = QCheckBox("Attivatori (popper→bersagli)")
        self._p2_activators.setChecked(True)
        tgt_form.addRow(self._p2_activators)

        layout.addWidget(tgt_group)

        # ── Ostacoli ──
        obs_group = QGroupBox("Ostacoli")
        obs_form = QFormLayout(obs_group)
        obs_form.setSpacing(8)

        self._p2_walls = QSpinBox()
        self._p2_walls.setRange(0, 15)
        self._p2_walls.setValue(1)
        obs_form.addRow("Muri:", self._p2_walls)

        self._p2_barriers = QSpinBox()
        self._p2_barriers.setRange(0, 10)
        self._p2_barriers.setValue(4)
        obs_form.addRow("Barriere:", self._p2_barriers)

        layout.addWidget(obs_group)

        # ── Difficoltà ──
        diff_group = QGroupBox("Parametri")
        diff_form = QFormLayout(diff_group)
        diff_form.setSpacing(8)

        self._p2_diff = QComboBox()
        self._p2_diff.addItems(["Facile", "Medio", "Difficile"])
        self._p2_diff.setCurrentIndex(1)
        diff_form.addRow("Difficoltà:", self._p2_diff)

        self._p2_course = QComboBox()
        self._p2_course.addItems(
            ["Non specificato", "Short Course", "Medium Course", "Long Course"]
        )
        self._p2_course.setCurrentIndex(0)
        diff_form.addRow("Tipo corso:", self._p2_course)

        layout.addWidget(diff_group)

        # ── Bottone Auto-Place ──
        self._btn_autoplace = QPushButton("🤖 Auto-Place: Posiziona Bersagli e Barriere")
        self._btn_autoplace.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #3b82f6; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self._btn_autoplace.clicked.connect(self._on_generate_phase2)
        layout.addWidget(self._btn_autoplace)

        self._p2_status = QLabel("")
        self._p2_status.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(self._p2_status)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _on_generate_phase2(self):
        diff_map = {0: "easy", 1: "medium", 2: "hard"}
        course_map = {"Non specificato": "", "Short Course": "short",
                       "Medium Course": "medium", "Long Course": "long"}

        # Raccogli shooting positions dalla lista
        positions: list[tuple[float, float, bool]] = []
        for i in range(self._pos_list.count()):
            item = self._pos_list.item(i)
            if item is None:
                continue
            text = item.text()
            try:
                # Formato: "S (x, y)" o "1 (x, y)"
                rest = text.split(" ", 1)[1] if " " in text else ""
                rest = rest.strip("()")
                parts = rest.split(",")
                if len(parts) >= 2:
                    x = float(parts[0].strip())
                    y = float(parts[1].strip())
                    is_start = text.startswith("S")
                    positions.append((x, y, is_start))
            except (ValueError, IndexError):
                continue

        config = Phase2Config(
            shooting_positions=positions,
            num_targets=self._p2_paper.value(),
            num_poppers=self._p2_poppers.value(),
            num_plates=self._p2_plates.value(),
            num_mini=self._p2_mini.value(),
            num_moving=self._p2_moving.value(),
            num_walls=self._p2_walls.value(),
            num_barriers=self._p2_barriers.value(),
            include_no_shoots=self._p2_noshoot.isChecked(),
            include_activators=self._p2_activators.isChecked(),
            difficulty=diff_map[self._p2_diff.currentIndex()],
            course_type=course_map[self._p2_course.currentText()],
        )

        self._btn_autoplace.setEnabled(False)
        self._btn_autoplace.setText("⏳ Posizionamento in corso...")
        self._p2_status.setText("Posizionamento bersagli e barriere in corso...")
        self._progress.setVisible(True)
        self.phase2Requested.emit(config)

    def on_phase2_complete(self):
        self._btn_autoplace.setEnabled(True)
        self._btn_autoplace.setText("✅ Completato — Rigenera")
        self._btn_autoplace.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #22c55e; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        self._p2_status.setText("✅ Stage completo! Bersagli e barriere posizionati.")
        self._progress.setVisible(False)

    def on_phase2_error(self, message: str):
        self._btn_autoplace.setEnabled(True)
        self._btn_autoplace.setText("🤖 Auto-Place: Posiziona Bersagli e Barriere")
        self._btn_autoplace.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #3b82f6; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self._p2_status.setText(f"❌ Errore: {message}")
        self._p2_status.setStyleSheet("font-size: 12px; color: #dc2626;")
        self._progress.setVisible(False)

    # ── Navigazione ───────────────────────────────────────────────────

    def _go_forward(self):
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._btn_back.setEnabled(True)
            self._btn_next.setEnabled(False)
            self._step_label.setText("Passo 2 di 2: Bersagli e posizioni")

    def _go_back(self):
        if self._stack.currentIndex() == 1:
            self._stack.setCurrentIndex(0)
            self._btn_back.setEnabled(False)
            self._btn_next.setEnabled(self._phase1_done)
            self._step_label.setText("Passo 1 di 2: Area di tiro")

    # ── Gestione posizioni di tiro ────────────────────────────────────

    def add_shooting_position(self, x: float, y: float, is_start: bool = False):
        """Aggiunge una posizione di tiro alla lista."""
        label = "S" if is_start else str(self._pos_list.count() + 1)
        text = f"{label} ({x:.2f}, {y:.2f})"
        item = QListWidgetItem(text)
        item.setIcon(self._icon_for_position(is_start))
        if is_start:
            # Inserisci all'inizio
            self._pos_list.insertItem(0, item)
        else:
            self._pos_list.addItem(item)

    def remove_shooting_position(self, index: int):
        """Rimuove una posizione di tiro dalla lista."""
        if 0 <= index < self._pos_list.count():
            self._pos_list.takeItem(index)

    def _toggle_place_mode(self, active: bool):
        self.placeModeToggled.emit(active)
        if active:
            self._btn_place_pos.setText("⏹️ Ferma")
        else:
            self._btn_place_pos.setText("✏️ Posiziona")

    def _clear_positions(self):
        self._pos_list.clear()
        # Resetta anche il contatore nella view
        self.placeModeToggled.emit(False)

    def get_shooting_positions(self) -> list[tuple[float, float, bool]]:
        """Ritorna tutte le posizioni di tiro configurate."""
        positions: list[tuple[float, float, bool]] = []
        for i in range(self._pos_list.count()):
            item = self._pos_list.item(i)
            if item is None:
                continue
            text = item.text()
            try:
                rest = text.split(" ", 1)[1] if " " in text else ""
                rest = rest.strip("()")
                parts = rest.split(",")
                if len(parts) >= 2:
                    x = float(parts[0].strip())
                    y = float(parts[1].strip())
                    is_start = text.startswith("S")
                    positions.append((x, y, is_start))
            except (ValueError, IndexError):
                continue
        return positions

    @staticmethod
    def _icon_for_position(is_start: bool):
        """Crea un'icona testuale per il tipo di posizione."""
        from PySide6.QtGui import QColor, QPixmap, QPainter
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#22c55e") if is_start else QColor("#3b82f6")
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        from PySide6.QtGui import QIcon
        return QIcon(pix)

    def reset(self):
        """Resetta il wizard allo stato iniziale."""
        self._stack.setCurrentIndex(0)
        self._phase1_done = False
        self._btn_back.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._step_label.setText("Passo 1 di 2: Area di tiro")
        self._btn_gen_area.setEnabled(True)
        self._btn_gen_area.setText("▶ Genera Area di Tiro")
        self._p1_status.setText("")
        self._p2_status.setText("")
        self._progress.setVisible(False)
        self._pos_list.clear()


# ── Compatibilità: alias GeneratorPanel per retrocompatibilità ──────────

class GeneratorPanel(StageWizard):
    """Alias per retrocompatibilità. Nuovo codice usi StageWizard."""
    generateRequested = Signal(GeneratorConfig)
    stopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Collega i nuovi segnali a quelli vecchi per compatibilità
        self.phase1Requested.connect(self._on_phase1_legacy)
        self.phase2Requested.connect(self._on_phase2_legacy)

    def _on_phase1_legacy(self, phase1: Phase1Config):
        # Converte in GeneratorConfig ed emette segnale legacy
        from core.generator import GeneratorConfig as GC
        cfg = GC(
            stage_width=phase1.stage_width,
            stage_depth=phase1.stage_depth,
            letter_shape=phase1.letter_shape,
            delimitation=phase1.delimitation,
        )
        self.generateRequested.emit(cfg)

    def _on_phase2_legacy(self, phase2: Phase2Config):
        pass

    def on_generation_finished(self):
        self.on_phase1_complete()

    def on_generation_error(self, message: str):
        self.on_phase1_error(message)
