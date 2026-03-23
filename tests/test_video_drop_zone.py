"""GUI tests for the video drop zone widget."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QPointF, QUrl, Qt
from PyQt6.QtGui import QMouseEvent

from src.widgets.video_drop_zone import DropZoneFrame, VideoDropZone


class FakeDropEvent:
    def __init__(self, file_path: str):
        self._mime_data = QMimeData()
        self._mime_data.setUrls([QUrl.fromLocalFile(file_path)])
        self.accepted = False

    def mimeData(self):
        return self._mime_data

    def acceptProposedAction(self):
        self.accepted = True


def test_video_drop_zone_set_clear_and_optional_validation(qtbot, tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    zone = VideoDropZone("Candidate", default_title="Default", show_title_input=True)
    qtbot.addWidget(zone)

    changed_paths: list[str] = []
    changed_titles: list[str] = []
    zone.video_changed.connect(changed_paths.append)
    zone.title_changed.connect(changed_titles.append)

    zone.set_video_path(str(video_path))
    zone.set_title("Manual Title")

    assert zone.get_video_path() == str(video_path)
    assert zone.get_title() == "Manual Title"
    assert zone.is_valid() is True
    assert changed_paths == [str(video_path)]
    assert changed_titles == ["Manual Title"]

    zone.clear()
    assert zone.get_video_path() == ""
    assert zone.is_valid() is False
    assert changed_paths[-1] == ""

    optional_zone = VideoDropZone("Optional", optional=True)
    qtbot.addWidget(optional_zone)
    assert optional_zone.is_valid() is True


def test_video_drop_zone_drag_drop_browse_and_disable(qtbot, monkeypatch, tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    zone = VideoDropZone("Candidate")
    qtbot.addWidget(zone)

    enter_event = FakeDropEvent(str(video_path))
    zone.dragEnterEvent(enter_event)
    assert enter_event.accepted is True
    assert zone.prompt_label.text() == "Drop Video Now!"

    drop_event = FakeDropEvent(str(video_path))
    zone.dropEvent(drop_event)
    assert drop_event.accepted is True
    assert Path(zone.get_video_path()) == video_path

    monkeypatch.setattr(
        "src.widgets.video_drop_zone.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(video_path), ""),
    )
    zone.clear()
    zone._browse_file()
    assert Path(zone.get_video_path()) == video_path

    zone.set_enabled_state(False)
    assert zone.browse_btn.isEnabled() is False
    assert zone.prompt_label.text() == "Disabled"


def test_drop_zone_frame_emits_clicked_signal(qtbot):
    frame = DropZoneFrame()
    qtbot.addWidget(frame)

    clicks: list[bool] = []
    frame.clicked.connect(lambda: clicks.append(True))

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(frame.rect().center()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    frame.mousePressEvent(event)

    assert clicks == [True]
