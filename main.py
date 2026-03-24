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

def run_smoke_check(argv: list[str]) -> int | None:
    """Run a lightweight packaged-runtime smoke check and exit."""
    if "--smoke-check" not in argv:
        return None

    smoke_video = None
    if "--smoke-video" in argv:
        video_index = argv.index("--smoke-video") + 1
        if video_index >= len(argv):
            print("smoke-check error: --smoke-video requires a path")
            return 1
        smoke_video = argv[video_index]

    try:
        import av
        from src.video_validator import VideoValidator
    except ImportError as exc:
        print(f"smoke-check error: failed to import runtime dependencies: {exc}")
        return 1

    validator = VideoValidator()
    print(f"smoke-check: av {av.__version__}")
    print(f"smoke-check: backends {', '.join(validator.get_available_metadata_backends())}")

    if smoke_video:
        try:
            info = validator.get_video_info(smoke_video, preferred_backend=VideoValidator.BACKEND_PYAV)
        except RuntimeError as exc:
            print(f"smoke-check error: {exc}")
            return 1

        if info is None:
            print(f"smoke-check error: failed to read {smoke_video} with PyAV")
            return 1

        print(
            "smoke-check: "
            f"{Path(smoke_video).name} {info.width}x{info.height} "
            f"{info.frame_count}f {info.codec}"
        )

    return 0


smoke_check_exit_code = run_smoke_check(sys.argv[1:])
if smoke_check_exit_code is not None:
    sys.exit(smoke_check_exit_code)

# Check dependencies BEFORE importing PyQt6
# Skip dependency check if running as a frozen application (binary)
if not getattr(sys, 'frozen', False):
    try:
        from src.dependency_manager import check_and_install_dependencies
        check_and_install_dependencies()
    except Exception as e:
        print(f"Warning: Failed to check dependencies: {e}")

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette, QColor, QFont
    from src.app_metadata import APP_NAME
    from src.main_window import MainWindow
except ImportError as e:
    print("CRITICAL ERROR: Failed to import PyQt6 or application modules.")
    print(f"Details: {e}")
    print("Please ensure all dependencies are installed by running:")
    print("pip install -r requirements.txt")
    sys.exit(1)


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
    app.setApplicationName(APP_NAME)
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
