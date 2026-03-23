"""GUI tests for the main window."""

from src.binary_finder import BinaryFinder
from src.main_window import MainWindow
from src.update_manager import ReleaseInfo, ReleaseVersion


def test_debug_mode_disables_third_video(qtbot, monkeypatch, tmp_path):
    dummy_binary = tmp_path / "dummy"
    dummy_binary.write_text("x", encoding="utf-8")

    monkeypatch.setattr(MainWindow, "_check_binaries_and_prompt", lambda self: None)
    monkeypatch.setattr(MainWindow, "_start_update_check", lambda self, manual=False: None)
    monkeypatch.setattr(BinaryFinder, "find_mpv", lambda self, custom_path="": str(dummy_binary))
    monkeypatch.setattr(BinaryFinder, "find_ffmpeg", lambda self, custom_path="": str(dummy_binary))
    monkeypatch.setattr(BinaryFinder, "find_font", lambda self, custom_path="": str(dummy_binary))

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.debug_view_combo.isHidden()
    window._set_combo_data(window.comparison_mode_combo, "debug_view")
    window._on_comparison_mode_changed(0)

    assert not window.debug_view_combo.isHidden()
    assert not window.enable_third_cb.isEnabled()


def test_update_button_is_shown_for_new_release(qtbot, monkeypatch):
    monkeypatch.setattr(MainWindow, "_check_binaries_and_prompt", lambda self: None)
    monkeypatch.setattr(MainWindow, "_start_update_check", lambda self, manual=False: None)
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
