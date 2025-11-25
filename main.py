#!/usr/bin/env python3
"""
Video Diff Tool - Main entry point.

A GUI tool for comparing videos side-by-side with difference visualization.
Supports preview with MPV and encoding with FFmpeg.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QFont

from src.main_window import MainWindow


def setup_light_theme(app: QApplication) -> None:
    """Setup light theme for the application."""
    # Set default font
    font = QFont()
    font.setFamily(".AppleSystemUIFont" if sys.platform == "darwin" else "Segoe UI")
    font.setPointSize(13 if sys.platform == "darwin" else 10)
    app.setFont(font)

    # Use fusion style for consistent cross-platform appearance
    app.setStyle("Fusion")
    
    # Create light palette
    palette = QPalette()
    
    # Window colors
    palette.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(51, 51, 51))
    
    # Base colors (for text inputs, lists, etc.)
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
    
    # Text colors
    palette.setColor(QPalette.ColorRole.Text, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    
    # Button colors
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(51, 51, 51))
    
    # Highlight colors
    palette.setColor(QPalette.ColorRole.Highlight, QColor(74, 144, 217))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    
    # Other colors
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.Link, QColor(74, 144, 217))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(128, 74, 217))
    
    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(160, 160, 160))
    
    app.setPalette(palette)


def main():
    """Main entry point."""
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Video Diff Tool")
    app.setOrganizationName("VideoDiffTool")
    
    # Setup light theme
    setup_light_theme(app)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

