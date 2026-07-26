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
    QSlider, QSizePolicy,
)

from core.generator import GeneratorConfig, Phase1Config


class StageWizard(QWidget):
    """Wizard a 2 pagine per la generazione dello stage."""

    # Segnali
    phase1Requested = Signal(Phase1Config)
    stopRequested = Signal()
    placeModeToggled = Signal(bool)  # True = attivo, False = disattivo
    placeObstacleModeToggled = Signal(bool, bool)  # active, is_wall

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

        # Pagina 2: Posizioni e barriere
        self._page2 = self._build_page2()
        self._stack.addWidget(self._page2)

        # Pagina 3: Aggiunta bersagli
        self._page3 = self._build_page3()
        self._stack.addWidget(self._page3)

        # Barra di navigazione
        nav = QHBoxLayout()
        nav.setContentsMargins(12, 4, 12, 8)

        self._btn_back = QPushButton("← Indietro")
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._go_back)
        nav.addWidget(self._btn_back)

        nav.addStretch()

        self._step_label = QLabel("Passo 1 di 3: Area di tiro")
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

        title = QLabel("🎯 Fase 2 — Posizioni di Tiro e Barriere")
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

        # ── Ostacoli posizionabili dall'utente ──
        obs_place_group = QGroupBox("Posiziona Ostacoli (opzionale)")
        obs_place_layout = QVBoxLayout(obs_place_group)
        obs_place_layout.setSpacing(8)

        obs_place_help = QLabel(
            "🖱️ Attiva la modalità e clicca sulla mappa per posizionare\n"
            "muri e barriere. Utile per definire ostacoli specifici;\n"
            "quelli non posizionati verranno generati automaticamente."
        )
        obs_place_help.setWordWrap(True)
        obs_place_help.setStyleSheet("font-size: 11px; color: #64748b; padding: 4px;")
        obs_place_layout.addWidget(obs_place_help)

        # Liste ostacoli
        list_row = QHBoxLayout()

        # Lista muri
        wall_layout = QVBoxLayout()
        wall_layout.addWidget(QLabel("Muri:"))
        self._walls_list = QListWidget()
        self._walls_list.setAlternatingRowColors(True)
        self._walls_list.setMaximumHeight(90)
        wall_layout.addWidget(self._walls_list)

        wall_btn_row = QHBoxLayout()
        self._btn_place_wall = QPushButton("🧱 Muro")
        self._btn_place_wall.setCheckable(True)
        self._btn_place_wall.setToolTip("Clicca sulla mappa per posizionare un muro")
        self._btn_place_wall.clicked.connect(lambda: self._toggle_obstacle_mode(True))
        wall_btn_row.addWidget(self._btn_place_wall)

        self._btn_clear_walls = QPushButton("🗑️")
        self._btn_clear_walls.setToolTip("Cancella tutti i muri posizionati")
        self._btn_clear_walls.setFixedWidth(36)
        self._btn_clear_walls.clicked.connect(lambda: self._clear_obstacles(True))
        wall_btn_row.addWidget(self._btn_clear_walls)
        wall_layout.addLayout(wall_btn_row)

        list_row.addLayout(wall_layout)

        # Lista barriere
        barrier_layout = QVBoxLayout()
        barrier_layout.addWidget(QLabel("Barriere:"))
        self._barriers_list = QListWidget()
        self._barriers_list.setAlternatingRowColors(True)
        self._barriers_list.setMaximumHeight(90)
        barrier_layout.addWidget(self._barriers_list)

        barrier_btn_row = QHBoxLayout()
        self._btn_place_barrier = QPushButton("🛡️ Barriera")
        self._btn_place_barrier.setCheckable(True)
        self._btn_place_barrier.setToolTip("Clicca sulla mappa per posizionare una barriera")
        self._btn_place_barrier.clicked.connect(lambda: self._toggle_obstacle_mode(False))
        barrier_btn_row.addWidget(self._btn_place_barrier)

        self._btn_clear_barriers = QPushButton("🗑️")
        self._btn_clear_barriers.setToolTip("Cancella tutte le barriere posizionate")
        self._btn_clear_barriers.setFixedWidth(36)
        self._btn_clear_barriers.clicked.connect(lambda: self._clear_obstacles(False))
        barrier_btn_row.addWidget(self._btn_clear_barriers)
        barrier_layout.addLayout(barrier_btn_row)

        list_row.addLayout(barrier_layout)
        obs_place_layout.addLayout(list_row)

        # Opzioni ostacolo (larghezza, rotazione)
        obs_opts_row = QHBoxLayout()
        obs_opts_row.addWidget(QLabel("Lunghezza:"))
        self._obs_width = QDoubleSpinBox()
        self._obs_width.setRange(0.5, 20.0)
        self._obs_width.setDecimals(1)
        self._obs_width.setValue(3.0)
        self._obs_width.setSuffix(" m")
        self._obs_width.setFixedWidth(80)
        self._obs_width.valueChanged.connect(self._on_obstacle_width_changed)
        obs_opts_row.addWidget(self._obs_width)

        obs_opts_row.addSpacing(12)
        obs_opts_row.addWidget(QLabel("Rotazione:"))
        self._obs_rotation = QSpinBox()
        self._obs_rotation.setRange(0, 359)
        self._obs_rotation.setValue(0)
        self._obs_rotation.setSuffix("°")
        self._obs_rotation.setFixedWidth(70)
        obs_opts_row.addWidget(self._obs_rotation)

        obs_opts_row.addStretch()
        obs_place_layout.addLayout(obs_opts_row)

        layout.addWidget(obs_place_group)

        layout.addWidget(obs_place_group)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _parse_list_item(self, text: str) -> tuple[float, float, bool] | None:
        """Estrae (x, y, is_start) da una riga della lista.

        Formato: "#N (x, y)" dove N=1 è la posizione di partenza (Start).
        """
        try:
            rest = text.split(" ", 1)[1] if " " in text else ""
            rest = rest.strip("()")
            parts = rest.split(",")
            if len(parts) >= 2:
                x = float(parts[0].strip())
                y = float(parts[1].strip())
                # Numero 1 = Start, tutti gli altri = intermedie
                is_start = text.startswith("#1 ")
                return (x, y, is_start)
        except (ValueError, IndexError):
            pass
        return None

    def _parse_obstacle_item(self, text: str) -> tuple[float, float, float, float] | None:
        """Estrae (x, y, width, rotation) da una riga della lista ostacoli.

        Formato: "#1M (x, y) w=3.0 rot=0°" o "#2B (x, y) w=2.0 rot=90°"
        """
        try:
            # Rimuovi il prefisso "#NM" o "#NB"
            rest = text
            if " " in text:
                rest = text.split(" ", 1)[1] if len(text.split(" ", 1)) > 1 else ""
            if "(" in rest and ")" in rest:
                coords = rest[rest.find("(") + 1:rest.find(")")]
                parts = coords.split(",")
                if len(parts) >= 2:
                    x = float(parts[0].strip())
                    y = float(parts[1].strip())
                    w = 3.0
                    rot = 0.0
                    if "w=" in rest:
                        w_str = rest.split("w=")[1].split()[0]
                        w = float(w_str)
                    if "rot=" in rest:
                        rot_str = rest.split("rot=")[1].split()[0].replace("°", "")
                        rot = float(rot_str)
                    return (x, y, w, rot)
        except (ValueError, IndexError):
            pass
        return None

    # ── Pagina 3: Aggiunta bersagli ───────────────────────────────────

    def _build_page3(self) -> QWidget:
        """Pagina 3: guida all'aggiunta manuale dei bersagli tramite toolbar."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        title = QLabel("🎯 Fase 3 — Aggiunta Bersagli")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        help_text = QLabel(
            "Utilizza i pulsanti nella barra strumenti in alto\n"
            "per aggiungere bersagli allo stage:\n\n"
            "🧱 + Muro     — Aggiunge un muro\n"
            "📄 + Paper    — Bersaglio cartaceo IPSC\n"
            "⚙️  + Steel   — Bersaglio metallico generico\n"
            "➖ + Fault    — Linea di fallo\n"
            "🚫 + NS       — Bersaglio No-Shoot\n"
            "🛡️ + Barriera — Barriera\n"
            "🚪 + Porta    — Porta\n"
            "🔄 + Swinger  — Bersaglio oscillante\n"
            "⬇️  + Drop    — Bersaglio a caduta\n"
            "➡️  + Mover   — Bersaglio su rotaia\n\n"
            "Dopo aver aggiunto i bersagli, puoi:\n"
            "  • Selezionarli e spostarli con il mouse\n"
            "  • Modificare le proprietà nel pannello laterale\n"
            "  • Usare Ctrl+Z per annullare"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-size: 12px; color: #334155; line-height: 1.6;")
        layout.addWidget(help_text)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ── Navigazione (3 passi) ────────────────────────────────────────

    def _go_forward(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            self._stack.setCurrentIndex(1)
            self._btn_back.setEnabled(True)
            self._btn_next.setEnabled(True)
            self._step_label.setText("Passo 2 di 3: Posizioni di tiro e barriere")
        elif idx == 1:
            self._stack.setCurrentIndex(2)
            self._btn_next.setEnabled(False)
            self._step_label.setText("Passo 3 di 3: Aggiunta bersagli")

    def _go_back(self):
        idx = self._stack.currentIndex()
        if idx == 1:
            self._stack.setCurrentIndex(0)
            self._btn_back.setEnabled(False)
            self._btn_next.setEnabled(self._phase1_done)
            self._step_label.setText("Passo 1 di 3: Area di tiro")
        elif idx == 2:
            self._stack.setCurrentIndex(1)
            self._btn_back.setEnabled(True)
            self._btn_next.setEnabled(True)
            self._step_label.setText("Passo 2 di 3: Posizioni di tiro e barriere")

    # ── Helper: lista con bottone elimina ────────────────────────────

    @staticmethod
    def _make_list_item_widget(text: str, on_delete: callable) -> QWidget:
        """Crea un widget per riga della lista con etichetta e bottone elimina."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(4)

        label = QLabel(text)
        label.setStyleSheet("font-size: 10px; color: #0f172a;")
        layout.addWidget(label, 1)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet("""
            QPushButton {
                font-size: 10px; font-weight: bold; color: #dc2626;
                background: transparent; border: none; padding: 0;
            }
            QPushButton:hover { color: #b91c1c; }
        """)
        btn_del.clicked.connect(lambda: on_delete(widget))
        layout.addWidget(btn_del)

        return widget

    def _find_item_text(self, item) -> str:
        """Recupera il testo dalla riga della lista."""
        if item is None:
            return ""
        widget = None
        for lst in [self._pos_list, self._walls_list, self._barriers_list]:
            w = lst.itemWidget(item)
            if w is not None:
                widget = w
                break
        if widget is None:
            return ""
        label = widget.findChild(QLabel)
        return label.text() if label else ""

    def _add_item_with_delete(self, lst: QListWidget, text: str,
                               on_delete_clicked: callable) -> None:
        """Aggiunge una riga con bottone elimina a una lista."""
        item = QListWidgetItem()
        widget = self._make_list_item_widget(text, lambda w: on_delete_clicked(item))
        item.setSizeHint(widget.sizeHint())
        lst.addItem(item)
        lst.setItemWidget(item, widget)

    # ── Gestione posizioni di tiro ────────────────────────────────────

    def add_shooting_position(self, x: float, y: float, is_start: bool = False,
                               on_delete_clicked: callable = None,
                               on_renumbered: callable = None):
        """Aggiunge una posizione di tiro numerata alla lista con bottone elimina.

        Args:
            on_delete_clicked: Callable(item) prima di rimuovere dalla lista.
            on_renumbered: Callable(list[str]) dopo la rinumerazione, con le
                          nuove etichette "#1", "#2", ... per aggiornare i marker.
        """
        numero = self._pos_list.count() + 1
        text = f"#{numero} ({x:.2f}, {y:.2f})"

        def _on_del(item):
            if on_delete_clicked:
                on_delete_clicked(item)
            row = self._pos_list.row(item)
            self._pos_list.takeItem(row)
            # Rinumerazione progressiva dopo eliminazione
            labels = []
            for j in range(self._pos_list.count()):
                it = self._pos_list.item(j)
                t = self._find_item_text(it)
                if t and t.startswith("#"):
                    new_num = f"#{j + 1}"
                    new_text = new_num + t[t.index(" "):]
                    labels.append(new_num)
                    w = self._pos_list.itemWidget(it)
                    if w:
                        lbl = w.findChild(QLabel)
                        if lbl:
                            lbl.setText(new_text)
            if on_renumbered:
                on_renumbered(labels)

        self._add_item_with_delete(self._pos_list, text, _on_del)

    def _toggle_place_mode(self, active: bool):
        self.placeModeToggled.emit(active)
        if active:
            self._btn_place_wall.setChecked(False)
            self._btn_place_barrier.setChecked(False)
            self.placeObstacleModeToggled.emit(False, True)
            self._btn_place_pos.setText("⏹️ Ferma")
        else:
            self._btn_place_pos.setText("✏️ Posiziona")

    def _clear_positions(self):
        self._pos_list.clear()
        self.placeModeToggled.emit(False)

    def get_shooting_positions(self) -> list[tuple[float, float, bool]]:
        """Ritorna tutte le posizioni di tiro configurate."""
        positions: list[tuple[float, float, bool]] = []
        for i in range(self._pos_list.count()):
            item = self._pos_list.item(i)
            text = self._find_item_text(item)
            if not text:
                continue
            parsed = self._parse_list_item(text)
            if parsed:
                positions.append(parsed)
        return positions

    # ── Gestione ostacoli posizionati ────────────────────────────────

    def add_obstacle(self, x: float, y: float, width: float, rotation: float,
                      is_wall: bool = True,
                      on_delete_clicked: callable = None,
                      on_renumbered: callable = None):
        """Aggiunge un ostacolo numerato alla lista con bottone elimina.

        Args:
            on_delete_clicked: Callable(item) prima di rimuovere dalla lista.
            on_renumbered: Callable(list[str]) dopo la rinumerazione.
        """
        lst = self._walls_list if is_wall else self._barriers_list
        prefix = "M" if is_wall else "B"
        numero = lst.count() + 1
        text = f"#{numero}{prefix} ({x:.2f}, {y:.2f}) w={width:.1f} rot={rotation:.0f}°"

        def _on_del(item):
            if on_delete_clicked:
                on_delete_clicked(item)
            row = lst.row(item)
            lst.takeItem(row)
            # Rinumerazione progressiva
            labels = []
            for j in range(lst.count()):
                it = lst.item(j)
                t = self._find_item_text(it)
                if t and (t.startswith("#") and len(t) > 1 and t[1].isdigit()):
                    new_prefix = "M" if t[2:].startswith("M") else "B"
                    new_num = f"#{j + 1}{new_prefix}"
                    labels.append(new_num)
                    resto = t[t.index("("):] if "(" in t else ""
                    new_text = f"{new_num} {resto}"
                    w = lst.itemWidget(it)
                    if w:
                        lbl = w.findChild(QLabel)
                        if lbl:
                            lbl.setText(new_text)
            if on_renumbered:
                on_renumbered(labels)

        self._add_item_with_delete(lst, text, _on_del)

    def _toggle_obstacle_mode(self, is_wall: bool):
        if is_wall:
            active = self._btn_place_wall.isChecked()
            self._btn_place_barrier.setChecked(False)
        else:
            active = self._btn_place_barrier.isChecked()
            self._btn_place_wall.setChecked(False)

        if active:
            self._btn_place_pos.setChecked(False)
            self._btn_place_pos.setText("✏️ Posiziona")
            self.placeModeToggled.emit(False)

        self.placeObstacleModeToggled.emit(active, is_wall)
        if active:
            btn = self._btn_place_wall if is_wall else self._btn_place_barrier
            btn.setText("⏹️ Ferma")
        else:
            self._btn_place_wall.setText("🧱 Muro")
            self._btn_place_barrier.setText("🛡️ Barriera")

    def _clear_obstacles(self, is_wall: bool):
        lst = self._walls_list if is_wall else self._barriers_list
        lst.clear()

    def _on_obstacle_width_changed(self, width: float):
        pass

    def get_placed_walls(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self._walls_list.count()):
            item = self._walls_list.item(i)
            text = self._find_item_text(item)
            if not text:
                continue
            parsed = self._parse_obstacle_item(text)
            if parsed:
                result.append({"x": parsed[0], "y": parsed[1],
                               "width": parsed[2], "rotation": parsed[3]})
        return result

    def get_placed_barriers(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self._barriers_list.count()):
            item = self._barriers_list.item(i)
            text = self._find_item_text(item)
            if not text:
                continue
            parsed = self._parse_obstacle_item(text)
            if parsed:
                result.append({"x": parsed[0], "y": parsed[1],
                               "width": parsed[2], "rotation": parsed[3]})
        return result

    def _toggle_obstacle_mode(self, is_wall: bool):
        """Attiva/disattiva la modalità posizionamento ostacoli."""
        if is_wall:
            active = self._btn_place_wall.isChecked()
            self._btn_place_barrier.setChecked(False)
        else:
            active = self._btn_place_barrier.isChecked()
            self._btn_place_wall.setChecked(False)

        if active:
            self._btn_place_pos.setChecked(False)
            self._btn_place_pos.setText("✏️ Posiziona")
            self.placeModeToggled.emit(False)

        self.placeObstacleModeToggled.emit(active, is_wall)
        if active:
            btn = self._btn_place_wall if is_wall else self._btn_place_barrier
            btn.setText("⏹️ Ferma")
        else:
            self._btn_place_wall.setText("🧱 Muro")
            self._btn_place_barrier.setText("🛡️ Barriera")

    def _clear_obstacles(self, is_wall: bool):
        lst = self._walls_list if is_wall else self._barriers_list
        lst.clear()

    def _on_obstacle_width_changed(self, width: float):
        pass

    def get_placed_walls(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self._walls_list.count()):
            item = self._walls_list.item(i)
            if item is None:
                continue
            widget = self._walls_list.itemWidget(item)
            text = self._find_item_text(widget) if widget else ""
            if not text:
                continue
            parsed = self._parse_obstacle_item(text)
            if parsed:
                result.append({"x": parsed[0], "y": parsed[1],
                               "width": parsed[2], "rotation": parsed[3]})
        return result

    def get_placed_barriers(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self._barriers_list.count()):
            item = self._barriers_list.item(i)
            if item is None:
                continue
            widget = self._barriers_list.itemWidget(item)
            text = self._find_item_text(widget) if widget else ""
            if not text:
                continue
            parsed = self._parse_obstacle_item(text)
            if parsed:
                result.append({"x": parsed[0], "y": parsed[1],
                               "width": parsed[2], "rotation": parsed[3]})
        return result

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
        self._step_label.setText("Passo 1 di 3: Area di tiro")
        self._btn_gen_area.setEnabled(True)
        self._btn_gen_area.setText("▶ Genera Area di Tiro")
        self._p1_status.setText("")
        self._pos_list.clear()
        self._walls_list.clear()
        self._barriers_list.clear()


# ── Compatibilità: alias GeneratorPanel per retrocompatibilità ──────────

class GeneratorPanel(StageWizard):
    """Alias per retrocompatibilità."""
    generateRequested = Signal(GeneratorConfig)
    stopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase1Requested.connect(self._on_phase1_legacy)

    def _on_phase1_legacy(self, phase1: Phase1Config):
        from core.generator import GeneratorConfig as GC
        cfg = GC(
            stage_width=phase1.stage_width,
            stage_depth=phase1.stage_depth,
            letter_shape=phase1.letter_shape,
            delimitation=phase1.delimitation,
        )
        self.generateRequested.emit(cfg)

    def on_generation_finished(self):
        self.on_phase1_complete()

    def on_generation_error(self, message: str):
        self.on_phase1_error(message)
