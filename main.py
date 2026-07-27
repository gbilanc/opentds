#!/usr/bin/env python3
# main.py
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

# Silenzia warning Wayland textinput (noti in Qt 6 su Wayland, innocui)
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.textinput=false")

from ui.main_window import MainWindow
from ui.theme import ThemeManager


def setup_high_dpi():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main():
    setup_high_dpi()
    app = QApplication(sys.argv)

    app.setApplicationName("OpenTDS")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("opentds-dev")

    font = QFont("Segoe UI, -apple-system, sans-serif")
    font.setPixelSize(14)
    app.setFont(font)

    # Inizializza tema (carica light.qss di default)
    theme = ThemeManager(app)
    app.setProperty("opentds_theme", theme)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
