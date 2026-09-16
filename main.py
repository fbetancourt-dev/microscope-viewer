#!/usr/bin/env python3
"""
Digital Microscope Dual Viewer (USB & WiFi) Entry Point.
High-performance, ultra-low latency desktop application for microscopy inspection.
"""

import sys
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui import MicroscopeMainWindow


def main():
    # Enable high-DPI attributes
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("MicroscopeViewer")
    app.setOrganizationName("LabTools")

    window = MicroscopeMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
