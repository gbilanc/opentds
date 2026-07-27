"""
Theme manager for OpenTDS — toggles between light and dark QSS themes.

Usage:
    theme = ThemeManager(app)
    theme.toggle()  # light → dark
    theme.apply_dark()
    theme.apply_light()
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


_STYLES_DIR = Path(__file__).resolve().parent / "resources" / "styles"


class ThemeManager(QObject):
    """Gestore tema light/dark con stili QSS caricati da file."""

    themeChanged = Signal(str)  # "light" | "dark"

    def __init__(self, app: QApplication, parent=None):
        super().__init__(parent)
        self._app = app
        self._dark_mode = False

        # Applica tema light di default (da file light.qss)
        self.apply_light()

    @property
    def dark_mode(self) -> bool:
        return self._dark_mode

    def toggle(self):
        """Alterna tra tema light e dark."""
        if self._dark_mode:
            self.apply_light()
        else:
            self.apply_dark()

    def apply_light(self):
        """Applica tema chiaro."""
        qss_path = _STYLES_DIR / "light.qss"
        self._apply_qss(qss_path)
        self._dark_mode = False
        self.themeChanged.emit("light")

    def apply_dark(self):
        """Applica tema scuro."""
        qss_path = _STYLES_DIR / "dark.qss"
        self._apply_qss(qss_path)
        self._dark_mode = True
        self.themeChanged.emit("dark")

    def _apply_qss(self, path: Path):
        """Carica e applica il foglio di stile QSS."""
        if path.exists():
            qss = path.read_text(encoding="utf-8")
            self._app.setStyleSheet(qss)
