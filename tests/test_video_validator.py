"""Unit tests for comparison validation."""

import json
import subprocess

from src.video_validator import VideoInfo, VideoValidator


def _video_info(path: str, width: int, height: int) -> VideoInfo:
    return VideoInfo(
        path=path,
        width=width,
        height=height,
        frame_count=10,
        duration=1.0,
        fps=10.0,
        codec="h264",
    )


def test_validate_debug_view_accepts_matching_4k_videos(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    infos = {
        "left.mp4": _video_info("left.mp4", 3840, 2160),
        "right.mp4": _video_info("right.mp4", 3840, 2160),
    }
    monkeypatch.setattr(validator, "get_video_info", lambda path: infos[path])

    valid, error, returned_infos = validator.validate_videos_for_debug_view("left.mp4", "right.mp4")

    assert valid is True
    assert error == ""
    assert returned_infos is not None


def test_validate_debug_view_rejects_resolution_mismatch(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    infos = {
        "left.mp4": _video_info("left.mp4", 3840, 2160),
        "right.mp4": _video_info("right.mp4", 1920, 1080),
    }
    monkeypatch.setattr(validator, "get_video_info", lambda path: infos[path])

    valid, error, returned_infos = validator.validate_videos_for_debug_view("left.mp4", "right.mp4")

    assert valid is False
    assert "matching input resolutions" in error
    assert returned_infos is None


def test_validate_debug_view_rejects_non_4k_layout(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    infos = {
        "left.mp4": _video_info("left.mp4", 1920, 1080),
        "right.mp4": _video_info("right.mp4", 1920, 1080),
    }
    monkeypatch.setattr(validator, "get_video_info", lambda path: infos[path])

    valid, error, returned_infos = validator.validate_videos_for_debug_view("left.mp4", "right.mp4")

    assert valid is False
    assert "expects 3840x2160" in error
    assert returned_infos is None


def test_get_video_info_uses_ffprobe_and_falls_back_to_duration_fps(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    payload = {
        "streams": [
            {
                "width": 1920,
                "height": 1080,
                "nb_frames": "0",
                "r_frame_rate": "24000/1001",
                "codec_name": "h264",
            }
        ],
        "format": {"duration": "2.5"},
    }

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=json.dumps(payload), stderr=""),
    )

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    info = validator.get_video_info(str(video_path))

    assert info is not None
    assert info.width == 1920
    assert info.height == 1080
    assert info.frame_count == int(2.5 * (24000 / 1001))
    assert round(info.aspect_ratio, 4) == round(1920 / 1080, 4)


def test_get_video_info_handles_missing_binary_file_and_bad_probe_output(tmp_path, monkeypatch, capsys):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    validator.ffprobe_path = None
    try:
        validator.get_video_info("missing.mp4")
        assert False, "Expected RuntimeError when ffprobe is missing"
    except RuntimeError as exc:
        assert "ffprobe not found" in str(exc)

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    assert validator.get_video_info(str(tmp_path / "missing.mp4")) is None

    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="probe failed"),
    )
    assert validator.get_video_info(str(video_path)) is None

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=json.dumps({"streams": []}), stderr=""),
    )
    assert validator.get_video_info(str(video_path)) is None

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="{invalid", stderr=""),
    )
    assert validator.get_video_info(str(video_path)) is None
    assert "Error getting video info" in capsys.readouterr().out


def test_validate_comparison_errors_and_frame_count_helpers(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    infos = {
        "left.mp4": _video_info("left.mp4", 1920, 1080),
        "right.mp4": VideoInfo(
            path="right.mp4",
            width=1920,
            height=1080,
            frame_count=12,
            duration=1.2,
            fps=10.0,
            codec="h264",
        ),
        "third.mp4": VideoInfo(
            path="third.mp4",
            width=1920,
            height=1080,
            frame_count=8,
            duration=0.8,
            fps=10.0,
            codec="h264",
        ),
    }

    monkeypatch.setattr(validator, "get_video_info", lambda path: infos.get(path))

    valid, error, returned_infos = validator.validate_videos_for_comparison("", "right.mp4")
    assert valid is False
    assert "No video specified for left" in error
    assert returned_infos is None

    valid, error, returned_infos = validator.validate_videos_for_comparison("left.mp4", "missing.mp4")
    assert valid is False
    assert "Could not read video" in error
    assert returned_infos is None

    valid, error, returned_infos = validator.validate_videos_for_comparison("left.mp4", "right.mp4")
    assert valid is False
    assert "Frame count mismatch!" in error
    assert returned_infos is None

    infos["right.mp4"] = _video_info("right.mp4", 1920, 1080)
    valid, error, returned_infos = validator.validate_videos_for_comparison("left.mp4", "right.mp4", "third.mp4")
    assert valid is False
    assert "Frame count mismatch with third video!" in error
    assert returned_infos is None

    assert validator.get_frame_count("left.mp4") == 10
    assert validator.get_frame_count("missing.mp4") == 0
