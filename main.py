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

    # Tema QSS minimale
    qss = """
    QMainWindow { background-color: #f8fafc; }
    QToolBar {
        background-color: #ffffff;
        border-bottom: 1px solid #e2e8f0;
        padding: 4px 8px;
        spacing: 6px;
    }
    QPushButton {
        padding: 6px 14px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        border: 1px solid #e2e8f0;
        background-color: #ffffff;
        color: #0f172a;
    }
    QPushButton:hover { background-color: #f1f5f9; border-color: #94a3b8; }
    QPushButton:pressed { background-color: #e2e8f0; }
    QStatusBar { background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 4px 16px; color: #475569; }
    """
    app.setStyleSheet(qss)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
