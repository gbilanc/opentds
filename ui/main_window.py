# ui/main_window.py
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QPushButton, QLabel, QStatusBar,
    QApplication, QDockWidget
)

from core.models import Stage, ItemType
from core.generator import GeneratorConfig, Phase1Config, Phase2Config, GeneratorResult, StageGenerator
from ui.editor.stage_scene import StageScene, StageItemWrapper
from ui.editor.stage_view import StageView
from ui.editor.property_dock import PropertyDock
from ui.editor.generator_panel import GeneratorPanel
from ui.editor.stage_info import StageInfoPanel
from ui.workers.generator_worker import GeneratorWorker, Phase2Worker
from services.serializer import save_stage, load_stage
from services.exporter import export_png, export_pdf
from services.openscad_exporter import (
    export_scad,
    render_scad_to_png,
    render_scad_to_stl,
    render_scad_to_3mf,
    openscad_available,
    ScadExportOptions,
)
from services.blender_exporter import (
    export_via_subprocess,
    export_via_subprocess_and_open,
    blender_available,
    get_blender_path,
)
from ui.dialogs.target_config_dialog import TargetConfigDialog


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
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        v2.addWidget(self._view)

        self._panel_2d = panel_2d
        self._ui_layout.addWidget(self._panel_2d)

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

        btn_del = QPushButton("\U0001f5d1 Elimina")
        btn_del.setToolTip("Elimina oggetti selezionati")
        btn_del.clicked.connect(self._scene.push_remove_selected)
        toolbar.addWidget(btn_del)

        toolbar.addSeparator()

        btn_validate = QPushButton("\u2705 Valida")
        btn_validate.setToolTip("Valida lo stage con IPSCRulesEngine")
        btn_validate.clicked.connect(self._on_validate)
        toolbar.addWidget(btn_validate)

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

        # ── OpenSCAD Export ──
        export_scad_action = QAction("OpenSCAD (&.scad)\u2026", self)
        export_scad_action.triggered.connect(self._on_export_scad)
        file_menu.addAction(export_scad_action)

        self._has_openscad = openscad_available()
        if self._has_openscad:
            export_scad_png_action = QAction("Rendering OpenSCAD (&PNG)\u2026", self)
            export_scad_png_action.triggered.connect(self._on_export_scad_png)
            file_menu.addAction(export_scad_png_action)

            export_stl_action = QAction("STL 3D (&.stl)\u2026", self)
            export_stl_action.triggered.connect(self._on_export_stl)
            file_menu.addAction(export_stl_action)

            export_3mf_action = QAction("3MF (&.3mf)\u2026", self)
            export_3mf_action.triggered.connect(self._on_export_3mf)
            file_menu.addAction(export_3mf_action)

        # ── Blender Export ──
        file_menu.addSeparator()

        export_blend_action = QAction("Blender (&.blend)…", self)
        export_blend_action.setShortcut(QKeySequence("Ctrl+Shift+B"))
        export_blend_action.triggered.connect(self._on_export_blend)
        file_menu.addAction(export_blend_action)

        self._has_blender = blender_available()
        if self._has_blender:
            open_blender_action = QAction("&Apri in Blender…", self)
            open_blender_action.setShortcut(QKeySequence("Ctrl+B"))
            open_blender_action.triggered.connect(self._on_open_in_blender)
            file_menu.addAction(open_blender_action)

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

        # ── Configurazione ──
        config_menu = menubar.addMenu("&Configurazione")

        target_appearance_action = QAction("&Aspetto Bersagli…", self)
        target_appearance_action.triggered.connect(self._on_target_config)
        config_menu.addAction(target_appearance_action)

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
        self._gen_panel.phase1Requested.connect(self._on_phase1_requested)
        self._gen_panel.phase2Requested.connect(self._on_phase2_requested)
        self._gen_panel.stopRequested.connect(self._on_stop_requested)
        self._view.shootingPositionPlaced.connect(self._on_shooting_position_placed)
        self._view.obstaclePlaced.connect(self._on_obstacle_placed)
        self._gen_panel.placeModeToggled.connect(self._view.set_placing_position_mode)
        self._gen_panel.placeObstacleModeToggled.connect(self._on_obstacle_mode_toggled)
        # Sincronizzazione → Info
        self._scene.itemAdded.connect(self._refresh_info)
        self._scene.itemUpdated.connect(self._refresh_info)
        self._scene.itemRemoved.connect(self._refresh_info)
        # Evidenziazione violazioni
        self._info_panel.violationsUpdated.connect(self._scene.set_violations)

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

    def _on_target_config(self):
        """Apre il dialog di configurazione aspetto bersagli."""
        dialog = TargetConfigDialog(self)
        if dialog.exec():
            self._scene.reload_all_targets()

    @Slot()
    def _on_validate(self):
        """Esegue validazione IPSC e mostra risultati in Info panel."""
        from core.ipsc_rules import IPSCRulesEngine
        engine = IPSCRulesEngine(self._stage)
        result = engine.validate()
        n_violations = len(result.violations)
        if n_violations == 0:
            msg = "✅ Stage valido — nessuna violazione IPSC"
            self._status.setStyleSheet("color: #16a34a;")
        else:
            msg = f"⚠️ {n_violations} violazion{'i' if n_violations != 1 else 'e'} IPSC"
            self._status.setStyleSheet("color: #dc2626;")
        self._status.showMessage(msg)
        self._refresh_info()

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

    # ── OpenSCAD Export ──────────────────────────────────────────────────

    def _on_export_scad(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta OpenSCAD", "stage.scad", "OpenSCAD (*.scad)"
        )
        if path:
            opts = ScadExportOptions()
            export_scad(self._stage, Path(path), opts)
            self._status.showMessage(f"OpenSCAD esportato: {path}")

    def _on_export_scad_png(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        if not self._has_openscad:
            QMessageBox.warning(self, "OpenSCAD non trovato",
                                "Installa OpenSCAD per il rendering automatico:\n"
                                "  sudo apt install openscad  # Linux\n"
                                "  brew install openscad      # macOS")
            return
        # Prima salva .scad temporaneo
        scad_path = Path("__openscad_export_temp.scad")
        try:
            opts = ScadExportOptions()
            export_scad(self._stage, scad_path, opts)
            png_path, _ = QFileDialog.getSaveFileName(
                self, "Salva rendering OpenSCAD", "stage.png", "PNG (*.png)"
            )
            if png_path:
                self._status.showMessage("Rendering OpenSCAD in corso...")
                result = render_scad_to_png(scad_path, Path(png_path))
                if result:
                    self._status.showMessage(f"Rendering OpenSCAD salvato: {png_path}")
                else:
                    self._status.showMessage("Rendering OpenSCAD fallito")
        finally:
            if scad_path.exists():
                scad_path.unlink()

    def _on_export_stl(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        if not self._has_openscad:
            QMessageBox.warning(self, "OpenSCAD non trovato",
                                "Installa OpenSCAD per l'esportazione STL.")
            return
        scad_path = Path("__openscad_export_temp.scad")
        try:
            opts = ScadExportOptions(scale_for_3d_print=True)
            export_scad(self._stage, scad_path, opts)
            stl_path, _ = QFileDialog.getSaveFileName(
                self, "Salva STL 3D", "stage.stl", "STL (*.stl)"
            )
            if stl_path:
                self._status.showMessage("Esportazione STL in corso...")
                result = render_scad_to_stl(scad_path, Path(stl_path))
                if result:
                    self._status.showMessage(f"STL esportato: {stl_path}")
                else:
                    self._status.showMessage("Esportazione STL fallita")
        finally:
            if scad_path.exists():
                scad_path.unlink()

    def _on_export_3mf(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        if not self._has_openscad:
            QMessageBox.warning(self, "OpenSCAD non trovato",
                                "Installa OpenSCAD per l'esportazione 3MF.")
            return
        scad_path = Path("__openscad_export_temp.scad")
        try:
            opts = ScadExportOptions(scale_for_3d_print=True)
            export_scad(self._stage, scad_path, opts)
            threemf_path, _ = QFileDialog.getSaveFileName(
                self, "Salva 3MF", "stage.3mf", "3MF (*.3mf)"
            )
            if threemf_path:
                self._status.showMessage("Esportazione 3MF in corso...")
                result = render_scad_to_3mf(scad_path, Path(threemf_path))
                if result:
                    self._status.showMessage(f"3MF esportato: {threemf_path}")
                else:
                    self._status.showMessage("Esportazione 3MF fallita")
        finally:
            if scad_path.exists():
                scad_path.unlink()

    # ── Blender Export ──────────────────────────────────────────────────

    @Slot()
    def _on_export_blend(self):
        """Esporta lo stage in un file .blend."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        if not get_blender_path():
            QMessageBox.warning(
                self, "Blender non trovato",
                "Blender non è installato o non è nel PATH.\n"
                "Installa Blender 5.2+ per esportare in .blend."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta in Blender", "stage.blend", "Blender (*.blend)"
        )
        if path:
            self._status.showMessage("Esportazione in Blender in corso...")
            try:
                export_via_subprocess(self._stage, Path(path))
                self._status.showMessage(f"✅ Blender esportato: {path}")
            except Exception as e:
                self._status.showMessage(f"❌ Errore esportazione Blender: {e}")
                QMessageBox.critical(self, "Errore", str(e))

    @Slot()
    def _on_open_in_blender(self):
        """Esporta lo stage in un file .blend temporaneo e lo apre in Blender."""
        from PySide6.QtWidgets import QMessageBox

        if not get_blender_path():
            QMessageBox.warning(
                self, "Blender non trovato",
                "Blender non è installato o non è nel PATH.\n"
                "Installa Blender 5.2+ per aprire in Blender."
            )
            return

        self._status.showMessage("Avvio Blender in corso...")
        try:
            output = Path("__opentds_blender_export.blend")
            export_via_subprocess_and_open(self._stage, output)
            self._status.showMessage(f"✅ Blender avviato con stage esportato")
        except Exception as e:
            self._status.showMessage(f"❌ Errore apertura Blender: {e}")
            QMessageBox.critical(self, "Errore", str(e))

    @Slot(Phase1Config)
    def _on_phase1_requested(self, phase1: Phase1Config):
        """Esegue la Fase 1: generazione area di tiro (sul thread principale)."""
        self._status.showMessage("Generazione area di tiro...")
        try:
            stage, poly = StageGenerator.generate_perimeter(phase1)
            self._replace_stage(stage)
            self._current_poly = poly
            self._gen_panel.on_phase1_complete(stage.name)
            self._status.showMessage("\u2705 Area di tiro generata")
        except Exception as e:
            self._gen_panel.on_phase1_error(str(e))
            self._status.showMessage(f"\u274c Errore Fase 1: {e}")

    @Slot(Phase2Config)
    def _on_phase2_requested(self, phase2: Phase2Config):
        """Esegue la Fase 2: posizionamento bersagli/ostacoli (in thread separato)."""
        poly = getattr(self, '_current_poly', None)
        if not poly:
            poly = self._stage.properties.get("perimeter_poly")
            if not poly:
                self._gen_panel.on_phase2_error(
                    "Nessuna area di tiro definita. Torna alla Fase 1.")
                return
            self._current_poly = poly

        self._status.showMessage("Posizionamento bersagli e barriere...")
        self._show_generating_dialog()
        worker = Phase2Worker(self._stage, phase2, self._current_poly)
        worker.signals.finished.connect(self._on_phase2_finished)
        worker.signals.error.connect(self._on_phase2_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot(GeneratorConfig)
    def _on_generate_requested(self, config: GeneratorConfig):
        self._status.showMessage("Generazione stage in corso\u2026")
        self._show_generating_dialog()
        worker = GeneratorWorker(config)
        worker.signals.finished.connect(self._on_generation_finished)
        worker.signals.error.connect(self._on_generation_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _show_generating_dialog(self):
        """Mostra un dialog modale che indica la generazione in corso."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
        dlg = QDialog(self)
        dlg.setWindowTitle("Generazione Stage")
        dlg.setFixedSize(320, 100)
        dlg.setModal(True)
        dlg.setWindowFlags(
            dlg.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        lbl = QLabel("Generazione stage IPSC in corso...")
        lbl.setStyleSheet("font-size: 13px; color: #0f172a;")
        layout.addWidget(lbl)
        progress = QProgressBar()
        progress.setRange(0, 0)  # indeterminato
        progress.setFixedHeight(20)
        layout.addWidget(progress)
        self._gen_dialog = dlg
        dlg.show()

    def _hide_generating_dialog(self):
        if hasattr(self, '_gen_dialog') and self._gen_dialog is not None:
            self._gen_dialog.close()
            self._gen_dialog = None

    @Slot()
    def _on_stop_requested(self):
        self._status.showMessage("Generazione interrotta")
        self._hide_generating_dialog()
        self._gen_panel.on_phase1_complete()
        self._current_worker = None

    @Slot(object)
    def _on_generation_finished(self, result: object):
        result: GeneratorResult = result
        self._hide_generating_dialog()
        msg = (
            f"\u2705 Stage generato! "
            f"Score: {result.score} | "
            f"Tentativi: {result.attempts} | "
            f"Bersagli: {len(result.stage.items)}"
        )
        self._status.showMessage(msg)
        self._replace_stage(result.stage)
        self._gen_panel.on_phase1_complete()
        self._current_worker = None

    @Slot(object)
    def _on_phase2_finished(self, result: object):
        """Callback per completamento Fase 2."""
        result: GeneratorResult = result
        self._hide_generating_dialog()
        msg = (
            f"\u2705 Stage completo! "
            f"Score: {result.score} | "
            f"Tentativi: {result.attempts} | "
            f"Item: {len(result.stage.items)}"
        )
        self._status.showMessage(msg)
        self._replace_stage(result.stage)
        self._gen_panel.on_phase2_complete()
        poly = result.stage.properties.get("perimeter_poly")
        if poly:
            self._current_poly = poly
        self._current_worker = None

    @Slot(str)
    def _on_phase2_error(self, message: str):
        self._hide_generating_dialog()
        self._status.showMessage(f"Errore Fase 2: {message}")
        self._gen_panel.on_phase2_error(message)
        self._current_worker = None

    @Slot(str)
    def _on_generation_error(self, message: str):
        self._hide_generating_dialog()
        self._status.showMessage(f"Errore generazione: {message}")
        self._gen_panel.on_phase1_error(message)
        self._current_worker = None

    @Slot(float, float, bool)
    def _on_shooting_position_placed(self, x: float, y: float, is_start: bool):
        """Aggiunge una shooting position dalla view al wizard."""
        saved_x, saved_y = x, y

        # Callback quando l'utente clicca ✕ sulla riga della lista
        def _on_pos_deleted(item):
            """Rimuove il marker corrispondente dalla scena."""
            for gi in list(self._scene.items()):
                if hasattr(gi, 'pos_m') and hasattr(gi, '_label'):
                    pm = gi.pos_m
                    if abs(pm[0] - saved_x) < 0.5 and abs(pm[1] - saved_y) < 0.5:
                        self._scene.removeItem(gi)
                        break

        # Callback per aggiornare i marker dopo rinumerazione lista
        def _renumber_markers(labels: list[str]):
            """Aggiorna le etichette dei marker sulla scena dopo cancellazione."""
            lst = self._gen_panel._pos_list
            for gi in self._scene.items():
                if not hasattr(gi, 'pos_m') or not hasattr(gi, '_is_start'):
                    continue  # solo ShootingPositionMarker
                pm = gi.pos_m
                for j in range(lst.count()):
                    item = lst.item(j)
                    text = self._gen_panel._find_item_text(item)
                    if not text:
                        continue
                    try:
                        rest = text.split(" ", 1)[1] if " " in text else ""
                        rest = rest.strip("()")
                        parts = rest.split(",")
                        if len(parts) >= 2:
                            ix = float(parts[0].strip())
                            iy = float(parts[1].strip())
                            if abs(ix - pm[0]) < 0.5 and abs(iy - pm[1]) < 0.5:
                                if j < len(labels):
                                    new_num = labels[j].lstrip("#")
                                    gi._label = new_num
                                    gi.update()
                                break
                    except (ValueError, IndexError):
                        continue

        self._gen_panel.add_shooting_position(
            saved_x, saved_y, is_start,
            on_delete_clicked=_on_pos_deleted,
            on_renumbered=_renumber_markers,
        )
        index = len(self._gen_panel.get_shooting_positions())

        # Callback quando la posizione viene spostata (aggiorna la label nella lista)
        def _on_pos_changed(marker):
            nonlocal saved_x, saved_y
            mx, my = marker.pos_m
            lst = self._gen_panel._pos_list
            for i in range(lst.count()):
                item = lst.item(i)
                text = self._gen_panel._find_item_text(item)
                if not text:
                    continue
                try:
                    rest = text.split(" ", 1)[1] if " " in text else ""
                    rest = rest.strip("()")
                    parts = rest.split(",")
                    if len(parts) >= 2:
                        ix = float(parts[0].strip())
                        iy = float(parts[1].strip())
                        if abs(ix - saved_x) < 0.5 and abs(iy - saved_y) < 0.5:
                            num_part = text.split(" ")[0] if " " in text else "#?"
                            new_text = f"{num_part} ({mx:.2f}, {my:.2f})"
                            widget = lst.itemWidget(item)
                            if widget:
                                label = widget.findChild(QLabel)
                                if label:
                                    label.setText(new_text)
                            saved_x, saved_y = mx, my
                            break
                except (ValueError, IndexError):
                    continue

        # Aggiunge marker visivo nella scena
        self._scene.add_shooting_position_marker(
            saved_x, saved_y, is_start=is_start, index=index,
            on_changed=_on_pos_changed,
        )
        self._status.showMessage(f"Posizione di tiro #{index} aggiunta: ({saved_x:.1f}, {saved_y:.1f})")

        # Auto-disattiva la modalità posizionamento dopo aver piazzato
        self._gen_panel._btn_place_pos.setChecked(False)
        self._gen_panel._btn_place_pos.setText("✏️ Posiziona")
        self._view.set_placing_position_mode(False)

    @Slot(float, float, float, float, bool)
    def _on_obstacle_placed(self, x: float, y: float, width: float,
                             rotation: float, is_wall: bool):
        """Aggiunge un ostacolo posizionato dall'utente."""
        saved_x, saved_y = x, y
        prefix = "M" if is_wall else "B"

        # Callback quando l'utente clicca ✕ sulla riga della lista
        def _on_obstacle_deleted(item):
            """Rimuove il marker corrispondente dalla scena."""
            for gi in list(self._scene.items()):
                if hasattr(gi, 'pos_m') and hasattr(gi, '_is_wall'):
                    pm = gi.pos_m
                    if abs(pm[0] - saved_x) < 0.5 and abs(pm[1] - saved_y) < 0.5:
                        self._scene.removeItem(gi)
                        break

        # Callback per aggiornare i marker dopo rinumerazione
        def _renumber_obstacles(labels: list[str]):
            """Aggiorna le etichette dei marker ostacoli sulla scena."""
            lst = self._gen_panel._walls_list if is_wall else self._gen_panel._barriers_list
            for gi in self._scene.items():
                if not hasattr(gi, 'pos_m') or not hasattr(gi, '_is_wall'):
                    continue
                if gi._is_wall != is_wall:
                    continue  # solo ostacoli dello stesso tipo
                pm = gi.pos_m
                for j in range(lst.count()):
                    item = lst.item(j)
                    text = self._gen_panel._find_item_text(item)
                    if not text:
                        continue
                    try:
                        rest = text.split(" ", 1)[1] if " " in text else ""
                        if "(" in rest and ")" in rest:
                            coords = rest[rest.find("(") + 1:rest.find(")")]
                            parts = coords.split(",")
                            if len(parts) >= 2:
                                ix = float(parts[0].strip())
                                iy = float(parts[1].strip())
                                if abs(ix - pm[0]) < 0.5 and abs(iy - pm[1]) < 0.5:
                                    if j < len(labels):
                                        gi._label = labels[j]
                                        gi.update()
                                    break
                    except (ValueError, IndexError):
                        continue

        self._gen_panel.add_obstacle(
            saved_x, saved_y, width, rotation, is_wall,
            on_delete_clicked=_on_obstacle_deleted,
            on_renumbered=_renumber_obstacles,
        )

        # Callback per aggiornare la label quando l'utente sposta/ruota
        def _on_obstacle_changed(marker):
            nonlocal saved_x, saved_y
            mx, my = marker.pos_m
            lst = self._gen_panel._walls_list if marker._is_wall else self._gen_panel._barriers_list
            for i in range(lst.count()):
                item = lst.item(i)
                text = self._gen_panel._find_item_text(item)
                if not text:
                    continue
                # Cerca per coordinate
                try:
                    rest = text.split(" ", 1)[1] if " " in text else ""
                    if "(" in rest and ")" in rest:
                        coords = rest[rest.find("(") + 1:rest.find(")")]
                        parts = coords.split(",")
                        if len(parts) >= 2:
                            ix = float(parts[0].strip())
                            iy = float(parts[1].strip())
                            if abs(ix - saved_x) < 0.5 and abs(iy - saved_y) < 0.5:
                                num_part = text.split(" ")[0] if " " in text else "#?"
                                new_text = f"{num_part} ({mx:.2f}, {my:.2f}) " \
                                           f"w={marker.width_m:.1f} rot={marker.rotation_deg:.0f}°"
                                widget = lst.itemWidget(item)
                                if widget:
                                    label_w = widget.findChild(QLabel)
                                    if label_w:
                                        label_w.setText(new_text)
                                saved_x, saved_y = mx, my
                                break
                except (ValueError, IndexError):
                    continue

        # Calcola il numero progressivo per il marker
        lst = self._gen_panel._walls_list if is_wall else self._gen_panel._barriers_list
        marker_number = lst.count()
        label_text = f"#{marker_number}{prefix}"

        self._scene.add_obstacle_marker(
            saved_x, saved_y, width=width, rotation=rotation,
            is_wall=is_wall, label=label_text,
            on_changed=_on_obstacle_changed,
        )
        tipo = "muro" if is_wall else "barriera"
        self._status.showMessage(f"{tipo} #{marker_number} posizionato: ({saved_x:.1f}, {saved_y:.1f})")

        # Auto-disattiva la modalità posizionamento
        if is_wall:
            self._gen_panel._btn_place_wall.setChecked(False)
            self._gen_panel._btn_place_wall.setText("🧱 Muro")
        else:
            self._gen_panel._btn_place_barrier.setChecked(False)
            self._gen_panel._btn_place_barrier.setText("🛡️ Barriera")
        self._view.set_placing_obstacle_mode(False, is_wall)

    @Slot(bool, bool)
    def _on_obstacle_mode_toggled(self, active: bool, is_wall: bool):
        """Attiva/disattiva la modalità posizionamento ostacoli."""
        width = self._gen_panel._obs_width.value()
        rotation = self._gen_panel._obs_rotation.value()
        self._view.set_placing_obstacle_mode(active, is_wall, width, rotation)

    @Slot()
    def _refresh_info(self):
        """Aggiorna il pannello Info Stage."""
        self._info_panel.set_stage(self._stage)

    def _replace_stage(self, new_stage: Stage):
        """Sostituisce lo stage nell'editor e ricostruisce la scena.

        Nota: se new_stage è lo stesso oggetto di self._stage (es. dopo
        Phase2Worker che modifica in-place), salta la copia dati per
        evitare di cancellare items prima di averli letti.
        """
        if new_stage is not self._stage:
            self._stage.name = new_stage.name
            self._stage.width = new_stage.width
            self._stage.depth = new_stage.depth
            self._stage.course_type = new_stage.course_type
            self._stage.division = new_stage.division
            self._stage.properties = dict(new_stage.properties)
            self._stage.shooting_positions = list(new_stage.shooting_positions)
            self._stage._next_id = new_stage._next_id
            self._stage.items.clear()
            for it in new_stage.items:
                self._stage.items.append(it)
        # Ricostruisce la scena da capo
        self._scene.stage = self._stage
        self._scene.clear()
        self._scene.grid = None
        self._scene._shooting_area = None
        self._scene._items.clear()
        self._scene._setup_grid()
        self._scene._sync_from_model()
        self._scene._update_shooting_area()
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._prop_dock.set_item(None)
        self._refresh_info()
