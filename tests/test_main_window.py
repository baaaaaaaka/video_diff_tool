"""GUI tests for the main window."""

from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from src.binary_finder import BinaryFinder
from src.main_window import MainWindow
from src.update_manager import ReleaseInfo, ReleaseVersion


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class FakeDownloadWorker:
    instances = []

    def __init__(self, manager, release):
        self.manager = manager
        self.release = release
        self.started = False
        self.progress_changed = _Signal()
        self.finished_download = _Signal()
        self.failed_download = _Signal()
        self.__class__.instances.append(self)

    def start(self):
        self.started = True


class FakeProgressDialog:
    def __init__(self, *args, **kwargs):
        self.visible = False
        self.closed = False
        self.maximum = None
        self.value = None
        self.label_text = None

    def setWindowTitle(self, title):
        self.window_title = title

    def setCancelButton(self, button):
        self.cancel_button = button

    def setWindowModality(self, modality):
        self.modality = modality

    def setMinimumDuration(self, duration):
        self.minimum_duration = duration

    def show(self):
        self.visible = True

    def setMaximum(self, maximum):
        self.maximum = maximum

    def setValue(self, value):
        self.value = value

    def setLabelText(self, text):
        self.label_text = text

    def close(self):
        self.closed = True


def _build_window(qtbot, monkeypatch, tmp_path):
    dummy_binary = tmp_path / "dummy"
    dummy_binary.write_text("x", encoding="utf-8")

    monkeypatch.setattr(MainWindow, "_check_binaries_and_prompt", lambda self: None)
    monkeypatch.setattr("src.main_window.QTimer.singleShot", lambda delay, callback: None)
    monkeypatch.setattr(BinaryFinder, "find_mpv", lambda self, custom_path="": str(dummy_binary))
    monkeypatch.setattr(BinaryFinder, "find_ffmpeg", lambda self, custom_path="": str(dummy_binary))
    monkeypatch.setattr(BinaryFinder, "find_font", lambda self, custom_path="": str(dummy_binary))

    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_debug_mode_disables_third_video(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)

    assert window.debug_view_combo.isHidden()
    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    assert not window.debug_view_combo.isHidden()
    assert not window.enable_third_cb.isEnabled()


def test_update_button_is_shown_for_new_release(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, "_check_binaries_and_prompt", lambda self: None)
    monkeypatch.setattr("src.main_window.QTimer.singleShot", lambda delay, callback: None)
    monkeypatch.setattr("src.main_window.UpdateManager.supports_auto_update", lambda self: True)

    window = MainWindow()
    qtbot.addWidget(window)

    release = ReleaseInfo(
        tag_name="v1.4.0-rc3",
        version=ReleaseVersion.parse("1.4.0-rc3"),
        published_at="2026-03-24T00:00:00Z",
        prerelease=True,
        asset_name="VideoDiffTool-v1.4.0-rc3-windows-x64.zip",
        asset_url="https://example.invalid/download.zip",
    )

    window._on_update_check_finished(release, manual=False)

    assert not window.update_btn.isHidden()
    assert "v1.4.0-rc3" in window.update_btn.text()


def test_layout_preview_updates_for_standard_and_debug_modes(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)

    window.video_left.set_title("Candidate")
    window.video_right.set_title("Baseline")
    window._update_layout_preview()
    assert "Difference" in window.layout_preview.text()

    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._set_combo_data(window.debug_view_combo, "flow")
    window._on_comparison_mode_changed(0)
    window._update_layout_preview()

    assert "Diff Flow" in window.layout_preview.text()
    assert "(Debug View)" in window.layout_preview.text()


def test_launch_mpv_handles_validation_errors_and_success(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    third = tmp_path / "third.mp4"
    for path in (left, right, third):
        path.write_text("x", encoding="utf-8")

    window.video_left.set_video_path(str(left))
    window.video_right.set_video_path(str(right))
    window.video_third.set_video_path(str(third))
    window.enable_third_cb.setChecked(True)
    window._on_third_video_toggle(1)

    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    critical_messages = []
    monkeypatch.setattr(
        "src.main_window.QMessageBox.critical",
        lambda parent, title, text: critical_messages.append(text),
    )
    monkeypatch.setattr(
        window.validator,
        "validate_videos_for_debug_view",
        lambda left_path, right_path: (False, "debug validation failed", {}),
    )

    window._launch_mpv()
    assert critical_messages == ["debug validation failed"]

    window._set_combo_data(window.comparison_mode_combo, "standard")
    window._on_comparison_mode_changed(0)

    launched = {}

    class DummyProcess:
        pass

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            launched["thread_target"] = target
            launched["thread_args"] = args
            launched["thread_daemon"] = daemon

        def start(self):
            launched["thread_started"] = True

    monkeypatch.setattr(
        window.mpv_launcher,
        "launch",
        lambda **kwargs: launched.setdefault("launch_kwargs", kwargs) or DummyProcess(),
    )
    monkeypatch.setattr("src.main_window.threading.Thread", FakeThread)

    window._launch_mpv()

    assert launched["launch_kwargs"]["video_third"] == str(third)
    assert launched["launch_kwargs"]["comparison_mode"] == "standard"
    assert launched["thread_started"] is True


def test_start_update_check_and_download_flow(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)

    info_messages = []
    warning_messages = []
    monkeypatch.setattr(
        window.update_manager,
        "get_release_asset_suffix",
        lambda: None,
    )
    monkeypatch.setattr(
        "src.main_window.QMessageBox.information",
        lambda parent, title, text: info_messages.append((title, text)),
    )
    monkeypatch.setattr(
        "src.main_window.QMessageBox.warning",
        lambda parent, title, text: warning_messages.append((title, text)),
    )

    window._start_update_check(manual=True)
    assert info_messages and info_messages[-1][0] == "Updates Unavailable"

    release = ReleaseInfo(
        tag_name="v1.4.0-rc8",
        version=ReleaseVersion.parse("1.4.0-rc8"),
        published_at="2026-03-24T00:00:00Z",
        prerelease=True,
        asset_name="VideoDiffTool-v1.4.0-rc8-windows-x64.zip",
        asset_url="https://example.invalid/download.zip",
    )
    window._pending_release = release
    monkeypatch.setattr(window.update_manager, "supports_auto_update", lambda: True)
    monkeypatch.setattr(
        "src.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr("src.main_window.QProgressDialog", FakeProgressDialog)
    FakeDownloadWorker.instances.clear()
    monkeypatch.setattr("src.main_window.UpdateDownloadWorker", FakeDownloadWorker)

    window._on_update_clicked()

    assert FakeDownloadWorker.instances[-1].started is True
    assert window.update_btn.isEnabled() is False
    assert isinstance(window._update_progress_dialog, FakeProgressDialog)

    window._on_update_download_progress(25, 100)
    assert window._update_progress_dialog.value == 25
    assert "25%" in window._update_progress_dialog.label_text

    window._on_update_download_failed("network failed")
    assert window.update_btn.isEnabled() is True
    assert warning_messages[-1] == ("Update Failed", "network failed")


def test_update_download_finished_and_mpv_monitoring(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    window._update_progress_dialog = FakeProgressDialog()

    prepared_archives = []
    info_messages = []
    timer_calls = []
    mpv_errors = []

    monkeypatch.setattr(
        window.update_manager,
        "prepare_update_and_restart",
        lambda archive_path: prepared_archives.append(Path(archive_path)),
    )
    monkeypatch.setattr(
        "src.main_window.QMessageBox.information",
        lambda parent, title, text: info_messages.append((title, text)),
    )
    monkeypatch.setattr(
        "src.main_window.QTimer.singleShot",
        lambda delay, callback: timer_calls.append(delay),
    )
    window.mpv_error_signal.disconnect()
    window.mpv_error_signal.connect(lambda error, advice: mpv_errors.append((error, advice)))

    window._on_update_download_finished(str(tmp_path / "update.zip"))

    assert prepared_archives == [tmp_path / "update.zip"]
    assert info_messages[-1][0] == "Restarting"
    assert timer_calls == [0]
    assert window._update_progress_dialog is None

    class FailedProcess:
        returncode = 1

        def __init__(self):
            self.stderr = type("Err", (), {"read": lambda self: "No such filter: 'drawtext'"})()

        def wait(self, timeout=None):
            return 1

    window._monitor_mpv_process(FailedProcess())
    assert mpv_errors
    assert "drawtext" in mpv_errors[-1][0]
