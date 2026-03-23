"""Main window for Video Diff Tool."""

from pathlib import Path
from typing import Optional
import threading
import subprocess

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QCheckBox, QMessageBox, QStatusBar,
    QComboBox, QProgressDialog,
    QApplication
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QAction, QIcon

from .app_metadata import APP_NAME, APP_VERSION
from .settings import get_settings
from .binary_finder import get_binary_finder
from .mpv_launcher import get_mpv_launcher
from .video_validator import get_video_validator
from .update_manager import ReleaseInfo, UpdateManager
from .comparison_mode import (
    get_comparison_mode_options,
    get_debug_view_name,
    get_debug_view_options,
    is_debug_view_mode,
)
from .widgets.video_drop_zone import VideoDropZone
from .widgets.encoding_dialog import EncodingDialog
from .widgets.settings_dialog import SettingsDialog


class UpdateCheckWorker(QThread):
    """Background worker for update checks."""

    finished_check = pyqtSignal(object)
    failed_check = pyqtSignal(str)

    def __init__(self, manager: UpdateManager):
        super().__init__()
        self.manager = manager

    def run(self) -> None:
        try:
            release = self.manager.get_latest_compatible_release()
        except RuntimeError as exc:
            self.failed_check.emit(str(exc))
            return

        self.finished_check.emit(release)


class UpdateDownloadWorker(QThread):
    """Background worker for update downloads."""

    progress_changed = pyqtSignal(int, int)
    finished_download = pyqtSignal(str)
    failed_download = pyqtSignal(str)

    def __init__(self, manager: UpdateManager, release: ReleaseInfo):
        super().__init__()
        self.manager = manager
        self.release = release

    def run(self) -> None:
        try:
            archive_path = self.manager.download_release_asset(
                self.release,
                progress_callback=lambda downloaded, total: self.progress_changed.emit(downloaded, total),
            )
        except RuntimeError as exc:
            self.failed_download.emit(str(exc))
            return

        self.finished_download.emit(str(archive_path))


class MainWindow(QMainWindow):
    """Main application window."""
    
    # Signal to show MPV error dialog from background thread
    mpv_error_signal = pyqtSignal(str, str)
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.finder = get_binary_finder()
        self.mpv_launcher = get_mpv_launcher()
        self.validator = get_video_validator()
        self.update_manager = UpdateManager()
        self._update_check_worker: Optional[UpdateCheckWorker] = None
        self._update_download_worker: Optional[UpdateDownloadWorker] = None
        self._update_progress_dialog: Optional[QProgressDialog] = None
        self._pending_release: Optional[ReleaseInfo] = None
        
        # Connect error signal
        self.mpv_error_signal.connect(self._show_mpv_error)
        
        self.setWindowTitle(APP_NAME)
        self._setup_ui()
        self._setup_menu()
        self._load_settings()
        self._update_status()
        self._check_binaries_and_prompt()
        QTimer.singleShot(0, self._start_update_check)
    
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
        header = QLabel(APP_NAME)
        header.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #333;
            padding: 10px 0;
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        self.update_btn = QPushButton()
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._on_update_clicked)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff8c42;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f07620;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        main_layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
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
            show_title_input=True,
            optional=False
        )
        self.video_left.video_changed.connect(self._on_video_changed)
        self.video_left.title_changed.connect(self._on_title_changed)
        main_videos_layout.addWidget(self.video_left)
        
        # Right video (Baseline)
        self.video_right = VideoDropZone(
            label="Right Video (Baseline)",
            default_title=self.settings.get("title_right"),
            show_title_input=True,
            optional=False
        )
        self.video_right.video_changed.connect(self._on_video_changed)
        self.video_right.title_changed.connect(self._on_title_changed)
        main_videos_layout.addWidget(self.video_right)
        
        videos_layout.addLayout(main_videos_layout)

        mode_controls_layout = QHBoxLayout()
        mode_controls_layout.setSpacing(10)

        self.comparison_mode_label = QLabel("Comparison Mode:")
        mode_controls_layout.addWidget(self.comparison_mode_label)

        self.comparison_mode_combo = QComboBox()
        for option in get_comparison_mode_options():
            self.comparison_mode_combo.addItem(option["name"], option["id"])
        self.comparison_mode_combo.currentIndexChanged.connect(self._on_comparison_mode_changed)
        self.comparison_mode_combo.setToolTip("Debug View mode crops one 1080p debug quadrant before preview or encoding.")
        mode_controls_layout.addWidget(self.comparison_mode_combo)

        self.debug_view_label = QLabel("Debug View:")
        mode_controls_layout.addWidget(self.debug_view_label)

        self.debug_view_combo = QComboBox()
        for option in get_debug_view_options():
            self.debug_view_combo.addItem(option["name"], option["id"])
        self.debug_view_combo.currentIndexChanged.connect(self._on_debug_view_changed)
        self.debug_view_combo.setToolTip("Choose which 2160p debug quadrant to compare.")
        mode_controls_layout.addWidget(self.debug_view_combo)
        mode_controls_layout.addStretch()

        videos_layout.addLayout(mode_controls_layout)
        
        # Third video section
        third_section_layout = QHBoxLayout()
        
        # Left side spacer/stretch
        third_section_layout.addStretch()
        
        # Right side container for third video controls
        third_video_container = QVBoxLayout()
        
        # Checkbox to enable third video
        self.enable_third_cb = QCheckBox("Enable Third Video")
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
        
        # Checkbox to show/hide titles (useful if MPV crashes due to missing drawtext)
        self.show_titles_cb = QCheckBox("Show Titles")
        self.show_titles_cb.setChecked(True)
        self.show_titles_cb.setToolTip("Uncheck this if MPV fails to launch due to missing font filters")
        self.show_titles_cb.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #555;
                padding: 5px;
            }
        """)
        third_video_container.addWidget(self.show_titles_cb)
        
        # Checkbox for MPV fullscreen mode
        self.fullscreen_cb = QCheckBox("Fullscreen Mode")
        self.fullscreen_cb.setChecked(self.settings.get("fullscreen_mode", True))
        self.fullscreen_cb.setToolTip("If unchecked, opens MPV in a maximized window instead of fullscreen")
        self.fullscreen_cb.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #555;
                padding: 5px;
            }
        """)
        # Removed from third_video_container to place under preview button

        # Third video drop zone
        self.video_third = VideoDropZone(
            label="Third Video (Bottom Right)",
            default_title=self.settings.get("title_third"),
            show_title_input=True,
            optional=True
        )
        self.video_third.video_changed.connect(self._on_video_changed)
        self.video_third.title_changed.connect(self._on_title_changed)
        self.video_third.set_enabled_state(self.enable_third_cb.isChecked())
        self.video_third.setMaximumWidth(450)
        third_video_container.addWidget(self.video_third)
        
        third_section_layout.addLayout(third_video_container)
        
        videos_layout.addLayout(third_section_layout)
        main_layout.addWidget(videos_group)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        # Preview section (Button + Checkbox)
        preview_container = QVBoxLayout()
        preview_container.setSpacing(5)
        
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
        preview_container.addWidget(self.preview_btn)
        
        # Add fullscreen checkbox here
        preview_container.addWidget(self.fullscreen_cb, alignment=Qt.AlignmentFlag.AlignCenter)
        
        buttons_layout.addLayout(preview_container)
        
        # Encode section (Button + Spacer to align with Preview)
        encode_container = QVBoxLayout()
        encode_container.setSpacing(5)
        
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
        encode_container.addWidget(self.encode_btn)
        
        # Spacer to match the checkbox height in the other column so buttons stay aligned top
        spacer_label = QLabel("")
        spacer_label.setFixedHeight(self.fullscreen_cb.sizeHint().height())
        encode_container.addWidget(spacer_label)
        
        buttons_layout.addLayout(encode_container)
        
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
        self.setMinimumSize(1100, 850)
        self.resize(1100, 850)
    
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
        
        check_updates_action = QAction("Check for Updates", self)
        check_updates_action.triggered.connect(lambda: self._start_update_check(manual=True))
        help_menu.addAction(check_updates_action)

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
        self.show_titles_cb.setChecked(self.settings.get("show_titles"))
        self.fullscreen_cb.setChecked(self.settings.get("fullscreen_mode", True))
        self._set_combo_data(self.comparison_mode_combo, self.settings.get("comparison_mode"))
        self._set_combo_data(self.debug_view_combo, self.settings.get("debug_view"))
        self._update_mode_controls()
    
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
        self.settings.set("show_titles", self.show_titles_cb.isChecked())
        self.settings.set("fullscreen_mode", self.fullscreen_cb.isChecked())
        self.settings.set("comparison_mode", self.comparison_mode_combo.currentData())
        self.settings.set("debug_view", self.debug_view_combo.currentData())
        
        # Third video enabled
        self.settings.set("enable_third_video", self.enable_third_cb.isChecked())

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        """Select a combo entry by its item data."""
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _is_debug_view_mode(self) -> bool:
        """Check whether the active comparison mode crops debug panels."""
        return is_debug_view_mode(self.comparison_mode_combo.currentData())

    def _update_mode_controls(self):
        """Update control visibility and debug-mode-only restrictions."""
        debug_mode = self._is_debug_view_mode()
        self.debug_view_label.setVisible(debug_mode)
        self.debug_view_combo.setVisible(debug_mode)
        self.enable_third_cb.setEnabled(not debug_mode)
        self.video_third.set_enabled_state(
            (not debug_mode) and self.enable_third_cb.isChecked()
        )
    
    def _on_video_changed(self, path: str):
        """Handle video path change."""
        self._update_buttons()
        self._update_layout_preview()

    def _on_title_changed(self, title: str):
        """Handle title change."""
        self._update_layout_preview()

    def _on_comparison_mode_changed(self, index: int):
        """Handle comparison mode change."""
        self._update_mode_controls()
        self._update_buttons()
        self._update_layout_preview()

    def _on_debug_view_changed(self, index: int):
        """Handle debug panel change."""
        self._update_layout_preview()
    
    def _on_third_video_toggle(self, state: int):
        """Handle third video checkbox toggle."""
        self._update_mode_controls()
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
        debug_mode = self._is_debug_view_mode()
        has_third = (
            not debug_mode
            and self.enable_third_cb.isChecked()
            and self.video_third.get_video_path()
        )

        left_title = self.video_left.get_title() or "Left"
        right_title = self.video_right.get_title() or "Right"
        panel_name = get_debug_view_name(self.debug_view_combo.currentData())
        third_title = self.video_third.get_title() or "Third" if has_third else "Black"
        
        # Create ASCII diagram
        width = 50
        half_width = width // 2
        
        def center(text: str, w: int) -> str:
            return text.center(w)
        
        border = "+" + "-" * half_width + "+" + "-" * half_width + "+"
        
        if debug_mode:
            diagram = [
                border,
                "|" + center(left_title[:half_width-2], half_width) + "|" + center(right_title[:half_width-2], half_width) + "|",
                "|" + center(f"({panel_name})", half_width) + "|" + center(f"({panel_name})", half_width) + "|",
                border,
                "|" + center(f"Diff {panel_name}"[:half_width-2], half_width) + "|" + center("Black", half_width) + "|",
                "|" + center("(Debug View)", half_width) + "|" + center("(Empty)", half_width) + "|",
                border,
            ]
        else:
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

    def _start_update_check(self, manual: bool = False):
        """Check GitHub for a newer packaged release."""
        if not self.update_manager.get_release_asset_suffix():
            if manual:
                QMessageBox.information(
                    self,
                    "Updates Unavailable",
                    "Automatic updates are only available for packaged macOS arm64 and Windows x64 releases.",
                )
            return

        if self._update_check_worker and self._update_check_worker.isRunning():
            return

        self._update_check_worker = UpdateCheckWorker(self.update_manager)
        self._update_check_worker.finished_check.connect(
            lambda release, manual=manual: self._on_update_check_finished(release, manual)
        )
        self._update_check_worker.failed_check.connect(
            lambda error, manual=manual: self._on_update_check_failed(error, manual)
        )
        self._update_check_worker.start()

    def _on_update_check_finished(self, release: Optional[ReleaseInfo], manual: bool):
        """Handle a completed update check."""
        self._pending_release = release
        if release is None:
            self.update_btn.setVisible(False)
            if manual:
                QMessageBox.information(
                    self,
                    "No Updates",
                    f"You are already on the latest compatible release ({APP_VERSION}).",
                )
            return

        if not self.update_manager.supports_auto_update():
            self.update_btn.setVisible(False)
            if manual:
                QMessageBox.information(
                    self,
                    "Update Available",
                    (
                        f"A newer packaged release is available: {release.tag_name}\n\n"
                        "Automatic installation is only supported from packaged macOS arm64 and Windows x64 builds."
                    ),
                )
            return

        self.update_btn.setText(f"Update to {release.tag_name}")
        self.update_btn.setToolTip(f"Download and install {release.tag_name}, then restart.")
        self.update_btn.setEnabled(True)
        self.update_btn.setVisible(True)

        if manual:
            QMessageBox.information(
                self,
                "Update Available",
                f"A newer release is available: {release.tag_name}",
            )

    def _on_update_check_failed(self, error: str, manual: bool):
        """Handle update check failures."""
        if manual:
            QMessageBox.warning(self, "Update Check Failed", error)

    def _on_update_clicked(self):
        """Download and install the discovered update."""
        release = self._pending_release
        if release is None:
            return

        if not self.update_manager.supports_auto_update():
            QMessageBox.information(
                self,
                "Automatic Updates Unavailable",
                "This build is not a packaged app bundle, so it cannot replace itself automatically.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Install Update",
            f"Download {release.tag_name}, replace the current app, and restart automatically?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.update_btn.setEnabled(False)
        self._update_progress_dialog = QProgressDialog("Downloading update...", "", 0, 100, self)
        self._update_progress_dialog.setWindowTitle("Updating")
        self._update_progress_dialog.setCancelButton(None)
        self._update_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._update_progress_dialog.setMinimumDuration(0)
        self._update_progress_dialog.show()

        self._update_download_worker = UpdateDownloadWorker(self.update_manager, release)
        self._update_download_worker.progress_changed.connect(self._on_update_download_progress)
        self._update_download_worker.finished_download.connect(self._on_update_download_finished)
        self._update_download_worker.failed_download.connect(self._on_update_download_failed)
        self._update_download_worker.start()

    def _on_update_download_progress(self, downloaded: int, total: int):
        """Update download progress text."""
        if not self._update_progress_dialog:
            return

        if total > 0:
            percent = int(downloaded * 100 / total)
            self._update_progress_dialog.setMaximum(100)
            self._update_progress_dialog.setValue(percent)
            self._update_progress_dialog.setLabelText(f"Downloading update... {percent}%")
        else:
            self._update_progress_dialog.setMaximum(0)
            self._update_progress_dialog.setLabelText("Downloading update...")

    def _on_update_download_finished(self, archive_path: str):
        """Apply the downloaded update and restart."""
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        try:
            self.update_manager.prepare_update_and_restart(Path(archive_path))
        except RuntimeError as exc:
            self._on_update_download_failed(str(exc))
            return

        QMessageBox.information(
            self,
            "Restarting",
            "The update has been downloaded. The application will now restart to finish installing it.",
        )
        QTimer.singleShot(0, QApplication.instance().quit)

    def _on_update_download_failed(self, error: str):
        """Handle update download failures."""
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        self.update_btn.setEnabled(True)
        QMessageBox.warning(self, "Update Failed", error)
    
    def _monitor_mpv_process(self, proc: subprocess.Popen):
        """Monitor MPV process for immediate startup errors."""
        try:
            # Wait briefly to see if it crashes immediately
            proc.wait(timeout=2.0)
            
            # If we get here, process exited within 2 seconds
            if proc.returncode != 0:
                # Read stderr
                stderr_output = proc.stderr.read() if proc.stderr else ""
                
                error_msg = f"MPV exited with code {proc.returncode}"
                advice = "Please check your MPV installation."
                
                if "No such filter: 'drawtext'" in stderr_output:
                    error_msg = "MPV failed because 'drawtext' filter is missing."
                    advice = "This usually happens with 'lite' MPV builds.\n\nSOLUTION: Uncheck the 'Show Titles' box in the bottom right to disable text overlays."
                elif "No option name near" in stderr_output:
                    error_msg = "MPV failed due to path parsing error."
                    advice = "This might be due to special characters in the file path."
                
                # Emit signal to show dialog on main thread
                self.mpv_error_signal.emit(error_msg, advice)
                
        except subprocess.TimeoutExpired:
            # Process is still running after 2 seconds, assume success
            pass
        except Exception as e:
            print(f"Error monitoring MPV: {e}")

    def _show_mpv_error(self, error: str, advice: str):
        """Show MPV error dialog."""
        QMessageBox.warning(
            self,
            "MPV Launch Failed",
            f"{error}\n\n{advice}"
        )

    def _launch_mpv(self):
        """Launch MPV preview."""
        try:
            comparison_mode = self.comparison_mode_combo.currentData()
            debug_view = self.debug_view_combo.currentData()
            debug_mode = self._is_debug_view_mode()
            video_third = None
            if not debug_mode and self.enable_third_cb.isChecked() and self.video_third.get_video_path():
                video_third = self.video_third.get_video_path()

            if debug_mode:
                valid, error, _ = self.validator.validate_videos_for_debug_view(
                    self.video_left.get_video_path(),
                    self.video_right.get_video_path(),
                )
                if not valid:
                    QMessageBox.critical(self, "Validation Error", error)
                    return
            
            proc = self.mpv_launcher.launch(
                video_left=self.video_left.get_video_path(),
                video_right=self.video_right.get_video_path(),
                video_third=video_third,
                title_left=self.video_left.get_title(),
                title_right=self.video_right.get_title(),
                title_third=self.video_third.get_title() if video_third else None,
                show_titles=self.show_titles_cb.isChecked(),
                fullscreen=self.fullscreen_cb.isChecked(),
                comparison_mode=comparison_mode,
                debug_view=debug_view,
            )
            
            # Monitor process in background thread
            threading.Thread(
                target=self._monitor_mpv_process, 
                args=(proc,), 
                daemon=True
            ).start()
            
        except RuntimeError as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to launch MPV: {e}\n\nPlease check your MPV installation in Settings."
            )
    
    def _show_encode_dialog(self):
        """Show encoding dialog."""
        debug_mode = self._is_debug_view_mode()
        video_third = None
        if not debug_mode and self.enable_third_cb.isChecked() and self.video_third.get_video_path():
            video_third = self.video_third.get_video_path()
        
        dialog = EncodingDialog(
            video_left=self.video_left.get_video_path(),
            video_right=self.video_right.get_video_path(),
            title_left=self.video_left.get_title(),
            title_right=self.video_right.get_title(),
            video_third=video_third,
            title_third=self.video_third.get_title() if video_third else "",
            comparison_mode=self.comparison_mode_combo.currentData(),
            debug_view=self.debug_view_combo.currentData(),
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
            f"About {APP_NAME}",
            f"<h2>{APP_NAME}</h2>"
            "<p>A tool for comparing videos side-by-side with difference visualization.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Preview comparisons with MPV</li>"
            "<li>Encode comparisons with FFmpeg 4:4:4 output</li>"
            "<li>Support for NVENC hardware-accelerated encoding</li>"
            "<li>Crop 4K debug videos to Display, Flow, Mask, or Warped panels</li>"
            "<li>Check GitHub for packaged app updates</li>"
            "<li>Customizable titles and settings</li>"
            "</ul>"
            f"<p>Version {APP_VERSION}</p>"
        )
    
    def closeEvent(self, event):
        """Handle close event."""
        self._save_settings()
        event.accept()
