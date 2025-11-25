"""Settings manager for Video Diff Tool."""

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, Optional


class Settings:
    """Manages application settings with JSON storage."""
    
    # Default settings
    DEFAULTS = {
        # Video titles
        "title_left": "Candidate",
        "title_right": "Baseline",
        "title_third": "",
        
        # Third video
        "enable_third_video": False,
        
        # Binary paths (empty = auto-detect)
        "mpv_path": "",
        "ffmpeg_path": "",
        "ffprobe_path": "",
        "font_path": "",
        
        # Encoding settings
        "output_resolution": "2160p",
        "custom_width": 3840,
        "custom_height": 2160,
        "output_fps": 60,
        "qp_value": 17,
        "gop_size": 30,
        "encoder": "auto",  # "auto", "cpu", or specific HW encoder
        "cpu_preset": "veryfast",
        
        # Last used paths
        "last_video_left": "",
        "last_video_right": "",
        "last_video_third": "",
        "last_output_dir": "",
        
        # Window geometry
        "window_x": 100,
        "window_y": 100,
        "window_width": 900,
        "window_height": 700,
    }
    
    # Resolution presets
    RESOLUTION_PRESETS = {
        "2160p": (3840, 2160),
        "1080p": (1920, 1080),
        "720p": (1280, 720),
        "custom": None,
    }
    
    def __init__(self):
        """Initialize settings manager."""
        self._settings: Dict[str, Any] = {}
        self._config_path = self._get_config_path()
        self.load()
    
    def _get_config_path(self) -> Path:
        """Get the configuration file path based on OS."""
        system = platform.system()
        
        if system == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home()))
        elif system == "Darwin":  # macOS
            base = Path.home() / "Library" / "Application Support"
        else:  # Linux and others
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        
        config_dir = base / "VideoDiffTool"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        return config_dir / "settings.json"
    
    def load(self) -> None:
        """Load settings from file, using defaults for missing values."""
        self._settings = self.DEFAULTS.copy()
        
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # Merge saved settings with defaults
                    for key, value in saved.items():
                        if key in self.DEFAULTS:
                            self._settings[key] = value
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load settings: {e}")
    
    def save(self) -> None:
        """Save current settings to file."""
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save settings: {e}")
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        self._settings = self.DEFAULTS.copy()
        self.save()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._settings.get(key, default if default is not None else self.DEFAULTS.get(key))
    
    def set(self, key: str, value: Any) -> None:
        """Set a setting value and save."""
        self._settings[key] = value
        self.save()
    
    def get_resolution(self) -> tuple[int, int]:
        """Get the current resolution as (width, height)."""
        preset = self.get("output_resolution")
        if preset == "custom":
            return (self.get("custom_width"), self.get("custom_height"))
        return self.RESOLUTION_PRESETS.get(preset, (3840, 2160))
    
    def set_resolution(self, preset: str, width: Optional[int] = None, height: Optional[int] = None) -> None:
        """Set resolution from preset or custom values."""
        self.set("output_resolution", preset)
        if preset == "custom" and width and height:
            self.set("custom_width", width)
            self.set("custom_height", height)
    
    @property
    def config_path(self) -> Path:
        """Get the configuration file path."""
        return self._config_path


# Global settings instance
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

