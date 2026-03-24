"""Unit tests for comparison validation."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import types

from src.video_validator import VideoInfo, VideoValidator


def _video_info(path: str, width: int, height: int, frame_count: int = 10) -> VideoInfo:
    return VideoInfo(
        path=path,
        width=width,
        height=height,
        frame_count=frame_count,
        duration=1.0,
        fps=10.0,
        codec="h264",
    )


def test_validate_debug_view_accepts_matching_4k_videos(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda videos, preferred_backend="auto": {
            "left": _video_info("left.mp4", 3840, 2160),
            "right": _video_info("right.mp4", 3840, 2160),
        },
    )

    valid, error, returned_infos = validator.validate_videos_for_debug_view("left.mp4", "right.mp4")

    assert valid is True
    assert error == ""
    assert returned_infos is not None


def test_validate_debug_view_rejects_resolution_mismatch(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda videos, preferred_backend="auto": {
            "left": _video_info("left.mp4", 3840, 2160),
            "right": _video_info("right.mp4", 1920, 1080),
        },
    )

    valid, error, returned_infos = validator.validate_videos_for_debug_view("left.mp4", "right.mp4")

    assert valid is False
    assert "matching input resolutions" in error
    assert returned_infos is None


def test_validate_debug_view_rejects_non_4k_layout(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda videos, preferred_backend="auto": {
            "left": _video_info("left.mp4", 1920, 1080),
            "right": _video_info("right.mp4", 1920, 1080),
        },
    )

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
    info = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_FFPROBE)

    assert info is not None
    assert info.width == 1920
    assert info.height == 1080
    assert info.frame_count == int(2.5 * (24000 / 1001))
    assert round(info.aspect_ratio, 4) == round(1920 / 1080, 4)


def test_get_video_info_handles_missing_binary_file_and_bad_probe_output(tmp_path, monkeypatch, capsys):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_resolve_ffprobe_path", lambda: None)
    existing_video = tmp_path / "existing.mp4"
    existing_video.write_text("x", encoding="utf-8")
    try:
        validator.get_video_info(str(existing_video), preferred_backend=VideoValidator.BACKEND_FFPROBE)
        assert False, "Expected RuntimeError when ffprobe is missing"
    except RuntimeError as exc:
        assert "ffprobe not found" in str(exc)

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    assert validator.get_video_info(str(tmp_path / "missing.mp4"), preferred_backend=VideoValidator.BACKEND_FFPROBE) is None

    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="probe failed"),
    )
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_FFPROBE) is None

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=json.dumps({"streams": []}), stderr=""),
    )
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_FFPROBE) is None

    monkeypatch.setattr(
        "src.video_validator.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="{invalid", stderr=""),
    )
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_FFPROBE) is None
    assert "Error getting video info via ffprobe" in capsys.readouterr().out


def test_validate_comparison_errors_and_frame_count_helpers(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    infos = {
        "left": _video_info("left.mp4", 1920, 1080),
        "right": VideoInfo(
            path="right.mp4",
            width=1920,
            height=1080,
            frame_count=12,
            duration=1.2,
            fps=10.0,
            codec="h264",
        ),
        "third": VideoInfo(
            path="third.mp4",
            width=1920,
            height=1080,
            frame_count=8,
            duration=0.8,
            fps=10.0,
            codec="h264",
        ),
    }

    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda videos, preferred_backend="auto": {
            name: None if "missing" in path else infos.get(name)
            for name, path in videos.items()
        },
    )
    monkeypatch.setattr(validator, "get_video_info", lambda path, preferred_backend="auto": infos.get("left") if path == "left.mp4" else None)

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

    infos["right"] = _video_info("right.mp4", 1920, 1080)
    valid, error, returned_infos = validator.validate_videos_for_comparison("left.mp4", "right.mp4", "third.mp4")
    assert valid is False
    assert "Frame count mismatch with third video!" in error
    assert returned_infos is None

    assert validator.get_frame_count("left.mp4") == 10
    assert validator.get_frame_count("missing.mp4") == 0


def test_batch_level_fallback_uses_a_single_backend_attempt(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    calls = []

    def fake_probe(video_paths, backend):
        calls.append((backend, tuple(video_paths)))
        if backend == validator.BACKEND_PYAV:
            return {
                "left": _video_info("left.mp4", 1920, 1080),
                "right": None,
            }
        return {
            "left": _video_info("left.mp4", 1920, 1080),
            "right": _video_info("right.mp4", 1920, 1080),
        }

    monkeypatch.setattr(validator, "_probe_videos_with_backend", fake_probe)

    infos = validator.get_video_infos({"left": "left.mp4", "right": "right.mp4"})

    assert infos["left"] is not None
    assert infos["right"] is not None
    assert calls == [
        (validator.BACKEND_PYAV, ("left", "right")),
        (validator.BACKEND_FFPROBE, ("left", "right")),
    ]


def test_get_video_info_uses_cache_until_file_changes(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: object())

    calls = {"count": 0}

    def fake_probe(path):
        calls["count"] += 1
        return _video_info(path, 1920, 1080)

    monkeypatch.setattr(validator, "_probe_with_pyav", fake_probe)

    first = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV)
    second = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV)

    assert first == second
    assert calls["count"] == 1

    video_path.write_text("updated", encoding="utf-8")
    third = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV)

    assert third is not None
    assert calls["count"] == 2


def test_single_flight_deduplicates_parallel_probes(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: object())

    calls = {"count": 0}
    release_probe = threading.Event()

    def fake_probe(path):
        calls["count"] += 1
        release_probe.wait(timeout=2)
        return _video_info(path, 1920, 1080)

    monkeypatch.setattr(validator, "_probe_with_pyav", fake_probe)

    results = []

    def worker():
        results.append(validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV))

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()

    time.sleep(0.1)
    release_probe.set()
    for thread in threads:
        thread.join(timeout=2)

    assert len(results) == 2
    assert all(result is not None for result in results)
    assert calls["count"] == 1


def test_probe_discards_result_when_file_changes_during_probe(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: object())

    def mutate_during_probe(path):
        Path(path).write_text("updated", encoding="utf-8")
        return _video_info(path, 1920, 1080)

    monkeypatch.setattr(validator, "_probe_with_pyav", mutate_during_probe)

    first = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV)
    assert first is None

    monkeypatch.setattr(validator, "_probe_with_pyav", lambda path: _video_info(path, 1920, 1080))
    second = validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV)
    assert second is not None


def test_probe_with_pyav_extracts_stream_metadata(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")

    class FakeRate:
        numerator = 30
        denominator = 1

    fake_stream = types.SimpleNamespace(
        type="video",
        width=1920,
        height=1080,
        codec_context=types.SimpleNamespace(width=1920, height=1080, name="h264"),
        average_rate=FakeRate(),
        base_rate=None,
        guessed_rate=None,
        duration=4,
        time_base=0.25,
        frames=0,
        name="stream-h264",
    )
    closed = {"value": False}

    class FakeContainer:
        streams = [fake_stream]
        duration = None

        def close(self):
            closed["value"] = True

    fake_av = types.SimpleNamespace(open=lambda path: FakeContainer(), time_base=1_000_000)
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: fake_av)

    info = validator._probe_with_pyav("clip.mp4")

    assert info == VideoInfo(
        path="clip.mp4",
        width=1920,
        height=1080,
        frame_count=30,
        duration=1.0,
        fps=30.0,
        codec="h264",
    )
    assert closed["value"] is True


def test_get_available_backends_and_clear_cache(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_text("x", encoding="utf-8")

    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: types.SimpleNamespace(__version__="17.0.0"))
    monkeypatch.setattr(validator, "_resolve_ffprobe_path", lambda: "/usr/bin/ffprobe")

    calls = {"count": 0}
    monkeypatch.setattr(
        validator,
        "_probe_with_pyav",
        lambda path: calls.__setitem__("count", calls["count"] + 1) or _video_info(path, 1920, 1080),
    )

    assert validator.get_available_metadata_backends() == ["pyav", "ffprobe"]
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV) is not None
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV) is not None
    assert calls["count"] == 1

    validator.clear_cache()
    assert validator.get_video_info(str(video_path), preferred_backend=VideoValidator.BACKEND_PYAV) is not None
    assert calls["count"] == 2


def test_get_video_infos_can_probe_without_consistent_backend(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    calls = []

    def fake_get_video_info(path, preferred_backend="auto"):
        calls.append((path, preferred_backend))
        return _video_info(path, 1920, 1080)

    monkeypatch.setattr(validator, "get_video_info", fake_get_video_info)

    infos = validator.get_video_infos(
        {"left": "left.mp4", "right": "right.mp4"},
        preferred_backend=VideoValidator.BACKEND_FFPROBE,
        require_consistent_backend=False,
    )

    assert infos["left"] is not None
    assert infos["right"] is not None
    assert calls == [
        ("left.mp4", VideoValidator.BACKEND_FFPROBE),
        ("right.mp4", VideoValidator.BACKEND_FFPROBE),
    ]


def test_prewarm_video_infos_empty_and_runtime_error_are_ignored(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    calls = []
    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda video_paths, preferred_backend="auto": calls.append((video_paths, preferred_backend)),
    )

    validator.prewarm_video_infos([])
    assert calls == []

    monkeypatch.setattr(
        validator,
        "_get_video_infos_batch",
        lambda video_paths, preferred_backend="auto": (_ for _ in ()).throw(RuntimeError("boom")),
    )
    validator.prewarm_video_infos(["left.mp4"])


def test_get_video_infos_batch_raises_when_all_backends_fail(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")

    def fake_probe(video_paths, backend):
        raise RuntimeError(f"{backend} unavailable")

    monkeypatch.setattr(validator, "_probe_videos_with_backend", fake_probe)

    try:
        validator.get_video_infos({"left": "left.mp4"})
        assert False, "Expected all-backend failure"
    except RuntimeError as exc:
        assert "ffprobe unavailable" in str(exc)


def test_probe_videos_with_backend_single_file_path(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_ensure_backend_available", lambda backend: None)
    monkeypatch.setattr(
        validator,
        "_get_video_info_with_backend",
        lambda path, backend: _video_info(path, 1920, 1080),
    )

    infos = validator._probe_videos_with_backend({"left": "left.mp4"}, VideoValidator.BACKEND_PYAV)

    assert infos == {"left": _video_info("left.mp4", 1920, 1080)}


def test_probe_with_pyav_handles_missing_video_stream_and_container_duration(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")

    class EmptyContainer:
        streams = [types.SimpleNamespace(type="audio")]

        def close(self):
            pass

    fake_av = types.SimpleNamespace(open=lambda path: EmptyContainer(), time_base=1_000_000)
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: fake_av)
    assert validator._probe_with_pyav("clip.mp4") is None

    fake_stream = types.SimpleNamespace(
        type="video",
        width=1280,
        height=720,
        codec_context=types.SimpleNamespace(width=1280, height=720, name=None),
        average_rate=None,
        base_rate=None,
        guessed_rate="24000/1001",
        duration=None,
        time_base=None,
        frames=0,
        name="stream-vp9",
    )

    class DurationContainer:
        streams = [fake_stream]
        duration = 2_000_000

        def close(self):
            pass

    fake_av = types.SimpleNamespace(open=lambda path: DurationContainer(), time_base=1_000_000)
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: fake_av)

    info = validator._probe_with_pyav("clip.mp4")

    assert info is not None
    assert info.width == 1280
    assert info.height == 720
    assert round(info.duration, 2) == 2.0
    assert round(info.fps, 3) == round(24000 / 1001, 3)
    assert info.codec == "stream-vp9"


def test_backend_availability_and_ratio_helpers(monkeypatch):
    validator = VideoValidator(ffprobe_path="/usr/bin/ffprobe")
    monkeypatch.setattr(validator, "_load_pyav_module", lambda: None)
    monkeypatch.setattr(validator, "_resolve_ffprobe_path", lambda: None)

    try:
        validator._ensure_backend_available(VideoValidator.BACKEND_PYAV)
        assert False, "Expected PyAV availability error"
    except RuntimeError as exc:
        assert "PyAV is not available" in str(exc)

    try:
        validator._ensure_backend_available(VideoValidator.BACKEND_FFPROBE)
        assert False, "Expected ffprobe availability error"
    except RuntimeError as exc:
        assert "ffprobe not found" in str(exc)

    assert validator._ratio_to_float("30000/1001") > 29.0
    assert validator._ratio_to_float(object()) == 0.0
    assert validator._parse_float("bad") == 0.0
