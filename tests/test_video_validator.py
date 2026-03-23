"""Unit tests for comparison validation."""

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
