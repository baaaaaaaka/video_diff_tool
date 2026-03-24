"""Cross-tool smoke tests using real ffmpeg/mpv binaries when available."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.binary_finder import get_binary_finder
from src.ffmpeg_encoder import FFmpegEncoder
from src.mpv_launcher import MPVLauncher
from src.settings import get_settings
from src.video_validator import VideoValidator


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        pytest.skip(f"{name} is not available")
    return path


def _require_font() -> str:
    font_path = get_binary_finder().find_font("")
    if not font_path:
        pytest.skip("No usable font found")
    return font_path


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _make_standard_videos(tmp_path: Path, ffmpeg_path: str) -> tuple[Path, Path]:
    left_path = tmp_path / "left.mp4"
    right_path = tmp_path / "right.mp4"
    _run([ffmpeg_path, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:r=2:d=1", str(left_path)])
    _run([ffmpeg_path, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=2:d=1", str(right_path)])
    return left_path, right_path


def _make_debug_videos(tmp_path: Path, ffmpeg_path: str) -> tuple[Path, Path]:
    left_path = tmp_path / "left_debug.mp4"
    right_path = tmp_path / "right_debug.mp4"
    left_filter = (
        "drawbox=x=0:y=0:w=1920:h=1080:color=red:t=fill,"
        "drawbox=x=1920:y=0:w=1920:h=1080:color=green:t=fill,"
        "drawbox=x=0:y=1080:w=1920:h=1080:color=blue:t=fill,"
        "drawbox=x=1920:y=1080:w=1920:h=1080:color=yellow:t=fill"
    )
    right_filter = (
        "drawbox=x=0:y=0:w=1920:h=1080:color=magenta:t=fill,"
        "drawbox=x=1920:y=0:w=1920:h=1080:color=teal:t=fill,"
        "drawbox=x=0:y=1080:w=1920:h=1080:color=cyan:t=fill,"
        "drawbox=x=1920:y=1080:w=1920:h=1080:color=orange:t=fill"
    )
    _run(
        [
            ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=3840x2160:r=1:d=1",
            "-vf",
            left_filter,
            "-pix_fmt",
            "yuv444p",
            str(left_path),
        ]
    )
    _run(
        [
            ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=3840x2160:r=1:d=1",
            "-vf",
            right_filter,
            "-pix_fmt",
            "yuv444p",
            str(right_path),
        ]
    )
    return left_path, right_path


@pytest.mark.smoke
def test_ffmpeg_encoder_smoke_standard_and_debug(tmp_path):
    ffmpeg_path = _require_binary("ffmpeg")
    ffprobe_path = _require_binary("ffprobe")
    font_path = _require_font()

    settings = get_settings()
    settings.set("ffmpeg_path", ffmpeg_path)
    settings.set("ffprobe_path", ffprobe_path)
    settings.set("font_path", font_path)

    encoder = FFmpegEncoder()
    logs: list[str] = []

    left_video, right_video = _make_standard_videos(tmp_path, ffmpeg_path)
    standard_output = tmp_path / "standard.mp4"
    assert encoder.encode(
        video_left=str(left_video),
        video_right=str(right_video),
        output_path=str(standard_output),
        title_left="Candidate",
        title_right="Baseline",
        output_width=1280,
        output_height=720,
        output_fps=2,
        qp=20,
        gop=1,
        encoder="cpu",
        cpu_preset="ultrafast",
        comparison_mode="standard",
        log_callback=logs.append,
    ), "".join(logs)
    assert standard_output.exists()

    debug_left, debug_right = _make_debug_videos(tmp_path, ffmpeg_path)
    debug_output = tmp_path / "debug.mp4"
    logs.clear()
    assert encoder.encode(
        video_left=str(debug_left),
        video_right=str(debug_right),
        output_path=str(debug_output),
        title_left="Candidate",
        title_right="Baseline",
        output_width=1920,
        output_height=1080,
        output_fps=1,
        qp=20,
        gop=1,
        encoder="cpu",
        cpu_preset="ultrafast",
        comparison_mode="debug_view",
        debug_view="flow",
        log_callback=logs.append,
    ), "".join(logs)
    assert debug_output.exists()


@pytest.mark.smoke
def test_mpv_filter_smoke_standard_and_debug(tmp_path):
    ffmpeg_path = _require_binary("ffmpeg")
    mpv_path = _require_binary("mpv")

    left_video, right_video = _make_standard_videos(tmp_path, ffmpeg_path)
    launcher = MPVLauncher()
    filter_complex = launcher.build_filter_complex(
        title_left="",
        title_right="",
        font_path=_require_font(),
        show_titles=False,
        comparison_mode="standard",
    )
    result = subprocess.run(
        [
            mpv_path,
            str(left_video),
            f"--external-file={right_video}",
            "--no-config",
            "--vo=null",
            "--ao=null",
            "--frames=1",
            f"--lavfi-complex={filter_complex}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    debug_left, debug_right = _make_debug_videos(tmp_path, ffmpeg_path)
    debug_filter = launcher.build_filter_complex(
        title_left="",
        title_right="",
        font_path=_require_font(),
        show_titles=False,
        comparison_mode="debug_view",
        debug_view="mask",
    )
    debug_result = subprocess.run(
        [
            mpv_path,
            str(debug_left),
            f"--external-file={debug_right}",
            "--no-config",
            "--vo=null",
            "--ao=null",
            "--frames=1",
            f"--lavfi-complex={debug_filter}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert debug_result.returncode == 0, debug_result.stderr


@pytest.mark.smoke
def test_video_validator_smoke_prefers_pyav(tmp_path):
    ffmpeg_path = _require_binary("ffmpeg")
    left_video, _ = _make_standard_videos(tmp_path, ffmpeg_path)

    validator = VideoValidator()
    if VideoValidator.BACKEND_PYAV not in validator.get_available_metadata_backends():
        pytest.skip("PyAV is not available")

    info = validator.get_video_info(str(left_video), preferred_backend=VideoValidator.BACKEND_PYAV)

    assert info is not None
    assert info.width == 320
    assert info.height == 180
    assert info.codec in {"h264", "libx264"}
