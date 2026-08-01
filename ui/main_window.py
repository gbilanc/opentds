# ui/main_window.py
from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.generator import Phase1Config
from core.models import ItemType, Stage
from services.exporter import export_pdf, export_png
from services.library import StageLibrary
from services.navigator_server import (
    export_stage_for_navigator,
    get_navigator_server,
)
from services.openscad_exporter import (
    ScadExportOptions,
    export_scad,
    openscad_available,
    render_scad_to_3mf,
    render_scad_to_png,
    render_scad_to_stl,
)
from services.serializer import load_stage, save_stage, stage_to_dict
from ui.dialogs.library_dialog import LibraryDialog
from ui.dialogs.target_config_dialog import TargetConfigDialog
from ui.editor.generator_panel import GeneratorPanel
from ui.editor.path_editor import PathEditorPanel
from ui.editor.property_dock import PropertyDock
from ui.editor.stage_info import StageInfoPanel
from ui.editor.stage_scene import StageItemWrapper, StageScene
from ui.editor.stage_view import StageView
from ui.icons import load_icon


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenTDS — Stage Generator")
        self.resize(1200, 850)

        self._stage = Stage(name="Stage IPSC", width=20.0, depth=15.0)
        self._library = StageLibrary()
        self._base_poly = None  # poligono base (senza rotazione/scala) per update live
        self._current_poly = None
        self._setup_ui()
        self._setup_toolbar()
        self._setup_menu()
        self._setup_status_bar()
        self._connect_signals()

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

        # Info dock (sinistra) — con QTabWidget per etichette sempre visibili
        self._info_panel = StageInfoPanel()
        self._gen_panel = GeneratorPanel(self)
        self._gen_panel.scene_ref = self._scene  # per Fase 3

        left_tabs = QTabWidget()
        left_tabs.setTabPosition(QTabWidget.TabPosition.North)
        left_tabs.addTab(self._info_panel, "Info Stage")
        left_tabs.addTab(self._gen_panel, "Generazione")

        self._info_dock = QDockWidget("Info Stage", self)
        self._info_dock.setWidget(left_tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._info_dock)

        # Property dock + Path editor (destra) — con QTabWidget per etichette sempre visibili
        self._prop_dock_widget = PropertyDock(self)
        self._path_panel = PathEditorPanel(self)

        right_tabs = QTabWidget()
        right_tabs.setTabPosition(QTabWidget.TabPosition.North)
        right_tabs.addTab(self._prop_dock_widget, "Proprietà")
        right_tabs.addTab(self._path_panel, "Percorso di Tiro")

        self._prop_dock = QDockWidget("Proprietà", self)
        self._prop_dock.setWidget(right_tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

    def _setup_toolbar(self):
        toolbar = QToolBar("Strumenti")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # ── Quick-add buttons ──
        btn_add_target = QPushButton(load_icon("target_paper"), "+Paper")
        btn_add_target.setToolTip("Aggiungi Paper Target al centro (Ctrl+1)")
        btn_add_target.clicked.connect(self._on_add_paper_target)
        toolbar.addWidget(btn_add_target)

        btn_add_steel = QPushButton(load_icon("target_steel"), "+Steel")
        btn_add_steel.setToolTip("Aggiungi Steel Target al centro (Ctrl+2)")
        btn_add_steel.clicked.connect(self._on_add_steel_target)
        toolbar.addWidget(btn_add_steel)

        btn_add_wall = QPushButton(load_icon("wall"), "+Muro")
        btn_add_wall.setToolTip("Aggiungi Muro al centro (Ctrl+3)")
        btn_add_wall.clicked.connect(self._on_add_wall)
        toolbar.addWidget(btn_add_wall)

        btn_add_noshoot = QPushButton(load_icon("no_shoot"), "+No-Shoot")
        btn_add_noshoot.setToolTip("Aggiungi No-Shoot al centro (Ctrl+4)")
        btn_add_noshoot.clicked.connect(self._on_add_no_shoot)
        toolbar.addWidget(btn_add_noshoot)

        toolbar.addSeparator()

        btn_del = QPushButton(load_icon("delete"), "Elimina")
        btn_del.setToolTip("Elimina oggetti selezionati")
        btn_del.clicked.connect(
            lambda: (
                self._scene.push_remove_selected(),
                self._refresh_info(),
            )
        )
        toolbar.addWidget(btn_del)

        toolbar.addSeparator()

        btn_validate = QPushButton(load_icon("check"), "Valida")
        btn_validate.setToolTip("Valida lo stage con IPSCRulesEngine")
        btn_validate.clicked.connect(self._on_validate)
        toolbar.addWidget(btn_validate)

        toolbar.addSeparator()

        btn_navigate_3d = QPushButton("3D")
        btn_navigate_3d.setToolTip("Naviga lo stage in 3D (Ctrl+3) — apre il browser")
        btn_navigate_3d.clicked.connect(self._on_navigate_3d)
        toolbar.addWidget(btn_navigate_3d)

        toolbar.addSeparator()

        self._btn_safety = QPushButton(load_icon("check"), "Sic")
        self._btn_safety.setCheckable(True)
        self._btn_safety.setToolTip("Mostra/nasconde zone di sicurezza (coni di ingaggio)")
        self._btn_safety.toggled.connect(self._on_toggle_safety_zones)
        toolbar.addWidget(self._btn_safety)

        toolbar.addSeparator()

        btn_undo = QPushButton(load_icon("undo"), "Undo")
        btn_undo.setToolTip("Annulla (Ctrl+Z)")
        btn_undo.clicked.connect(
            lambda: (
                self._scene.undo_stack.undo(),
                self._refresh_info(),
            )
        )
        toolbar.addWidget(btn_undo)

        btn_redo = QPushButton(load_icon("redo"), "Redo")
        btn_redo.setToolTip("Ripeti (Ctrl+Shift+Z)")
        btn_redo.clicked.connect(
            lambda: (
                self._scene.undo_stack.redo(),
                self._refresh_info(),
            )
        )
        toolbar.addWidget(btn_redo)

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        library_action = QAction(load_icon("library"), "&Libreria Stage…", self)
        library_action.setShortcut(QKeySequence("Ctrl+L"))
        library_action.triggered.connect(self._on_library)
        file_menu.addAction(library_action)

        file_menu.addSeparator()

        save_library_action = QAction("Salva nella &libreria…", self)
        save_library_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_library_action.triggered.connect(self._on_save_to_library)
        file_menu.addAction(save_library_action)

        save_action = QAction("&Salva Stage…", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        open_action = QAction("&Apri Stage…", self)
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

        file_menu.addSeparator()

        exit_action = QAction("&Esci", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu("&Modifica")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(
            lambda: (
                self._scene.undo_stack.undo(),
                self._refresh_info(),
            )
        )
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_action.triggered.connect(
            lambda: (
                self._scene.undo_stack.redo(),
                self._refresh_info(),
            )
        )
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        del_action = QAction("&Elimina selezionati", self)
        del_action.setShortcut(QKeySequence.Delete)
        del_action.triggered.connect(
            lambda: (
                self._scene.push_remove_selected(),
                self._refresh_info(),
            )
        )
        edit_menu.addAction(del_action)

        dup_action = QAction("&Duplica selezionati", self)
        dup_action.setShortcut(QKeySequence("Ctrl+D"))
        dup_action.triggered.connect(
            lambda: (
                self._scene.push_duplicate_selected(),
                self._refresh_info(),
            )
        )
        edit_menu.addAction(dup_action)

        # ── Strumenti ──
        tools_menu = menubar.addMenu("&Strumenti")

        navigate_3d_action = QAction("Naviga in &3D", self)
        navigate_3d_action.setShortcut(QKeySequence("Ctrl+3"))
        navigate_3d_action.triggered.connect(self._on_navigate_3d)
        tools_menu.addAction(navigate_3d_action)

        tools_menu.addSeparator()

        svg_editor_action = QAction(load_icon("edit"), "Editor Bersagli &SVG…", self)
        svg_editor_action.triggered.connect(self._on_svg_editor)
        tools_menu.addAction(svg_editor_action)

        # ── Vista ──
        view_menu = menubar.addMenu("&Visualizza")

        toggle_theme_action = QAction("Alterna tema &scuro", self)
        toggle_theme_action.setShortcut(QKeySequence("Ctrl+T"))
        toggle_theme_action.setCheckable(True)
        toggle_theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(toggle_theme_action)

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
        self._scene.selectionChangedWrapper.connect(self._prop_dock_widget.set_item)
        self._scene.markerSelected.connect(self._prop_dock_widget.set_marker)
        self._prop_dock_widget.propertyChanged.connect(self._on_property_changed)
        self._prop_dock_widget.markerChanged.connect(self._on_marker_changed)
        self._gen_panel.phase1Requested.connect(self._on_phase1_requested)
        self._gen_panel.phase1PreviewChanged.connect(self._on_phase1_preview)
        self._view.shootingPositionPlaced.connect(self._on_shooting_position_placed)
        self._gen_panel.placeModeToggled.connect(self._view.set_placing_position_mode)
        # Sincronizzazione → Info
        self._scene.itemAdded.connect(self._refresh_info)
        self._scene.itemUpdated.connect(self._refresh_info)
        self._scene.itemRemoved.connect(self._refresh_info)
        # Evidenziazione violazioni
        self._info_panel.violationsUpdated.connect(self._scene.set_violations)
        # Path editor → scene (aggiorna rendering path)
        self._path_panel.pathChanged.connect(self._on_path_changed)

    @Slot(StageItemWrapper)
    def _on_item_added(self, _wrapper):
        pass

    @Slot(int)
    def _on_item_updated(self, item_id: int):
        wrapper = self._prop_dock_widget._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock_widget.set_item(wrapper)

    @Slot(int)
    def _on_item_removed(self, item_id: int):
        wrapper = self._prop_dock_widget._wrapper
        if wrapper and wrapper.item.id == item_id:
            self._prop_dock_widget.set_item(None)

    @Slot(int, dict)
    def _on_property_changed(self, item_id: int, props: dict):
        self._scene.update_item_from_properties(item_id, **props)

    @Slot(dict)
    def _on_marker_changed(self, props: dict):
        """Aggiorna un marker sulla scena quando l'utente modifica le proprietà nel dock."""
        dock = self._prop_dock_widget
        marker = getattr(dock, "_marker_ref", None)
        if marker is None:
            return
        scale = self._scene.scale
        if "x" in props:
            marker.setPos(props["x"] * scale, marker.pos().y())
        if "y" in props:
            marker.setPos(marker.pos().x(), props["y"] * scale)
        if "rotation" in props and hasattr(marker, "setRotation"):
            marker.setRotation(props["rotation"])
        if "width" in props and hasattr(marker, "_width"):
            marker._width = props["width"]
        marker.update()
        # Notifica il cambiamento per aggiornare la lista
        if hasattr(marker, "_on_changed") and marker._on_changed:
            marker._on_changed(marker)

    def _toggle_theme(self):
        """Alterna tema chiaro/scuro."""
        app = QApplication.instance()
        theme = app.property("opentds_theme")
        if theme:
            theme.toggle()
            # Aggiorna stato status bar
            mode = "scuro" if theme.dark_mode else "chiaro"
            self._status.showMessage(f"Tema {mode} attivato")
            # Re-render scena con colori aggiornati
            self._scene._update_shooting_area()

    def _on_navigate_3d(self):
        """Esporta lo stage corrente e apre il navigatore 3D nel browser."""
        try:
            # Serializza lo stage corrente in JSON
            data = stage_to_dict(self._stage)
            stage_json = json.dumps(data, indent=2, ensure_ascii=False)

            # Scrivi il JSON nella directory dist/ del navigator
            target = export_stage_for_navigator(stage_json)

            # Avvia il server HTTP (se non già attivo)
            server = get_navigator_server()
            if not server.is_running:
                server.start()

            url = server.stage_url(target.name)
            webbrowser.open(url)

            self._status.showMessage(
                f"🌐 Navigatore 3D aperto nel browser: {url}  (server su porta {server.port})"
            )
        except Exception as e:
            self._status.showMessage(f"❌ Errore navigatore 3D: {e}")

    def closeEvent(self, event):
        """Arresta il server HTTP alla chiusura dell'applicazione."""
        server = get_navigator_server()
        if server.is_running:
            server.stop()
        super().closeEvent(event)

    # ── Azioni Strumenti ───────────────────────────────────────────────

    def _on_svg_editor(self):
        """Apre l'editor bersagli SVG."""
        from ui.dialogs.svg_editor_dialog import SvgEditorDialog

        dialog = SvgEditorDialog(self)
        if dialog.exec():
            # Refresh la scena per aggiornare eventuali bersagli che usano SVG modificati
            self._scene.reload_all_targets()

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
            msg = " Stage valido — nessuna violazione IPSC"
            self._status.setStyleSheet("color: #16a34a;")
        else:
            msg = f"‼ {n_violations} violazion{'i' if n_violations != 1 else 'e'} IPSC"
            self._status.setStyleSheet("color: #dc2626;")
        self._status.showMessage(msg)
        self._refresh_info()

    def _on_toggle_safety_zones(self, checked: bool):
        """Toggle zone di sicurezza (coni di ingaggio)."""
        self._scene.toggle_safety_zones(checked)
        self._scene.update()

    def _on_library(self):
        """Apre la libreria stage."""
        dialog = LibraryDialog(self._library, self)
        if dialog.exec():
            entry = dialog.selected_entry
            if entry:
                stage = self._library.load_stage(entry)
                if stage:
                    self._replace_stage(stage)
                    self._status.showMessage(f"Stage caricato dalla libreria: {entry.name}")
                else:
                    self._status.showMessage(f"Errore: impossibile caricare '{entry.name}'")

    def _on_save_to_library(self):
        """Salva lo stage corrente nella libreria."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            "Salva nella libreria",
            "Nome dello stage:",
            text=self._stage.name,
        )
        if ok and name:
            desc, ok2 = QInputDialog.getText(
                self,
                "Descrizione",
                "Descrizione (opzionale):",
            )
            description = desc if ok2 else ""
            entry = self._library.save_stage(
                self._stage,
                name=name,
                description=description,
                tags=["utente"],
            )
            self._status.showMessage(f"Stage salvato in libreria: {entry.name}")

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
            QMessageBox.warning(
                self,
                "OpenSCAD non trovato",
                "Installa OpenSCAD per il rendering automatico:\n"
                "  sudo apt install openscad  # Linux\n"
                "  brew install openscad      # macOS",
            )
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
            QMessageBox.warning(
                self, "OpenSCAD non trovato", "Installa OpenSCAD per l'esportazione STL."
            )
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
            QMessageBox.warning(
                self, "OpenSCAD non trovato", "Installa OpenSCAD per l'esportazione 3MF."
            )
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

    def _on_add_paper_target(self):
        """Aggiunge un Paper Target al centro dello stage."""
        cx, cy = self._stage.width / 2, self._stage.depth / 2
        self._scene.add_target(cx, cy, 0.45, 0.75, ItemType.PAPER_TARGET)
        self._refresh_info()

    def _on_add_steel_target(self):
        """Aggiunge uno Steel Target (popper) al centro dello stage."""
        cx, cy = self._stage.width / 2, self._stage.depth / 2
        self._scene.add_popper(cx, cy)
        self._refresh_info()

    def _on_add_wall(self):
        """Aggiunge un Muro al centro dello stage."""
        cx, cy = self._stage.width / 2, self._stage.depth / 2
        self._scene.add_wall(cx, cy, 3.0, 0.2)
        self._refresh_info()

    def _on_add_no_shoot(self):
        """Aggiunge un No-Shoot al centro dello stage."""
        cx, cy = self._stage.width / 2, self._stage.depth / 2
        self._scene.add_no_shoot(cx, cy)
        self._refresh_info()

    # ── Helpers: applica trasformazioni al poligono base ─────────────────

    @staticmethod
    def _transform_polygon(
        poly: list[tuple[float, float]],
        rotation: float,
        scale: float,
        stage_width: float,
        stage_depth: float,
    ) -> list[tuple[float, float]]:
        """Applica rotazione e scala a un poligono base, poi trasla verso l'up-range."""
        from core.constants import MIN_BACKSTOP_DEPTH
        from core.shapes import _clamp_poly, _rotate_poly, _scale_poly

        margin = 1.0  # MIN_TARGET_TO_EDGE
        d_eff = stage_depth - MIN_BACKSTOP_DEPTH
        poly = list(poly)

        # Rotazione
        if rotation != 0:
            cx, cy = stage_width / 2, d_eff / 2
            poly = _rotate_poly(poly, rotation, cx, cy)
            poly = _clamp_poly(poly, stage_width, d_eff, margin)

        # Scala
        if scale != 1.0:
            cx, cy = stage_width / 2, d_eff / 2
            poly = _scale_poly(poly, scale, cx, cy)
            poly = _clamp_poly(poly, stage_width, d_eff, margin)

        # Trasla verso up-range
        min_y = min(y for _, y in poly)
        dy = (margin + 0.1) - min_y
        if abs(dy) > 0.01:
            poly = [(x, y + dy) for x, y in poly]
            poly = _clamp_poly(poly, stage_width, d_eff, margin)

        return poly

    def _apply_perimeter(self, poly: list[tuple[float, float]], delimitation: str) -> None:
        """Sostituisce gli item perimetrali nella scena con quelli del nuovo poligono.

        Non tocca undo stack, non ricostruisce la scena.
        """
        from core.generator import _assign_ids
        from core.shapes import perimeter_to_items

        self._current_poly = poly
        self._stage.properties["perimeter_poly"] = [(round(x, 2), round(y, 2)) for x, y in poly]

        new_items = perimeter_to_items(
            poly,
            style=delimitation,
            stage_width=self._stage.width,
            stage_depth=self._stage.depth,
        )
        _assign_ids(new_items)

        # Rimuove vecchi item perimetrali dalla scena
        old_ids = {it.id for it in self._stage.items if it.properties.get("perimeter")}
        for gid in old_ids:
            g = self._scene._items.pop(gid, None)
            if g:
                self._scene.removeItem(g)

        # Sostituisce nello stage
        self._stage.items = [it for it in self._stage.items if not it.properties.get("perimeter")]
        self._stage.items.extend(new_items)
        self._stage._next_id = max((it.id for it in self._stage.items), default=0) + 1

        # Aggiunge nuovi item alla scena
        for it in new_items:
            self._scene._do_add_graphics_item(it)

        self._scene._update_shooting_area()
        self._refresh_info()

    def _sync_wizard_positions(self):
        """Popola la lista posizioni del wizard e crea marker con callback.

        A differenza di sync_shooting_positions() sulla scena, qui i marker
        vengono creati con callback on_changed/on_deleted che mantengono
        sincronizzati _pos_list, stage.shooting_positions e i marker visivi.
        """
        self._scene.clear_shooting_position_markers()
        self._gen_panel._pos_list.clear()

        for i, sp in enumerate(self._stage.shooting_positions):
            _cap = [sp.x, sp.y]  # mutable capture per i callback
            x, y = sp.x, sp.y
            is_start = sp.is_start
            index = i + 1

            # ── Callback: eliminazione dalla lista ──
            def _on_pos_deleted(item, _x=x, _y=y):
                for gi in list(self._scene.items()):
                    if hasattr(gi, "pos_m") and hasattr(gi, "_label"):
                        pm = gi.pos_m
                        if abs(pm[0] - _x) < 0.5 and abs(pm[1] - _y) < 0.5:
                            self._scene.removeItem(gi)
                            break
                self._sync_shooting_positions()

            # ── Callback: rinumerazione dopo cancellazione ──
            def _renumber_markers(labels):
                lst = self._gen_panel._pos_list
                for gi in self._scene.items():
                    if not hasattr(gi, "pos_m") or not hasattr(gi, "_is_start"):
                        continue
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
                                        gi._label = labels[j].lstrip("#")
                                        gi.update()
                                    break
                        except (ValueError, IndexError):
                            continue
                self._sync_shooting_positions()

            self._gen_panel.add_shooting_position(
                x,
                y,
                is_start,
                on_delete_clicked=_on_pos_deleted,
                on_renumbered=_renumber_markers,
            )

            # ── Callback: spostamento marker → aggiorna lista e stage ──
            def _on_pos_changed(marker, _cap=_cap):
                mx, my = marker.pos_m
                old_x, old_y = _cap[0], _cap[1]
                lst = self._gen_panel._pos_list
                for k in range(lst.count()):
                    item = lst.item(k)
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
                            if abs(ix - old_x) < 0.5 and abs(iy - old_y) < 0.5:
                                num_part = text.split(" ")[0] if " " in text else "#?"
                                new_text = f"{num_part} ({mx:.2f}, {my:.2f})"
                                widget = lst.itemWidget(item)
                                if widget:
                                    label = widget.findChild(QLabel)
                                    if label:
                                        label.setText(new_text)
                                _cap[0], _cap[1] = mx, my
                                self._sync_shooting_positions()
                                break
                    except (ValueError, IndexError):
                        continue

            self._scene.add_shooting_position_marker(
                x,
                y,
                is_start=is_start,
                index=index,
                on_changed=_on_pos_changed,
            )

        self._sync_shooting_positions()

    # ── Fase 1: generazione iniziale ──────────────────────────────────

    @Slot()
    def _on_phase1_requested(self, phase1: Phase1Config):
        """Esegue la Fase 1: genera il poligono base (senza rotazione/scala),
        poi applica le trasformazioni corrente e popola lo stage.

        Se lo stage ha già oggetti oltre al perimetro (bersagli, posizioni, ecc.),
        mostra un avviso prima di rigenerare perché verranno persi.
        """
        non_perimeter_items = [it for it in self._stage.items if not it.properties.get("perimeter")]
        has_positions = bool(self._stage.shooting_positions)
        if non_perimeter_items or has_positions:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.warning(
                self,
                "Rigenera area di tiro",
                "Modificando l'area di tiro verranno rimossi tutti gli oggetti\n"
                "e le posizioni di tiro già aggiunte. Continuare?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._gen_panel.on_phase1_complete()
                return
            self._gen_panel._pos_list.clear()
            if self._gen_panel.scene_ref:
                self._gen_panel.scene_ref.clear_shooting_position_markers()

        self._status.showMessage("Generazione area di tiro...")
        try:
            # 1. Genera il poligono BASE (rotazione=0, scala=1)
            from core.shapes import generate_perimeter_polygon

            self._base_poly = generate_perimeter_polygon(
                self._stage,
                letter_shape=phase1.letter_shape,
                rotation=0,
                scale=1.0,
            )
            # 2. Applica le trasformazioni correnti
            poly = self._transform_polygon(
                self._base_poly,
                rotation=phase1.rotation,
                scale=phase1.polygon_scale,
                stage_width=phase1.stage_width,
                stage_depth=phase1.stage_depth,
            )
            # 3. Applica il poligono trasformato alla scena
            from core.generator import _assign_ids
            from core.shapes import perimeter_to_items

            self._current_poly = poly
            self._stage.properties["perimeter_poly"] = [(round(x, 2), round(y, 2)) for x, y in poly]
            new_items = perimeter_to_items(
                poly,
                style=phase1.delimitation,
                stage_width=phase1.stage_width,
                stage_depth=phase1.stage_depth,
            )
            _assign_ids(new_items)
            self._stage.items = new_items
            self._stage._next_id = max((it.id for it in self._stage.items), default=0) + 1

            self._replace_stage(self._stage)
            self._gen_panel.on_phase1_complete(self._stage.name)
            self._status.showMessage("\u2705 Area di tiro generata")
        except Exception as e:
            self._gen_panel.on_phase1_error(str(e))
            self._status.showMessage(f"\u274c Errore Fase 1: {e}")

    # ── Update live (rotazione/scala) ─────────────────────────────────

    @Slot(Phase1Config)
    def _on_phase1_preview(self, phase1: Phase1Config):
        """Update live: applica rotazione e scala al poligono base,
        aggiorna solo gli item perimetrali senza ricostruire la scena.
        """
        non_perimeter = [it for it in self._stage.items if not it.properties.get("perimeter")]
        if non_perimeter or self._stage.shooting_positions:
            return
        if self._base_poly is None:
            return

        try:
            # Applica rotazione e scala al poligono base
            poly = self._transform_polygon(
                self._base_poly,
                rotation=phase1.rotation,
                scale=phase1.polygon_scale,
                stage_width=self._stage.width,
                stage_depth=self._stage.depth,
            )
            self._apply_perimeter(poly, phase1.delimitation)
        except Exception:
            pass

    # ── Helper: sincronizza stage.shooting_positions dalla lista wizard ──

    def _sync_shooting_positions(self):
        """Ricostruisce stage.shooting_positions dalla lista del wizard."""
        positions = self._gen_panel.get_shooting_positions()
        from core.models import ShootingPosition

        self._stage.shooting_positions = [
            ShootingPosition(
                id=i + 1,
                x=x,
                y=y,
                label="Start" if is_start else f"Pos {i + 1}",
                is_start=is_start,
                angle=90.0,
            )
            for i, (x, y, is_start) in enumerate(positions)
        ]
        self._refresh_info()

    @Slot(float, float, bool)
    def _on_shooting_position_placed(self, x: float, y: float, is_start: bool):
        """Aggiunge una shooting position dalla view al wizard."""
        saved_x, saved_y = x, y

        # Callback quando l'utente clicca  sulla riga della lista
        def _on_pos_deleted(item):
            """Rimuove il marker corrispondente dalla scena."""
            for gi in list(self._scene.items()):
                if hasattr(gi, "pos_m") and hasattr(gi, "_label"):
                    pm = gi.pos_m
                    if abs(pm[0] - saved_x) < 0.5 and abs(pm[1] - saved_y) < 0.5:
                        self._scene.removeItem(gi)
                        break
            self._sync_shooting_positions()

        # Callback per aggiornare i marker dopo rinumerazione lista
        def _renumber_markers(labels: list[str]):
            """Aggiorna le etichette dei marker sulla scena dopo cancellazione."""
            lst = self._gen_panel._pos_list
            for gi in self._scene.items():
                if not hasattr(gi, "pos_m") or not hasattr(gi, "_is_start"):
                    continue
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
            self._sync_shooting_positions()

        self._gen_panel.add_shooting_position(
            saved_x,
            saved_y,
            is_start,
            on_delete_clicked=_on_pos_deleted,
            on_renumbered=_renumber_markers,
        )
        index = len(self._gen_panel.get_shooting_positions())

        # Callback quando la posizione viene spostata (aggiorna label lista e stage)
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
                            self._sync_shooting_positions()
                            break
                except (ValueError, IndexError):
                    continue

        # Aggiunge marker visivo nella scena
        self._scene.add_shooting_position_marker(
            saved_x,
            saved_y,
            is_start=is_start,
            index=index,
            on_changed=_on_pos_changed,
        )
        self._status.showMessage(
            f"Posizione di tiro #{index} aggiunta: ({saved_x:.1f}, {saved_y:.1f})"
        )
        self._sync_shooting_positions()

        # Auto-disattiva la modalità posizionamento dopo aver piazzato
        self._gen_panel._btn_place_pos.setChecked(False)
        self._gen_panel._btn_place_pos.setText("Posiziona")
        self._view.set_placing_position_mode(False)

    @Slot()
    def _on_path_changed(self):
        """Aggiorna la scena quando il percorso di tiro cambia."""
        wps = self._path_panel.get_waypoint_data()
        self._scene.set_shooting_path(wps)

    @Slot(float, float, float, float, bool)
    @Slot()
    def _refresh_info(self):
        """Aggiorna il pannello Info Stage e il percorso di tiro."""
        self._info_panel.set_stage(self._stage)
        # Sync path editor (passa lo stage corrente)
        self._path_panel.set_stage(self._stage)
        wps = self._path_panel.get_waypoint_data()
        self._scene.set_shooting_path(wps)

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
        self._prop_dock_widget.set_item(None)
        self._refresh_info()
        # ── Prepara wizard e marker per editing (solo se caricamento esterno) ──
        if new_stage is not self._stage:
            self._gen_panel.on_stage_loaded(self._stage.name)
            self._sync_wizard_positions()
            # Ricostruisci _base_poly dal perimetro salvato
            self._base_poly = self._stage.properties.get("perimeter_poly")
            self._current_poly = self._base_poly
