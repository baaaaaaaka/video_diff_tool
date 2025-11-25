"""Main window for Video Diff Tool."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QCheckBox, QMessageBox, QStatusBar,
    QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QIcon

from .settings import get_settings
from .binary_finder import get_binary_finder
from .mpv_launcher import get_mpv_launcher
from .widgets.video_drop_zone import VideoDropZone
from .widgets.encoding_dialog import EncodingDialog
from .widgets.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.finder = get_binary_finder()
        self.mpv_launcher = get_mpv_launcher()
        
        self.setWindowTitle("Video Diff Tool")
        self._setup_ui()
        self._setup_menu()
        self._load_settings()
        self._update_status()
        self._check_binaries_and_prompt()
    
    def _check_binaries_and_prompt(self):
        """Check for required binaries and prompt user if missing."""
        mpv_path = self.finder.find_mpv(self.settings.get("mpv_path"))
        ffmpeg_path = self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        
        missing = []
        if not mpv_path:
            missing.append("mpv")
        if not ffmpeg_path:
            missing.append("ffmpeg")
            
        if missing:
            msg = "The following required tools were not found:\n\n"
            for binary in missing:
                msg += f"• {binary.upper()}\n"
            
            msg += "\nMost features will not work without them.\n\n"
            msg += "Would you like to see installation instructions?"
            
            reply = QMessageBox.warning(
                self,
                "Missing Dependencies",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                instructions = ""
                for binary in missing:
                    instructions += f"--- {binary.upper()} ---\n"
                    instructions += self.finder.get_install_instructions(binary)
                    instructions += "\n\n"
                
                QMessageBox.information(self, "Installation Instructions", instructions)
    
    def _setup_ui(self):
        """Setup the main UI."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Video Comparison Tool")
        header.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #333;
            padding: 10px 0;
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)
        
        # Video inputs section
        videos_group = QGroupBox("Video Inputs")
        videos_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }
        """)
        videos_layout = QVBoxLayout(videos_group)
        
        # Main videos row (left and right)
        main_videos_layout = QHBoxLayout()
        
        # Left video (Candidate)
        self.video_left = VideoDropZone(
            label="Left Video (Candidate)",
            default_title=self.settings.get("title_left"),
            show_title_input=False,
            optional=False
        )
        self.video_left.video_changed.connect(self._on_video_changed)
        main_videos_layout.addWidget(self.video_left)
        
        # Right video (Baseline)
        self.video_right = VideoDropZone(
            label="Right Video (Baseline)",
            default_title=self.settings.get("title_right"),
            show_title_input=False,
            optional=False
        )
        self.video_right.video_changed.connect(self._on_video_changed)
        main_videos_layout.addWidget(self.video_right)
        
        videos_layout.addLayout(main_videos_layout)
        
        # Third video section
        third_section_layout = QHBoxLayout()
        
        # Left side spacer/stretch
        third_section_layout.addStretch()
        
        # Right side container for third video controls
        third_video_container = QVBoxLayout()
        
        # Checkbox to enable third video
        self.enable_third_cb = QCheckBox("Enable Third Video (Bottom Right)")
        self.enable_third_cb.setChecked(self.settings.get("enable_third_video"))
        self.enable_third_cb.stateChanged.connect(self._on_third_video_toggle)
        self.enable_third_cb.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #555;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        third_video_container.addWidget(self.enable_third_cb)
        
        # Third video drop zone
        self.video_third = VideoDropZone(
            label="Third Video (Bottom Right)",
            default_title=self.settings.get("title_third"),
            show_title_input=False,
            optional=True
        )
        self.video_third.video_changed.connect(self._on_video_changed)
        self.video_third.set_enabled_state(self.enable_third_cb.isChecked())
        self.video_third.setMaximumWidth(450)
        third_video_container.addWidget(self.video_third)
        
        third_section_layout.addLayout(third_video_container)
        
        videos_layout.addLayout(third_section_layout)
        main_layout.addWidget(videos_group)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        # Preview with MPV button
        self.preview_btn = QPushButton("Preview with MPV")
        self.preview_btn.setEnabled(False)
        self.preview_btn.clicked.connect(self._launch_mpv)
        self.preview_btn.setMinimumHeight(45)
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a7bc8;
            }
            QPushButton:pressed {
                background-color: #2a6bb8;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        buttons_layout.addWidget(self.preview_btn)
        
        # Encode with FFmpeg button
        self.encode_btn = QPushButton("Encode with FFmpeg")
        self.encode_btn.setEnabled(False)
        self.encode_btn.clicked.connect(self._show_encode_dialog)
        self.encode_btn.setMinimumHeight(45)
        self.encode_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        buttons_layout.addWidget(self.encode_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Layout preview diagram
        preview_group = QGroupBox("Output Layout Preview")
        preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
            }
        """)
        preview_layout = QHBoxLayout(preview_group)
        
        self.layout_preview = QLabel()
        self._update_layout_preview()
        self.layout_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_preview.setStyleSheet("""
            font-family: "Menlo", "Consolas", "Monaco", "Liberation Mono", "Lucida Console", monospace;
            font-size: 12px;
            background-color: #f8f8f8;
            padding: 15px;
            border-radius: 4px;
            color: #333;
        """)
        preview_layout.addWidget(self.layout_preview)
        
        main_layout.addWidget(preview_group)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Set window styling (light theme)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                background-color: #fff;
            }
        """)
        
        # Set minimum size
        self.setMinimumSize(800, 600)
    
    def _setup_menu(self):
        """Setup menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _load_settings(self):
        """Load settings and restore state."""
        # Restore window geometry
        x = self.settings.get("window_x")
        y = self.settings.get("window_y")
        w = self.settings.get("window_width")
        h = self.settings.get("window_height")
        self.setGeometry(x, y, w, h)
        
        # Restore last used videos
        last_left = self.settings.get("last_video_left")
        if last_left and Path(last_left).exists():
            self.video_left.set_video_path(last_left)
        
        last_right = self.settings.get("last_video_right")
        if last_right and Path(last_right).exists():
            self.video_right.set_video_path(last_right)
        
        last_third = self.settings.get("last_video_third")
        if last_third and Path(last_third).exists():
            self.video_third.set_video_path(last_third)
        
        # Restore titles
        self.video_left.set_title(self.settings.get("title_left"))
        self.video_right.set_title(self.settings.get("title_right"))
        self.video_third.set_title(self.settings.get("title_third"))
    
    def _save_settings(self):
        """Save current state to settings."""
        # Window geometry
        geo = self.geometry()
        self.settings.set("window_x", geo.x())
        self.settings.set("window_y", geo.y())
        self.settings.set("window_width", geo.width())
        self.settings.set("window_height", geo.height())
        
        # Video paths
        self.settings.set("last_video_left", self.video_left.get_video_path())
        self.settings.set("last_video_right", self.video_right.get_video_path())
        self.settings.set("last_video_third", self.video_third.get_video_path())
        
        # Titles
        self.settings.set("title_left", self.video_left.get_title())
        self.settings.set("title_right", self.video_right.get_title())
        self.settings.set("title_third", self.video_third.get_title())
        
        # Third video enabled
        self.settings.set("enable_third_video", self.enable_third_cb.isChecked())
    
    def _on_video_changed(self, path: str):
        """Handle video path change."""
        self._update_buttons()
        self._update_layout_preview()
    
    def _on_third_video_toggle(self, state: int):
        """Handle third video checkbox toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.video_third.set_enabled_state(enabled)
        self._update_buttons()
        self._update_layout_preview()
    
    def _update_buttons(self):
        """Update button enabled states."""
        has_left = bool(self.video_left.get_video_path())
        has_right = bool(self.video_right.get_video_path())
        
        # Check if binaries are available
        mpv_available = bool(self.finder.find_mpv(self.settings.get("mpv_path")))
        ffmpeg_available = bool(self.finder.find_ffmpeg(self.settings.get("ffmpeg_path")))
        font_available = bool(self.finder.find_font(self.settings.get("font_path")))
        
        can_preview = has_left and has_right and mpv_available and font_available
        can_encode = has_left and has_right and ffmpeg_available and font_available
        
        self.preview_btn.setEnabled(can_preview)
        self.encode_btn.setEnabled(can_encode)
    
    def _update_layout_preview(self):
        """Update the layout preview diagram."""
        has_third = self.enable_third_cb.isChecked() and self.video_third.get_video_path()
        
        left_title = self.video_left.get_title() or "Left"
        right_title = self.video_right.get_title() or "Right"
        third_title = self.video_third.get_title() or "Third" if has_third else "Black"
        
        # Create ASCII diagram
        width = 50
        half_width = width // 2
        
        def center(text: str, w: int) -> str:
            return text.center(w)
        
        border = "+" + "-" * half_width + "+" + "-" * half_width + "+"
        
        diagram = [
            border,
            "|" + center(left_title[:half_width-2], half_width) + "|" + center(right_title[:half_width-2], half_width) + "|",
            "|" + center("(Video 1)", half_width) + "|" + center("(Video 2)", half_width) + "|",
            border,
            "|" + center("Difference", half_width) + "|" + center(third_title[:half_width-2], half_width) + "|",
            "|" + center("(Blend)", half_width) + "|" + center("(Video 3)" if has_third else "(Empty)", half_width) + "|",
            border,
        ]
        
        self.layout_preview.setText("\n".join(diagram))
    
    def _update_status(self):
        """Update status bar."""
        mpv_path = self.finder.find_mpv(self.settings.get("mpv_path"))
        ffmpeg_path = self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        font_path = self.finder.find_font(self.settings.get("font_path"))
        
        status_parts = []
        
        if mpv_path:
            status_parts.append("MPV: ✓")
        else:
            status_parts.append("MPV: ✗")
        
        if ffmpeg_path:
            status_parts.append("FFmpeg: ✓")
        else:
            status_parts.append("FFmpeg: ✗")
        
        if font_path:
            status_parts.append("Font: ✓")
        else:
            status_parts.append("Font: ✗")
        
        self.status_bar.showMessage(" | ".join(status_parts))
    
    def _launch_mpv(self):
        """Launch MPV preview."""
        try:
            video_third = None
            if self.enable_third_cb.isChecked() and self.video_third.get_video_path():
                video_third = self.video_third.get_video_path()
            
            self.mpv_launcher.launch(
                video_left=self.video_left.get_video_path(),
                video_right=self.video_right.get_video_path(),
                video_third=video_third,
                title_left=self.video_left.get_title(),
                title_right=self.video_right.get_title(),
                title_third=self.video_third.get_title() if video_third else None,
                fullscreen=True
            )
        except RuntimeError as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to launch MPV: {e}\n\nPlease check your MPV installation in Settings."
            )
    
    def _show_encode_dialog(self):
        """Show encoding dialog."""
        video_third = None
        if self.enable_third_cb.isChecked() and self.video_third.get_video_path():
            video_third = self.video_third.get_video_path()
        
        dialog = EncodingDialog(
            video_left=self.video_left.get_video_path(),
            video_right=self.video_right.get_video_path(),
            title_left=self.video_left.get_title(),
            title_right=self.video_right.get_title(),
            video_third=video_third,
            title_third=self.video_third.get_title() if video_third else "",
            parent=self
        )
        dialog.exec()
    
    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Reload settings
            self.video_left.set_title(self.settings.get("title_left"))
            self.video_right.set_title(self.settings.get("title_right"))
            self.video_third.set_title(self.settings.get("title_third"))
            self._update_status()
            self._update_buttons()
            self._update_layout_preview()
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Video Diff Tool",
            "<h2>Video Diff Tool</h2>"
            "<p>A tool for comparing videos side-by-side with difference visualization.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Preview comparisons with MPV</li>"
            "<li>Encode comparisons with FFmpeg (HEVC)</li>"
            "<li>Support for hardware-accelerated encoding</li>"
            "<li>Customizable titles and settings</li>"
            "</ul>"
            "<p>Version 1.0.0</p>"
        )
    
    def closeEvent(self, event):
        """Handle close event."""
        self._save_settings()
        event.accept()

