"""MPV launcher for video comparison."""

import subprocess
import platform
import os
from pathlib import Path
from typing import Optional

from .settings import get_settings
from .binary_finder import get_binary_finder
from .comparison_mode import (
    get_debug_crop_filter,
    is_debug_view_mode,
    normalize_comparison_mode,
    normalize_debug_view,
)


class MPVLauncher:
    """Launches MPV with video comparison filter complex."""
    
    def __init__(self):
        """Initialize MPV launcher."""
        self.settings = get_settings()
        self.finder = get_binary_finder()
    
    def build_filter_complex(
        self,
        title_left: str,
        title_right: str,
        font_path: str,
        title_third: Optional[str] = None,
        has_third_video: bool = False,
        show_titles: bool = True,
        comparison_mode: str = "standard",
        debug_view: str = "display",
    ) -> str:
        """
        Build the lavfi-complex filter string for MPV.
        """
        # Format font path for FFmpeg
        formatted_font = self.finder.format_font_path_for_ffmpeg(font_path)
        
        # Escape special characters in titles for drawtext filter
        title_left_escaped = self._escape_drawtext(title_left)
        title_right_escaped = self._escape_drawtext(title_right)
        comparison_mode = normalize_comparison_mode(comparison_mode)
        debug_view = normalize_debug_view(debug_view)
        debug_crop = get_debug_crop_filter(debug_view) if is_debug_view_mode(comparison_mode) else ""

        def make_split_chain(input_label: str, source_label: str, display_label: str, diff_label: str) -> str:
            """Build input preprocessing and split chain."""
            if debug_crop:
                return (
                    f"{input_label}{debug_crop}[{source_label}];"
                    f"[{source_label}]split[{display_label}][{diff_label}]"
                )
            return f"{input_label}split[{display_label}][{diff_label}]"
        
        # Build filter for left video
        if show_titles:
            drawtext_left = (
                f"drawtext=fontfile='{formatted_font}':"
                f"text='{title_left_escaped}':"
                f"x=(w-text_w)/2:y=(h-text_h)-100:"
                f"fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.5:boxborderw=5"
            )
            filter_left = f"[vid11] {drawtext_left} [left]"
        else:
            filter_left = "[vid11] copy [left]"
        
        # Build filter for right video
        if show_titles:
            drawtext_right = (
                f"drawtext=fontfile='{formatted_font}':"
                f"text='{title_right_escaped}':"
                f"x=(w-text_w)/2:y=(h-text_h)-100:"
                f"fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.5:boxborderw=5"
            )
            filter_right = f"[vid21] {drawtext_right} [right]"
        else:
            filter_right = "[vid21] copy [right]"
        
        if has_third_video:
            # 3 video layout with third video in bottom right
            title_third_escaped = self._escape_drawtext(title_third or "")
            
            # Build filter for third video
            if show_titles and title_third_escaped:
                drawtext_third = (
                    f"drawtext=fontfile='{formatted_font}':"
                    f"text='{title_third_escaped}':"
                    f"x=(w-text_w)/2:y=(h-text_h)-100:"
                    f"fontsize=36:fontcolor=white:"
                    f"box=1:boxcolor=black@0.5:boxborderw=5"
                )
                third_filter = f"[vid3] {drawtext_third} [third]"
            else:
                third_filter = "[vid3] copy [third]"
            
            filter_complex = (
                # Preprocess video 1 and split for display/diff.
                f"{make_split_chain('[vid1]', 'vid1_src', 'vid11', 'vid12')};"
                # Preprocess video 2 and split for display/diff.
                f"{make_split_chain('[vid2]', 'vid2_src', 'vid21', 'vid22')};"
                # Add title to video 1
                f"{filter_left};"
                # Add title to video 2
                f"{filter_right};"
                # Create difference blend from the splits
                "[vid12][vid22] blend=all_mode='difference' [blended];"
                # Process third video
                f"{third_filter};"
                # Stack bottom row (diff + third video)
                "[blended][third] hstack [down];"
                # Stack top row (left + right)
                "[left][right] hstack [up];"
                # Stack top and bottom
                "[up][down] vstack [vo]"
            )
        else:
            # 2 video layout with black in bottom right
            filter_complex = (
                # Preprocess video 1 and split for display/diff.
                f"{make_split_chain('[vid1]', 'vid1_src', 'vid11', 'vid12')};"
                # Preprocess video 2 and split for display/diff.
                f"{make_split_chain('[vid2]', 'vid2_src', 'vid21', 'vid22')};"
                # Add title to video 1
                f"{filter_left};"
                # Add title to video 2
                f"{filter_right};"
                # Create difference blend from the splits
                "[vid12][vid22] blend=all_mode='difference' [blended];"
                # Create black frame same size as blended
                "[blended] pad=2*iw:ih:0:0:black [down];"
                # Stack top row (left + right)
                "[left][right] hstack [up];"
                # Stack top and bottom
                "[up][down] vstack [vo]"
            )
        
        return filter_complex
    
    def _escape_drawtext(self, text: str) -> str:
        """Escape special characters for drawtext filter."""
        # Escape characters that have special meaning in drawtext
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "\\'")
        text = text.replace(":", "\\:")
        text = text.replace("%", "\\%")
        return text
    
    def launch(
        self,
        video_left: str,
        video_right: str,
        video_third: Optional[str] = None,
        title_left: Optional[str] = None,
        title_right: Optional[str] = None,
        title_third: Optional[str] = None,
        show_titles: bool = True,
        fullscreen: bool = True,
        comparison_mode: str = "standard",
        debug_view: str = "display",
    ) -> subprocess.Popen:
        """
        Launch MPV with video comparison.
        """
        print(f"MPV Launch Request:")
        print(f"  Left: {video_left}")
        print(f"  Right: {video_right}")
        print(f"  Third: {video_third}")
        print(f"  Show Titles: {show_titles}")
        print(f"  Comparison Mode: {comparison_mode}")
        print(f"  Debug View: {debug_view}")
        
        # Get paths
        mpv_path = self.finder.find_mpv(self.settings.get("mpv_path"))
        font_path = self.finder.find_font(self.settings.get("font_path"))
        
        if not mpv_path:
            raise RuntimeError("MPV not found")
        
        if not font_path:
            raise RuntimeError("Font file not found")
        
        if not video_left or not Path(video_left).exists():
            raise RuntimeError(f"Left video not found: {video_left}")
            
        if not video_right or not Path(video_right).exists():
            raise RuntimeError(f"Right video not found: {video_right}")
        
        if video_left == video_right:
            print("WARNING: Left and Right videos are the same file!")
        
        # Get titles from settings if not provided
        if title_left is None:
            title_left = self.settings.get("title_left")
        if title_right is None:
            title_right = self.settings.get("title_right")
        if title_third is None:
            title_third = self.settings.get("title_third")
        
        has_third = video_third is not None and Path(video_third).exists()
        
        # Build filter complex
        filter_complex = self.build_filter_complex(
            title_left=title_left,
            title_right=title_right,
            font_path=font_path,
            title_third=title_third,
            has_third_video=has_third,
            show_titles=show_titles,
            comparison_mode=comparison_mode,
            debug_view=debug_view,
        )
        
        # Build command
        cmd = [mpv_path, video_left]
        
        # Add external files
        cmd.append(f"--external-file={video_right}")
        
        if has_third:
            cmd.append(f"--external-file={video_third}")
        
        # Add filter complex
        cmd.append(f"--lavfi-complex={filter_complex}")
        
        # Add fullscreen if requested
        if fullscreen:
            cmd.append("--fs")
        else:
            # Use autofit-larger to ensure window fits on screen
            cmd.append("--autofit-larger=100%x100%")
            # Ensure window is resizable
            cmd.append("--no-keepaspect-window")
        
        # Force window
        cmd.append("--force-window=immediate")

        # Screenshot directory (defaults to Desktop to avoid permission issues)
        desktop_path = Path(os.path.expanduser("~/Desktop"))
        if desktop_path.exists():
            cmd.append(f"--screenshot-directory={desktop_path}")
            cmd.append("--screenshot-template=video-diff-%F-%p")
        
        # Launch MPV
        print(f"Launching MPV command: {cmd}")
        
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1  # Line buffered
        }
        
        if platform.system() == "Windows":
            # On Windows, use CREATE_NO_WINDOW to avoid console popup
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startupinfo
            
        return subprocess.Popen(cmd, **kwargs)
    
    def get_mpv_status(self) -> tuple[bool, str]:
        """Check if MPV is available and return status."""
        mpv_path = self.finder.find_mpv(self.settings.get("mpv_path"))
        
        if mpv_path:
            valid, version = self.finder.validate_binary(mpv_path, "mpv")
            if valid:
                return True, f"MPV found: {version}"
            return False, f"MPV invalid: {version}"
        
        return False, "MPV not found"
    
    def get_font_status(self) -> tuple[bool, str]:
        """Check if font is available and return status."""
        font_path = self.finder.find_font(self.settings.get("font_path"))
        
        if font_path:
            return True, f"Font: {Path(font_path).name}"
        
        return False, "No suitable font found"


# Global instance
_launcher_instance: Optional[MPVLauncher] = None


def get_mpv_launcher() -> MPVLauncher:
    """Get the global MPV launcher instance."""
    global _launcher_instance
    if _launcher_instance is None:
        _launcher_instance = MPVLauncher()
    return _launcher_instance
