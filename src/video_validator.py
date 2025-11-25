"""Video validation utilities."""

import subprocess
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from .binary_finder import get_binary_finder


@dataclass
class VideoInfo:
    """Video file information."""
    path: str
    width: int
    height: int
    frame_count: int
    duration: float
    fps: float
    codec: str
    
    @property
    def aspect_ratio(self) -> float:
        """Get aspect ratio."""
        return self.width / self.height if self.height > 0 else 1.0


class VideoValidator:
    """Validates video files and checks compatibility."""
    
    def __init__(self, ffprobe_path: Optional[str] = None):
        """Initialize validator."""
        self.ffprobe_path = ffprobe_path or get_binary_finder().find_ffprobe()
    
    def get_video_info(self, video_path: str) -> Optional[VideoInfo]:
        """Get video information using ffprobe."""
        if not self.ffprobe_path:
            raise RuntimeError("ffprobe not found")
        
        if not Path(video_path).exists():
            return None
        
        try:
            # Get stream info
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    "-select_streams", "v:0",
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return None
            
            data = json.loads(result.stdout)
            
            if not data.get("streams"):
                return None
            
            stream = data["streams"][0]
            format_info = data.get("format", {})
            
            # Extract frame count
            frame_count = int(stream.get("nb_frames", 0))
            
            # If nb_frames not available, try to calculate from duration and fps
            if frame_count == 0:
                duration = float(format_info.get("duration", 0))
                fps_str = stream.get("r_frame_rate", "30/1")
                fps_parts = fps_str.split("/")
                fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
                frame_count = int(duration * fps)
            
            # Get FPS
            fps_str = stream.get("r_frame_rate", "30/1")
            fps_parts = fps_str.split("/")
            fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
            
            return VideoInfo(
                path=video_path,
                width=int(stream.get("width", 0)),
                height=int(stream.get("height", 0)),
                frame_count=frame_count,
                duration=float(format_info.get("duration", 0)),
                fps=fps,
                codec=stream.get("codec_name", "unknown")
            )
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Error getting video info: {e}")
            return None
    
    def validate_videos_for_comparison(
        self, 
        video1_path: str, 
        video2_path: str,
        video3_path: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, VideoInfo]]]:
        """
        Validate videos for comparison encoding.
        
        Returns:
            Tuple of (is_valid, error_message, video_infos)
        """
        videos = {"left": video1_path, "right": video2_path}
        if video3_path:
            videos["third"] = video3_path
        
        infos: Dict[str, VideoInfo] = {}
        
        # Get info for all videos
        for name, path in videos.items():
            if not path:
                return False, f"No video specified for {name}", None
            
            info = self.get_video_info(path)
            if not info:
                return False, f"Could not read video: {path}", None
            
            infos[name] = info
        
        # Validate frame counts match
        left_frames = infos["left"].frame_count
        right_frames = infos["right"].frame_count
        
        if left_frames != right_frames:
            return False, (
                f"Frame count mismatch!\n"
                f"Left video: {left_frames} frames\n"
                f"Right video: {right_frames} frames\n"
                f"Videos must have the same number of frames."
            ), None
        
        if video3_path and "third" in infos:
            third_frames = infos["third"].frame_count
            if third_frames != left_frames:
                return False, (
                    f"Frame count mismatch with third video!\n"
                    f"Left/Right videos: {left_frames} frames\n"
                    f"Third video: {third_frames} frames\n"
                    f"All videos must have the same number of frames."
                ), None
        
        return True, "", infos
    
    def get_frame_count(self, video_path: str) -> int:
        """Get frame count for a single video."""
        info = self.get_video_info(video_path)
        return info.frame_count if info else 0


# Global instance
_validator_instance: Optional[VideoValidator] = None


def get_video_validator() -> VideoValidator:
    """Get the global video validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = VideoValidator()
    return _validator_instance

