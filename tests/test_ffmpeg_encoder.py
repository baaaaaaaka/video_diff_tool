"""Unit tests for FFmpeg command generation and runtime control."""

import io
import signal
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


def test_resolve_encoder_auto_prefers_nvenc_and_status_uses_validated_binary(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)
    monkeypatch.setattr(
        encoder.finder,
        "get_available_hw_encoders",
        lambda ffmpeg_path: [
            {"id": "hevc_qsv", "name": "QuickSync"},
            {"id": "hevc_nvenc", "name": "NVENC"},
        ],
    )
    monkeypatch.setattr(encoder.finder, "validate_binary", lambda path, binary: (True, "ffmpeg 7.0"))

    assert encoder.normalize_encoder_id("cpu_h264_444") == "cpu"
    assert encoder._resolve_encoder("auto") == "hevc_nvenc"
    assert encoder.get_ffmpeg_status() == (True, "FFmpeg found: ffmpeg 7.0")


def test_encode_reports_progress_and_success(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)
    monkeypatch.setattr(
        encoder.validator,
        "validate_videos_for_comparison",
        lambda left, right, third: (True, "", {"left": _video_info(left)}),
    )

    class DummyProcess:
        def __init__(self):
            self.stderr = io.StringIO("frame=    5 fps=30.0 bitrate=1000.0kbits/s time=00:00:01.00 speed=1.2x\n")
            self.returncode = 0
            self.pid = 123

        def wait(self):
            return self.returncode

    monkeypatch.setattr("src.ffmpeg_encoder.subprocess.Popen", lambda *args, **kwargs: DummyProcess())

    progress_updates = []
    logs = []
    success = encoder.encode(
        video_left="left.mp4",
        video_right="right.mp4",
        output_path=str(tmp_path / "out.mp4"),
        encoder="cpu",
        progress_callback=progress_updates.append,
        log_callback=logs.append,
    )

    assert success is True
    assert progress_updates and progress_updates[0].frame == 5
    assert progress_updates[0].percent == 50.0
    assert any("Encoding completed successfully!" in line for line in logs)


def test_encode_can_be_cancelled_and_kills_process(tmp_path, monkeypatch):
    encoder = _build_encoder(tmp_path, monkeypatch)
    monkeypatch.setattr(
        encoder.validator,
        "validate_videos_for_comparison",
        lambda left, right, third: (True, "", {"left": _video_info(left)}),
    )

    class DummyProcess:
        def __init__(self):
            self.stderr = io.StringIO("frame=    1 fps=30.0\nframe=    2 fps=30.0\n")
            self.returncode = 0
            self.pid = 456
            self.wait_calls = 0

        def wait(self):
            self.wait_calls += 1
            return self.returncode

    process = DummyProcess()
    kills = []
    monkeypatch.setattr("src.ffmpeg_encoder.subprocess.Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("src.ffmpeg_encoder.os.kill", lambda pid, sig: kills.append((pid, sig)))

    def log_callback(line: str):
        if "frame=" in line:
            encoder.cancel()

    success = encoder.encode(
        video_left="left.mp4",
        video_right="right.mp4",
        output_path=str(tmp_path / "out.mp4"),
        encoder="cpu",
        log_callback=log_callback,
    )

    assert success is False
    assert kills == [(456, signal.SIGTERM)]
    assert process.wait_calls >= 1


def test_parse_progress_handles_invalid_lines_and_windows_kill(monkeypatch):
    encoder = FFmpegEncoder()
    assert encoder._parse_progress("no ffmpeg progress here", 10) is not None
    assert encoder._parse_progress("frame=oops", 10).frame == 0

    class DummyProcess:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self):
            self.waited = True

    process = DummyProcess()
    encoder._process = process
    monkeypatch.setattr("src.ffmpeg_encoder.platform.system", lambda: "Windows")
    encoder._kill_process()

    assert process.terminated is True
    assert process.waited is True
