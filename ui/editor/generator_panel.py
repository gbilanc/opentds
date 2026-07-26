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
from core.models import ItemType


class StageWizard(QWidget):
    """Wizard a 2 pagine per la generazione dello stage."""

    # Segnali
    phase1Requested = Signal(Phase1Config)
    stopRequested = Signal()
    placeModeToggled = Signal(bool)  # True = attivo, False = disattivo
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase1_done = False
        self.scene_ref = None  # impostato da main_window per Fase 3
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

        title = QLabel("🎯 Fase 2 — Posizioni di Tiro")
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

    # ── Pagina 3: Aggiunta bersagli ───────────────────────────────────

    def _build_page3(self) -> QWidget:
        """Pagina 3: pulsanti per aggiungere bersagli/ostacoli allo stage."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("🎯 Fase 3 — Aggiunta Bersagli e Ostacoli")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        def _add_btn(text, tip, callback):
            """Crea un pulsante con stile."""
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setStyleSheet("""
                QPushButton {
                    padding: 8px 14px; font-size: 12px; font-weight: 500;
                    border: 1px solid #e2e8f0; border-radius: 6px;
                    background-color: #ffffff; color: #0f172a;
                    text-align: left;
                }
                QPushButton:hover { background-color: #f1f5f9; border-color: #94a3b8; }
            """)
            b.clicked.connect(callback)
            return b

        # Pulsanti organizzati per categorie
        layout.addWidget(QLabel("Bersagli cartacei:"))
        btn_row1 = QHBoxLayout()
        btn_row1.addWidget(_add_btn("📄 Paper", "Bersaglio cartaceo IPSC",
            lambda: self._add_via_scene(lambda s: s.add_target(5, 5, 0.45, 0.45, ItemType.PAPER_TARGET))))
        btn_row1.addWidget(_add_btn("📄 Mini", "Mini target (App. B3)",
            lambda: self._add_via_scene(lambda s: s.add_mini_target(6, 5))))
        btn_row1.addWidget(_add_btn("📄 Micro", "Micro target",
            lambda: self._add_via_scene(lambda s: s.add_micro_target(7, 5))))
        btn_row1.addStretch()
        layout.addLayout(btn_row1)

        layout.addWidget(QLabel("Bersagli metallici:"))
        btn_row2 = QHBoxLayout()
        btn_row2.addWidget(_add_btn("⚙️ Steel", "Bersaglio metallico generico",
            lambda: self._add_via_scene(lambda s: s.add_target(5, 6, 0.30, 0.30, ItemType.STEEL_TARGET))))
        btn_row2.addWidget(_add_btn("🥇 Popper", "Popper calibrato (App. C1)",
            lambda: self._add_via_scene(lambda s: s.add_popper(6, 6))))
        btn_row2.addWidget(_add_btn("⭕ Plate", "Piatto metallico (App. C3)",
            lambda: self._add_via_scene(lambda s: s.add_metal_plate(7, 6))))
        btn_row2.addStretch()
        layout.addLayout(btn_row2)

        layout.addWidget(QLabel("Bersagli mobili:"))
        btn_row3 = QHBoxLayout()
        btn_row3.addWidget(_add_btn("🔄 Swinger", "Bersaglio oscillante",
            lambda: self._add_via_scene(lambda s: s.add_swinger(8, 7))))
        btn_row3.addWidget(_add_btn("⬇️ Drop", "Bersaglio a caduta",
            lambda: self._add_via_scene(lambda s: s.add_drop_turner(9, 7))))
        btn_row3.addWidget(_add_btn("➡️ Mover", "Bersaglio su rotaia",
            lambda: self._add_via_scene(lambda s: s.add_mover(10, 7))))
        btn_row3.addStretch()
        layout.addLayout(btn_row3)

        layout.addWidget(QLabel("Ostacoli e coperture:"))
        btn_row4 = QHBoxLayout()
        btn_row4.addWidget(_add_btn("🧱 Muro", "Aggiunge un muro",
            lambda: self._add_via_scene(lambda s: s.add_wall(5, 8, 3.0, 0.2))))
        btn_row4.addWidget(_add_btn("🛡️ Barriera", "Aggiunge una barriera",
            lambda: self._add_via_scene(lambda s: s.add_barrier(5, 9, 2.0, 0.15))))
        btn_row4.addWidget(_add_btn("🚪 Porta", "Aggiunge una porta",
            lambda: self._add_via_scene(lambda s: s.add_door(5, 10, 0.9, 0.05))))
        btn_row4.addStretch()
        layout.addLayout(btn_row4)

        layout.addWidget(QLabel("Altro:"))
        btn_row5 = QHBoxLayout()
        btn_row5.addWidget(_add_btn("➖ Fault Line", "Linea di fallo",
            lambda: self._add_via_scene(lambda s: s.add_fault_line(5, 11, 3.0))))
        btn_row5.addWidget(_add_btn("🚫 No-Shoot", "Bersaglio No-Shoot",
            lambda: self._add_via_scene(lambda s: s.add_no_shoot(5, 12, 0.45, 0.45))))
        btn_row5.addWidget(_add_btn("⬛ Hard Cover", "Copertura impenetrabile",
            lambda: self._add_via_scene(lambda s: s.add_hard_cover(5, 13))))
        btn_row5.addWidget(_add_btn("⬜ Soft Cover", "Copertura visiva",
            lambda: self._add_via_scene(lambda s: s.add_soft_cover(5, 14))))
        btn_row5.addStretch()
        layout.addLayout(btn_row5)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _add_via_scene(self, add_func: callable):
        """Chiama una funzione di aggiunta sulla scena e aggiorna info.

        add_func: callable che riceve la scena e chiama add_wall/add_target/etc.
        """
        if self.scene_ref is None:
            return
        add_func(self.scene_ref)
        # Notifica il parent (MainWindow) per aggiornare info stage
        parent = self.parent()
        if parent and hasattr(parent, '_refresh_info'):
            parent._refresh_info()

    # ── Navigazione (3 passi) ────────────────────────────────────────

    def _go_forward(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            self._stack.setCurrentIndex(1)
            self._btn_back.setEnabled(True)
            self._btn_next.setEnabled(True)
            self._step_label.setText("Passo 2 di 3: Posizioni di tiro")
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
            self._step_label.setText("Passo 2 di 3: Posizioni di tiro")

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
        widget = self._pos_list.itemWidget(item)
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
