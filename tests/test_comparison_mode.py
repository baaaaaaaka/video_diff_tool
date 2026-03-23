"""Tests for comparison-mode helpers."""

from src.comparison_mode import (
    ComparisonMode,
    DebugViewType,
    get_comparison_mode_name,
    get_comparison_mode_options,
    get_debug_crop_filter,
    get_debug_view_name,
    get_debug_view_options,
    is_debug_view_mode,
    normalize_comparison_mode,
    normalize_debug_view,
)


def test_comparison_mode_helpers_normalize_invalid_values():
    assert normalize_comparison_mode("unknown") == ComparisonMode.STANDARD.value
    assert normalize_debug_view("unknown") == DebugViewType.DISPLAY.value
    assert is_debug_view_mode("debug_view") is True
    assert is_debug_view_mode("unknown") is False
    assert get_comparison_mode_name("unknown") == "Standard"
    assert get_debug_view_name("unknown") == "Display Image"
    assert get_debug_crop_filter("warped") == "crop=iw/2:ih/2:iw/2:ih/2"


def test_comparison_mode_options_cover_all_supported_values():
    mode_ids = [option["id"] for option in get_comparison_mode_options()]
    debug_ids = [option["id"] for option in get_debug_view_options()]

    assert mode_ids == [mode.value for mode in ComparisonMode]
    assert debug_ids == [debug_view.value for debug_view in DebugViewType]
