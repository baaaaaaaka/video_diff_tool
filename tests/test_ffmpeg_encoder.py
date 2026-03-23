"""Unit tests for FFmpeg command generation."""

from pathlib import Path

from src.ffmpeg_encoder import FFmpegEncoder
from src.video_validator import VideoInfo


def _video_info(path: str, width: int = 1920, height: int = 1080) -> VideoInfo:
    return VideoInfo(
        path=path,
        width=width,
        height=height,
        frame_count=10,
        duration=1.0,
        fps=10.0,
        codec="h264",
    )


def _build_encoder(tmp_path: Path, monkeypatch) -> FFmpegEncoder:
    encoder = FFmpegEncoder()
    font_path = tmp_path / "font.ttf"
    font_path.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(encoder.finder, "find_ffmpeg", lambda custom_path="": "/usr/bin/ffmpeg")
    monkeypatch.setattr(encoder.finder, "find_font", lambda custom_path="": str(font_path))
    monkeypatch.setattr(encoder.finder, "has_ffmpeg_filter", lambda ffmpeg_path, filter_name: True)
    monkeypatch.setattr(
        encoder.validator,
        "get_video_info",
        lambda path: _video_info(
            path,
            3840 if "debug" in path else 1920,
            2160 if "debug" in path else 1080,
        ),
    )
    return encoder


def test_build_encoding_command_includes_debug_crop(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)

    command = encoder.build_encoding_command(
        video_left="left_debug.mp4",
        video_right="right_debug.mp4",
        output_path="out.mp4",
        encoder="cpu",
        comparison_mode="debug_view",
        debug_view="flow",
    )

    command_str = " ".join(command)
    assert "crop=iw/2:ih/2:iw/2:0" in command_str
    assert "-pix_fmt yuv444p" in command_str


def test_build_encoding_command_keeps_standard_mode_uncropped(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)

    command = encoder.build_encoding_command(
        video_left="left.mp4",
        video_right="right.mp4",
        output_path="out.mp4",
        encoder="cpu",
        comparison_mode="standard",
    )

    command_str = " ".join(command)
    assert "crop=iw/2:ih/2" not in command_str
    assert "[0:v]split" in command_str or "[0:v]split" in command[command.index("-filter_complex") + 1]


def test_build_encoding_command_skips_drawtext_when_filter_is_unavailable(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)
    monkeypatch.setattr(encoder.finder, "has_ffmpeg_filter", lambda ffmpeg_path, filter_name: False)

    command = encoder.build_encoding_command(
        video_left="left.mp4",
        video_right="right.mp4",
        output_path="out.mp4",
        title_left="Candidate",
        title_right="Baseline",
        encoder="cpu",
        comparison_mode="standard",
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "drawtext=" not in filter_complex
