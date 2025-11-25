"""Drag and drop video zone widget."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, 
    QHBoxLayout, QFileDialog, QLineEdit, QFrame,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent


class DropZoneFrame(QFrame):
    """Frame that accepts drops and handles visual style."""
    
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setMinimumHeight(60) # Reduced minimum height
        self.setObjectName("dropFrame")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    
    def mousePressEvent(self, event):
        """Handle mouse press to emit clicked signal."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class VideoDropZone(QWidget):
    """Widget for drag-and-drop video file selection."""
    
    # Signal emitted when video path changes
    video_changed = pyqtSignal(str)
    
    # Supported video extensions
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.flv', '.m4v'}
    
    def __init__(
        self, 
        label: str = "Video", 
        default_title: str = "",
        show_title_input: bool = False, # Default to False as requested
        optional: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.label_text = label
        self.default_title = default_title
        self.show_title_input = show_title_input
        self.optional = optional
        self._video_path: str = ""
        self._enabled = True
        
        # Removed the aggressive minimum height
        # self.setMinimumHeight(200)
        
        self.setAcceptDrops(True)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the UI components."""
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 1. Header Label
        self.label = QLabel(self.label_text)
        self.label.setStyleSheet("font-weight: 600; font-size: 13px; color: #333;")
        layout.addWidget(self.label)
        
        # 2. Drop Zone (Dashed Box)
        self.drop_frame = DropZoneFrame()
        self.drop_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.drop_frame.clicked.connect(self._browse_file)
        
        # Layout inside the dashed box
        frame_layout = QVBoxLayout(self.drop_frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.prompt_label = QLabel("Drag & Drop Video Here\nor click to Browse")
        self.prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt_label.setStyleSheet("background: transparent; border: none;")
        frame_layout.addWidget(self.prompt_label)
        
        layout.addWidget(self.drop_frame, 1) # Stretch factor 1
        
        # 3. Controls Container (Path + Browse + Clear)
        self.controls_container = QWidget()
        controls_layout = QHBoxLayout(self.controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        
        self.path_display = QLineEdit()
        self.path_display.setPlaceholderText("No video selected")
        self.path_display.setReadOnly(True)
        self.path_display.setStyleSheet("""
            QLineEdit {
                background-color: #fafafa;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                color: #333;
            }
            QLineEdit:disabled {
                background-color: #f5f5f5;
                color: #999;
            }
        """)
        controls_layout.addWidget(self.path_display, 1)
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_file)
        self.browse_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.browse_btn.setFixedWidth(70) # Slightly smaller
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 0px;
                font-size: 12px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #3a7bc8;
            }
            QPushButton:pressed {
                background-color: #2a6bb8;
            }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #a0a0a0;
            }
        """)
        controls_layout.addWidget(self.browse_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        self.clear_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setFixedWidth(50) # Slightly smaller
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 0px;
                font-size: 12px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #4e555b;
            }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #a0a0a0;
            }
        """)
        controls_layout.addWidget(self.clear_btn)
        
        layout.addWidget(self.controls_container)
        
        # 4. Title Input (Removed based on user request, but keeping logic if re-enabled)
        if self.show_title_input:
            title_wrapper = QWidget()
            title_layout = QHBoxLayout(title_wrapper)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(8)
            
            title_label = QLabel("Title:")
            title_label.setStyleSheet("font-size: 12px; color: #555;")
            title_layout.addWidget(title_label)
            
            self.title_input = QLineEdit()
            self.title_input.setPlaceholderText(self.default_title or "Enter title...")
            self.title_input.setText(self.default_title)
            self.title_input.setStyleSheet("""
                QLineEdit {
                    background-color: #fff;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-size: 12px;
                }
                QLineEdit:disabled {
                    background-color: #f5f5f5;
                    color: #999;
                }
            """)
            title_layout.addWidget(self.title_input, 1)
            
            layout.addWidget(title_wrapper)
        else:
            self.title_input = None
        
        # Apply initial styles
        self._apply_styles()
    
    def _apply_styles(self) -> None:
        """Apply visual styles based on state."""
        if not self._enabled:
            # Disabled style
            self.drop_frame.setStyleSheet("""
                #dropFrame {
                    border: 2px dashed #ddd;
                    border-radius: 6px;
                    background-color: #f9f9f9;
                }
            """)
            self.prompt_label.setStyleSheet("color: #ccc; font-size: 13px; font-weight: 500; border: none;")
            self.prompt_label.setText("Disabled")
            self.label.setStyleSheet("font-weight: 600; font-size: 13px; color: #999;")
            
        elif self._video_path:
            # Video selected style
            self.drop_frame.setStyleSheet("""
                #dropFrame {
                    border: 2px solid #28a745;
                    border-radius: 6px;
                    background-color: #f0fff4;
                }
                #dropFrame:hover {
                    border-color: #218838;
                    background-color: #e6fffa;
                }
            """)
            filename = Path(self._video_path).name
            if len(filename) > 35:
                filename = filename[:32] + "..."
            self.prompt_label.setStyleSheet("color: #155724; font-weight: 600; font-size: 13px; border: none;")
            self.prompt_label.setText(f"✓ {filename}")
            self.label.setStyleSheet("font-weight: 600; font-size: 13px; color: #333;")
            
        else:
            # Default style
            self.drop_frame.setStyleSheet("""
                #dropFrame {
                    border: 2px dashed #ccc;
                    border-radius: 6px;
                    background-color: #fafafa;
                }
                #dropFrame:hover {
                    border-color: #4a90d9;
                    background-color: #f0f8ff;
                }
            """)
            self.prompt_label.setStyleSheet("color: #666; font-size: 13px; font-weight: 500; border: none;")
            self.prompt_label.setText("Drag & Drop Video Here\nor click to Browse")
            self.label.setStyleSheet("font-weight: 600; font-size: 13px; color: #333;")

    # ... (Rest of methods are unchanged)
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        if not self._enabled:
            return
            
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and self._is_video_file(urls[0].toLocalFile()):
                event.acceptProposedAction()
                self.drop_frame.setStyleSheet("""
                    #dropFrame {
                        border: 2px dashed #4a90d9;
                        border-radius: 6px;
                        background-color: #e3f2fd;
                    }
                """)
                self.prompt_label.setStyleSheet("color: #1976d2; font-weight: 600; font-size: 13px; border: none;")
                self.prompt_label.setText("Drop Video Now!")

    def dragLeaveEvent(self, event) -> None:
        """Handle drag leave event."""
        self._apply_styles()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event."""
        if not self._enabled:
            return
            
        self._apply_styles()
        
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if self._is_video_file(file_path):
                    self.set_video_path(file_path)
                    event.acceptProposedAction()
    
    def _is_video_file(self, path: str) -> bool:
        """Check if file is a supported video format."""
        return Path(path).suffix.lower() in self.VIDEO_EXTENSIONS
    
    def _browse_file(self) -> None:
        """Open file dialog to browse for video."""
        if not self._enabled:
            return
            
        file_filter = "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.wmv *.flv *.m4v);;All Files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.label_text}",
            "",
            file_filter
        )
        
        if file_path:
            self.set_video_path(file_path)
    
    def set_video_path(self, path: str) -> None:
        """Set the video path."""
        self._video_path = path
        self.path_display.setText(path)
        self.clear_btn.setEnabled(True and self._enabled)
        self._apply_styles()
        
        # Emit signal
        self.video_changed.emit(path)
    
    def get_video_path(self) -> str:
        """Get the current video path."""
        return self._video_path
    
    def get_title(self) -> str:
        """Get the title text."""
        if self.title_input:
            return self.title_input.text() or self.default_title
        return self.default_title
    
    def set_title(self, title: str) -> None:
        """Set the title text."""
        if self.title_input:
            self.title_input.setText(title)
    
    def clear(self) -> None:
        """Clear the video selection."""
        self._video_path = ""
        self.path_display.setText("")
        self.clear_btn.setEnabled(False)
        self._apply_styles()
        self.video_changed.emit("")
    
    def is_valid(self) -> bool:
        """Check if this zone has a valid video selected (or is optional and empty)."""
        if self.optional:
            return True
        return bool(self._video_path) and Path(self._video_path).exists()
    
    def set_enabled_state(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        self._enabled = enabled
        self.setAcceptDrops(enabled)
        
        self.browse_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled and bool(self._video_path))
        self.path_display.setEnabled(enabled)
        self.drop_frame.setEnabled(enabled)
        self.label.setEnabled(enabled)
        
        if self.title_input:
            self.title_input.setEnabled(enabled)
        
        self._apply_styles()
