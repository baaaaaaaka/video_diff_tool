"""Comparison mode helpers for standard and debug-view workflows."""

from enum import Enum
from typing import Dict, List


class ComparisonMode(Enum):
    """Comparison layout modes."""

    STANDARD = "standard"
    DEBUG_VIEW = "debug_view"


class DebugViewType(Enum):
    """Supported debug-view panels."""

    DISPLAY = "display"
    FLOW = "flow"
    MASK = "mask"
    WARPED = "warped"


MODE_NAMES = {
    ComparisonMode.STANDARD.value: "Standard",
    ComparisonMode.DEBUG_VIEW.value: "Debug View",
}

DEBUG_VIEW_NAMES = {
    DebugViewType.DISPLAY.value: "Display Image",
    DebugViewType.FLOW.value: "Flow",
    DebugViewType.MASK.value: "Mask",
    DebugViewType.WARPED.value: "Warped",
}

DEBUG_VIEW_CROP_FILTERS = {
    DebugViewType.DISPLAY.value: "crop=iw/2:ih/2:0:0",
    DebugViewType.FLOW.value: "crop=iw/2:ih/2:iw/2:0",
    DebugViewType.MASK.value: "crop=iw/2:ih/2:0:ih/2",
    DebugViewType.WARPED.value: "crop=iw/2:ih/2:iw/2:ih/2",
}


def normalize_comparison_mode(mode: str) -> str:
    """Return a supported comparison mode id."""

    if mode in MODE_NAMES:
        return mode
    return ComparisonMode.STANDARD.value


def normalize_debug_view(debug_view: str) -> str:
    """Return a supported debug-view id."""

    if debug_view in DEBUG_VIEW_NAMES:
        return debug_view
    return DebugViewType.DISPLAY.value


def is_debug_view_mode(mode: str) -> bool:
    """Check whether the comparison mode uses cropped debug panels."""

    return normalize_comparison_mode(mode) == ComparisonMode.DEBUG_VIEW.value


def get_comparison_mode_name(mode: str) -> str:
    """Get the user-facing name for a comparison mode."""

    return MODE_NAMES[normalize_comparison_mode(mode)]


def get_debug_view_name(debug_view: str) -> str:
    """Get the user-facing name for a debug panel."""

    return DEBUG_VIEW_NAMES[normalize_debug_view(debug_view)]


def get_debug_crop_filter(debug_view: str) -> str:
    """Get the FFmpeg crop filter for a debug panel."""

    return DEBUG_VIEW_CROP_FILTERS[normalize_debug_view(debug_view)]


def get_comparison_mode_options() -> List[Dict[str, str]]:
    """Get UI-ready comparison mode options."""

    return [
        {"id": mode.value, "name": MODE_NAMES[mode.value]}
        for mode in ComparisonMode
    ]


def get_debug_view_options() -> List[Dict[str, str]]:
    """Get UI-ready debug-view options."""

    return [
        {"id": debug_view.value, "name": DEBUG_VIEW_NAMES[debug_view.value]}
        for debug_view in DebugViewType
    ]
