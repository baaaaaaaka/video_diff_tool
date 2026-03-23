"""Unit tests for MPV filter and command construction."""

from __future__ import annotations

from src.mpv_launcher import MPVLauncher


def test_build_filter_complex_includes_debug_crop_and_third_video(monkeypatch):
    launcher = MPVLauncher()
    monkeypatch.setattr(launcher.finder, "format_font_path_for_ffmpeg", lambda path: path)

    filter_complex = launcher.build_filter_complex(
        title_left="Left",
        title_right="Right",
        title_third="Third",
        font_path="/tmp/font.ttf",
        has_third_video=True,
        show_titles=False,
        comparison_mode="debug_view",
        debug_view="mask",
    )

    assert "crop=iw/2:ih/2:0:ih/2" in filter_complex
    assert "[third]" in filter_complex
    assert "drawtext=" not in filter_complex


def test_launch_builds_windowed_command_with_screenshot_directory(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    desktop_dir = home_dir / "Desktop"
    desktop_dir.mkdir(parents=True)
    left_video = tmp_path / "left.mp4"
    right_video = tmp_path / "right.mp4"
    third_video = tmp_path / "third.mp4"
    font_path = tmp_path / "font.ttf"

    for path in (left_video, right_video, third_video, font_path):
        path.write_text("x", encoding="utf-8")

    launcher = MPVLauncher()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setattr(launcher.finder, "find_mpv", lambda custom_path="": "/usr/bin/mpv")
    monkeypatch.setattr(launcher.finder, "find_font", lambda custom_path="": str(font_path))

    captured: dict[str, object] = {}

    class DummyProcess:
        pass

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr("src.mpv_launcher.subprocess.Popen", fake_popen)

    process = launcher.launch(
        video_left=str(left_video),
        video_right=str(right_video),
        video_third=str(third_video),
        title_left="Candidate",
        title_right="Baseline",
        title_third="Reference",
        show_titles=False,
        fullscreen=False,
        comparison_mode="debug_view",
        debug_view="flow",
    )

    assert isinstance(process, DummyProcess)
    cmd = captured["cmd"]
    assert cmd[0] == "/usr/bin/mpv"
    assert f"--external-file={right_video}" in cmd
    assert f"--external-file={third_video}" in cmd
    assert any(part.startswith("--lavfi-complex=") for part in cmd)
    assert "--autofit-larger=100%x100%" in cmd
    assert "--no-keepaspect-window" in cmd
    assert f"--screenshot-directory={desktop_dir}" in cmd


def test_launch_windows_adds_startupinfo_and_status_helpers(tmp_path, monkeypatch):
    left_video = tmp_path / "left.mp4"
    right_video = tmp_path / "right.mp4"
    font_path = tmp_path / "font.ttf"
    mpv_path = tmp_path / "mpv.exe"
    left_video.write_text("x", encoding="utf-8")
    right_video.write_text("x", encoding="utf-8")
    font_path.write_text("x", encoding="utf-8")
    mpv_path.write_text("x", encoding="utf-8")

    launcher = MPVLauncher()
    monkeypatch.setattr(launcher.finder, "find_mpv", lambda custom_path="": str(mpv_path))
    monkeypatch.setattr(launcher.finder, "find_font", lambda custom_path="": str(font_path))
    monkeypatch.setattr(launcher.finder, "validate_binary", lambda path, binary: (True, "mpv 1.0"))
    monkeypatch.setattr("src.mpv_launcher.platform.system", lambda: "Windows")

    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0

    captured: dict[str, object] = {}

    monkeypatch.setattr("src.mpv_launcher.subprocess.STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr("src.mpv_launcher.subprocess.STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(
        "src.mpv_launcher.subprocess.Popen",
        lambda cmd, **kwargs: captured.update({"cmd": cmd, "kwargs": kwargs}) or object(),
    )

    launcher.launch(str(left_video), str(right_video), show_titles=False)

    assert isinstance(captured["kwargs"]["startupinfo"], FakeStartupInfo)
    assert captured["kwargs"]["startupinfo"].dwFlags == 1
    assert launcher.get_mpv_status() == (True, "MPV found: mpv 1.0")
    assert launcher.get_font_status() == (True, f"Font: {font_path.name}")
