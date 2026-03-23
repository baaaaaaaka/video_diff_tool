"""GUI tests for the encoding dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from src.settings import get_settings
from src.widgets.encoding_dialog import EncodingDialog


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class FakeEncoder:
    def normalize_encoder_id(self, value: str) -> str:
        return "cpu" if value == "cpu_h264_444" else value


class FakeValidator:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.debug_calls = []
        self.compare_calls = []

    def validate_videos_for_debug_view(self, left: str, right: str):
        self.debug_calls.append((left, right))
        return self.valid, ("" if self.valid else "debug validation failed"), {}

    def validate_videos_for_comparison(self, left: str, right: str, third: str | None):
        self.compare_calls.append((left, right, third))
        return self.valid, ("" if self.valid else "comparison validation failed"), {}


class FakeWorker:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.cancelled = False
        self.waited = False
        self.progress_updated = _Signal()
        self.log_updated = _Signal()
        self.finished_encoding = _Signal()
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def wait(self):
        self.waited = True


class FakeCloseEvent:
    def __init__(self):
        self.accepted = False
        self.ignored = False

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _make_dialog(monkeypatch, qtbot, tmp_path, comparison_mode="standard", debug_view="display"):
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    third = tmp_path / "third.mp4"
    for path in (left, right, third):
        path.write_text("x", encoding="utf-8")

    monkeypatch.setattr("src.widgets.encoding_dialog.get_ffmpeg_encoder", lambda: FakeEncoder())
    validator = FakeValidator()
    monkeypatch.setattr("src.widgets.encoding_dialog.get_video_validator", lambda: validator)
    monkeypatch.setattr(EncodingDialog, "_start_encoder_loading", lambda self: None)

    dialog = EncodingDialog(
        video_left=str(left),
        video_right=str(right),
        video_third=str(third),
        title_left="Candidate",
        title_right="Baseline",
        title_third="Reference",
        comparison_mode=comparison_mode,
        debug_view=debug_view,
    )
    qtbot.addWidget(dialog)
    dialog.validator = validator
    return dialog, validator


def test_encoding_dialog_loads_encoders_and_toggles_cpu_preset(qtbot, monkeypatch, tmp_path):
    settings = get_settings()
    settings.set("encoder", "cpu_h264_444")

    dialog, _validator = _make_dialog(monkeypatch, qtbot, tmp_path)

    dialog._on_encoders_loaded(
        [
            {"id": "cpu", "name": "CPU (libx264 H.264 4:4:4)"},
            {"id": "hevc_nvenc", "name": "NVENC (NVIDIA)"},
        ]
    )

    assert dialog.encoder_combo.currentData() == "cpu"
    assert not dialog.cpu_preset_combo.isHidden()
    dialog.encoder_combo.setCurrentIndex(0)
    dialog._on_encoder_changed()
    assert dialog.cpu_preset_combo.isHidden()


def test_encoding_dialog_start_encoding_uses_debug_validation(qtbot, monkeypatch, tmp_path):
    dialog, validator = _make_dialog(
        monkeypatch,
        qtbot,
        tmp_path,
        comparison_mode="debug_view",
        debug_view="flow",
    )
    dialog.output_path_edit.setText(str(tmp_path / "out.mp4"))
    dialog._on_encoders_loaded([{"id": "cpu", "name": "CPU (libx264 H.264 4:4:4)"}])

    FakeWorker.instances.clear()
    monkeypatch.setattr("src.widgets.encoding_dialog.EncodingWorker", FakeWorker)

    dialog._start_encoding()

    assert validator.debug_calls == [(dialog.video_left, dialog.video_right)]
    assert validator.compare_calls == []
    assert FakeWorker.instances[-1].kwargs["video_third"] is None
    assert FakeWorker.instances[-1].kwargs["comparison_mode"] == "debug_view"
    assert FakeWorker.instances[-1].started is True
    assert dialog.cancel_btn.isEnabled()
    assert not dialog.encode_btn.isEnabled()
    dialog._on_finished(False)


def test_encoding_dialog_validation_failure_and_finish_success(qtbot, monkeypatch, tmp_path):
    dialog, validator = _make_dialog(monkeypatch, qtbot, tmp_path)
    dialog.output_path_edit.setText(str(tmp_path / "out.mp4"))
    dialog._on_encoders_loaded([{"id": "cpu", "name": "CPU (libx264 H.264 4:4:4)"}])
    validator.valid = False

    critical_messages: list[str] = []
    info_messages: list[str] = []
    monkeypatch.setattr(
        "src.widgets.encoding_dialog.QMessageBox.critical",
        lambda parent, title, text: critical_messages.append(text),
    )
    monkeypatch.setattr(
        "src.widgets.encoding_dialog.QMessageBox.information",
        lambda parent, title, text: info_messages.append(text),
    )
    monkeypatch.setattr("src.widgets.encoding_dialog.EncodingWorker", FakeWorker)

    dialog._start_encoding()
    assert critical_messages == ["comparison validation failed"]

    dialog._on_finished(True)
    assert dialog.progress_bar.value() == 100
    assert dialog.progress_label.text() == "Encoding completed successfully!"
    assert info_messages and "Video encoded successfully!" in info_messages[0]


def test_encoding_dialog_close_event_cancels_worker_when_confirmed(qtbot, monkeypatch, tmp_path):
    dialog, _validator = _make_dialog(monkeypatch, qtbot, tmp_path)
    worker = FakeWorker()
    dialog._worker = worker
    dialog._is_encoding = True

    monkeypatch.setattr(
        "src.widgets.encoding_dialog.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    event = FakeCloseEvent()
    dialog.closeEvent(event)

    assert worker.cancelled is True
    assert worker.waited is True
    assert event.accepted is True
