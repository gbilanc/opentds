"""
Pannello informativo con statistiche e violazioni IPSC in tempo reale.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QGridLayout, QSizePolicy,
)

from core.models import Stage, ItemType
from core.ipsc_rules import IPSCRulesEngine


class StageInfoPanel(QWidget):
    """Pannello laterale che mostra statistiche e violazioni IPSC live."""
    violationsUpdated = Signal(set)  # emette set[int] di ID item con violazioni

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: IPSCRulesEngine | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Titolo
        title = QLabel("📊 Info Stage")
        title.setStyleSheet("font-weight: 700; font-size: 15px; color: #0f172a;")
        layout.addWidget(title)

        # Statistiche
        stats_title = QLabel("Statistiche")
        stats_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #475569;")
        layout.addWidget(stats_title)

        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(4)
        self._stats_labels: dict[str, QLabel] = {}
        stats_items = [
            ("Dimensioni", "— × — m"),
            ("Area", "— m²"),
            ("Oggetti", "—"),
            ("Paper", "—"),
            ("Steel", "—"),
            ("Mobili", "—"),
            ("No-Shoot", "—"),
            ("Muri", "—"),
            ("Barriere", "—"),
            ("Pos. tiro", "—"),
        ]
        for i, (label, default) in enumerate(stats_items):
            row_label = QLabel(label)
            row_label.setStyleSheet("font-size: 11px; color: #64748b;")
            row_value = QLabel(default)
            row_value.setStyleSheet("font-size: 11px; font-weight: 600; color: #0f172a;")
            row_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._stats_grid.addWidget(row_label, i, 0)
            self._stats_grid.addWidget(row_value, i, 1)
            self._stats_labels[label] = row_value
        layout.addLayout(self._stats_grid)

        layout.addSpacing(8)

        # Violazioni
        viol_title = QLabel("Violazioni IPSC")
        viol_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #475569;")
        layout.addWidget(viol_title)

        self._violations_area = QScrollArea()
        self._violations_area.setWidgetResizable(True)
        self._violations_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
        """)
        self._violations_container = QWidget()
        self._violations_layout = QVBoxLayout(self._violations_container)
        self._violations_layout.setSpacing(4)
        self._violations_layout.setContentsMargins(0, 0, 0, 0)
        self._violations_area.setWidget(self._violations_container)
        layout.addWidget(self._violations_area, 1)

        # Label nessuna violazione
        self._no_violations = QLabel("✅ Nessuna violazione")
        self._no_violations.setStyleSheet("font-size: 11px; color: #16a34a; padding: 8px;")
        self._violations_layout.addWidget(self._no_violations)

    def set_stage(self, stage: Stage):
        """Aggiorna le info con un nuovo stage."""
        self._engine = IPSCRulesEngine(stage)
        self.refresh()

    def refresh(self):
        """Ricalcola statistiche e violazioni."""
        if self._engine is None:
            return

        stage = self._engine.stage
        counts = self._engine.count_targets()

        # Statistiche
        self._stats_labels["Dimensioni"].setText(
            f"{stage.width:.1f} × {stage.depth:.1f} m")
        self._stats_labels["Area"].setText(
            f"{stage.width * stage.depth:.0f} m²")
        self._stats_labels["Oggetti"].setText(
            str(len(stage.items)))
        self._stats_labels["Paper"].setText(
            str(counts["paper"]))
        self._stats_labels["Steel"].setText(
            str(counts["steel"]))
        self._stats_labels["Mobili"].setText(
            str(counts["moving"]))
        self._stats_labels["No-Shoot"].setText(
            str(counts["no_shoots"]))
        self._stats_labels["Muri"].setText(
            str(sum(1 for it in stage.items if it.item_type == ItemType.WALL)))
        self._stats_labels["Barriere"].setText(
            str(sum(1 for it in stage.items if it.item_type == ItemType.BARRIER)))
        self._stats_labels["Pos. tiro"].setText(
            str(len(stage.shooting_positions)))

        # Violazioni
        result = self._engine.validate()
        self._show_violations(result.violations)

        # Estrai ID item coinvolti in violazioni e notifica la scena
        import re
        viol_ids: set[int] = set()
        for v_text in result.violations:
            for m in re.finditer(r'#(\d+)', v_text):
                viol_ids.add(int(m.group(1)))
        self.violationsUpdated.emit(viol_ids)

    def _show_violations(self, violations: list[str]):
        """Mostra o aggiorna le violazioni nella scroll area."""
        # Pulisce violazioni esistenti
        for i in reversed(range(self._violations_layout.count())):
            widget = self._violations_layout.itemAt(i).widget()
            if widget and widget is not self._no_violations:
                self._violations_layout.removeWidget(widget)
                widget.deleteLater()

        if not violations:
            self._no_violations.show()
            return

        self._no_violations.hide()

        for v in violations:
            label = QLabel(f"⚠️ {v}")
            label.setWordWrap(True)
            label.setStyleSheet("""
                font-size: 10px;
                color: #dc2626;
                background-color: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 4px;
                padding: 6px 8px;
            """)
            self._violations_layout.addWidget(label)

        self._violations_layout.addStretch()
