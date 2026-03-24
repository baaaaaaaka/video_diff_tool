"""Tests for the top-level main entry helpers."""

from __future__ import annotations

import importlib
import sys
import types

from src.video_validator import VideoInfo


def _import_main(monkeypatch):
    import src.dependency_manager as dependency_manager

    monkeypatch.setattr(dependency_manager, "check_and_install_dependencies", lambda: None)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_run_smoke_check_returns_none_without_flag(monkeypatch):
    main_module = _import_main(monkeypatch)

    assert main_module.run_smoke_check([]) is None


def test_run_smoke_check_requires_a_path_for_smoke_video(monkeypatch, capsys):
    main_module = _import_main(monkeypatch)

    exit_code = main_module.run_smoke_check(["--smoke-check", "--smoke-video"])

    assert exit_code == 1
    assert "--smoke-video requires a path" in capsys.readouterr().out


def test_run_smoke_check_reports_runtime_errors(monkeypatch, capsys):
    main_module = _import_main(monkeypatch)

    class FakeValidator:
        BACKEND_PYAV = "pyav"

        def get_available_metadata_backends(self):
            return ["pyav", "ffprobe"]

        def get_video_info(self, path, preferred_backend="auto"):
            raise RuntimeError("cannot probe")

    monkeypatch.setitem(sys.modules, "av", types.SimpleNamespace(__version__="17.0.0"))
    monkeypatch.setattr("src.video_validator.VideoValidator", FakeValidator)

    exit_code = main_module.run_smoke_check(["--smoke-check", "--smoke-video", "clip.mp4"])

    assert exit_code == 1
    assert "cannot probe" in capsys.readouterr().out


def test_run_smoke_check_success(monkeypatch, capsys):
    main_module = _import_main(monkeypatch)

    class FakeValidator:
        BACKEND_PYAV = "pyav"

        def get_available_metadata_backends(self):
            return ["pyav", "ffprobe"]

        def get_video_info(self, path, preferred_backend="auto"):
            assert preferred_backend == self.BACKEND_PYAV
            return VideoInfo(
                path=path,
                width=320,
                height=180,
                frame_count=2,
                duration=1.0,
                fps=2.0,
                codec="h264",
            )

    monkeypatch.setitem(sys.modules, "av", types.SimpleNamespace(__version__="17.0.0"))
    monkeypatch.setattr("src.video_validator.VideoValidator", FakeValidator)

    exit_code = main_module.run_smoke_check(["--smoke-check", "--smoke-video", "clip.mp4"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "smoke-check: av 17.0.0" in output
    assert "backends pyav, ffprobe" in output
    assert "clip.mp4 320x180 2f h264" in output


def test_run_smoke_check_reports_none_info(monkeypatch, capsys):
    main_module = _import_main(monkeypatch)

    class FakeValidator:
        BACKEND_PYAV = "pyav"

        def get_available_metadata_backends(self):
            return ["pyav"]

        def get_video_info(self, path, preferred_backend="auto"):
            return None

    monkeypatch.setitem(sys.modules, "av", types.SimpleNamespace(__version__="17.0.0"))
    monkeypatch.setattr("src.video_validator.VideoValidator", FakeValidator)

    exit_code = main_module.run_smoke_check(["--smoke-check", "--smoke-video", "clip.mp4"])

    assert exit_code == 1
    assert "failed to read clip.mp4 with PyAV" in capsys.readouterr().out


def test_import_main_warns_when_dependency_check_fails(monkeypatch, capsys):
    import src.dependency_manager as dependency_manager

    monkeypatch.setattr(
        dependency_manager,
        "check_and_install_dependencies",
        lambda: (_ for _ in ()).throw(RuntimeError("install failed")),
    )
    monkeypatch.setattr(sys, "argv", ["main.py"])
    sys.modules.pop("main", None)

    importlib.import_module("main")

    assert "Warning: Failed to check dependencies: install failed" in capsys.readouterr().out
