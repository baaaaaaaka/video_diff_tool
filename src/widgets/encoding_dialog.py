"""Encoding dialog with progress and log display."""

from pathlib import Path
from typing import Optional, List, Dict
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QGroupBox, QFormLayout, QComboBox,
    QSpinBox, QFileDialog, QLineEdit, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ..settings import get_settings
from ..ffmpeg_encoder import get_ffmpeg_encoder, EncodingProgress
from ..video_validator import get_video_validator


class EncoderLoader(QThread):
    """Worker thread for loading encoders."""
    
    encoders_loaded = pyqtSignal(list)
    
    def __init__(self, encoder_instance):
        super().__init__()
        self.encoder = encoder_instance
        
    def run(self):
        """Load encoders."""
        encoders = self.encoder.get_available_encoders()
        self.encoders_loaded.emit(encoders)


class EncodingWorker(QThread):
    """Worker thread for encoding."""
    
    progress_updated = pyqtSignal(object)  # EncodingProgress
    log_updated = pyqtSignal(str)
    finished_encoding = pyqtSignal(bool)  # success
    
    def __init__(
        self,
        video_left: str,
        video_right: str,
        output_path: str,
        video_third: Optional[str],
        title_left: str,
        title_right: str,
        title_third: str,
        output_width: int,
        output_height: int,
        output_fps: int,
        qp: int,
        gop: int,
        encoder: str,
        cpu_preset: str,
    ):
        super().__init__()
        self.video_left = video_left
        self.video_right = video_right
        self.output_path = output_path
        self.video_third = video_third
        self.title_left = title_left
        self.title_right = title_right
        self.title_third = title_third
        self.output_width = output_width
        self.output_height = output_height
        self.output_fps = output_fps
        self.qp = qp
        self.gop = gop
        self.encoder = encoder
        self.cpu_preset = cpu_preset
        self._encoder = get_ffmpeg_encoder()
    
    def run(self):
        """Run encoding."""
        success = self._encoder.encode(
            video_left=self.video_left,
            video_right=self.video_right,
            output_path=self.output_path,
            video_third=self.video_third,
            title_left=self.title_left,
            title_right=self.title_right,
            title_third=self.title_third,
            output_width=self.output_width,
            output_height=self.output_height,
            output_fps=self.output_fps,
            qp=self.qp,
            gop=self.gop,
            encoder=self.encoder,
            cpu_preset=self.cpu_preset,
            progress_callback=lambda p: self.progress_updated.emit(p),
            log_callback=lambda l: self.log_updated.emit(l),
        )
        self.finished_encoding.emit(success)
    
    def cancel(self):
        """Cancel encoding."""
        self._encoder.cancel()


class EncodingDialog(QDialog):
    """Dialog for configuring and running FFmpeg encoding."""
    
    def __init__(
        self,
        video_left: str,
        video_right: str,
        title_left: str,
        title_right: str,
        video_third: Optional[str] = None,
        title_third: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.video_left = video_left
        self.video_right = video_right
        self.video_third = video_third
        self.title_left = title_left
        self.title_right = title_right
        self.title_third = title_third
        
        self.settings = get_settings()
        self.encoder = get_ffmpeg_encoder()
        self.validator = get_video_validator()
        self._worker: Optional[EncodingWorker] = None
        self._loader: Optional[EncoderLoader] = None
        self._is_encoding = False
        
        self.setWindowTitle("Encode Video Comparison")
        self.setMinimumSize(700, 600)
        self.setModal(True)
        
        self._setup_ui()
        self._load_settings()
        self._start_encoder_loading()
    
    def _setup_ui(self):
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # Output settings group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_group)
        
        # Output file
        output_file_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output file...")
        output_file_layout.addWidget(self.output_path_edit, 1)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output)
        output_file_layout.addWidget(browse_btn)
        output_layout.addRow("Output File:", output_file_layout)
        
        # Resolution
        res_layout = QHBoxLayout()
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["2160p", "1080p", "720p", "Custom"])
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        res_layout.addWidget(self.resolution_combo)
        
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 7680)
        self.width_spin.setValue(3840)
        self.width_spin.setEnabled(False)
        res_layout.addWidget(QLabel("W:"))
        res_layout.addWidget(self.width_spin)
        
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 4320)
        self.height_spin.setValue(2160)
        self.height_spin.setEnabled(False)
        res_layout.addWidget(QLabel("H:"))
        res_layout.addWidget(self.height_spin)
        output_layout.addRow("Resolution:", res_layout)
        
        # FPS
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(60)
        output_layout.addRow("Output FPS:", self.fps_spin)
        
        layout.addWidget(output_group)
        
        # Encoding settings group
        enc_group = QGroupBox("Encoding Settings")
        enc_layout = QFormLayout(enc_group)
        
        # Encoder
        self.encoder_combo = QComboBox()
        enc_layout.addRow("Encoder:", self.encoder_combo)
        
        # CPU preset (shown only for CPU encoder)
        self.cpu_preset_combo = QComboBox()
        self.cpu_preset_combo.addItems([
            "ultrafast", "superfast", "veryfast", "faster", 
            "fast", "medium", "slow", "slower", "veryslow"
        ])
        self.cpu_preset_combo.setCurrentText("veryfast")
        self.cpu_preset_label = QLabel("CPU Preset:")
        enc_layout.addRow(self.cpu_preset_label, self.cpu_preset_combo)
        
        # QP
        self.qp_spin = QSpinBox()
        self.qp_spin.setRange(0, 51)
        self.qp_spin.setValue(17)
        enc_layout.addRow("QP (Quality):", self.qp_spin)
        
        # GOP
        self.gop_spin = QSpinBox()
        self.gop_spin.setRange(1, 600)
        self.gop_spin.setValue(30)
        enc_layout.addRow("GOP Size:", self.gop_spin)
        
        layout.addWidget(enc_group)
        
        # Progress group
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        # Progress info
        self.progress_label = QLabel("Ready to encode")
        progress_layout.addWidget(self.progress_label)
        
        # Log output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: "SF Mono", "Menlo", "Monaco", "Consolas", "Courier New", monospace;
                font-size: 11px;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        progress_layout.addWidget(self.log_text)
        
        layout.addWidget(progress_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.encode_btn = QPushButton("Start Encoding")
        self.encode_btn.clicked.connect(self._start_encoding)
        self.encode_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        btn_layout.addWidget(self.encode_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_encoding)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        btn_layout.addWidget(self.cancel_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("""
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
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_settings(self):
        """Load settings into UI."""
        # Resolution
        resolution = self.settings.get("output_resolution")
        self.resolution_combo.setCurrentText(resolution)
        self.width_spin.setValue(self.settings.get("custom_width"))
        self.height_spin.setValue(self.settings.get("custom_height"))
        
        # FPS
        self.fps_spin.setValue(self.settings.get("output_fps"))
        
        # Encoding
        self.qp_spin.setValue(self.settings.get("qp_value"))
        self.gop_spin.setValue(self.settings.get("gop_size"))
        self.cpu_preset_combo.setCurrentText(self.settings.get("cpu_preset"))
        
        # Default output path
        last_output_dir = self.settings.get("last_output_dir")
        if last_output_dir and Path(last_output_dir).exists():
            default_output = Path(last_output_dir) / "comparison_output.mp4"
        else:
            default_output = Path(self.video_left).parent / "comparison_output.mp4"
        self.output_path_edit.setText(str(default_output))
    
    def _save_settings(self):
        """Save current settings."""
        self.settings.set("output_resolution", self.resolution_combo.currentText())
        self.settings.set("custom_width", self.width_spin.value())
        self.settings.set("custom_height", self.height_spin.value())
        self.settings.set("output_fps", self.fps_spin.value())
        self.settings.set("qp_value", self.qp_spin.value())
        self.settings.set("gop_size", self.gop_spin.value())
        self.settings.set("cpu_preset", self.cpu_preset_combo.currentText())
        self.settings.set("encoder", self.encoder_combo.currentData())
        
        output_path = self.output_path_edit.text()
        if output_path:
            self.settings.set("last_output_dir", str(Path(output_path).parent))
    
    def _start_encoder_loading(self):
        """Start background thread to load encoders."""
        self.encoder_combo.clear()
        self.encoder_combo.addItem("Loading encoders...", "cpu")
        self.encoder_combo.setEnabled(False)
        self.encode_btn.setEnabled(False)
        
        self._loader = EncoderLoader(self.encoder)
        self._loader.encoders_loaded.connect(self._on_encoders_loaded)
        self._loader.start()
    
    def _on_encoders_loaded(self, encoders: List[Dict[str, str]]):
        """Handle encoders loaded event."""
        self.encoder_combo.clear()
        
        # Add auto option
        self.encoder_combo.addItem("Auto (NVENC if Available)", "auto")
        
        # Add available encoders
        for enc in encoders:
            self.encoder_combo.addItem(enc["name"], enc["id"])
        
        self.encoder_combo.setEnabled(True)
        self.encode_btn.setEnabled(True)
        
        # Set saved encoder if available
        saved_encoder = self.encoder.normalize_encoder_id(self.settings.get("encoder"))
        for i in range(self.encoder_combo.count()):
            if self.encoder_combo.itemData(i) == saved_encoder:
                self.encoder_combo.setCurrentIndex(i)
                break
        
        # Connect signal to show/hide CPU preset
        # Disconnect first to avoid multiple connections if reloaded (though unlikely here)
        try:
            self.encoder_combo.currentIndexChanged.disconnect(self._on_encoder_changed)
        except TypeError:
            pass
        self.encoder_combo.currentIndexChanged.connect(self._on_encoder_changed)
        self._on_encoder_changed()
    
    def _on_encoder_changed(self):
        """Handle encoder selection change."""
        encoder = self.encoder_combo.currentData()
        is_cpu = encoder == "cpu"
        self.cpu_preset_combo.setVisible(is_cpu)
        self.cpu_preset_label.setVisible(is_cpu)
    
    def _on_resolution_changed(self, text: str):
        """Handle resolution preset change."""
        is_custom = text == "Custom"
        self.width_spin.setEnabled(is_custom)
        self.height_spin.setEnabled(is_custom)
        
        if not is_custom:
            presets = {"2160p": (3840, 2160), "1080p": (1920, 1080), "720p": (1280, 720)}
            if text in presets:
                w, h = presets[text]
                self.width_spin.setValue(w)
                self.height_spin.setValue(h)
    
    def _browse_output(self):
        """Browse for output file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output Video",
            self.output_path_edit.text(),
            "MP4 Video (*.mp4)"
        )
        if file_path:
            if not file_path.lower().endswith('.mp4'):
                file_path += '.mp4'
            self.output_path_edit.setText(file_path)
    
    def _start_encoding(self):
        """Start encoding process."""
        # Validate output path
        output_path = self.output_path_edit.text()
        if not output_path:
            QMessageBox.warning(self, "Error", "Please specify output file path.")
            return
        
        # Save settings
        self._save_settings()
        
        # Validate videos
        has_third = self.video_third and Path(self.video_third).exists()
        valid, error, _ = self.validator.validate_videos_for_comparison(
            self.video_left, 
            self.video_right,
            self.video_third if has_third else None
        )
        
        if not valid:
            QMessageBox.critical(self, "Validation Error", error)
            return
        
        # Get settings
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        # Update UI
        self._is_encoding = True
        self.encode_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.progress_label.setText("Starting encoding...")
        
        # Create worker
        self._worker = EncodingWorker(
            video_left=self.video_left,
            video_right=self.video_right,
            output_path=output_path,
            video_third=self.video_third if has_third else None,
            title_left=self.title_left,
            title_right=self.title_right,
            title_third=self.title_third,
            output_width=width,
            output_height=height,
            output_fps=self.fps_spin.value(),
            qp=self.qp_spin.value(),
            gop=self.gop_spin.value(),
            encoder=self.encoder_combo.currentData(),
            cpu_preset=self.cpu_preset_combo.currentText(),
        )
        
        # Connect signals
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.log_updated.connect(self._on_log)
        self._worker.finished_encoding.connect(self._on_finished)
        
        # Start
        self._worker.start()
    
    def _cancel_encoding(self):
        """Cancel encoding process."""
        if self._worker:
            self._worker.cancel()
    
    def _on_progress(self, progress: EncodingProgress):
        """Handle progress update."""
        self.progress_bar.setValue(int(progress.percent))
        self.progress_label.setText(
            f"Frame {progress.frame}/{progress.total_frames} | "
            f"FPS: {progress.fps:.1f} | "
            f"Speed: {progress.speed} | "
            f"Time: {progress.time}"
        )
    
    def _on_log(self, line: str):
        """Handle log update."""
        self.log_text.append(line.rstrip())
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _on_finished(self, success: bool):
        """Handle encoding finished."""
        self._is_encoding = False
        self.encode_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        
        if success:
            self.progress_bar.setValue(100)
            self.progress_label.setText("Encoding completed successfully!")
            QMessageBox.information(
                self, 
                "Success", 
                f"Video encoded successfully!\n\nOutput: {self.output_path_edit.text()}"
            )
        else:
            self.progress_label.setText("Encoding failed or cancelled.")
    
    def closeEvent(self, event):
        """Handle close event."""
        if self._is_encoding:
            reply = QMessageBox.question(
                self,
                "Confirm Close",
                "Encoding is in progress. Are you sure you want to cancel and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self._worker:
                    self._worker.cancel()
                    self._worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
