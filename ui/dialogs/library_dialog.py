"""
Library browser dialog for OpenTDS.

Allows browsing, searching, loading, importing, and managing
predefined and user-saved stages.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QFileDialog, QMessageBox,
    QFrame, QSizePolicy, QWidget,
)

from services.library import StageLibrary, LibraryEntry


class LibraryDialog(QDialog):
    """Dialog for browsing and loading stages from the library."""

    def __init__(self, library: StageLibrary, parent=None):
        super().__init__(parent)
        self._library = library
        self._selected_entry: Optional[LibraryEntry] = None

        self.setWindowTitle("Libreria Stage — OpenTDS")
        self.setMinimumSize(750, 500)
        self.resize(800, 550)
        self._setup_ui()
        self._refresh()

    @property
    def selected_entry(self) -> Optional[LibraryEntry]:
        return self._selected_entry

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        title = QLabel("📚 Libreria Stage")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Stage predefiniti e salvati dall'utente. "
            "Seleziona uno stage per caricarlo nell'editor."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Cerca stage per nome, descrizione o tag...")
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input, 1)

        self._filter_predefined = QPushButton("Predefiniti")
        self._filter_predefined.setCheckable(True)
        self._filter_predefined.clicked.connect(self._on_filter)
        search_layout.addWidget(self._filter_predefined)

        btn_import = QPushButton("📥 Importa...")
        btn_import.clicked.connect(self._on_import)
        search_layout.addWidget(btn_import)

        layout.addLayout(search_layout)

        # Split: list + preview
        split_layout = QHBoxLayout()
        split_layout.setSpacing(12)

        # Left: list
        self._list = QListWidget()
        self._list.setMinimumWidth(300)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._on_load)
        split_layout.addWidget(self._list, 1)

        # Right: preview
        preview_frame = QFrame()
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(8)

        self._preview_title = QLabel("Nessuno stage selezionato")
        self._preview_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #0f172a;")
        self._preview_title.setWordWrap(True)
        preview_layout.addWidget(self._preview_title)

        self._preview_desc = QLabel("")
        self._preview_desc.setStyleSheet("font-size: 12px; color: #475569;")
        self._preview_desc.setWordWrap(True)
        preview_layout.addWidget(self._preview_desc)

        # Info grid
        info_style = "font-size: 12px; color: #64748b;"
        self._preview_course = QLabel("")
        self._preview_course.setStyleSheet(info_style)
        preview_layout.addWidget(self._preview_course)

        self._preview_size = QLabel("")
        self._preview_size.setStyleSheet(info_style)
        preview_layout.addWidget(self._preview_size)

        self._preview_targets = QLabel("")
        self._preview_targets.setStyleSheet(info_style)
        preview_layout.addWidget(self._preview_targets)

        self._preview_rounds = QLabel("")
        self._preview_rounds.setStyleSheet(info_style)
        preview_layout.addWidget(self._preview_rounds)

        self._preview_tags = QLabel("")
        self._preview_tags.setStyleSheet(info_style)
        preview_layout.addWidget(self._preview_tags)

        preview_layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._btn_load = QPushButton("📂 Carica stage")
        self._btn_load.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; color: white;
                border: none; padding: 10px 24px;
                border-radius: 8px; font-weight: 600;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self._btn_load.clicked.connect(self._on_load)
        self._btn_load.setEnabled(False)
        btn_layout.addWidget(self._btn_load)

        btn_export = QPushButton("📤 Esporta...")
        btn_export.clicked.connect(self._on_export)
        btn_layout.addWidget(btn_export)

        self._btn_delete = QPushButton("🗑️ Elimina")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)
        btn_layout.addWidget(self._btn_delete)

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        preview_layout.addLayout(btn_layout)

        split_layout.addWidget(preview_frame, 1)
        layout.addLayout(split_layout, 1)

    # ── Handlers ───────────────────────────────────────────────────────

    def _refresh(self, query: str = "", tag_filter: str = ""):
        """Refresh the list from the library."""
        self._list.blockSignals(True)
        self._list.clear()

        entries = self._library.search(query=query)
        if tag_filter:
            entries = [e for e in entries if tag_filter in e.tags]

        for entry in entries:
            icon = "📄" if entry.is_predefined else "💾"
            text = f"{icon} {entry.name}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            if entry.is_predefined:
                item.setForeground(QColor("#2563eb"))
            self._list.addItem(item)

        self._list.blockSignals(False)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._clear_preview()

    def _clear_preview(self):
        self._preview_title.setText("Nessuno stage trovato")
        self._preview_desc.setText("")
        self._preview_course.setText("")
        self._preview_size.setText("")
        self._preview_targets.setText("")
        self._preview_rounds.setText("")
        self._preview_tags.setText("")
        self._btn_load.setEnabled(False)
        self._btn_delete.setEnabled(False)

    def _show_preview(self, entry: LibraryEntry):
        self._preview_title.setText(entry.name)
        desc = entry.description or "Nessuna descrizione"
        self._preview_desc.setText(desc)
        self._preview_course.setText(f"🏷️ Tipo corso: {entry.course_type or 'Non specificato'}")
        self._preview_size.setText(f"📐 Dimensioni: {entry.width:.0f}×{entry.depth:.0f} m")
        self._preview_targets.setText(f"🎯 Bersagli: {entry.target_count}")
        self._preview_rounds.setText(f"🔫 Colpi: {entry.round_count}")
        self._preview_tags.setText(f"🏷️ Tag: {', '.join(entry.tags) if entry.tags else '—'}")
        self._btn_load.setEnabled(True)
        self._btn_delete.setEnabled(not entry.is_predefined)

    @Slot()
    def _on_search(self):
        query = self._search_input.text()
        tag_filter = "predefinito" if self._filter_predefined.isChecked() else ""
        self._refresh(query, tag_filter)

    @Slot()
    def _on_filter(self):
        self._on_search()

    @Slot(int)
    def _on_selection_changed(self, row: int):
        if row < 0:
            self._clear_preview()
            return
        item = self._list.item(row)
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self._library.get(entry_id)
        if entry:
            self._show_preview(entry)

    @Slot()
    def _on_load(self):
        """Load selected stage and close dialog."""
        item = self._list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self._library.get(entry_id)
        if entry:
            self._selected_entry = entry
            self.accept()

    @Slot()
    def _on_import(self):
        """Import a .opentds or .json file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa Stage", "",
            "Stage OpenTDS (*.opentds *.json);;Tutti i file (*)",
        )
        if path:
            entry = self._library.import_from_file(Path(path))
            if entry:
                self._refresh()
                QMessageBox.information(
                    self, "Importato",
                    f"Stage '{entry.name}' importato con successo!",
                )
            else:
                QMessageBox.warning(
                    self, "Errore",
                    "Impossibile importare il file. Verifica che sia un formato valido.",
                )

    @Slot()
    def _on_export(self):
        """Export selected stage to file."""
        item = self._list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self._library.get(entry_id)
        if not entry:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta Stage", entry.filename or f"{entry.id}.opentds",
            "Stage OpenTDS (*.opentds);;JSON (*.json)",
        )
        if path:
            if self._library.export_to_file(entry_id, Path(path)):
                QMessageBox.information(
                    self, "Esportato",
                    f"Stage '{entry.name}' esportato con successo!",
                )
            else:
                QMessageBox.warning(self, "Errore", "Esportazione fallita.")

    @Slot()
    def _on_delete(self):
        """Delete selected user-saved stage."""
        item = self._list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self._library.get(entry_id)
        if not entry or entry.is_predefined:
            return
        reply = QMessageBox.question(
            self, "Conferma eliminazione",
            f"Eliminare '{entry.name}' dalla libreria?\nQuesta operazione non può essere annullata.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._library.delete_entry(entry_id)
            self._refresh()
