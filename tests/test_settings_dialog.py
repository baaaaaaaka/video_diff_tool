"""GUI tests for the settings dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from src.settings import get_settings
from src.widgets.settings_dialog import SettingsDialog


class FakeFinder:
    def __init__(self, mpv_path: str, ffmpeg_path: str, font_path: str):
        self._mpv_path = mpv_path
        self._ffmpeg_path = ffmpeg_path
        self._font_path = font_path

    def find_mpv(self, custom_path: str = "") -> str:
        return custom_path or self._mpv_path

    def find_ffmpeg(self, custom_path: str = "") -> str:
        return custom_path or self._ffmpeg_path

    def find_font(self, custom_path: str = "") -> str:
        return custom_path or self._font_path

    def validate_binary(self, path: str, binary_type: str) -> tuple[bool, str]:
        return True, f"{binary_type} version"

    def get_install_instructions(self, binary_type: str) -> str:
        return f"install {binary_type}"


def test_settings_dialog_auto_detect_and_save(qtbot, monkeypatch, tmp_path):
    mpv_path = tmp_path / "mpv"
    ffmpeg_path = tmp_path / "ffmpeg"
    font_path = tmp_path / "font.ttf"
    for path in (mpv_path, ffmpeg_path, font_path):
        path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "src.widgets.settings_dialog.get_binary_finder",
        lambda: FakeFinder(str(mpv_path), str(ffmpeg_path), str(font_path)),
    )

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    dialog._auto_detect("mpv")
    dialog._auto_detect("ffmpeg")
    dialog._auto_detect_font()
    dialog.default_title_left.setText("New Candidate")
    dialog.default_resolution.setCurrentText("1080p")
    dialog.default_fps.setValue(48)

    accepted: list[bool] = []
    monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

    dialog._save_and_close()

    settings = get_settings()
    assert settings.get("mpv_path") == str(mpv_path)
    assert settings.get("ffmpeg_path") == str(ffmpeg_path)
    assert settings.get("font_path") == str(font_path)
    assert settings.get("title_left") == "New Candidate"
    assert settings.get("output_resolution") == "1080p"
    assert settings.get("output_fps") == 48
    assert accepted == [True]


def test_settings_dialog_reset_to_defaults(qtbot, monkeypatch, tmp_path):
    font_path = tmp_path / "font.ttf"
    font_path.write_text("x", encoding="utf-8")
    finder = FakeFinder(str(tmp_path / "mpv"), str(tmp_path / "ffmpeg"), str(font_path))

    monkeypatch.setattr("src.widgets.settings_dialog.get_binary_finder", lambda: finder)
    monkeypatch.setattr(
        "src.widgets.settings_dialog.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    info_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "src.widgets.settings_dialog.QMessageBox.information",
        lambda parent, title, text: info_messages.append((title, text)),
    )

    settings = get_settings()
    settings.set("title_left", "Overridden")

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.default_title_left.setText("Still Overridden")

    dialog._reset_to_defaults()

    assert dialog.default_title_left.text() == settings.DEFAULTS["title_left"]
    assert any(title == "Reset Complete" for title, _ in info_messages)
