"""Tests for persisted application settings."""

from __future__ import annotations

import json

from src.settings import Settings, get_settings


def test_settings_load_save_and_ignore_unknown_keys():
    settings = get_settings()
    settings.set("title_left", "Candidate A")
    settings.set("output_fps", 48)

    saved_payload = {
        "title_left": "Reloaded Title",
        "output_fps": 24,
        "unknown_key": "ignored",
    }
    settings.config_path.write_text(json.dumps(saved_payload), encoding="utf-8")

    settings.load()

    assert settings.get("title_left") == "Reloaded Title"
    assert settings.get("output_fps") == 24
    assert settings.get("unknown_key") is None


def test_settings_invalid_json_keeps_defaults(capsys):
    settings = get_settings()
    settings.config_path.write_text("{ invalid json", encoding="utf-8")

    settings.load()

    assert settings.get("title_left") == Settings.DEFAULTS["title_left"]
    assert "Warning: Could not load settings" in capsys.readouterr().out


def test_settings_resolution_updates_and_reset_to_defaults():
    settings = get_settings()

    settings.set_resolution("custom", width=1234, height=567)
    assert settings.get_resolution() == (1234, 567)

    settings.set("title_right", "Changed")
    settings.reset_to_defaults()

    assert settings.get_resolution() == Settings.RESOLUTION_PRESETS["2160p"]
    assert settings.get("title_right") == Settings.DEFAULTS["title_right"]
