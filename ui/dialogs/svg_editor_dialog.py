"""
SVG Target Editor — dialog per disegnare/modificare bersagli SVG personalizzati.

Caratteristiche:
- Canvas interattivo: click per aggiungere zone, drag per spostare
- Silhouette IPSC con griglia metrica e centro evidenziato
- Tool: Seleziona / Rettangolo / Ellisse
- Preset zone A/B/C/D con dimensioni e colori IPSC predefiniti
- Importa SVG esistente per modifica
- Esporta in resources/targets/custom/
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QKeySequence,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem,
    QListWidget, QListWidgetItem,
    QColorDialog, QSpinBox, QLineEdit, QFormLayout,
    QGroupBox, QMessageBox, QWidget, QFileDialog,
)

from core.target_designer import (
    SvgTargetDesign, SvgZone, ZONE_COLORS,
    make_ipsc_silhouette, ensure_custom_dir,
    CUSTOM_TARGETS_DIR,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  SilhouetteItem — sagoma del bersaglio
# ═══════════════════════════════════════════════════════════════════════════════

class SilhouetteItem(QGraphicsRectItem):
    """Sfondo che rappresenta la silhouette del bersaglio."""

    def __init__(self, design: SvgTargetDesign, scale: float, parent=None):
        w = design.width * scale
        h = design.height * scale
        super().__init__(0, 0, w, h, parent)
        self._design = design
        self._scale = scale
        self.setBrush(QBrush(QColor("#f1f5f9")))
        self.setPen(QPen(QColor("#cbd5e1"), 2))
        self.setZValue(0)
        self.setAcceptHoverEvents(False)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.save()
        s = self._scale
        w = self._design.width * s
        h = self._design.height * s

        # Bordo tratteggiato esterno
        painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, int(w), int(h))

        # Croce centrale
        cx, cy = w / 2, h / 2
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.drawLine(int(cx), 0, int(cx), int(h))
        painter.drawLine(0, int(cy), int(w), int(cy))

        # Label "TOP" in alto
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(QRectF(4, 4, 60, 14), Qt.AlignmentFlag.AlignLeft, "TOP ↑")

        painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
#  ZoneGraphicsItem — zona di punteggio (rettangolo o ellisse)
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneGraphicsItem(QGraphicsItem):
    """Zona di punteggio interattiva sul canvas."""

    HANDLE_SIZE = 8

    def __init__(self, zone: SvgZone, scale: float, parent=None):
        super().__init__(parent)
        self._zone = zone
        self._scale = scale
        self._resizing = False
        self._resize_corner = ""

        self.setPos(zone.x * scale, zone.y * scale)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    @property
    def zone(self) -> SvgZone:
        return self._zone

    def boundingRect(self):
        w = self._zone.width * self._scale
        h = self._zone.height * self._scale
        return QRectF(-self.HANDLE_SIZE, -self.HANDLE_SIZE,
                       w + self.HANDLE_SIZE * 2, h + self.HANDLE_SIZE * 2)

    def shape(self):
        w = self._zone.width * self._scale
        h = self._zone.height * self._scale
        path = QPainterPath()
        if self._zone.shape_type == "ellipse":
            path.addEllipse(0, 0, w, h)
        elif self._zone.shape_type == "hexagon":
            path.addPolygon(self._hexagon_points(w, h))
        else:
            path.addRect(0, 0, w, h)
        return path

    def paint(self, painter, option, widget=None):
        w = self._zone.width * self._scale
        h = self._zone.height * self._scale
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Colore di riempimento
        color = QColor(self._zone.color)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor("#ffffff"), 2))

        if self._zone.shape_type == "ellipse":
            painter.drawEllipse(QRectF(0, 0, w, h))
        elif self._zone.shape_type == "hexagon":
            points = self._hexagon_points(w, h)
            painter.drawPolygon(points)
        else:
            painter.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)

        # Label al centro
        painter.setPen(QPen(QColor("white"), 1))
        f = painter.font()
        f.setPointSize(max(8, int(min(w, h) / 4)))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(0, 0, w, h),
                         Qt.AlignmentFlag.AlignCenter, self._zone.label)

        # Cornice di selezione
        if self.isSelected():
            painter.setPen(QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-2, -2, w + 4, h + 4))
            # Handle angolari
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2563eb")))
            hs = self.HANDLE_SIZE / 2
            for px, py in [(0, 0), (w, 0), (0, h), (w, h)]:
                painter.drawRect(QRectF(px - hs, py - hs, hs * 2, hs * 2))

        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            s = self._scale
            self._zone.x = self.pos().x() / s
            self._zone.y = self.pos().y() / s
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # Check resize handles
        if self.isSelected() and event.button() == Qt.MouseButton.LeftButton:
            s = self._scale
            w = self._zone.width * s
            h = self._zone.height * s
            pos = event.pos()
            hs = self.HANDLE_SIZE
            corners = {
                "tl": (0, 0), "tr": (w, 0),
                "bl": (0, h), "br": (w, h),
            }
            for name, (cx, cy) in corners.items():
                if abs(pos.x() - cx) <= hs and abs(pos.y() - cy) <= hs:
                    self._resizing = True
                    self._resize_corner = name
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            s = self._scale
            pos = event.pos()
            w = max(10, pos.x() / s)
            h = max(10, pos.y() / s)
            if "l" in self._resize_corner:
                self._zone.width = w
            if "r" in self._resize_corner:
                self._zone.width = w
            if "t" in self._resize_corner:
                self._zone.height = h
            if "b" in self._resize_corner:
                self._zone.height = h
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        super().mouseReleaseEvent(event)

    @staticmethod
    def _hexagon_points(w: float, h: float):
        """Calcola i 6 vertici dell'esagono inscritto nel rettangolo w×h."""
        import math
        from PySide6.QtGui import QPolygonF
        cx, cy = w / 2, h / 2
        rx, ry = w / 2, h / 2
        pts = [QPointF(cx + rx * math.cos(3.14159 * 2 * i / 6 - 3.14159 / 2),
                       cy + ry * math.sin(3.14159 * 2 * i / 6 - 3.14159 / 2))
               for i in range(6)]
        return QPolygonF(pts)

    def hoverMoveEvent(self, event):
        """Cambia cursore sugli angoli per hint di resize."""
        s = self._scale
        w = self._zone.width * s
        h = self._zone.height * s
        pos = event.pos()
        hs = self.HANDLE_SIZE
        on_corner = any(
            abs(pos.x() - cx) <= hs and abs(pos.y() - cy) <= hs
            for cx, cy in [(0, 0), (w, 0), (0, h), (w, h)]
        )
        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor if on_corner
            else Qt.CursorShape.ArrowCursor
        )
        super().hoverMoveEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
#  Scene personalizzata per gestire i click di aggiunta zone
# ═══════════════════════════════════════════════════════════════════════════════

class SvgEditorScene(QGraphicsScene):
    """Scena che gestisce click per aggiungere zone in base allo strumento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor: 'SvgEditorDialog | None' = None

    def mousePressEvent(self, event):
        dialog = self.editor
        if dialog and dialog._current_tool in ("rect", "ellipse"):
            # Aggiunge una zona nel punto cliccato
            pos = event.scenePos()
            s = dialog._scale
            x = max(0, pos.x() / s - 20)
            y = max(0, pos.y() / s - 20)
            dialog._add_zone(dialog._current_tool, x, y)
            event.accept()
            return
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
#  SvgEditorDialog
# ═══════════════════════════════════════════════════════════════════════════════

class SvgEditorDialog(QDialog):
    """Dialog per creare/modificare bersagli SVG personalizzati."""

    def __init__(self, parent=None, design: SvgTargetDesign | None = None):
        super().__init__(parent)
        self._design = design or SvgTargetDesign(
            name="Nuovo Bersaglio",
            silhouette_path=make_ipsc_silhouette(),
        )
        self._scale = 3.0
        self._zone_items: list[ZoneGraphicsItem] = []

        self.setWindowTitle(f"✏️ Editor Bersagli SVG — {self._design.name}")
        self.setMinimumSize(950, 650)
        self.resize(1100, 750)
        self._setup_ui()
        self._sync_to_scene()

    # ── UI ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ── Canvas (sinistra) ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._btn_select = QPushButton("↖ Seleziona")
        self._btn_select.setCheckable(True)
        self._btn_select.setChecked(True)
        self._btn_select.clicked.connect(lambda: self._set_tool("select"))
        self._style_tool_btn(self._btn_select)
        toolbar.addWidget(self._btn_select)

        self._btn_rect = QPushButton("▭ Rettangolo")
        self._btn_rect.setCheckable(True)
        self._btn_rect.clicked.connect(lambda: self._set_tool("rect"))
        self._style_tool_btn(self._btn_rect)
        toolbar.addWidget(self._btn_rect)

        self._btn_ellipse = QPushButton("⬭ Ellisse")
        self._btn_ellipse.setCheckable(True)
        self._btn_ellipse.clicked.connect(lambda: self._set_tool("ellipse"))
        self._style_tool_btn(self._btn_ellipse)
        toolbar.addWidget(self._btn_ellipse)

        self._btn_hex = QPushButton("⬡ Esagono")
        self._btn_hex.setCheckable(True)
        self._btn_hex.clicked.connect(lambda: self._set_tool("hexagon"))
        self._style_tool_btn(self._btn_hex)
        toolbar.addWidget(self._btn_hex)

        toolbar.addSpacing(12)

        # Preset zone
        for label, color, w, h in [("A", ZONE_COLORS["A"], 60, 40),
                                     ("B", ZONE_COLORS["B"], 45, 30),
                                     ("C", ZONE_COLORS["C"], 30, 20),
                                     ("D", ZONE_COLORS["D"], 20, 15)]:
            btn = QPushButton(label)
            btn.setFixedSize(32, 28)
            btn.setStyleSheet(
                f"background-color: {color}; color: white; "
                f"font-weight: bold; border-radius: 4px; "
                f"font-size: 12px; border: 1px solid rgba(0,0,0,0.2);"
            )
            btn.setToolTip(f"Aggiungi zona {label} ({w}×{h})")
            btn.clicked.connect(
                lambda checked, l=label, c=color, w=w, h=h:
                self._add_zone("rect", 20, 20, w, h, label=l, color=c)
            )
            toolbar.addWidget(btn)

        toolbar.addSpacing(12)

        self._btn_delete = QPushButton("🗑")
        self._btn_delete.setToolTip("Elimina zona selezionata (Canc)")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_delete.setFixedWidth(36)
        toolbar.addWidget(self._btn_delete)

        left_layout.addLayout(toolbar)

        # Canvas
        self._scene = SvgEditorScene(self)
        self._scene.editor = self
        self._scene.setSceneRect(
            -20, -20,
            self._design.width * self._scale + 40,
            self._design.height * self._scale + 40,
        )

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setStyleSheet("""
            QGraphicsView {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        left_layout.addWidget(self._view, 1)

        # Status bar
        status = QHBoxLayout()
        self._info_label = QLabel(
            f"📐 {self._design.width:.0f}×{self._design.height:.0f}  |  "
            f"🖱 Click per zona  |  "
            f"🔍 Zoom con rotellina"
        )
        self._info_label.setStyleSheet("font-size: 11px; color: #64748b; padding: 2px 4px;")
        status.addWidget(self._info_label)
        status.addStretch()

        self._zone_count_label = QLabel("0 zone")
        self._zone_count_label.setStyleSheet("font-size: 11px; color: #64748b;")
        status.addWidget(self._zone_count_label)
        left_layout.addLayout(status)

        layout.addWidget(left, 1)

        # ── Pannello destro ──
        right = QWidget()
        right.setFixedWidth(280)
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(10)

        # Nome
        name_gb = QGroupBox("Bersaglio")
        nf = QFormLayout(name_gb)
        nf.setSpacing(4)
        self._name_input = QLineEdit(self._design.name)
        self._name_input.textChanged.connect(self._on_name_changed)
        nf.addRow("Nome:", self._name_input)
        self._desc_input = QLineEdit(self._design.description)
        self._desc_input.setPlaceholderText("Opzionale")
        self._desc_input.textChanged.connect(self._on_desc_changed)
        nf.addRow("Descr.:", self._desc_input)
        right_layout.addWidget(name_gb)

        # Lista zone
        right_layout.addWidget(QLabel("Zone (click per selezionare):"))
        self._zone_list = QListWidget()
        self._zone_list.setMinimumHeight(100)
        self._zone_list.currentRowChanged.connect(self._on_zone_selected)
        right_layout.addWidget(self._zone_list, 1)

        # Proprietà zona
        prop_gb = QGroupBox("Proprietà Zona")
        pf = QFormLayout(prop_gb)
        pf.setSpacing(3)
        pf.setContentsMargins(8, 12, 8, 8)

        self._zone_label = QLineEdit("A")
        self._zone_label.setMaxLength(3)
        self._zone_label.textChanged.connect(self._on_zone_prop_changed)
        pf.addRow("Label:", self._zone_label)

        self._zone_color_btn = QPushButton()
        self._zone_color_btn.setFixedHeight(28)
        self._zone_color_btn.clicked.connect(self._pick_zone_color)
        pf.addRow("Colore:", self._zone_color_btn)

        self._zone_points = QSpinBox()
        self._zone_points.setRange(0, 100)
        self._zone_points.valueChanged.connect(self._on_zone_prop_changed)
        pf.addRow("Punti:", self._zone_points)

        sz = QHBoxLayout()
        self._zone_w = QSpinBox()
        self._zone_w.setRange(5, 500)
        self._zone_w.valueChanged.connect(self._on_zone_size_changed)
        sz.addWidget(self._zone_w)
        sz.addWidget(QLabel("×"))
        self._zone_h = QSpinBox()
        self._zone_h.setRange(5, 500)
        self._zone_h.valueChanged.connect(self._on_zone_size_changed)
        sz.addWidget(self._zone_h)
        pf.addRow("Dim.:", sz)

        xy = QHBoxLayout()
        self._zone_x = QSpinBox()
        self._zone_x.setRange(0, 500)
        self._zone_x.valueChanged.connect(self._on_zone_pos_changed)
        xy.addWidget(self._zone_x)
        xy.addWidget(QLabel("×"))
        self._zone_y = QSpinBox()
        self._zone_y.setRange(0, 500)
        self._zone_y.valueChanged.connect(self._on_zone_pos_changed)
        xy.addWidget(self._zone_y)
        pf.addRow("Pos.:", xy)

        self._zone_shape = QLabel("rettangolo")
        self._zone_shape.setStyleSheet("color: #64748b; font-size: 11px;")
        pf.addRow("Tipo:", self._zone_shape)

        right_layout.addWidget(prop_gb)

        # Pulsanti azione
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        btn_load = QPushButton("📂 Carica")
        btn_load.setToolTip("Carica SVG esistente per modificarlo")
        btn_load.clicked.connect(self._load_svg)
        btn_layout.addWidget(btn_load)

        btn_save = QPushButton("💾 Salva")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white;
                border: none; border-radius: 6px; padding: 8px 20px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_save.clicked.connect(self._save_svg)
        btn_layout.addWidget(btn_save)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()
        layout.addWidget(right)

    @staticmethod
    def _style_tool_btn(btn: QPushButton):
        btn.setFixedHeight(32)
        btn.setStyleSheet("""
            QPushButton {
                padding: 4px 12px; font-size: 12px; font-weight: 500;
                border: 1px solid #e2e8f0; border-radius: 6px;
                background: #ffffff; color: #0f172a;
            }
            QPushButton:hover { background: #f1f5f9; border-color: #94a3b8; }
            QPushButton:checked {
                background: #dbeafe; border-color: #2563eb; color: #2563eb;
            }
        """)

    # ── Tool management ────────────────────────────────────────────────

    _current_tool: str = "select"

    def _set_tool(self, tool: str):
        self._current_tool = tool
        self._btn_select.setChecked(tool == "select")
        self._btn_rect.setChecked(tool == "rect")
        self._btn_ellipse.setChecked(tool == "ellipse")

        if tool in ("rect", "ellipse"):
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
            self._info_label.setText(
                f"✏️ Click sul canvas per aggiungere zona {tool}"
            )
        else:
            self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._view.setCursor(Qt.CursorShape.ArrowCursor)
            self._info_label.setText(
                f"📐 {self._design.width:.0f}×{self._design.height:.0f}  |  "
                f"🖱 Seleziona e sposta zone"
            )

    # ── Scene ──────────────────────────────────────────────────────────

    def _sync_to_scene(self):
        self._scene.clear()
        self._zone_items.clear()
        self._draw_grid()

        # Silhouette
        sil = SilhouetteItem(self._design, self._scale)
        self._scene.addItem(sil)

        # Zone
        for z in self._design.zones:
            self._add_zone_item(z)
        self._refresh_zone_list()
        self._update_zone_count()

    def _draw_grid(self):
        s = self._scale
        w = self._design.width * s
        h = self._design.height * s
        pen = QPen(QColor("#f1f5f9"), 1)
        step = 10 * s
        for i in range(0, int(w) + 1, int(step)):
            self._scene.addLine(i, 0, i, h, pen)
        for i in range(0, int(h) + 1, int(step)):
            self._scene.addLine(0, i, w, i, pen)

    def _add_zone_item(self, zone: SvgZone) -> ZoneGraphicsItem:
        item = ZoneGraphicsItem(zone, self._scale)
        self._scene.addItem(item)
        self._zone_items.append(item)
        return item

    def _refresh_zone_list(self):
        self._zone_list.blockSignals(True)
        self._zone_list.clear()
        for i, z in enumerate(self._design.zones):
            shape = "⬭" if z.shape_type == "ellipse" else "▭"
            item = QListWidgetItem(
                f"{shape} {z.label}  {z.color}  ({z.points}pt)"
            )
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._zone_list.addItem(item)
        self._zone_list.blockSignals(False)
        self._update_zone_count()

    def _update_zone_count(self):
        self._zone_count_label.setText(f"{len(self._design.zones)} zone")

    # ── Zone ops ───────────────────────────────────────────────────────

    def _add_zone(self, shape_type: str, x: float, y: float,
                  w: float = 40.0, h: float = 40.0,
                  label: str = "", color: str = ""):
        if not label:
            label = chr(65 + len(self._design.zones))
        if not color:
            colors = list(ZONE_COLORS.values())
            color = colors[len(self._design.zones) % len(colors)]
        zone = SvgZone(
            label=label, color=color, points=5,
            shape_type=shape_type, x=x, y=y, width=w, height=h,
        )
        self._design.add_zone(zone)
        self._add_zone_item(zone)
        self._refresh_zone_list()
        self._zone_list.setCurrentRow(len(self._design.zones) - 1)

    def _delete_selected(self):
        selected = [it for it in self._zone_items if it.isSelected()]
        for item in selected:
            if item.zone in self._design.zones:
                self._design.zones.remove(item.zone)
            self._scene.removeItem(item)
            self._zone_items.remove(item)
        self._refresh_zone_list()

    def _clear_all(self):
        for item in self._zone_items:
            self._scene.removeItem(item)
        self._design.zones.clear()
        self._zone_items.clear()
        self._refresh_zone_list()

    # ── Zone properties ────────────────────────────────────────────────

    def _on_zone_selected(self, row: int):
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        self._zone_label.setText(zone.label)
        self._zone_color_btn.setText(f"  {zone.color}")
        self._zone_color_btn.setStyleSheet(
            f"background-color: {zone.color}; color: white; "
            f"border-radius: 4px; font-weight: 500; text-align: left;"
        )
        self._zone_points.setValue(zone.points)
        self._zone_w.setValue(int(zone.width))
        self._zone_h.setValue(int(zone.height))
        self._zone_x.setValue(int(zone.x))
        self._zone_y.setValue(int(zone.y))
        shape_names = {"rect": "rettangolo", "ellipse": "ellisse", "hexagon": "esagono"}
        self._zone_shape.setText(shape_names.get(zone.shape_type, zone.shape_type))

        # Selezione scena
        for item in self._zone_items:
            item.setSelected(False)
        if row < len(self._zone_items):
            self._zone_items[row].setSelected(True)

    def _on_zone_prop_changed(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.label = self._zone_label.text()[:3] or "?"
        zone.points = self._zone_points.value()
        self._refresh_zone_list()

    def _on_zone_size_changed(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.width = float(self._zone_w.value())
        zone.height = float(self._zone_h.value())
        self._zone_items[row].prepareGeometryChange()
        self._zone_items[row].update()

    def _on_zone_pos_changed(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.x = float(self._zone_x.value())
        zone.y = float(self._zone_y.value())
        self._zone_items[row].setPos(zone.x * self._scale, zone.y * self._scale)

    def _pick_zone_color(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        color = QColorDialog.getColor(QColor(zone.color), self, "Colore zona")
        if color.isValid():
            zone.color = color.name()
            self._zone_color_btn.setText(f"  {zone.color}")
            self._zone_color_btn.setStyleSheet(
                f"background-color: {zone.color}; color: white; "
                f"border-radius: 4px; font-weight: 500;"
            )
            self._zone_items[row].update()
            self._refresh_zone_list()

    # ── Nome ───────────────────────────────────────────────────────────

    def _on_name_changed(self, text: str):
        self._design.name = text or "Bersaglio"
        self.setWindowTitle(f"✏️ Editor Bersagli SVG — {self._design.name}")

    def _on_desc_changed(self, text: str):
        self._design.description = text

    # ── Load / Save ────────────────────────────────────────────────────

    def _load_svg(self):
        """Carica un SVG esistente per modificarlo."""
        # Prima prova dalla cartella custom
        custom_dir = CUSTOM_TARGETS_DIR
        start_dir = custom_dir if os.path.isdir(custom_dir) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Carica SVG bersaglio", start_dir,
            "SVG (*.svg);;Tutti i file (*)",
        )
        if not path:
            return
        design = SvgTargetDesign.from_svg(path)
        if design is None:
            QMessageBox.warning(self, "Errore", f"Impossibile caricare:\n{path}")
            return
        self._design = design
        self._name_input.setText(design.name)
        self._desc_input.setText(design.description)
        self._sync_to_scene()
        self.setWindowTitle(f"✏️ Editor Bersagli SVG — {design.name}")

    def _save_svg(self):
        """Salva il bersaglio come SVG."""
        ensure_custom_dir()
        name = self._design.name.strip().lower().replace(" ", "_")
        name = "".join(c for c in name if c.isalnum() or c in "_-")
        if not name:
            name = "bersaglio"
        filename = f"{name}.svg"
        filepath = os.path.join(CUSTOM_TARGETS_DIR, filename)

        if os.path.isfile(filepath):
            reply = QMessageBox.question(
                self, "Sovrascrivere?",
                f"'{filename}' esiste già. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        svg = self._design.to_svg()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(svg)

        QMessageBox.information(
            self, "✅ Salvato",
            f"Bersaglio salvato:\n{filepath}\n\n"
            f"Riavvia l'app per usarlo nell'editor.",
        )
        self.accept()

    def get_design(self) -> SvgTargetDesign:
        return self._design
