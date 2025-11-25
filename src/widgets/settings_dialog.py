"""Settings dialog for application preferences."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QLineEdit, QFileDialog, QMessageBox,
    QTabWidget, QWidget, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt

from ..settings import get_settings
from ..binary_finder import get_binary_finder


class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.finder = get_binary_finder()
        
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # Tab widget
        tabs = QTabWidget()
        
        # Paths tab
        paths_tab = QWidget()
        paths_layout = QVBoxLayout(paths_tab)
        
        # MPV settings
        mpv_group = QGroupBox("MPV")
        mpv_layout = QFormLayout(mpv_group)
        
        mpv_path_layout = QHBoxLayout()
        self.mpv_path_edit = QLineEdit()
        self.mpv_path_edit.setPlaceholderText("Auto-detect")
        mpv_path_layout.addWidget(self.mpv_path_edit, 1)
        
        mpv_browse_btn = QPushButton("Browse...")
        mpv_browse_btn.clicked.connect(lambda: self._browse_binary("mpv"))
        mpv_path_layout.addWidget(mpv_browse_btn)
        
        mpv_detect_btn = QPushButton("Detect")
        mpv_detect_btn.clicked.connect(lambda: self._auto_detect("mpv"))
        mpv_path_layout.addWidget(mpv_detect_btn)
        
        mpv_layout.addRow("MPV Path:", mpv_path_layout)
        
        self.mpv_status = QLabel()
        mpv_layout.addRow("Status:", self.mpv_status)
        
        mpv_install_btn = QPushButton("How to Install MPV")
        mpv_install_btn.clicked.connect(lambda: self._show_install_instructions("mpv"))
        mpv_layout.addRow("", mpv_install_btn)
        
        paths_layout.addWidget(mpv_group)
        
        # FFmpeg settings
        ffmpeg_group = QGroupBox("FFmpeg")
        ffmpeg_layout = QFormLayout(ffmpeg_group)
        
        ffmpeg_path_layout = QHBoxLayout()
        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setPlaceholderText("Auto-detect")
        ffmpeg_path_layout.addWidget(self.ffmpeg_path_edit, 1)
        
        ffmpeg_browse_btn = QPushButton("Browse...")
        ffmpeg_browse_btn.clicked.connect(lambda: self._browse_binary("ffmpeg"))
        ffmpeg_path_layout.addWidget(ffmpeg_browse_btn)
        
        ffmpeg_detect_btn = QPushButton("Detect")
        ffmpeg_detect_btn.clicked.connect(lambda: self._auto_detect("ffmpeg"))
        ffmpeg_path_layout.addWidget(ffmpeg_detect_btn)
        
        ffmpeg_layout.addRow("FFmpeg Path:", ffmpeg_path_layout)
        
        self.ffmpeg_status = QLabel()
        ffmpeg_layout.addRow("Status:", self.ffmpeg_status)
        
        ffmpeg_install_btn = QPushButton("How to Install FFmpeg")
        ffmpeg_install_btn.clicked.connect(lambda: self._show_install_instructions("ffmpeg"))
        ffmpeg_layout.addRow("", ffmpeg_install_btn)
        
        paths_layout.addWidget(ffmpeg_group)
        
        # Font settings
        font_group = QGroupBox("Font")
        font_layout = QFormLayout(font_group)
        
        font_path_layout = QHBoxLayout()
        self.font_path_edit = QLineEdit()
        self.font_path_edit.setPlaceholderText("Auto-detect")
        font_path_layout.addWidget(self.font_path_edit, 1)
        
        font_browse_btn = QPushButton("Browse...")
        font_browse_btn.clicked.connect(self._browse_font)
        font_path_layout.addWidget(font_browse_btn)
        
        font_detect_btn = QPushButton("Detect")
        font_detect_btn.clicked.connect(self._auto_detect_font)
        font_path_layout.addWidget(font_detect_btn)
        
        font_layout.addRow("Font Path:", font_path_layout)
        
        self.font_status = QLabel()
        font_layout.addRow("Status:", self.font_status)
        
        paths_layout.addWidget(font_group)
        paths_layout.addStretch()
        
        tabs.addTab(paths_tab, "Paths")
        
        # Defaults tab
        defaults_tab = QWidget()
        defaults_layout = QVBoxLayout(defaults_tab)
        
        # Titles group
        titles_group = QGroupBox("Default Titles")
        titles_layout = QFormLayout(titles_group)
        
        self.default_title_left = QLineEdit()
        titles_layout.addRow("Left Video Title:", self.default_title_left)
        
        self.default_title_right = QLineEdit()
        titles_layout.addRow("Right Video Title:", self.default_title_right)
        
        self.default_title_third = QLineEdit()
        titles_layout.addRow("Third Video Title:", self.default_title_third)
        
        defaults_layout.addWidget(titles_group)
        
        # Encoding defaults group
        enc_group = QGroupBox("Encoding Defaults")
        enc_layout = QFormLayout(enc_group)
        
        self.default_resolution = QComboBox()
        self.default_resolution.addItems(["2160p", "1080p", "720p", "Custom"])
        enc_layout.addRow("Resolution:", self.default_resolution)
        
        self.default_fps = QSpinBox()
        self.default_fps.setRange(1, 120)
        enc_layout.addRow("FPS:", self.default_fps)
        
        self.default_qp = QSpinBox()
        self.default_qp.setRange(0, 51)
        enc_layout.addRow("QP:", self.default_qp)
        
        self.default_gop = QSpinBox()
        self.default_gop.setRange(1, 600)
        enc_layout.addRow("GOP:", self.default_gop)
        
        self.default_cpu_preset = QComboBox()
        self.default_cpu_preset.addItems([
            "ultrafast", "superfast", "veryfast", "faster", 
            "fast", "medium", "slow", "slower", "veryslow"
        ])
        enc_layout.addRow("CPU Preset:", self.default_cpu_preset)
        
        defaults_layout.addWidget(enc_group)
        defaults_layout.addStretch()
        
        tabs.addTab(defaults_tab, "Defaults")
        
        layout.addWidget(tabs)
        
        # Bottom buttons
        btn_layout = QHBoxLayout()
        
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
        """)
        btn_layout.addWidget(reset_btn)
        
        btn_layout.addStretch()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_and_close)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_settings(self):
        """Load current settings into UI."""
        # Paths
        self.mpv_path_edit.setText(self.settings.get("mpv_path"))
        self.ffmpeg_path_edit.setText(self.settings.get("ffmpeg_path"))
        self.font_path_edit.setText(self.settings.get("font_path"))
        
        # Titles
        self.default_title_left.setText(self.settings.get("title_left"))
        self.default_title_right.setText(self.settings.get("title_right"))
        self.default_title_third.setText(self.settings.get("title_third"))
        
        # Encoding
        self.default_resolution.setCurrentText(self.settings.get("output_resolution"))
        self.default_fps.setValue(self.settings.get("output_fps"))
        self.default_qp.setValue(self.settings.get("qp_value"))
        self.default_gop.setValue(self.settings.get("gop_size"))
        self.default_cpu_preset.setCurrentText(self.settings.get("cpu_preset"))
        
        # Update status labels
        self._update_status_labels()
    
    def _update_status_labels(self):
        """Update binary status labels."""
        # MPV
        mpv_path = self.finder.find_mpv(self.mpv_path_edit.text())
        if mpv_path:
            valid, info = self.finder.validate_binary(mpv_path, "mpv")
            if valid:
                self.mpv_status.setText(f"✓ Found: {info}")
                self.mpv_status.setStyleSheet("color: green;")
            else:
                self.mpv_status.setText(f"✗ Invalid: {info}")
                self.mpv_status.setStyleSheet("color: red;")
        else:
            self.mpv_status.setText("✗ Not found")
            self.mpv_status.setStyleSheet("color: red;")
        
        # FFmpeg
        ffmpeg_path = self.finder.find_ffmpeg(self.ffmpeg_path_edit.text())
        if ffmpeg_path:
            valid, info = self.finder.validate_binary(ffmpeg_path, "ffmpeg")
            if valid:
                self.ffmpeg_status.setText(f"✓ Found: {info}")
                self.ffmpeg_status.setStyleSheet("color: green;")
            else:
                self.ffmpeg_status.setText(f"✗ Invalid: {info}")
                self.ffmpeg_status.setStyleSheet("color: red;")
        else:
            self.ffmpeg_status.setText("✗ Not found")
            self.ffmpeg_status.setStyleSheet("color: red;")
        
        # Font
        font_path = self.finder.find_font(self.font_path_edit.text())
        if font_path:
            self.font_status.setText(f"✓ Found: {Path(font_path).name}")
            self.font_status.setStyleSheet("color: green;")
        else:
            self.font_status.setText("✗ Not found")
            self.font_status.setStyleSheet("color: red;")
    
    def _browse_binary(self, binary_type: str):
        """Browse for binary file."""
        if binary_type == "mpv":
            title = "Select MPV Executable"
            edit = self.mpv_path_edit
        else:
            title = "Select FFmpeg Executable"
            edit = self.ffmpeg_path_edit
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            "Executable Files (*)"
        )
        
        if file_path:
            edit.setText(file_path)
            self._update_status_labels()
    
    def _browse_font(self):
        """Browse for font file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Font File",
            "",
            "Font Files (*.ttf *.otf *.ttc);;All Files (*)"
        )
        
        if file_path:
            self.font_path_edit.setText(file_path)
            self._update_status_labels()
    
    def _auto_detect(self, binary_type: str):
        """Auto-detect binary path."""
        if binary_type == "mpv":
            path = self.finder.find_mpv()
            edit = self.mpv_path_edit
        else:
            path = self.finder.find_ffmpeg()
            edit = self.ffmpeg_path_edit
        
        if path:
            edit.setText(path)
            self._update_status_labels()
        else:
            QMessageBox.warning(
                self,
                "Not Found",
                f"Could not auto-detect {binary_type}. Please browse manually or install it."
            )
    
    def _auto_detect_font(self):
        """Auto-detect font path."""
        path = self.finder.find_font()
        if path:
            self.font_path_edit.setText(path)
            self._update_status_labels()
        else:
            QMessageBox.warning(
                self,
                "Not Found",
                "Could not find a suitable font file. Please browse manually."
            )
    
    def _show_install_instructions(self, binary_type: str):
        """Show installation instructions."""
        instructions = self.finder.get_install_instructions(binary_type)
        QMessageBox.information(
            self,
            f"Install {binary_type.upper()}",
            instructions
        )
    
    def _reset_to_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.reset_to_defaults()
            self._load_settings()
            QMessageBox.information(
                self,
                "Reset Complete",
                "All settings have been reset to their default values."
            )
    
    def _save_and_close(self):
        """Save settings and close dialog."""
        # Paths
        self.settings.set("mpv_path", self.mpv_path_edit.text())
        self.settings.set("ffmpeg_path", self.ffmpeg_path_edit.text())
        self.settings.set("font_path", self.font_path_edit.text())
        
        # Titles
        self.settings.set("title_left", self.default_title_left.text())
        self.settings.set("title_right", self.default_title_right.text())
        self.settings.set("title_third", self.default_title_third.text())
        
        # Encoding
        self.settings.set("output_resolution", self.default_resolution.currentText())
        self.settings.set("output_fps", self.default_fps.value())
        self.settings.set("qp_value", self.default_qp.value())
        self.settings.set("gop_size", self.default_gop.value())
        self.settings.set("cpu_preset", self.default_cpu_preset.currentText())
        
        self.accept()

