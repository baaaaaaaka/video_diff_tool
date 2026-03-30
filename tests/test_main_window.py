"""GUI tests for the main window."""

from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog

from src.binary_finder import BinaryFinder
from src.main_window import MainWindow
from src.update_manager import ReleaseInfo, ReleaseVersion


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


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


class FakeValidationWorker:
    instances = []
    auto_emit = True
    next_valid = True
    next_error = ""
    next_failure = None

    def __init__(self, request_id, validator, video_left, video_right):
        self.request_id = request_id
        self.validator = validator
        self.video_left = video_left
        self.video_right = video_right
        self.started = False
        self.wait_called = False
        self.finished_validation = _Signal()
        self.failed_validation = _Signal()
        self.finished = _Signal()
        self.__class__.instances.append(self)

    def start(self):
        self.started = True
        if self.__class__.auto_emit:
            self.emit_configured_result()

    def emit_configured_result(self):
        if self.__class__.next_failure is not None:
            self.failed_validation.emit(self.request_id, self.__class__.next_failure)
        else:
            self.finished_validation.emit(
                self.request_id,
                self.__class__.next_valid,
                self.__class__.next_error,
            )
        self.finished.emit()

    def isRunning(self):
        return self.started and not self.wait_called

    def wait(self, timeout=None):
        self.wait_called = True
        return True


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


def test_check_binaries_and_prompt_shows_install_instructions(qtbot, monkeypatch):
    info_messages = []
    monkeypatch.setattr(BinaryFinder, "find_mpv", lambda self, custom_path="": None)
    monkeypatch.setattr(BinaryFinder, "find_ffmpeg", lambda self, custom_path="": None)
    monkeypatch.setattr(
        "src.main_window.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "src.main_window.QMessageBox.information",
        lambda parent, title, text: info_messages.append((title, text)),
    )
    monkeypatch.setattr("src.main_window.QTimer.singleShot", lambda delay, callback: None)

    window = MainWindow()
    qtbot.addWidget(window)

    assert info_messages
    assert info_messages[-1][0] == "Installation Instructions"
    assert "MPV" in info_messages[-1][1]
    assert "FFMPEG" in info_messages[-1][1]


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


def test_update_check_finished_and_failed_manual_paths(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    info_messages = []
    warning_messages = []
    monkeypatch.setattr(
        "src.main_window.QMessageBox.information",
        lambda parent, title, text: info_messages.append((title, text)),
    )
    monkeypatch.setattr(
        "src.main_window.QMessageBox.warning",
        lambda parent, title, text: warning_messages.append((title, text)),
    )

    window._on_update_check_finished(None, manual=True)
    assert info_messages[-1][0] == "No Updates"

    release = ReleaseInfo(
        tag_name="v1.4.2",
        version=ReleaseVersion.parse("1.4.2"),
        published_at="2026-03-24T00:00:00Z",
        prerelease=False,
        asset_name="VideoDiffTool-v1.4.2-macos-arm64.zip",
        asset_url="https://example.invalid/download.zip",
    )
    monkeypatch.setattr(window.update_manager, "supports_auto_update", lambda: False)
    window._on_update_check_finished(release, manual=True)
    assert info_messages[-1][0] == "Update Available"
    assert window.update_btn.isHidden()

    window._on_update_check_failed("network down", manual=True)
    assert warning_messages[-1] == ("Update Check Failed", "network down")


def test_launch_mpv_handles_validation_errors_and_success(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(window, "_schedule_debug_prewarm", lambda: None)
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
        lambda parent, title, text: critical_messages.append((title, text)),
    )
    FakeValidationWorker.instances.clear()
    FakeValidationWorker.auto_emit = True
    FakeValidationWorker.next_valid = False
    FakeValidationWorker.next_error = "debug validation failed"
    FakeValidationWorker.next_failure = None
    monkeypatch.setattr("src.main_window.PreviewValidationWorker", FakeValidationWorker)

    window._launch_mpv()
    assert critical_messages == [("Debug View Validation Failed", "debug validation failed")]

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


def test_launch_mpv_debug_success_and_stale_validation_are_handled(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(window, "_schedule_debug_prewarm", lambda: None)
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    for path in (left, right):
        path.write_text("x", encoding="utf-8")

    window.video_left.set_video_path(str(left))
    window.video_right.set_video_path(str(right))
    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    launched = {}
    critical_messages = []

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            launched["monitor_started"] = True

    monkeypatch.setattr("src.main_window.threading.Thread", FakeThread)
    monkeypatch.setattr(
        "src.main_window.QMessageBox.critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )
    monkeypatch.setattr(
        window.mpv_launcher,
        "launch",
        lambda **kwargs: launched.setdefault("launch_kwargs", kwargs) or object(),
    )
    monkeypatch.setattr("src.main_window.PreviewValidationWorker", FakeValidationWorker)
    monkeypatch.setattr(window, "_schedule_debug_prewarm", lambda: None)

    FakeValidationWorker.instances.clear()
    FakeValidationWorker.auto_emit = True
    FakeValidationWorker.next_valid = True
    FakeValidationWorker.next_error = ""
    FakeValidationWorker.next_failure = None
    window._launch_mpv()

    assert launched["launch_kwargs"]["comparison_mode"] == "debug_view"
    assert launched["launch_kwargs"]["debug_view"] == "display"
    assert critical_messages == []
    assert window.preview_btn.text() == "Preview with MPV"

    FakeValidationWorker.instances.clear()
    FakeValidationWorker.auto_emit = False
    launched.clear()
    window._launch_mpv()
    assert window.preview_btn.text() == "Preparing Preview..."

    window._on_video_changed(str(left))
    assert window.preview_btn.isEnabled() is True
    window._launch_mpv()
    assert len(FakeValidationWorker.instances) == 2
    FakeValidationWorker.instances[0].emit_configured_result()

    assert launched == {}
    assert critical_messages == []
    assert window.preview_btn.text() == "Preparing Preview..."

    FakeValidationWorker.instances[1].emit_configured_result()
    assert launched["launch_kwargs"]["comparison_mode"] == "debug_view"
    assert window.preview_btn.text() == "Preview with MPV"


def test_debug_video_change_triggers_metadata_prewarm(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(window, "_schedule_debug_prewarm", lambda: None)
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    for path in (left, right):
        path.write_text("x", encoding="utf-8")

    window.video_left.set_video_path(str(left))
    window.video_right.set_video_path(str(right))
    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    started = {}

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr("src.main_window.threading.Thread", FakeThread)

    MainWindow._schedule_debug_prewarm(window)

    assert started["target"] == window.validator.prewarm_video_infos
    assert started["args"] == ([str(left), str(right)],)
    assert started["daemon"] is True
    assert started["started"] is True


def test_debug_preview_reports_preparation_and_launch_failures(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(window, "_schedule_debug_prewarm", lambda: None)
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    for path in (left, right):
        path.write_text("x", encoding="utf-8")

    window.video_left.set_video_path(str(left))
    window.video_right.set_video_path(str(right))
    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    critical_messages = []
    monkeypatch.setattr(
        "src.main_window.QMessageBox.critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )
    monkeypatch.setattr("src.main_window.PreviewValidationWorker", FakeValidationWorker)

    FakeValidationWorker.instances.clear()
    FakeValidationWorker.auto_emit = True
    FakeValidationWorker.next_valid = True
    FakeValidationWorker.next_error = ""
    FakeValidationWorker.next_failure = "probe crashed"
    window._launch_mpv()

    assert critical_messages == [("Preview Preparation Failed", "probe crashed")]
    assert window.preview_btn.text() == "Preview with MPV"
    assert window.preview_btn.isEnabled() is True

    FakeValidationWorker.instances.clear()
    FakeValidationWorker.next_failure = None
    monkeypatch.setattr(window.mpv_launcher, "launch", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("mpv boom")))
    window._launch_mpv()

    assert critical_messages[-1][0] == "MPV Launch Failed"
    assert "mpv boom" in critical_messages[-1][1]


def test_close_event_waits_for_preview_validation_worker(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    waited = []
    saved = []
    accepted = []

    class FakeWorker:
        def isRunning(self):
            return True

        def wait(self, timeout=None):
            waited.append(timeout)
            return True

    class FakeEvent:
        def accept(self):
            accepted.append(True)

    window._preview_validation_worker = FakeWorker()
    window._preview_validation_workers = [window._preview_validation_worker]
    monkeypatch.setattr(window, "_save_settings", lambda: saved.append(True))

    window.closeEvent(FakeEvent())

    assert waited == [5000]
    assert saved == [True]
    assert accepted == [True]


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


def test_start_update_check_skips_when_worker_is_running(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(window.update_manager, "get_release_asset_suffix", lambda: "windows-x64")

    class RunningWorker:
        def isRunning(self):
            return True

    window._update_check_worker = RunningWorker()
    window._start_update_check(manual=True)
    assert isinstance(window._update_check_worker, RunningWorker)


def test_update_download_finished_and_mpv_monitoring(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    window._update_progress_dialog = FakeProgressDialog()

    app = QApplication.instance()
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
        lambda *args: info_messages.append(args),
    )
    monkeypatch.setattr(
        "src.main_window.QTimer.singleShot",
        lambda delay, callback: timer_calls.append((delay, callback)),
    )
    window.mpv_error_signal.disconnect()
    window.mpv_error_signal.connect(lambda error, advice: mpv_errors.append((error, advice)))

    window._on_update_download_finished(str(tmp_path / "update.zip"))

    assert prepared_archives == [tmp_path / "update.zip"]
    assert window.isHidden()
    assert info_messages == []
    assert len(timer_calls) == 1
    assert timer_calls[0][0] == 0
    assert timer_calls[0][1].__self__ is app
    assert timer_calls[0][1].__name__ == "quit"
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

    class PathParseProcess:
        returncode = 1

        def __init__(self):
            self.stderr = type("Err", (), {"read": lambda self: "No option name near foo"})()

        def wait(self, timeout=None):
            return 1

    window._monitor_mpv_process(PathParseProcess())
    assert "path parsing error" in mpv_errors[-1][0]


def test_show_settings_encode_dialog_and_about(qtbot, monkeypatch, tmp_path):
    window = _build_window(qtbot, monkeypatch, tmp_path)
    left = tmp_path / "left.mp4"
    right = tmp_path / "right.mp4"
    left.write_text("x", encoding="utf-8")
    right.write_text("x", encoding="utf-8")
    window.video_left.set_video_path(str(left))
    window.video_right.set_video_path(str(right))

    events = []

    class FakeSettingsDialog:
        def __init__(self, parent):
            events.append(("settings_init", parent))

        def exec(self):
            events.append(("settings_exec", None))
            return True

    class FakeEncodingDialog:
        def __init__(self, **kwargs):
            events.append(("encoding_init", kwargs))

        def exec(self):
            events.append(("encoding_exec", None))
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("src.main_window.SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr("src.main_window.EncodingDialog", FakeEncodingDialog)
    monkeypatch.setattr(
        "src.main_window.QMessageBox.about",
        lambda parent, title, text: events.append(("about", (title, text))),
    )

    window._show_settings()
    window._show_encode_dialog()
    window._show_about()

    assert events[0][0] == "settings_init"
    assert ("settings_exec", None) in events
    encoding_kwargs = next(value for kind, value in events if kind == "encoding_init")
    assert encoding_kwargs["video_left"] == str(left)
    assert encoding_kwargs["video_right"] == str(right)
    assert any(kind == "encoding_exec" for kind, _ in events)
    about_payload = next(value for kind, value in events if kind == "about")
    assert "About Video Diff Tool" in about_payload[0]
