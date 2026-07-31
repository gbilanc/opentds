# ui/editor/generator_panel.py
"""Wizard a 2 fasi per la generazione procedurale degli stage IPSC.

Fase 1: dimensioni + forma + rotazione area di tiro
Fase 2: posizioni di tiro + bersagli + auto-place
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.generator import GeneratorConfig, Phase1Config
from core.models import ItemType
from ui.icons import load_icon


class StageWizard(QWidget):
    """Wizard a 2 pagine per la generazione dello stage."""

    # Segnali
    phase1Requested = Signal(Phase1Config)
    phase1PreviewChanged = Signal(Phase1Config)  # update live (rotazione/scala)
    stopRequested = Signal()
    placeModeToggled = Signal(bool)  # True = attivo, False = disattivo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase1_done = False
        self._live_connected = False
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

        title = QLabel("Fase 1 — Area di Tiro")
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
        self._p1_shape.addItems(["Casuale", "Quadrato", "Rettangolo", "T", "U", "W", "X", "Y", "Z"])
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

        scale_row = QHBoxLayout()
        self._p1_scale = QSpinBox()
        self._p1_scale.setRange(30, 150)
        self._p1_scale.setValue(100)
        self._p1_scale.setSuffix("%")
        self._p1_scale.setFixedWidth(80)

        self._p1_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._p1_scale_slider.setRange(30, 150)
        self._p1_scale_slider.setValue(100)
        self._p1_scale_slider.valueChanged.connect(self._p1_scale.setValue)
        self._p1_scale.valueChanged.connect(self._p1_scale_slider.setValue)
        scale_row.addWidget(self._p1_scale)
        scale_row.addWidget(self._p1_scale_slider, 1)
        shape_form.addRow("Scala:", scale_row)

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

    def _build_phase1_config(self) -> Phase1Config:
        """Costruisce un Phase1Config dai valori correnti dei controlli."""
        shape_map = {
            "Casuale": "random",
            "Quadrato": "Q",
            "Rettangolo": "O",
            "T": "T",
            "U": "U",
            "W": "W",
            "X": "X",
            "Y": "Y",
            "Z": "Z",
        }
        delim_map = {
            "Fault Lines": "fault_lines",
            "Barriere": "barriers",
            "Muri": "walls",
            "Misto": "mixed",
        }
        return Phase1Config(
            stage_width=self._p1_width.value(),
            stage_depth=self._p1_depth.value(),
            letter_shape=shape_map[self._p1_shape.currentText()],
            rotation=float(self._p1_rotation.value()),
            polygon_scale=self._p1_scale.value() / 100.0,
            delimitation=delim_map[self._p1_delim.currentText()],
        )

    def _connect_live_preview(self):
        """Collega i controlli di rotazione e scala all'update live della scena."""
        if self._live_connected:
            return
        self._live_connected = True
        self._p1_rotation.valueChanged.connect(self._on_live_param_changed)
        self._p1_rot_slider.valueChanged.connect(self._on_live_param_changed)
        self._p1_scale.valueChanged.connect(self._on_live_param_changed)
        self._p1_scale_slider.valueChanged.connect(self._on_live_param_changed)

    def _disconnect_live_preview(self):
        """Scollega i controlli dall'update live."""
        if not self._live_connected:
            return
        self._live_connected = False
        self._p1_rotation.valueChanged.disconnect(self._on_live_param_changed)
        self._p1_rot_slider.valueChanged.disconnect(self._on_live_param_changed)
        self._p1_scale.valueChanged.disconnect(self._on_live_param_changed)
        self._p1_scale_slider.valueChanged.disconnect(self._on_live_param_changed)

    def _on_live_param_changed(self):
        """Emesso quando rotazione o scala cambiano dopo la generazione iniziale."""
        if not self._phase1_done:
            return
        config = self._build_phase1_config()
        self.phase1PreviewChanged.emit(config)

    def _on_generate_phase1(self):
        config = self._build_phase1_config()
        self._btn_gen_area.setEnabled(False)
        self._btn_gen_area.setText("⏳ Generazione in corso...")
        self._p1_status.setText("Generazione area di tiro in corso...")
        self.phase1Requested.emit(config)

    def on_phase1_complete(self, stage_name: str = "Stage"):
        """Chiamato quando la Fase 1 è completata con successo."""
        self._phase1_done = True
        self._btn_gen_area.setEnabled(True)
        self._btn_gen_area.setText("Area Generata — Rigenera")
        self._btn_gen_area.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; font-size: 14px; font-weight: 600;
                background-color: #f59e0b; color: white;
                border: none; border-radius: 8px;
            }
            QPushButton:hover { background-color: #d97706; }
        """)
        self._p1_status.setText(f"Area di tiro generata ({stage_name})")
        self._btn_next.setEnabled(True)
        # Attiva update live per rotazione e scala
        self._connect_live_preview()

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
        self._p1_status.setText(f"Errore: {message}")
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

        title = QLabel("Fase 2 — Posizioni di Tiro")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        # ── Shooting positions ──
        pos_group = QGroupBox("Posizioni di Tiro")
        pos_layout = QVBoxLayout(pos_group)
        pos_layout.setSpacing(8)

        pos_help = QLabel(
            "Clicca sulla mappa nell'editor per aggiungere posizioni.\n"
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
        self._pos_list.setMinimumHeight(150)
        pos_layout.addWidget(self._pos_list, 1)

        btn_row = QHBoxLayout()
        self._btn_place_pos = QPushButton("Posiziona")
        self._btn_place_pos.setCheckable(True)
        self._btn_place_pos.setToolTip("Clicca sulla mappa per aggiungere posizioni")
        self._btn_place_pos.clicked.connect(self._toggle_place_mode)
        btn_row.addWidget(self._btn_place_pos)

        self._btn_clear_pos = QPushButton("Cancella tutte")
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
        """Pagina 3: lista di bersagli e ostacoli aggiungibili allo stage.

        Clicca su un elemento per aggiungerlo al centro della scena.
        Include tutti i tipi standard e compositi (doppietti, bobber, target+noshoot).
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Fase 3 — Aggiunta Bersagli e Ostacoli")
        title.setStyleSheet("font-weight: 700; font-size: 16px; color: #0f172a;")
        layout.addWidget(title)

        help_text = QLabel(
            "Clicca su un elemento per aggiungerlo al centro dello stage.\n"
            "Trascinalo poi nella posizione desiderata."
        )
        help_text.setStyleSheet("font-size: 11px; color: #64748b;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # Lista bersagli
        self._target_list = QListWidget()
        self._target_list.setAlternatingRowColors(True)
        self._target_list.setIconSize(QSize(20, 20))
        self._target_list.itemClicked.connect(self._on_target_list_clicked)
        self._target_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e2e8f0; border-radius: 8px;
                background-color: #ffffff;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px; border-radius: 4px;
                font-size: 12px;
            }
            QListWidget::item:hover {
                background-color: #f1f5f9;
            }
            QListWidget::item:selected {
                background-color: #dbeafe; color: #0f172a;
            }
        """)

        # Struttura: (categoria, [(nome_icona, label, tip, item_type, (w, h)), ...])
        _ICON_MAP = {
            "paper": "target_paper",
            "steel": "target_steel",
            "popper": "target_popper",
            "plate": "target_plate",
            "bobber": "target_bobber",
            "double": "target_double",
            "double_hostage": "target_double_hostage",
            "swinger": "target_swinger",
            "drop": "target_drop",
            "mover": "target_mover",
            "wall": "wall",
            "barrier": "barrier",
            "door": "door",
            "hard_cover": "hard_cover",
            "soft_cover": "soft_cover",
            "fault_line": "fault_line",
            "no_shoot": "no_shoot",
        }
        ITEMS = [
            (
                "Bersagli cartacei",
                [
                    (
                        "paper",
                        "Paper Target",
                        "Bersaglio cartaceo IPSC",
                        ItemType.PAPER_TARGET,
                        (0.45, 0.75),
                    ),
                    (
                        "paper",
                        "Mini Target",
                        "Bersaglio ridotto (App. B3)",
                        ItemType.MINI_TARGET,
                        (0.30, 0.30),
                    ),
                    (
                        "paper",
                        "Micro Target",
                        "Bersaglio micro",
                        ItemType.MICRO_TARGET,
                        (0.20, 0.20),
                    ),
                    (
                        "double",
                        "Doppio affiancato",
                        "Due paper affiancati (gap 5cm)",
                        ItemType.DOUBLET_SIDE,
                        (0.95, 0.75),
                    ),
                    (
                        "double",
                        "Doppio sovrapposto",
                        "Due paper sovrapposti 40%",
                        ItemType.DOUBLET_OVERLAP,
                        (0.65, 0.75),
                    ),
                    (
                        "double_hostage",
                        "Doppio + ostaggio (aff.)",
                        "Due paper con no-shoot nel mezzo",
                        ItemType.DOUBLET_SIDE_HOSTAGE,
                        (1.20, 0.75),
                    ),
                    (
                        "double_hostage",
                        "Doppio + ostaggio (sovr.)",
                        "Due paper sovrapposti con no-shoot",
                        ItemType.DOUBLET_OVERLAP_HOSTAGE,
                        (0.90, 0.75),
                    ),
                    (
                        "double_hostage",
                        "Target + No-Shoot",
                        "Paper con no-shoot sovrapposto 40%",
                        ItemType.TARGET_PLUS_NOSHOOT,
                        (0.70, 0.75),
                    ),
                ],
            ),
            (
                "Bersagli metallici",
                [
                    (
                        "steel",
                        "Steel generico",
                        "Bersaglio metallico",
                        ItemType.STEEL_TARGET,
                        (0.30, 0.30),
                    ),
                    (
                        "popper",
                        "Popper calibrato",
                        "Metallico calibrato (App. C1)",
                        ItemType.POPPER,
                        (0.30, 0.30),
                    ),
                    (
                        "plate",
                        "Piatto metallico",
                        "Non calibrato (App. C3)",
                        ItemType.METAL_PLATE,
                        (0.20, 0.20),
                    ),
                    (
                        "bobber",
                        "Piatto bobber",
                        "Pop-up che scompare se colpito",
                        ItemType.BOBBER_PLATE,
                        (0.20, 0.20),
                    ),
                    (
                        "bobber",
                        "Doppio bobber",
                        "Due bobber affiancati",
                        ItemType.DOUBLE_BOBBER,
                        (0.50, 0.20),
                    ),
                ],
            ),
            (
                "Bersagli mobili",
                [
                    ("swinger", "Swinger", "Bersaglio oscillante", ItemType.SWINGER, (0.45, 0.75)),
                    (
                        "drop",
                        "Drop Turner",
                        "Bersaglio a caduta",
                        ItemType.DROP_TURNER,
                        (0.45, 0.75),
                    ),
                    ("mover", "Mover", "Bersaglio su rotaia", ItemType.MOVER, (0.45, 0.75)),
                ],
            ),
            (
                "Ostacoli e coperture",
                [
                    ("wall", "Muro", "Muro per oscurare bersagli", ItemType.WALL, (3.0, 0.2)),
                    ("barrier", "Barriera", "Barriera visiva", ItemType.BARRIER, (2.0, 0.15)),
                    ("door", "Porta", "Porta", ItemType.DOOR, (0.9, 0.05)),
                    (
                        "hard_cover",
                        "Hard Cover",
                        "Copertura impenetrabile",
                        ItemType.HARD_COVER,
                        (2.0, 0.2),
                    ),
                    (
                        "soft_cover",
                        "Soft Cover",
                        "Copertura visiva",
                        ItemType.SOFT_COVER,
                        (2.0, 0.15),
                    ),
                ],
            ),
            (
                "Altro",
                [
                    (
                        "fault_line",
                        "Fault Line",
                        "Linea di fallo perimetrale",
                        ItemType.FAULT_LINE,
                        (3.0, 0.0),
                    ),
                    (
                        "no_shoot",
                        "No-Shoot",
                        "Bersaglio di penalità",
                        ItemType.NO_SHOOT,
                        (0.45, 0.75),
                    ),
                ],
            ),
        ]

        # Aggiungi i bersagli SVG personalizzati come categoria dinamica
        custom_items = self._list_custom_svg_items()
        if custom_items:
            ITEMS.append(("Bersagli personalizzati (SVG)", custom_items))

        for category, items in ITEMS:
            # Header di categoria
            h_item = QListWidgetItem(f"  {category}")
            h_item.setFlags(Qt.ItemFlag.NoItemFlags)
            h_item.setData(Qt.ItemDataRole.UserRole, "__header__")
            font = h_item.font()
            font.setBold(True)
            font.setPointSize(10)
            h_item.setFont(font)
            h_item.setForeground(QColor("#0f172a"))
            self._target_list.addItem(h_item)

            # Items della categoria
            for entry in items:
                if len(entry) == 6:
                    icon_name, label, tip, itype, (def_w, def_h), custom_svg = entry
                else:
                    icon_name, label, tip, itype, (def_w, def_h) = entry
                    custom_svg = ""
                item = QListWidgetItem(label)
                svg_name = _ICON_MAP.get(icon_name, icon_name)
                item.setIcon(load_icon(svg_name))
                item.setToolTip(tip)
                item.setData(Qt.ItemDataRole.UserRole, "__target__")
                item.setData(Qt.ItemDataRole.UserRole + 1, itype.name)
                item.setData(Qt.ItemDataRole.UserRole + 2, def_w)
                item.setData(Qt.ItemDataRole.UserRole + 3, def_h)
                item.setData(Qt.ItemDataRole.UserRole + 4, custom_svg)
                self._target_list.addItem(item)

        layout.addWidget(self._target_list, 1)

        pos_info = QLabel(
            "Gli oggetti vengono aggiunti al centro dello stage.\n"
            "Spostali con drag & drop sulla scena."
        )
        pos_info.setStyleSheet("font-size: 10px; color: #94a3b8;")
        layout.addWidget(pos_info)

        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _list_custom_svg_items() -> list[tuple]:
        """Restituisce la lista dei bersagli SVG personalizzati disponibili.

        Ogni entry è una tupla:
        (icon_name, label, tooltip, item_type, (w, h), custom_svg_path)
        """
        import os

        from core.target_designer import CUSTOM_TARGETS_DIR
        from ui.editor.stage_scene import SvgTargetGraphicsItem

        items: list[tuple] = []
        if not os.path.isdir(CUSTOM_TARGETS_DIR):
            return items
        for fname in sorted(os.listdir(CUSTOM_TARGETS_DIR)):
            if not fname.lower().endswith(".svg"):
                continue
            full_path = os.path.join(CUSTOM_TARGETS_DIR, fname)
            portable = SvgTargetGraphicsItem._make_path_portable(full_path)
            label = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").title()
            def_w, def_h = 0.45, 0.75
            try:
                from xml.etree import ElementTree as ET

                tree = ET.parse(full_path)
                root = tree.getroot()
                vb = root.get("viewBox", "")
                if vb:
                    parts = vb.split()
                    if len(parts) >= 4:
                        svg_w = float(parts[2])
                        svg_h = float(parts[3])
                        if svg_w > 0 and svg_h > 0:
                            def_h = 0.75
                            def_w = 0.75 * svg_w / svg_h
            except Exception:
                pass
            items.append(
                (
                    "paper",
                    label,
                    f"SVG personalizzato: {fname}",
                    ItemType.PAPER_TARGET,
                    (def_w, def_h),
                    portable,  # percorso relativo per portabilità
                )
            )
        return items

    def _on_target_list_clicked(self, item: QListWidgetItem):
        """Aggiunge il bersaglio selezionato alla scena."""
        role = item.data(Qt.ItemDataRole.UserRole)
        if role != "__target__" or self.scene_ref is None:
            return

        type_name = item.data(Qt.ItemDataRole.UserRole + 1)
        def_w = item.data(Qt.ItemDataRole.UserRole + 2)
        def_h = item.data(Qt.ItemDataRole.UserRole + 3)
        custom_svg = item.data(Qt.ItemDataRole.UserRole + 4) or ""

        try:
            itype = getattr(ItemType, type_name)
        except AttributeError:
            return

        # Posizione centrale di default
        if hasattr(self.scene_ref, "stage"):
            cx = self.scene_ref.stage.width / 2
            cy = self.scene_ref.stage.depth / 2
        else:
            cx, cy = 10.0, 7.5

        s = self.scene_ref

        if itype == ItemType.PAPER_TARGET:
            s.add_target(cx, cy, def_w, def_h, itype)
        elif itype == ItemType.MINI_TARGET:
            s.add_mini_target(cx, cy)
        elif itype == ItemType.MICRO_TARGET:
            s.add_micro_target(cx, cy)
        elif itype == ItemType.STEEL_TARGET:
            s.add_target(cx, cy, def_w, def_h, itype)
        elif itype == ItemType.POPPER:
            s.add_popper(cx, cy)
        elif itype == ItemType.METAL_PLATE:
            s.add_metal_plate(cx, cy)
        elif itype in (
            ItemType.DOUBLET_SIDE,
            ItemType.DOUBLET_OVERLAP,
            ItemType.DOUBLET_SIDE_HOSTAGE,
            ItemType.DOUBLET_OVERLAP_HOSTAGE,
            ItemType.BOBBER_PLATE,
            ItemType.DOUBLE_BOBBER,
            ItemType.TARGET_PLUS_NOSHOOT,
        ):
            s.add_composite(cx, cy, itype)
        elif itype == ItemType.SWINGER:
            s.add_swinger(cx, cy)
        elif itype == ItemType.DROP_TURNER:
            s.add_drop_turner(cx, cy)
        elif itype == ItemType.MOVER:
            s.add_mover(cx, cy)
        elif itype == ItemType.WALL:
            s.add_wall(cx, cy, def_w, def_h)
        elif itype == ItemType.BARRIER:
            s.add_barrier(cx, cy, def_w, def_h)
        elif itype == ItemType.DOOR:
            s.add_door(cx, cy, def_w, def_h)
        elif itype == ItemType.HARD_COVER:
            s.add_hard_cover(cx, cy, def_w, def_h)
        elif itype == ItemType.SOFT_COVER:
            s.add_soft_cover(cx, cy, def_w, def_h)
        elif itype == ItemType.FAULT_LINE:
            s.add_fault_line(cx, cy, def_w)
        elif itype == ItemType.NO_SHOOT:
            s.add_no_shoot(cx, cy, def_w, def_h)

        # Applica SVG personalizzato se specificato
        if custom_svg:
            # Trova l'ultimo item aggiunto e impostagli il custom_svg_path
            if s.stage.items:
                last_item = s.stage.items[-1]
                last_item.properties["custom_svg_path"] = custom_svg
                # Aggiorna il graphics item per renderizzare con il nuovo SVG
                g = s._items.get(last_item.id)
                if g and hasattr(g, "update_from_model"):
                    g.update_from_model()

        # Notifica parent
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_info"):
            parent._refresh_info()

    def _add_via_scene(self, add_func: callable):
        """Chiama una funzione di aggiunta sulla scena e aggiorna info.

        add_func: callable che riceve la scena e chiama add_wall/add_target/etc.
        """
        if self.scene_ref is None:
            return
        add_func(self.scene_ref)
        # Notifica il parent (MainWindow) per aggiornare info stage
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_info"):
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
        widget.setMinimumHeight(36)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        label = QLabel(text)
        label.setStyleSheet("font-size: 13px; font-weight: 500; color: #0f172a;")
        layout.addWidget(label, 1)

        btn_del = QPushButton(load_icon("close"), "")
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

    def _add_item_with_delete(
        self, lst: QListWidget, text: str, on_delete_clicked: callable
    ) -> None:
        """Aggiunge una riga con bottone elimina a una lista."""
        item = QListWidgetItem()
        widget = self._make_list_item_widget(text, lambda w: on_delete_clicked(item))
        item.setSizeHint(widget.minimumSizeHint())
        lst.addItem(item)
        lst.setItemWidget(item, widget)

    # ── Gestione posizioni di tiro ────────────────────────────────────

    def add_shooting_position(
        self,
        x: float,
        y: float,
        is_start: bool = False,
        on_delete_clicked: callable = None,
        on_renumbered: callable = None,
    ):
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
                    new_text = new_num + t[t.index(" ") :]
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
            self._btn_place_pos.setText("Posiziona")

    def _clear_positions(self):
        self._pos_list.clear()
        self.placeModeToggled.emit(False)
        # Rimuove anche i marker dalla scena
        if self.scene_ref:
            self.scene_ref.clear_shooting_position_markers()
            # Sincronizza stage.shooting_positions
            self.scene_ref.stage.shooting_positions.clear()
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_info"):
            parent._refresh_info()

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
        from PySide6.QtGui import QColor, QPainter, QPixmap

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
