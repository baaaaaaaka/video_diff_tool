"""Binary finder for MPV, FFmpeg, and fonts."""

import os
import platform
import shutil
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


class BinaryFinder:
    """Finds and validates required binaries and fonts."""
    
    # Common installation paths by OS
    MPV_PATHS = {
        "Darwin": [
            "/opt/homebrew/bin/mpv",
            "/usr/local/bin/mpv",
            "/Applications/mpv.app/Contents/MacOS/mpv",
        ],
        "Windows": [
            r"C:\Program Files\mpv\mpv.exe",
            r"C:\Program Files (x86)\mpv\mpv.exe",
            r"C:\mpv\mpv.exe",
        ],
    }
    
    FFMPEG_PATHS = {
        "Darwin": [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
        ],
        "Windows": [
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
        ],
    }
    
    FFPROBE_PATHS = {
        "Darwin": [
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
        ],
        "Windows": [
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
            r"C:\ffmpeg\bin\ffprobe.exe",
        ],
    }
    
    # Font paths by OS
    FONT_PATHS = {
        "Darwin": [
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/HelveticaNeue.ttc",
        ],
        "Linux": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ],
        "Windows": [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\Arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
        ],
    }
    
    # Installation instructions
    INSTALL_INSTRUCTIONS = {
        "mpv": {
            "Darwin": "Install mpv using Homebrew:\n\nbrew install mpv\n\nOr download from: https://mpv.io/installation/",
            "Windows": "Download mpv from: https://mpv.io/installation/\n\nOr use Chocolatey:\nchoco install mpv\n\nOr use Scoop:\nscoop install mpv",
        },
        "ffmpeg": {
            "Darwin": "Install FFmpeg using Homebrew:\n\nbrew install ffmpeg\n\nOr download from: https://ffmpeg.org/download.html",
            "Windows": "Download FFmpeg from: https://ffmpeg.org/download.html\n\nOr use Chocolatey:\nchoco install ffmpeg\n\nOr use Scoop:\nscoop install ffmpeg",
        },
    }
    
    def __init__(self):
        """Initialize binary finder."""
        self.system = platform.system()
        self._hw_encoders_cache: Optional[List[Dict[str, str]]] = None
        self._ffmpeg_filter_cache: Dict[Tuple[str, str], bool] = {}
    
    def find_mpv(self, custom_path: str = "") -> Optional[str]:
        """Find mpv binary."""
        return self._find_binary("mpv", custom_path, self.MPV_PATHS)
    
    def find_ffmpeg(self, custom_path: str = "") -> Optional[str]:
        """Find ffmpeg binary."""
        return self._find_binary("ffmpeg", custom_path, self.FFMPEG_PATHS)
    
    def find_ffprobe(self, custom_path: str = "") -> Optional[str]:
        """Find ffprobe binary."""
        return self._find_binary("ffprobe", custom_path, self.FFPROBE_PATHS)
    
    def find_font(self, custom_path: str = "") -> Optional[str]:
        """Find a suitable font file."""
        if custom_path and Path(custom_path).exists():
            return custom_path
        
        # Check OS-specific paths
        paths = self.FONT_PATHS.get(self.system, [])
        existing_paths = [path for path in paths if Path(path).exists()]

        if self.system == "Darwin":
            # FFmpeg drawtext is more reliable with TTF than TTC collections.
            existing_paths.sort(key=lambda path: Path(path).suffix.lower() != ".ttf")

        for path in existing_paths:
            return path

        if self.system == "Linux":
            try:
                result = subprocess.run(
                    ["fc-match", "--format", "%{file}\n", "sans"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                candidate = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
                if candidate and Path(candidate).exists():
                    return candidate
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError, IndexError):
                pass
        
        return None
    
    def _find_binary(self, name: str, custom_path: str, paths_dict: Dict[str, List[str]]) -> Optional[str]:
        """Find a binary by name."""
        # Check custom path first
        if custom_path:
            path = Path(custom_path)
            if path.exists() and path.is_file():
                return str(path)
        
        # Check PATH
        which_result = shutil.which(name)
        if which_result:
            return which_result
        
        # Check OS-specific paths
        paths = paths_dict.get(self.system, [])
        for path in paths:
            if Path(path).exists():
                return path
        
        return None
    
    def get_install_instructions(self, binary: str) -> str:
        """Get installation instructions for a binary."""
        instructions = self.INSTALL_INSTRUCTIONS.get(binary, {})
        return instructions.get(self.system, f"Please install {binary} and add it to your PATH.")
    
    def get_available_hw_encoders(self, ffmpeg_path: Optional[str] = None) -> List[Dict[str, str]]:
        """Get list of available hardware HEVC encoders."""
        if self._hw_encoders_cache is not None:
            return self._hw_encoders_cache
        
        if not ffmpeg_path:
            ffmpeg_path = self.find_ffmpeg()
        
        if not ffmpeg_path:
            return []
        
        encoders = []
        
        try:
            result = subprocess.run(
                [ffmpeg_path, "-encoders", "-hide_banner"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout
            
            # HEVC hardware encoders to look for
            hw_encoder_info = {
                "hevc_videotoolbox": {"name": "VideoToolbox (macOS)", "os": "Darwin"},
                "hevc_nvenc": {"name": "NVENC (NVIDIA)", "os": "all"},
                "hevc_qsv": {"name": "QuickSync (Intel)", "os": "all"},
                "hevc_vaapi": {"name": "VAAPI (Linux)", "os": "Linux"},
                "hevc_amf": {"name": "AMF (AMD)", "os": "Windows"},
            }
            
            potential_encoders = []
            for encoder, info in hw_encoder_info.items():
                if info["os"] != "all" and info["os"] != self.system:
                    continue
                    
                # Check if encoder is in the output
                if re.search(rf'\s{encoder}\s', output):
                    potential_encoders.append((encoder, info))
            
            # Check usability in parallel
            usable_results = {}
            with ThreadPoolExecutor() as executor:
                future_to_encoder = {
                    executor.submit(self._check_encoder_usability, ffmpeg_path, enc): enc
                    for enc, info in potential_encoders
                }
                
                for future in as_completed(future_to_encoder):
                    enc_id = future_to_encoder[future]
                    try:
                        usable_results[enc_id] = future.result()
                    except Exception:
                        usable_results[enc_id] = False
            
            # Re-populate encoders list preserving preference order
            for enc, info in potential_encoders:
                if usable_results.get(enc, False):
                    encoders.append({
                        "id": enc,
                        "name": info["name"],
                    })
        
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            pass
        
        self._hw_encoders_cache = encoders
        return encoders

    def has_ffmpeg_filter(self, ffmpeg_path: str, filter_name: str) -> bool:
        """Check whether the selected FFmpeg build exposes a specific filter."""

        cache_key = (ffmpeg_path, filter_name)
        if cache_key in self._ffmpeg_filter_cache:
            return self._ffmpeg_filter_cache[cache_key]

        available = False
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                available = re.search(rf"\s{re.escape(filter_name)}\s", result.stdout) is not None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            available = False

        self._ffmpeg_filter_cache[cache_key] = available
        return available
    
    def _check_encoder_usability(self, ffmpeg_path: str, encoder: str) -> bool:
        """Check if an encoder is actually usable on the system."""
        try:
            pix_fmt = "yuv420p"
            profile = "main"
            if encoder == "hevc_nvenc":
                pix_fmt = "yuv444p"
                profile = "rext"

            # Run a minimal encoding test: 1 frame of black color
            # Use 256x256 to satisfy alignment requirements of some HW encoders (128x128 is too small for some NVENC)
            cmd = [
                ffmpeg_path,
                "-y",
                "-v", "error",
                "-f", "lavfi",
                "-i", "color=black:s=256x256:r=1",
                "-c:v", encoder,
                "-pix_fmt", pix_fmt,
                "-profile:v", profile,
                "-frames:v", "1",
                "-f", "null",
                "-"
            ]
            
            # On Windows, suppress console window
            startupinfo = None
            if self.system == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                startupinfo=startupinfo
            )
            
            return result.returncode == 0
        except Exception:
            return False
    
    def validate_binary(self, path: str, binary_type: str) -> Tuple[bool, str]:
        """Validate a binary by running a version check."""
        if not path or not Path(path).exists():
            return False, "File not found"
        
        try:
            if binary_type in ("mpv", "ffmpeg", "ffprobe"):
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Extract version from first line
                    version = result.stdout.split('\n')[0]
                    return True, version
                return False, "Invalid binary"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            return False, str(e)
        
        return False, "Unknown error"
    
    def format_font_path_for_ffmpeg(self, font_path: str) -> str:
        """Format font path for use in FFmpeg filter (handles Windows paths)."""
        if self.system == "Windows":
            # On Windows, replace backslashes with forward slashes
            # AND escape the colon (C: -> C\:)
            # This works safely inside single quotes in the filter string.
            path = font_path.replace("\\", "/")
            if len(path) > 1 and path[1] == ":":
                path = path[0] + "\\:" + path[2:]
            return path
        return font_path


# Global instance
_finder_instance: Optional[BinaryFinder] = None


def get_binary_finder() -> BinaryFinder:
    """Get the global binary finder instance."""
    global _finder_instance
    if _finder_instance is None:
        _finder_instance = BinaryFinder()
    return _finder_instance
