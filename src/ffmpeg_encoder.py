"""FFmpeg encoder for video comparison output."""

import subprocess
import platform
import re
import os
import signal
from pathlib import Path
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
from enum import Enum

from .settings import get_settings
from .binary_finder import get_binary_finder
from .video_validator import get_video_validator, VideoInfo
from .comparison_mode import (
    get_debug_crop_filter,
    is_debug_view_mode,
    normalize_comparison_mode,
    normalize_debug_view,
)


class EncoderType(Enum):
    """Encoder types."""
    CPU = "cpu"
    VIDEOTOOLBOX = "hevc_videotoolbox"
    NVENC = "hevc_nvenc"
    AMF = "hevc_amf"
    QSV = "hevc_qsv"
    VAAPI = "hevc_vaapi"


@dataclass
class EncodingProgress:
    """Encoding progress information."""
    frame: int
    total_frames: int
    fps: float
    bitrate: str
    time: str
    speed: str
    percent: float


class FFmpegEncoder:
    """
    FFmpeg encoder for creating comparison videos.
    
    Output format: MP4 with YUV444-only video output
    Default settings:
    - Resolution: 2160p (3840x2160)
    - FPS: 60
    - QP: 17
    - GOP: 30
    """
    
    # CPU presets
    CPU_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
    YUV444_SAFE_ENCODERS = {
        EncoderType.CPU.value,
        EncoderType.NVENC.value,
    }
    LEGACY_ENCODER_ALIASES = {
        "cpu_h264_444": EncoderType.CPU.value,
    }
    
    # Resolution presets
    RESOLUTION_PRESETS = {
        "2160p": (3840, 2160),
        "1080p": (1920, 1080),
        "720p": (1280, 720),
    }
    
    def __init__(self):
        """Initialize encoder."""
        self.settings = get_settings()
        self.finder = get_binary_finder()
        self.validator = get_video_validator()
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._last_title_warning: Optional[str] = None
    
    def get_available_encoders(self) -> List[Dict[str, str]]:
        """Get list of available encoders (CPU + HW)."""
        encoders = [
            {"id": EncoderType.CPU.value, "name": "CPU (libx264 H.264 4:4:4)"},
        ]
        
        hw_encoders = self.finder.get_available_hw_encoders(
            self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        )
        encoders.extend(
            enc for enc in hw_encoders if enc["id"] in self.YUV444_SAFE_ENCODERS
        )
        
        return encoders
    
    def build_filter_complex(
        self,
        video_infos: Dict[str, VideoInfo],
        output_width: int,
        output_height: int,
        title_left: str,
        title_right: str,
        font_path: str,
        title_third: Optional[str] = None,
        has_third_video: bool = False,
        comparison_mode: str = "standard",
        debug_view: str = "display",
        enable_titles: bool = True,
    ) -> str:
        """
        Build FFmpeg filter complex for encoding.
        
        Each input video is scaled to 1/2 of output dimensions while keeping aspect ratio.
        """
        # Calculate cell dimensions (1/2 of output)
        cell_width = output_width // 2
        cell_height = output_height // 2
        
        # Format font path for FFmpeg
        formatted_font = self.finder.format_font_path_for_ffmpeg(font_path) if enable_titles else ""
        
        # Escape special characters
        title_left_escaped = self._escape_ffmpeg_text(title_left)
        title_right_escaped = self._escape_ffmpeg_text(title_right)
        comparison_mode = normalize_comparison_mode(comparison_mode)
        debug_view = normalize_debug_view(debug_view)
        debug_crop = get_debug_crop_filter(debug_view) if is_debug_view_mode(comparison_mode) else ""
        
        # Scale filter with padding to fit each output cell while maintaining aspect ratio.
        scale_pad = (
            f"scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,"
            f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:black"
        )

        def make_drawtext(title: str) -> str:
            """Build a drawtext filter without leading separators."""
            if not enable_titles or not title:
                return ""
            return (
                f"drawtext=fontfile='{formatted_font}':"
                f"text='{title}':"
                f"x=(w-text_w)/2:y=(h-text_h)-100:"
                f"fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.5:boxborderw=5"
            )

        def make_chain(*filters: str) -> str:
            """Join non-empty filters into a valid FFmpeg chain."""
            return ",".join(filter(None, filters))

        def make_split_chain(input_label: str, source_label: str, display_label: str, diff_label: str) -> str:
            """Build input preprocessing and split chain."""
            if debug_crop:
                return (
                    f"{input_label}{debug_crop}[{source_label}];"
                    f"[{source_label}]split[{display_label}][{diff_label}]"
                )
            return f"{input_label}split[{display_label}][{diff_label}]"
        
        if has_third_video:
            title_third_escaped = self._escape_ffmpeg_text(title_third or "")
            
            filter_complex = (
                # Preprocess left/right so display and diff branches stay independent.
                f"{make_split_chain('[0:v]', 'v0_src', 'v0_display', 'v0_diff')};"
                f"{make_split_chain('[1:v]', 'v1_src', 'v1_display', 'v1_diff')};"
                # Scale display copies to the output cell size and add titles.
                f"[v0_display]{make_chain(scale_pad, make_drawtext(title_left_escaped))}[left];"
                f"[v1_display]{make_chain(scale_pad, make_drawtext(title_right_escaped))}[right];"
                # Match MPV preview semantics by blending original frames before scaling.
                f"[v0_diff][v1_diff]blend=all_mode=difference,{scale_pad}[blended];"
                # Scale and title the optional third video.
                f"[2:v]{make_chain(scale_pad, make_drawtext(title_third_escaped))}[third];"
                # Stack bottom row
                "[blended][third]hstack[down];"
                # Stack top row
                "[left][right]hstack[up];"
                # Stack top and bottom
                "[up][down]vstack[vo]"
            )
        else:
            # Create black frame for bottom right using pad
            filter_complex = (
                # Preprocess left/right so display and diff branches stay independent.
                f"{make_split_chain('[0:v]', 'v0_src', 'v0_display', 'v0_diff')};"
                f"{make_split_chain('[1:v]', 'v1_src', 'v1_display', 'v1_diff')};"
                # Scale display copies to the output cell size and add titles.
                f"[v0_display]{make_chain(scale_pad, make_drawtext(title_left_escaped))}[left];"
                f"[v1_display]{make_chain(scale_pad, make_drawtext(title_right_escaped))}[right];"
                # Match MPV preview semantics by blending original frames before scaling.
                f"[v0_diff][v1_diff]blend=all_mode=difference,{scale_pad}[blended];"
                # Pad blended to create black area on right (2x width)
                f"[blended]pad=2*iw:ih:0:0:black[down];"
                # Stack top row
                "[left][right]hstack[up];"
                # Stack top and bottom
                "[up][down]vstack[vo]"
            )
        
        return filter_complex

    def normalize_encoder_id(self, encoder: str) -> str:
        """Map legacy encoder ids to the current set of supported ids."""
        return self.LEGACY_ENCODER_ALIASES.get(encoder, encoder)
    
    def _escape_ffmpeg_text(self, text: str) -> str:
        """Escape special characters for FFmpeg drawtext filter."""
        if not text:
            return ""
        # Escape in order: backslash, single quote, colon, percent, backslash for ffmpeg
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "'\\''")
        text = text.replace(":", "\\:")
        text = text.replace("%", "\\%")
        return text
    
    def build_encoding_command(
        self,
        video_left: str,
        video_right: str,
        output_path: str,
        video_third: Optional[str] = None,
        title_left: Optional[str] = None,
        title_right: Optional[str] = None,
        title_third: Optional[str] = None,
        output_width: int = 3840,
        output_height: int = 2160,
        output_fps: int = 60,
        qp: int = 17,
        gop: int = 30,
        encoder: str = "auto",
        cpu_preset: str = "veryfast",
        comparison_mode: str = "standard",
        debug_view: str = "display",
    ) -> List[str]:
        """Build FFmpeg command for encoding."""
        ffmpeg_path = self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        font_path = self.finder.find_font(self.settings.get("font_path"))
        comparison_mode = normalize_comparison_mode(comparison_mode)
        debug_view = normalize_debug_view(debug_view)
        self._last_title_warning = None
        
        if not ffmpeg_path:
            raise RuntimeError("FFmpeg not found")
        
        # Get titles from settings if not provided
        if title_left is None:
            title_left = self.settings.get("title_left")
        if title_right is None:
            title_right = self.settings.get("title_right")
        if title_third is None:
            title_third = self.settings.get("title_third")
        
        has_third = (
            not is_debug_view_mode(comparison_mode)
            and video_third is not None
            and Path(video_third).exists()
        )

        enable_titles = True
        title_warning = self._get_title_overlay_warning(
            ffmpeg_path=ffmpeg_path,
            font_path=font_path,
            title_left=title_left,
            title_right=title_right,
            title_third=title_third,
            has_third=has_third,
        )
        if title_warning:
            enable_titles = False
            self._last_title_warning = title_warning
        
        # Get video info for building filter
        videos_to_check = {"left": video_left, "right": video_right}
        if has_third:
            videos_to_check["third"] = video_third
        
        video_infos = {
            name: info
            for name, info in self.validator.get_video_infos(
                videos_to_check,
                require_consistent_backend=True,
            ).items()
            if info is not None
        }
        
        # Build filter complex
        filter_complex = self.build_filter_complex(
            video_infos=video_infos,
            output_width=output_width,
            output_height=output_height,
            title_left=title_left,
            title_right=title_right,
            font_path=font_path,
            title_third=title_third,
            has_third_video=has_third,
            comparison_mode=comparison_mode,
            debug_view=debug_view,
            enable_titles=enable_titles,
        )
        
        # Determine encoder
        actual_encoder = self._resolve_encoder(encoder)
        
        # Build command
        cmd = [ffmpeg_path, "-y"]  # -y to overwrite output
        
        # Add inputs
        cmd.extend(["-i", video_left])
        cmd.extend(["-i", video_right])
        if has_third:
            cmd.extend(["-i", video_third])
        
        # Add filter complex
        cmd.extend(["-filter_complex", filter_complex])
        
        # Map output from filter
        cmd.extend(["-map", "[vo]"])
        
        # Set output FPS
        cmd.extend(["-r", str(output_fps)])
        
        # Encoding settings based on encoder type
        if actual_encoder not in self.YUV444_SAFE_ENCODERS:
            raise RuntimeError(
                f"Encoder '{actual_encoder}' does not support the required yuv444p output."
            )

        if actual_encoder == EncoderType.CPU.value:
            # CPU encoding with libx264 High 4:4:4 Predictive
            cmd.extend([
                "-c:v", "libx264",
                "-preset", cpu_preset,
                "-qp", str(qp),
                "-profile:v", "high444",
                "-pix_fmt", "yuv444p",
                "-tag:v", "avc1",
            ])
            cmd.extend(["-g", str(gop)])
        elif actual_encoder == EncoderType.NVENC.value:
            # NVIDIA NVENC
            cmd.extend([
                "-c:v", "hevc_nvenc",
                "-preset", "p7",  # Highest quality preset for NVENC
                "-tune", "hq",
                "-rc", "constqp",
                "-qp", str(qp),
                "-profile:v", "rext",  # Use rext for 4:4:4 support (main444 not always available)
                "-pix_fmt", "yuv444p",
                "-tag:v", "hvc1",
            ])
            cmd.extend(["-g", str(gop)])
        else:
            # Fallback to CPU
            cmd.extend([
                "-c:v", "libx264",
                "-preset", cpu_preset,
                "-qp", str(qp),
                "-profile:v", "high444",
                "-pix_fmt", "yuv444p",
                "-tag:v", "avc1",
            ])
            cmd.extend(["-g", str(gop)])
        
        # No audio
        cmd.extend(["-an"])
        
        # Output format
        cmd.extend(["-f", "mp4"])
        
        # Output file
        cmd.append(output_path)
        
        return cmd

    def _get_title_overlay_warning(
        self,
        ffmpeg_path: str,
        font_path: Optional[str],
        title_left: Optional[str],
        title_right: Optional[str],
        title_third: Optional[str],
        has_third: bool,
    ) -> Optional[str]:
        """Return a warning string when title overlays cannot be applied."""

        titles_requested = bool(title_left or title_right or (title_third if has_third else ""))
        if not titles_requested:
            return None

        if not self.finder.has_ffmpeg_filter(ffmpeg_path, "drawtext"):
            return "FFmpeg drawtext filter is unavailable; encoding without title overlays."

        if not font_path:
            return "No font file was found; encoding without title overlays."

        return None
    
    def _resolve_encoder(self, encoder: str) -> str:
        """Resolve 'auto' encoder to best available."""
        encoder = self.normalize_encoder_id(encoder)
        if encoder != "auto":
            return encoder
        
        # Try to find the best available HW encoder that preserves yuv444p.
        hw_encoders = self.finder.get_available_hw_encoders(
            self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        )

        for enc in hw_encoders:
            if enc["id"] in self.YUV444_SAFE_ENCODERS:
                return enc["id"]
        
        return EncoderType.CPU.value
    
    def encode(
        self,
        video_left: str,
        video_right: str,
        output_path: str,
        video_third: Optional[str] = None,
        title_left: Optional[str] = None,
        title_right: Optional[str] = None,
        title_third: Optional[str] = None,
        output_width: int = 3840,
        output_height: int = 2160,
        output_fps: int = 60,
        qp: int = 17,
        gop: int = 30,
        encoder: str = "auto",
        cpu_preset: str = "veryfast",
        comparison_mode: str = "standard",
        debug_view: str = "display",
        progress_callback: Optional[Callable[[EncodingProgress], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Encode video comparison.
        
        Args:
            video_left: Path to left video
            video_right: Path to right video  
            output_path: Output file path
            video_third: Optional third video
            title_*: Video titles
            output_width/height: Output resolution
            output_fps: Output frame rate
            qp: Quality parameter
            gop: GOP size
            encoder: Encoder to use
            cpu_preset: CPU encoding preset
            progress_callback: Called with progress updates
            log_callback: Called with log lines
            
        Returns:
            True if successful, False otherwise
        """
        self._cancelled = False
        
        # Validate videos
        comparison_mode = normalize_comparison_mode(comparison_mode)
        debug_view = normalize_debug_view(debug_view)
        has_third = video_third is not None and Path(video_third).exists()
        if is_debug_view_mode(comparison_mode):
            valid, error, video_infos = self.validator.validate_videos_for_debug_view(
                video_left,
                video_right,
            )
            has_third = False
        else:
            valid, error, video_infos = self.validator.validate_videos_for_comparison(
                video_left,
                video_right,
                video_third if has_third else None,
            )
        
        if not valid:
            if log_callback:
                log_callback(f"ERROR: {error}")
            return False
        
        # Get total frames for progress
        total_frames = video_infos["left"].frame_count if video_infos else 0
        
        # Build command
        cmd = self.build_encoding_command(
            video_left=video_left,
            video_right=video_right,
            output_path=output_path,
            video_third=video_third,
            title_left=title_left,
            title_right=title_right,
            title_third=title_third,
            output_width=output_width,
            output_height=output_height,
            output_fps=output_fps,
            qp=qp,
            gop=gop,
            encoder=encoder,
            cpu_preset=cpu_preset,
            comparison_mode=comparison_mode,
            debug_view=debug_view,
        )
        
        if log_callback:
            log_callback(f"Command: {' '.join(cmd)}\n")
            log_callback("-" * 50 + "\n")
            if self._last_title_warning:
                log_callback(f"WARNING: {self._last_title_warning}\n")
        
        try:
            # Start FFmpeg process
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Read stderr for progress
            for line in self._process.stderr:
                if self._cancelled:
                    self._kill_process()
                    if log_callback:
                        log_callback("\nEncoding cancelled by user.\n")
                    return False
                
                if log_callback:
                    log_callback(line)
                
                # Parse progress
                if progress_callback and "frame=" in line:
                    progress = self._parse_progress(line, total_frames)
                    if progress:
                        progress_callback(progress)
            
            # Wait for completion
            self._process.wait()
            
            if self._process.returncode == 0:
                if log_callback:
                    log_callback("\nEncoding completed successfully!\n")
                return True
            else:
                if log_callback:
                    log_callback(f"\nEncoding failed with return code: {self._process.returncode}\n")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"\nError during encoding: {e}\n")
            return False
        finally:
            self._process = None
    
    def _parse_progress(self, line: str, total_frames: int) -> Optional[EncodingProgress]:
        """Parse FFmpeg progress line."""
        try:
            # Parse frame=
            frame_match = re.search(r'frame=\s*(\d+)', line)
            frame = int(frame_match.group(1)) if frame_match else 0
            
            # Parse fps=
            fps_match = re.search(r'fps=\s*([\d.]+)', line)
            fps = float(fps_match.group(1)) if fps_match else 0.0
            
            # Parse bitrate=
            bitrate_match = re.search(r'bitrate=\s*([\d.]+\w+)', line)
            bitrate = bitrate_match.group(1) if bitrate_match else "N/A"
            
            # Parse time=
            time_match = re.search(r'time=\s*([\d:.]+)', line)
            time_str = time_match.group(1) if time_match else "00:00:00"
            
            # Parse speed=
            speed_match = re.search(r'speed=\s*([\d.]+x)', line)
            speed = speed_match.group(1) if speed_match else "N/A"
            
            # Calculate percent
            percent = (frame / total_frames * 100) if total_frames > 0 else 0
            
            return EncodingProgress(
                frame=frame,
                total_frames=total_frames,
                fps=fps,
                bitrate=bitrate,
                time=time_str,
                speed=speed,
                percent=min(100, percent)
            )
        except (ValueError, AttributeError):
            return None
    
    def cancel(self) -> None:
        """Cancel ongoing encoding."""
        self._cancelled = True
    
    def _kill_process(self) -> None:
        """Kill the FFmpeg process."""
        if self._process:
            if platform.system() == "Windows":
                self._process.terminate()
            else:
                os.kill(self._process.pid, signal.SIGTERM)
            self._process.wait()
    
    def get_ffmpeg_status(self) -> tuple[bool, str]:
        """Check if FFmpeg is available and return status."""
        ffmpeg_path = self.finder.find_ffmpeg(self.settings.get("ffmpeg_path"))
        
        if ffmpeg_path:
            valid, version = self.finder.validate_binary(ffmpeg_path, "ffmpeg")
            if valid:
                return True, f"FFmpeg found: {version}"
            return False, f"FFmpeg invalid: {version}"
        
        return False, "FFmpeg not found"


# Global instance
_encoder_instance: Optional[FFmpegEncoder] = None


def get_ffmpeg_encoder() -> FFmpegEncoder:
    """Get the global FFmpeg encoder instance."""
    global _encoder_instance
    if _encoder_instance is None:
        _encoder_instance = FFmpegEncoder()
    return _encoder_instance
