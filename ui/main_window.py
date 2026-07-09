# ui/main_window.py
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QPushButton, QLabel, QStatusBar,
    QApplication, QDockWidget
)

from core.models import Stage, ItemType
from core.generator import GeneratorConfig, GeneratorResult
from ui.editor.stage_scene import StageScene, StageItemWrapper
from ui.editor.stage_view import StageView
from ui.editor.property_dock import PropertyDock
from ui.editor.generator_panel import GeneratorPanel
from ui.editor.stage_info import StageInfoPanel
from ui.viewer3d.quick_3d_widget import Quick3DWidget
from ui.workers.generator_worker import GeneratorWorker
from services.serializer import save_stage, load_stage
from services.exporter import export_png, export_pdf


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenTDS — Stage Generator")
        self.resize(1200, 850)

        self._stage = Stage(name="Stage IPSC", width=20.0, depth=15.0)
        self._setup_ui()
        self._setup_toolbar()
        self._setup_menu()
        self._setup_status_bar()
        self._connect_signals()
        self._current_worker: GeneratorWorker | None = None

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self._ui_layout = QHBoxLayout(central)
        self._ui_layout.setContentsMargins(0, 0, 0, 0)
        self._ui_layout.setSpacing(0)

        # Pannello editor 2D (sinistra)
        panel_2d = QWidget()
        v2 = QVBoxLayout(panel_2d)
        v2.setContentsMargins(8, 8, 8, 8)
        v2.setSpacing(6)

        header_2d = QLabel("Editor 2D (m)")
        header_2d.setStyleSheet("font-weight: 600; font-size: 14px; color: #0f172a;")
        v2.addWidget(header_2d)

        self._scene = StageScene(self._stage)
        self._view = StageView(self._scene)
        v2.addWidget(self._view)

        self._panel_2d = panel_2d
        self._ui_layout.addWidget(self._panel_2d)

        # Viewer 3D (a destra, inizialmente nascosto)
        self._viewer_3d = Quick3DWidget(self._stage)
        self._viewer_3d.setMinimumWidth(400)
        self._viewer_3d.setVisible(False)
        self._ui_layout.addWidget(self._viewer_3d)

        # Info dock (sinistra)
        self._info_panel = StageInfoPanel()
        self._info_dock = QDockWidget("Info Stage", self)
        self._info_dock.setWidget(self._info_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._info_dock)

        # Property dock (destra)
        self._prop_dock = PropertyDock(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

        # Generator dock (raggruppato con info a sinistra)
        self._gen_panel = GeneratorPanel(self)
        self._gen_dock = QDockWidget("Generazione", self)
        self._gen_dock.setWidget(self._gen_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._gen_dock)
        self.tabifyDockWidget(self._info_dock, self._gen_dock)

    def _setup_toolbar(self):
        toolbar = QToolBar("Strumenti")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        def _btn(text, tip, callback):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(callback)
            return b

        cx, cy = self._stage.width / 2, self._stage.depth / 2

        toolbar.addWidget(_btn("+ Muro", "Aggiungi muro",
            lambda: self._scene.add_wall(cx, cy, 3.0, 0.2)))
        toolbar.addWidget(_btn("+ Paper", "Aggiungi bersaglio cartaceo",
            lambda: self._scene.add_target(cx + 1, cy, 0.45, 0.45, ItemType.PAPER_TARGET)))
        toolbar.addWidget(_btn("+ Steel", "Aggiungi bersaglio metallico",
            lambda: self._scene.add_target(cx - 1, cy, 0.30, 0.30, ItemType.STEEL_TARGET)))
        toolbar.addWidget(_btn("+ Fault", "Aggiungi fault line",
            lambda: self._scene.add_fault_line(cx, cy + 2, 3.0)))
        toolbar.addWidget(_btn("+ NS", "Aggiungi no-shoot",
            lambda: self._scene.add_no_shoot(cx + 0.5, cy + 0.5, 0.45, 0.45)))
        toolbar.addWidget(_btn("+ Barriera", "Aggiungi barriera",
            lambda: self._scene.add_barrier(cx, cy - 1, 2.0, 0.15)))
        toolbar.addWidget(_btn("+ Porta", "Aggiungi porta",
            lambda: self._scene.add_door(cx, cy - 2, 0.9, 0.05)))
        toolbar.addWidget(_btn("+ Swinger", "Aggiungi swinger",
            lambda: self._scene.add_swinger(cx + 1.5, cy)))
        toolbar.addWidget(_btn("+ Drop", "Aggiungi drop turner",
            lambda: self._scene.add_drop_turner(cx - 1.5, cy)))
        toolbar.addWidget(_btn("+ Mover", "Aggiungi mover",
            lambda: self._scene.add_mover(cx, cy + 2.5)))

        toolbar.addSeparator()

        # Toggle 3D viewer
        self._btn_3d = QPushButton("🎮 3D")
        self._btn_3d.setToolTip("Mostra/nascondi viewer 3D")
        self._btn_3d.setCheckable(True)
        self._btn_3d.toggled.connect(self._toggle_3d_view)
        toolbar.addWidget(self._btn_3d)

        toolbar.addSeparator()

        btn_del = QPushButton("\U0001f5d1 Elimina")
        btn_del.setToolTip("Elimina oggetti selezionati")
        btn_del.clicked.connect(self._scene.push_remove_selected)
        toolbar.addWidget(btn_del)

        toolbar.addSeparator()

        btn_undo = QPushButton("\u21a9\ufe0f Undo")
        btn_undo.setToolTip("Annulla (Ctrl+Z)")
        btn_undo.clicked.connect(self._scene.undo_stack.undo)
        toolbar.addWidget(btn_undo)

        btn_redo = QPushButton("\u21aa\ufe0f Redo")
        btn_redo.setToolTip("Ripeti (Ctrl+Shift+Z)")
        btn_redo.clicked.connect(self._scene.undo_stack.redo)
        toolbar.addWidget(btn_redo)

    def _setup_menu(self):
        from PySide6.QtWidgets import QFileDialog
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Salva Stage\u2026", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        open_action = QAction("&Apri Stage\u2026", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_png_action = QAction("Esporta &PNG\u2026", self)
        export_png_action.triggered.connect(self._on_export_png)
        file_menu.addAction(export_png_action)

        export_pdf_action = QAction("Esporta &PDF\u2026", self)
        export_pdf_action.triggered.connect(self._on_export_pdf)
        file_menu.addAction(export_pdf_action)

        file_menu.addSeparator()

        exit_action = QAction("&Esci", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("&Modifica")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(self._scene.undo_stack.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_action.triggered.connect(self._scene.undo_stack.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        del_action = QAction("&Elimina selezionati", self)
        del_action.setShortcut(QKeySequence.Delete)
        del_action.triggered.connect(self._scene.push_remove_selected)
        edit_menu.addAction(del_action)

        gen_menu = menubar.addMenu("&Genera")
        gen_action = QAction("&Genera Stage IPSC\u2026", self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._gen_dock.show)
        gen_menu.addAction(gen_action)

    def _setup_status_bar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            "Pronto \u2014 zoom rotella | drag oggetti | Ctrl+Z undo | seleziona per propriet\u00e0"
        )

    def _connect_signals(self):
        self._scene.itemAdded.connect(self._on_item_added)
        self._scene.itemUpdated.connect(self._on_item_updated)
        self._scene.itemRemoved.connect(self._on_item_removed)
        self._scene.selectionChangedWrapper.connect(self._prop_dock.set_item)
        self._prop_dock.propertyChanged.connect(self._on_property_changed)
        self._gen_panel.generateRequested.connect(self._on_generate_requested)
        self._gen_panel.stopRequested.connect(self._on_stop_requested)
        # Sincronizzazione 2D → 3D e Info
        self._scene.itemAdded.connect(self._refresh_3d)
        self._scene.itemUpdated.connect(self._refresh_3d)
        self._scene.itemRemoved.connect(self._refresh_3d)
        self._scene.itemAdded.connect(self._refresh_info)
        self._scene.itemUpdated.connect(self._refresh_info)
        self._scene.itemRemoved.connect(self._refresh_info)

    @Slot(StageItemWrapper)
    def _on_item_added(self, _wrapper):
        pass

    @Slot(int)
    def _on_item_updated(self, item_id: int):
        wrapper = self._prop_dock._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock.set_item(wrapper)

    @Slot(int)
    def _on_item_removed(self, item_id: int):
        wrapper = self._prop_dock._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock.set_item(None)

    @Slot(int, dict)
    def _on_property_changed(self, item_id: int, props: dict):
        self._scene.update_item_from_properties(item_id, **props)

    def _on_save(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Salva Stage", "stage.json", "JSON (*.json)")
        if path:
            save_stage(self._stage, Path(path))
            self._status.showMessage(f"Stage salvato: {path}")

    def _on_open(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Apri Stage", "", "JSON (*.json)")
        if path:
            new_stage = load_stage(Path(path))
            self._replace_stage(new_stage)
            self._status.showMessage(f"Stage caricato: {path}")

    def _on_export_png(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Esporta PNG", "stage.png", "PNG (*.png)")
        if path:
            export_png(self._scene, Path(path))
            self._status.showMessage(f"PNG esportato: {path}")

    def _on_export_pdf(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Esporta PDF", "stage.pdf", "PDF (*.pdf)")
        if path:
            export_pdf(self._stage, self._scene, Path(path))
            self._status.showMessage(f"PDF esportato: {path}")

    @Slot(GeneratorConfig)
    def _on_generate_requested(self, config: GeneratorConfig):
        self._status.showMessage("Generazione stage in corso\u2026")
        worker = GeneratorWorker(config)
        worker.signals.finished.connect(self._on_generation_finished)
        worker.signals.error.connect(self._on_generation_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot()
    def _on_stop_requested(self):
        self._status.showMessage("Generazione interrotta")
        self._gen_panel.on_generation_finished()

    @Slot(object)
    def _on_generation_finished(self, result: object):
        result: GeneratorResult = result
        self._status.showMessage(
            f"Stage generato! Score: {result.score} | Tentativi: {result.attempts} | Bersagli: {len(result.stage.items)}"
        )
        self._replace_stage(result.stage)
        self._gen_panel.on_generation_finished()
        self._current_worker = None

    @Slot(str)
    def _on_generation_error(self, message: str):
        self._status.showMessage(f"Errore generazione: {message}")
        self._gen_panel.on_generation_error(message)
        self._current_worker = None

    @Slot(bool)
    def _toggle_3d_view(self, visible: bool):
        """Mostra/nasconde il viewer 3D nella UI."""
        self._viewer_3d.setVisible(visible)
        if visible:
            self._viewer_3d.refresh()
            self._viewer_3d.reset_camera()
            self._status.showMessage("Vista 3D attivata — drag orbita | WASD pan | F11 fullscreen")
        else:
            self._status.showMessage("Vista 3D disattivata")

    @Slot()
    def _refresh_3d(self):
        """Aggiorna la vista 3D dopo cambiamenti nell'editor 2D."""
        if self._viewer_3d.isVisible():
            self._viewer_3d.refresh()

    @Slot()
    def _refresh_info(self):
        """Aggiorna il pannello Info Stage."""
        self._info_panel.set_stage(self._stage)

    def _replace_stage(self, new_stage: Stage):
        """Sostituisce lo stage nell'editor 2D, 3D e Info."""
        self._scene.clear()
        self._stage.name = new_stage.name
        self._stage.width = new_stage.width
        self._stage.depth = new_stage.depth
        self._stage.items.clear()
        self._stage._next_id = new_stage._next_id
        for it in new_stage.items:
            self._stage.items.append(it)
        self._scene.stage = self._stage
        self._scene._items.clear()
        self._scene._setup_grid()
        self._scene._sync_from_model()
        self._prop_dock.set_item(None)
        # Aggiorna viewer 3D e Info
        self._viewer_3d.update_dimensions(self._stage.width, self._stage.depth)
        self._refresh_info()
