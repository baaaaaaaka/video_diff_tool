"""Unit tests for binary and font discovery helpers."""

from __future__ import annotations

import subprocess

from src.binary_finder import BinaryFinder


def test_find_font_prefers_ttf_on_macos(tmp_path, monkeypatch):
    ttc_path = tmp_path / "Helvetica.ttc"
    ttf_path = tmp_path / "Arial.ttf"
    ttc_path.write_text("x", encoding="utf-8")
    ttf_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        BinaryFinder,
        "FONT_PATHS",
        {"Darwin": [str(ttc_path), str(ttf_path)]},
    )

    finder = BinaryFinder()
    finder.system = "Darwin"

    assert finder.find_font() == str(ttf_path)


def test_find_font_uses_fc_match_fallback_on_linux(tmp_path, monkeypatch):
    fallback_font = tmp_path / "FallbackSans.ttf"
    fallback_font.write_text("x", encoding="utf-8")

    monkeypatch.setattr(BinaryFinder, "FONT_PATHS", {"Linux": []})
    monkeypatch.setattr(
        "src.binary_finder.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=f"{fallback_font}\n",
            stderr="",
        ),
    )

    finder = BinaryFinder()
    finder.system = "Linux"

    assert finder.find_font() == str(fallback_font)


def test_has_ffmpeg_filter_uses_cached_result(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=" ... drawtext ... ",
            stderr="",
        )

    monkeypatch.setattr("src.binary_finder.subprocess.run", fake_run)

    finder = BinaryFinder()

    assert finder.has_ffmpeg_filter("/usr/bin/ffmpeg", "drawtext") is True
    assert finder.has_ffmpeg_filter("/usr/bin/ffmpeg", "drawtext") is True
    assert len(calls) == 1


def test_get_available_hw_encoders_filters_by_usability_and_caches(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=(
                " V..... hevc_videotoolbox VideoToolbox\n"
                " V..... hevc_nvenc NVIDIA NVENC\n"
                " V..... hevc_qsv QuickSync\n"
            ),
            stderr="",
        )

    finder = BinaryFinder()
    finder.system = "Darwin"
    monkeypatch.setattr("src.binary_finder.subprocess.run", fake_run)
    monkeypatch.setattr(
        finder,
        "_check_encoder_usability",
        lambda ffmpeg_path, encoder: encoder != "hevc_qsv",
    )

    encoders = finder.get_available_hw_encoders("/usr/bin/ffmpeg")

    assert [encoder["id"] for encoder in encoders] == ["hevc_videotoolbox", "hevc_nvenc"]
    assert finder.get_available_hw_encoders("/usr/bin/ffmpeg") == encoders
    assert len(calls) == 1


def test_check_encoder_usability_uses_nvenc_444_settings(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("src.binary_finder.subprocess.run", fake_run)

    finder = BinaryFinder()
    assert finder._check_encoder_usability("/usr/bin/ffmpeg", "hevc_nvenc") is True

    cmd = seen[0]
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv444p"
    assert cmd[cmd.index("-profile:v") + 1] == "rext"


def test_validate_binary_and_windows_font_path_formatting(tmp_path, monkeypatch):
    binary_path = tmp_path / "ffmpeg"
    binary_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "src.binary_finder.subprocess.run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd,
            0,
            stdout="ffmpeg version 7.0\nbuilt with tests\n",
            stderr="",
        ),
    )

    finder = BinaryFinder()
    valid, info = finder.validate_binary(str(binary_path), "ffmpeg")
    assert valid is True
    assert info == "ffmpeg version 7.0"

    assert finder.validate_binary(str(tmp_path / "missing"), "ffmpeg") == (False, "File not found")

    finder.system = "Windows"
    assert finder.format_font_path_for_ffmpeg(r"C:\Windows\Fonts\arial.ttf") == r"C\:/Windows/Fonts/arial.ttf"
