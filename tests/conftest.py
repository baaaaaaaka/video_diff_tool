"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Redirect settings storage to a temporary file for each test."""

    from src import binary_finder as binary_finder_module
    from src import ffmpeg_encoder as ffmpeg_encoder_module
    from src import mpv_launcher as mpv_launcher_module
    from src import settings as settings_module
    from src import video_validator as video_validator_module

    monkeypatch.setattr(
        settings_module.Settings,
        "_get_config_path",
        lambda self: tmp_path / "settings.json",
    )
    settings_module._settings_instance = None
    binary_finder_module._finder_instance = None
    ffmpeg_encoder_module._encoder_instance = None
    mpv_launcher_module._launcher_instance = None
    video_validator_module._validator_instance = None
    yield
    settings_module._settings_instance = None
    binary_finder_module._finder_instance = None
    ffmpeg_encoder_module._encoder_instance = None
    mpv_launcher_module._launcher_instance = None
    video_validator_module._validator_instance = None
