# ui/main_window.py
from __future__ import annotations

from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QPushButton, QLabel, QStatusBar,
    QApplication, QDockWidget
)

from core.models import Stage, ItemType, StageItem
from core.generator import GeneratorConfig, GeneratorResult
from ui.editor.stage_scene import StageScene, StageItemWrapper
from ui.editor.stage_view import StageView
from ui.editor.property_dock import PropertyDock
from ui.editor.generator_panel import GeneratorPanel
from ui.workers.generator_worker import GeneratorWorker
from ui.viewer3d.quick_3d_widget import Quick3DWidget
from services.serializer import save_stage, load_stage
from services.exporter import export_png, export_pdf


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenTDS — Stage Generator")
        self.resize(1600, 950)

        self._stage = Stage(name="Stage IPSC", width=20.0, depth=15.0)
        self._setup_ui()
        self._setup_toolbar()
        self._setup_menu()
        self._setup_status_bar()
        self._connect_signals()
        self._current_worker: GeneratorWorker | None = None

        # Dati di esempio
        self._scene.add_wall(5.0, 7.0, 4.0, 0.2)
        self._scene.add_wall(12.0, 10.0, 0.2, 3.0)
        self._scene.add_target(6.0, 5.0, 0.45, 0.45, ItemType.PAPER_TARGET)
        self._scene.add_target(13.0, 8.0, 0.30, 0.30, ItemType.STEEL_TARGET)
        self._scene.add_fault_line(3.0, 10.0, 4.0)
        self._scene.add_no_shoot(6.5, 5.5, 0.45, 0.45)
        self._scene.add_barrier(10.0, 3.0, 2.0, 0.15)
        self._scene.add_door(8.0, 2.0, 0.9, 0.05)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter 2D | 3D
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Pannello 2D
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

        splitter.addWidget(panel_2d)

        # Pannello 3D
        panel_3d = QWidget()
        v3 = QVBoxLayout(panel_3d)
        v3.setContentsMargins(0, 0, 0, 0)
        v3.setSpacing(0)

        self._viewer3d = Quick3DWidget(self._stage)
        v3.addWidget(self._viewer3d)

        splitter.addWidget(panel_3d)
        splitter.setSizes([800, 800])

        # Property dock
        self._prop_dock = PropertyDock(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

        # Generator dock
        self._gen_panel = GeneratorPanel(self)
        self._gen_dock = QDockWidget("Generazione", self)
        self._gen_dock.setWidget(self._gen_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._gen_dock)
        self.tabifyDockWidget(self._gen_dock, self._prop_dock)

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

        btn_del = QPushButton("🗑 Elimina")
        btn_del.setToolTip("Elimina oggetti selezionati")
        btn_del.clicked.connect(self._scene.push_remove_selected)
        toolbar.addWidget(btn_del)

        toolbar.addSeparator()

        btn_undo = QPushButton("↩️ Undo")
        btn_undo.setToolTip("Annulla (Ctrl+Z)")
        btn_undo.clicked.connect(self._scene.undo_stack.undo)
        toolbar.addWidget(btn_undo)

        btn_redo = QPushButton("↪️ Redo")
        btn_redo.setToolTip("Ripeti (Ctrl+Shift+Z)")
        btn_redo.clicked.connect(self._scene.undo_stack.redo)
        toolbar.addWidget(btn_redo)

    def _setup_menu(self):
        from PySide6.QtWidgets import QFileDialog
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Salva Stage…", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        open_action = QAction("&Apri Stage…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_png_action = QAction("Esporta &PNG…", self)
        export_png_action.triggered.connect(self._on_export_png)
        file_menu.addAction(export_png_action)

        export_pdf_action = QAction("Esporta &PDF…", self)
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
        gen_action = QAction("&Genera Stage IPSC…", self)
        gen_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_action.triggered.connect(self._gen_dock.show)
        gen_menu.addAction(gen_action)

    def _setup_status_bar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            "Pronto — zoom rotella | drag oggetti | Ctrl+Z undo | seleziona per proprietà"
        )

    def _connect_signals(self):
        self._scene.itemAdded.connect(self._on_item_added)
        self._scene.itemUpdated.connect(self._on_item_updated)
        self._scene.itemRemoved.connect(self._on_item_removed)
        self._scene.selectionChangedWrapper.connect(self._prop_dock.set_item)
        self._prop_dock.propertyChanged.connect(self._on_property_changed)
        self._gen_panel.generateRequested.connect(self._on_generate_requested)
        self._gen_panel.stopRequested.connect(self._on_stop_requested)

    @Slot()
    def _on_item_added(self):
        self._viewer3d.refresh()

    @Slot(int)
    def _on_item_updated(self, item_id: int):
        # Se l'item aggiornato è quello selezionato, refresh dock
        wrapper = self._prop_dock._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock.set_item(wrapper)
        self._viewer3d.refresh()

    @Slot(int)
    def _on_item_removed(self, item_id: int):
        wrapper = self._prop_dock._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock.set_item(None)
        self._viewer3d.refresh()

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
        self._status.showMessage("Generazione stage in corso…")
        worker = GeneratorWorker(config)
        worker.signals.finished.connect(self._on_generation_finished)
        worker.signals.error.connect(self._on_generation_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot()
    def _on_stop_requested(self):
        # Non c'è un modo clean di fermare un QRunnable in corso
        # Il worker finirà naturalmente in pochi ms
        self._status.showMessage("Generazione interrotta")
        self._gen_panel.on_generation_finished()

    @Slot(object)
    def _on_generation_finished(self, result: object):
        result: GeneratorResult = result  # type: ignore
        self._status.showMessage(
            f"Stage generato! Score: {result.score} | Tentativi: {result.attempts} | Bersagli: {len(result.stage.items)}"
        )
        # Sostituisci lo stage nell'editor
        self._replace_stage(result.stage)
        self._gen_panel.on_generation_finished()
        self._current_worker = None

    @Slot(str)
    def _on_generation_error(self, message: str):
        self._status.showMessage(f"Errore generazione: {message}")
        self._gen_panel.on_generation_error(message)
        self._current_worker = None

    def _replace_stage(self, new_stage: Stage):
        """Sostituisce lo stage corrente con uno nuovo, aggiornando editor e 3D."""
        # Pulisci scene
        self._scene.clear()
        self._stage = new_stage
        self._scene.stage = new_stage
        self._scene._items.clear()
        self._scene._setup_grid()
        self._scene._sync_from_model()
        # Aggiorna 3D
        self._viewer3d.update_dimensions(new_stage.width, new_stage.depth)
        self._viewer3d.refresh()
        # Reset property dock
        self._prop_dock.set_item(None)
