"""
SVG Target Editor — dialog per disegnare/modificare bersagli SVG personalizzati.

Caratteristiche:
- Canvas QGraphicsView con silhouette del bersaglio
- Aggiunta di zone rettangolo/ellisse con colore e label
- Selezione, spostamento, ridimensionamento zone
- Preview colorata con anteprima IPSC
- Esportazione in SVG
"""
from __future__ import annotations

import os
import math
from typing import Optional, List

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem,
    QGraphicsTextItem, QListWidget, QListWidgetItem,
    QColorDialog, QSpinBox, QLineEdit, QFormLayout,
    QGroupBox, QMessageBox, QWidget, QToolBar,
)

from core.target_designer import (
    SvgTargetDesign, SvgZone, ZONE_COLORS,
    make_ipsc_silhouette, ensure_custom_dir,
    CUSTOM_TARGETS_DIR,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  ZoneGraphicsItem — elemento grafico per una zona sul canvas
# ═══════════════════════════════════════════════════════════════════════════════

class ZoneGraphicsItem(QGraphicsRectItem):
    """Rappresentazione grafica di una zona sul canvas.

    Supporta selezione, spostamento e ridimensionamento interattivo.
    """

    def __init__(self, zone: SvgZone, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._zone = zone
        self._scale = scale
        self._editing = False
        self._resize_handle_size = 6

        self.setRect(zone.x * scale, zone.y * scale,
                     zone.width * scale, zone.height * scale)
        self.setBrush(QBrush(QColor(zone.color)))
        self.setPen(QPen(QColor("#ffffff"), 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(10)

        # Label
        self._text = QGraphicsTextItem(zone.label, self)
        self._text.setDefaultTextColor(QColor("#ffffff"))
        f = self._text.font()
        f.setPointSize(12)
        f.setBold(True)
        self._text.setFont(f)
        self._center_text()

    def _center_text(self):
        r = self.rect()
        self._text.setPos(
            r.x() + (r.width() - self._text.boundingRect().width()) / 2,
            r.y() + (r.height() - self._text.boundingRect().height()) / 2,
        )

    @property
    def zone(self) -> SvgZone:
        return self._zone

    def update_from_zone(self):
        """Sincronizza la grafica con il modello."""
        s = self._scale
        self.setRect(self._zone.x * s, self._zone.y * s,
                     self._zone.width * s, self._zone.height * s)
        self.setBrush(QBrush(QColor(self._zone.color)))
        self._text.setPlainText(self._zone.label)
        self._center_text()
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = self._snap(value)
            return new_pos
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            s = self._scale
            self._zone.x = self.pos().x() / s
            self._zone.y = self.pos().y() / s
            self._center_text()
        return super().itemChange(change, value)

    def _snap(self, pos: QPointF) -> QPointF:
        snap = 2.0 * self._scale
        x = round(pos.x() / snap) * snap
        y = round(pos.y() / snap) * snap
        return QPointF(x, y)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            painter.setPen(QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(-3, -3, 3, 3))
            # Resize handles
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2563eb")))
            r = self.rect()
            h = self._resize_handle_size / 2
            for px, py in [(r.x(), r.y()), (r.x() + r.width(), r.y()),
                           (r.x(), r.y() + r.height()),
                           (r.x() + r.width(), r.y() + r.height())]:
                painter.drawRect(QRectF(px - h, py - h, h * 2, h * 2))
            painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
#  SvgEditorDialog
# ═══════════════════════════════════════════════════════════════════════════════

class SvgEditorDialog(QDialog):
    """Dialog per creare/modificare bersagli SVG personalizzati."""

    def __init__(self, parent=None, design: Optional[SvgTargetDesign] = None):
        super().__init__(parent)
        self._design = design or SvgTargetDesign(
            name="Nuovo Bersaglio",
            silhouette_path=make_ipsc_silhouette(),
        )
        self._scale = 3.0  # pixel per unità viewBox
        self._zone_items: list[ZoneGraphicsItem] = []

        self.setWindowTitle(f"Editor Bersagli SVG — {self._design.name}")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        self._setup_ui()
        self._sync_to_scene()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Canvas ──
        canvas_layout = QVBoxLayout()
        canvas_layout.setSpacing(4)

        toolbar = QToolBar("Strumenti")
        toolbar.setIconSize(Qt.QSize(16, 16))

        self._btn_select = QPushButton("↖ Seleziona")
        self._btn_select.setCheckable(True)
        self._btn_select.setChecked(True)
        self._btn_select.clicked.connect(lambda: self._set_tool("select"))
        toolbar.addWidget(self._btn_select)

        self._btn_rect = QPushButton("▭ Zona Retta")
        self._btn_rect.setCheckable(True)
        self._btn_rect.clicked.connect(lambda: self._set_tool("rect"))
        toolbar.addWidget(self._btn_rect)

        self._btn_ellipse = QPushButton("⬭ Zona Ellisse")
        self._btn_ellipse.setCheckable(True)
        self._btn_ellipse.clicked.connect(lambda: self._set_tool("ellipse"))
        toolbar.addWidget(self._btn_ellipse)

        toolbar.addSeparator()

        self._btn_delete = QPushButton("🗑 Elimina")
        self._btn_delete.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._btn_delete)

        self._btn_clear = QPushButton("🗑 Elimina tutte")
        self._btn_clear.clicked.connect(self._clear_all)
        toolbar.addWidget(self._btn_clear)

        canvas_layout.addWidget(toolbar)

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(
            -10, -10,
            self._design.width * self._scale + 20,
            self._design.height * self._scale + 20,
        )
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setStyleSheet("""
            QGraphicsView {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        canvas_layout.addWidget(self._view, 1)

        # Info label
        self._info_label = QLabel(
            f"Dimensione: {self._design.width:.0f}×{self._design.height:.0f} | "
            f"Zoom: Click per aggiungere zone"
        )
        self._info_label.setStyleSheet("font-size: 11px; color: #64748b;")
        canvas_layout.addWidget(self._info_label)

        layout.addLayout(canvas_layout, 1)

        # ── Pannello destro ──
        right = QWidget()
        right.setFixedWidth(280)
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(8)

        # Nome bersaglio
        name_group = QGroupBox("Bersaglio")
        name_form = QFormLayout(name_group)
        self._name_input = QLineEdit(self._design.name)
        self._name_input.textChanged.connect(self._on_name_changed)
        name_form.addRow("Nome:", self._name_input)

        self._desc_input = QLineEdit(self._design.description)
        self._desc_input.textChanged.connect(self._on_desc_changed)
        name_form.addRow("Descrizione:", self._desc_input)

        right_layout.addWidget(name_group)

        # Lista zone
        right_layout.addWidget(QLabel("Zone:"))
        self._zone_list = QListWidget()
        self._zone_list.currentRowChanged.connect(self._on_zone_selected)
        right_layout.addWidget(self._zone_list, 1)

        # Proprietà zona selezionata
        prop_group = QGroupBox("Proprietà Zona")
        prop_form = QFormLayout(prop_group)
        prop_form.setSpacing(4)

        self._zone_label = QLineEdit("A")
        self._zone_label.textChanged.connect(self._on_zone_prop_changed)
        prop_form.addRow("Label:", self._zone_label)

        self._zone_color_btn = QPushButton("🟩 Verde")
        self._zone_color_btn.clicked.connect(self._pick_zone_color)
        prop_form.addRow("Colore:", self._zone_color_btn)

        self._zone_points = QSpinBox()
        self._zone_points.setRange(0, 100)
        self._zone_points.setValue(5)
        self._zone_points.valueChanged.connect(self._on_zone_prop_changed)
        prop_form.addRow("Punti:", self._zone_points)

        self._zone_w = QSpinBox()
        self._zone_w.setRange(5, 500)
        self._zone_w.valueChanged.connect(self._on_zone_size_changed)
        prop_form.addRow("Larghezza:", self._zone_w)

        self._zone_h = QSpinBox()
        self._zone_h.setRange(5, 500)
        self._zone_h.valueChanged.connect(self._on_zone_size_changed)
        prop_form.addRow("Altezza:", self._zone_h)

        self._zone_x = QSpinBox()
        self._zone_x.setRange(0, 500)
        self._zone_x.valueChanged.connect(self._on_zone_pos_changed)
        prop_form.addRow("X:", self._zone_x)

        self._zone_y = QSpinBox()
        self._zone_y.setRange(0, 500)
        self._zone_y.valueChanged.connect(self._on_zone_pos_changed)
        prop_form.addRow("Y:", self._zone_y)

        right_layout.addWidget(prop_group)

        # Pulsanti azione
        btn_layout = QHBoxLayout()
        btn_preview = QPushButton("👁 Anteprima")
        btn_preview.clicked.connect(self._show_preview)
        btn_layout.addWidget(btn_preview)

        btn_save = QPushButton("💾 Salva SVG")
        btn_save.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: white;
                border: none; border-radius: 6px; padding: 8px 16px;
                font-weight: 600; }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_save.clicked.connect(self._save_svg)
        btn_layout.addWidget(btn_save)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()

        layout.addWidget(right)

    # ── Tool management ────────────────────────────────────────────────

    _current_tool: str = "select"

    def _set_tool(self, tool: str):
        self._current_tool = tool
        self._btn_select.setChecked(tool == "select")
        self._btn_rect.setChecked(tool == "rect")
        self._btn_ellipse.setChecked(tool == "ellipse")

        if tool == "rect" or tool == "ellipse":
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._view.setCursor(Qt.CursorShape.ArrowCursor)

    # mousePressEvent non serve: la gestione click è nella scena via tool mode

    # ── Scene sync ─────────────────────────────────────────────────────

    def _sync_to_scene(self):
        """Ricarica la scena dal modello."""
        self._scene.clear()
        self._zone_items.clear()
        self._zone_list.clear()

        # Sfondo griglia
        self._draw_grid()

        # Silhouette principale
        if self._design.silhouette_path:
            # Disegna la sagoma con un box grigio
            sil = QGraphicsRectItem(
                0, 0,
                self._design.width * self._scale,
                self._design.height * self._scale,
            )
            sil.setBrush(QBrush(QColor("#e2e8f0")))
            sil.setPen(QPen(QColor("#94a3b8"), 2))
            sil.setZValue(0)
            self._scene.addItem(sil)

        # Zone
        for zone in self._design.zones:
            self._add_zone_item(zone)

        self._refresh_zone_list()

    def _draw_grid(self):
        """Disegna una griglia di riferimento leggera."""
        s = self._scale
        w = self._design.width * s
        h = self._design.height * s
        pen = QPen(QColor("#e2e8f0"), 0.5)
        for i in range(0, int(w), int(10 * s)):
            self._scene.addLine(i, 0, i, h, pen)
        for i in range(0, int(h), int(10 * s)):
            self._scene.addLine(0, i, w, i, pen)

    def _add_zone_item(self, zone: SvgZone) -> ZoneGraphicsItem:
        """Aggiunge una zona alla scena."""
        item = ZoneGraphicsItem(zone, self._scale)
        self._scene.addItem(item)
        self._zone_items.append(item)
        return item

    def _refresh_zone_list(self):
        """Aggiorna la lista delle zone."""
        self._zone_list.blockSignals(True)
        self._zone_list.clear()
        for i, z in enumerate(self._design.zones):
            item = QListWidgetItem(f"{z.label} — {z.color} ({z.points}pt)")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._zone_list.addItem(item)
        self._zone_list.blockSignals(False)

    # ── Zone operations ────────────────────────────────────────────────

    def _add_zone(self, shape_type: str, x: float, y: float,
                  w: float = 40.0, h: float = 40.0):
        """Aggiunge una nuova zona al modello e alla scena."""
        label = chr(65 + len(self._design.zones))  # A, B, C, ...
        color = list(ZONE_COLORS.values())[len(self._design.zones) % len(ZONE_COLORS)]
        zone = SvgZone(
            label=label, color=color, points=5,
            shape_type=shape_type,
            x=x, y=y, width=w, height=h,
        )
        self._design.add_zone(zone)
        self._add_zone_item(zone)
        self._refresh_zone_list()
        # Seleziona l'ultima zona
        self._zone_list.setCurrentRow(len(self._design.zones) - 1)

    def _delete_selected(self):
        """Elimina la zona selezionata."""
        selected = [it for it in self._zone_items if it.isSelected()]
        for item in selected:
            if item.zone in self._design.zones:
                self._design.zones.remove(item.zone)
            self._scene.removeItem(item)
            self._zone_items.remove(item)
        self._refresh_zone_list()

    def _clear_all(self):
        """Elimina tutte le zone."""
        for item in self._zone_items:
            self._scene.removeItem(item)
        self._design.zones.clear()
        self._zone_items.clear()
        self._refresh_zone_list()

    # ── Zone properties ────────────────────────────────────────────────

    def _on_zone_selected(self, row: int):
        """Carica le proprietà della zona selezionata."""
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        self._zone_label.blockSignals(True)
        self._zone_label.setText(zone.label)
        self._zone_label.blockSignals(False)

        self._zone_color_btn.setText(f"🟩 {zone.color}")
        self._zone_color_btn.setStyleSheet(
            f"background-color: {zone.color}; color: white;"
        )

        self._zone_points.blockSignals(True)
        self._zone_points.setValue(zone.points)
        self._zone_points.blockSignals(False)

        self._zone_w.blockSignals(True)
        self._zone_w.setValue(int(zone.width))
        self._zone_w.blockSignals(False)

        self._zone_h.blockSignals(True)
        self._zone_h.setValue(int(zone.height))
        self._zone_h.blockSignals(False)

        self._zone_x.blockSignals(True)
        self._zone_x.setValue(int(zone.x))
        self._zone_x.blockSignals(False)

        self._zone_y.blockSignals(True)
        self._zone_y.setValue(int(zone.y))
        self._zone_y.blockSignals(False)

        # Seleziona l'item sulla scena
        for item in self._zone_items:
            item.setSelected(False)
        if row < len(self._zone_items):
            self._zone_items[row].setSelected(True)

    def _on_zone_prop_changed(self):
        """Aggiorna la zona selezionata con i valori correnti."""
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.label = self._zone_label.text()[:1] or "?"
        zone.points = self._zone_points.value()
        Updated = True
        if row < len(self._zone_items):
            self._zone_items[row].update_from_zone()
        self._refresh_zone_list()

    def _on_zone_size_changed(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.width = float(self._zone_w.value())
        zone.height = float(self._zone_h.value())
        if row < len(self._zone_items):
            self._zone_items[row].update_from_zone()

    def _on_zone_pos_changed(self):
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        zone.x = float(self._zone_x.value())
        zone.y = float(self._zone_y.value())
        if row < len(self._zone_items):
            self._zone_items[row].update_from_zone()

    def _pick_zone_color(self):
        """Apre il color picker per la zona selezionata."""
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._design.zones):
            return
        zone = self._design.zones[row]
        color = QColorDialog.getColor(QColor(zone.color), self, "Colore zona")
        if color.isValid():
            zone.color = color.name()
            self._zone_color_btn.setText(f"🟩 {zone.color}")
            self._zone_color_btn.setStyleSheet(
                f"background-color: {zone.color}; color: white;"
            )
            if row < len(self._zone_items):
                self._zone_items[row].update_from_zone()

    # ── Name / desc ───────────────────────────────────────────────────

    def _on_name_changed(self, text: str):
        self._design.name = text or "Bersaglio"
        self.setWindowTitle(f"Editor Bersagli SVG — {self._design.name}")

    def _on_desc_changed(self, text: str):
        self._design.description = text

    # ── Preview & Save ────────────────────────────────────────────────

    def _show_preview(self):
        """Mostra un'anteprima del bersaglio finito."""
        svg = self._design.to_svg()
        msg = QMessageBox(self)
        msg.setWindowTitle(f"Anteprima — {self._design.name}")
        msg.setText(
            f"<b>{self._design.name}</b><br><br>"
            f"<pre style='font-size:9px; color:#64748b;'>{svg[:500]}...</pre><br>"
            f"Zone: {len(self._design.zones)} | "
            f"Dimensione: {self._design.width:.0f}×{self._design.height:.0f}"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _save_svg(self):
        """Salva il bersaglio come SVG nella cartella custom."""
        ensure_custom_dir()
        name = self._design.name.strip().lower().replace(" ", "_").replace("-", "_")
        filename = f"{name}.svg"
        filepath = os.path.join(CUSTOM_TARGETS_DIR, filename)

        # Controllo sovrascrittura
        if os.path.isfile(filepath):
            reply = QMessageBox.question(
                self, "Sovrascrivere?",
                f"Il file '{filename}' esiste già. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        svg = self._design.to_svg()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(svg)

        QMessageBox.information(
            self, "Salvato",
            f"Bersaglio salvato come:\n{filepath}\n\n"
            f"Riavvia l'app per vederlo nella lista bersagli.",
        )
        self.accept()

    def get_design(self) -> SvgTargetDesign:
        return self._design
