"""Video validation utilities."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from .binary_finder import get_binary_finder
from .settings import get_settings


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class _FileFingerprint:
    """Stable cache fingerprint for a path on disk."""

    normalized_path: str
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass
class _InflightProbe:
    """Tracks a single metadata probe shared across threads."""

    event: threading.Event
    value: Optional[VideoInfo] = None


class VideoValidator:
    """Validates video files and checks compatibility."""

    DEBUG_VIEW_RESOLUTION = (3840, 2160)
    MAX_CACHE_ENTRIES = 128
    MAX_PARALLEL_PROBES = 4
    BACKEND_AUTO = "auto"
    BACKEND_PYAV = "pyav"
    BACKEND_FFPROBE = "ffprobe"

    def __init__(self, ffprobe_path: Optional[str] = None):
        """Initialize validator."""
        self.settings = get_settings()
        self.finder = get_binary_finder()
        self._ffprobe_path_override = ffprobe_path
        self._cache: "OrderedDict[tuple[object, ...], VideoInfo]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._inflight: Dict[tuple[object, ...], _InflightProbe] = {}
        self._pyav_module = None
        self._pyav_loaded = False
        self._pyav_lock = threading.Lock()

    def get_available_metadata_backends(self) -> list[str]:
        """Return metadata backends available on this machine."""
        backends: list[str] = []
        if self._load_pyav_module() is not None:
            backends.append(self.BACKEND_PYAV)
        if self._resolve_ffprobe_path():
            backends.append(self.BACKEND_FFPROBE)
        return backends

    def clear_cache(self) -> None:
        """Clear all cached metadata and in-flight bookkeeping."""
        with self._cache_lock:
            self._cache.clear()
            self._inflight.clear()

    def get_video_info(
        self,
        video_path: str,
        preferred_backend: str = BACKEND_AUTO,
    ) -> Optional[VideoInfo]:
        """Get video information using the preferred backend order."""
        if not video_path:
            return None

        if not Path(video_path).exists():
            return None

        backend_error: Optional[RuntimeError] = None
        for backend in self._get_backend_order(preferred_backend):
            try:
                self._ensure_backend_available(backend)
                info = self._get_video_info_with_backend(video_path, backend)
            except RuntimeError as exc:
                backend_error = exc
                continue
            if info is not None:
                return info

        if backend_error is not None:
            raise backend_error

        return None

    def get_video_infos(
        self,
        video_paths: Dict[str, str],
        preferred_backend: str = BACKEND_AUTO,
        require_consistent_backend: bool = True,
    ) -> Dict[str, Optional[VideoInfo]]:
        """Get video metadata for multiple paths."""
        if require_consistent_backend:
            return self._get_video_infos_batch(video_paths, preferred_backend)

        return {
            name: self.get_video_info(path, preferred_backend=preferred_backend)
            for name, path in video_paths.items()
        }

    def prewarm_video_infos(
        self,
        video_paths: Iterable[str],
        preferred_backend: str = BACKEND_AUTO,
    ) -> None:
        """Warm the in-memory metadata cache for the provided paths."""
        unique_paths: dict[str, str] = {}
        for index, path in enumerate(video_paths):
            if path:
                unique_paths[f"video_{index}"] = path

        if not unique_paths:
            return

        try:
            self._get_video_infos_batch(unique_paths, preferred_backend)
        except RuntimeError:
            # Prewarm is best-effort and should never interrupt UI flows.
            return

    def validate_videos_for_comparison(
        self,
        video1_path: str,
        video2_path: str,
        video3_path: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, VideoInfo]]]:
        """
        Validate videos for comparison encoding.

        Returns:
            Tuple of (is_valid, error_message, video_infos)
        """
        videos = {"left": video1_path, "right": video2_path}
        if video3_path:
            videos["third"] = video3_path

        for name, path in videos.items():
            if not path:
                return False, f"No video specified for {name}", None

        try:
            infos = self._get_video_infos_batch(videos, preferred_backend=self.BACKEND_AUTO)
        except RuntimeError as exc:
            return False, str(exc), None

        for name, path in videos.items():
            if infos.get(name) is None:
                return False, f"Could not read video: {path}", None

        typed_infos = {name: info for name, info in infos.items() if info is not None}

        # Validate frame counts match
        left_frames = typed_infos["left"].frame_count
        right_frames = typed_infos["right"].frame_count

        if left_frames != right_frames:
            return False, (
                f"Frame count mismatch!\n"
                f"Left video: {left_frames} frames\n"
                f"Right video: {right_frames} frames\n"
                f"Videos must have the same number of frames."
            ), None

        if video3_path and "third" in typed_infos:
            third_frames = typed_infos["third"].frame_count
            if third_frames != left_frames:
                return False, (
                    f"Frame count mismatch with third video!\n"
                    f"Left/Right videos: {left_frames} frames\n"
                    f"Third video: {third_frames} frames\n"
                    f"All videos must have the same number of frames."
                ), None

        return True, "", typed_infos

    def validate_videos_for_debug_view(
        self,
        video1_path: str,
        video2_path: str,
    ) -> Tuple[bool, str, Optional[Dict[str, VideoInfo]]]:
        """Validate videos for cropped debug-view comparison."""

        valid, error, infos = self.validate_videos_for_comparison(
            video1_path,
            video2_path,
            None,
        )
        if not valid or infos is None:
            return valid, error, infos

        left_info = infos["left"]
        right_info = infos["right"]

        if left_info.width != right_info.width or left_info.height != right_info.height:
            return False, (
                "Debug View mode requires matching input resolutions.\n"
                f"Left video: {left_info.width}x{left_info.height}\n"
                f"Right video: {right_info.width}x{right_info.height}"
            ), None

        required_width, required_height = self.DEBUG_VIEW_RESOLUTION
        if (left_info.width, left_info.height) != self.DEBUG_VIEW_RESOLUTION:
            return False, (
                "Debug View mode expects 3840x2160 debug videos.\n"
                f"Left video: {left_info.width}x{left_info.height}\n"
                f"Right video: {right_info.width}x{right_info.height}\n"
                f"Expected: {required_width}x{required_height}"
            ), None

        return True, "", infos

    def get_frame_count(self, video_path: str) -> int:
        """Get frame count for a single video."""
        info = self.get_video_info(video_path)
        return info.frame_count if info else 0

    def _get_video_infos_batch(
        self,
        video_paths: Dict[str, str],
        preferred_backend: str,
    ) -> Dict[str, Optional[VideoInfo]]:
        """Probe a batch of videos using one backend per attempt."""
        backend_error: Optional[RuntimeError] = None
        last_result = {name: None for name in video_paths}

        for backend in self._get_backend_order(preferred_backend):
            try:
                result = self._probe_videos_with_backend(video_paths, backend)
            except RuntimeError as exc:
                backend_error = exc
                continue

            last_result = result
            if all(info is not None for info in result.values()):
                return result

        if backend_error is not None and all(info is None for info in last_result.values()):
            raise backend_error

        return last_result

    def _probe_videos_with_backend(
        self,
        video_paths: Dict[str, str],
        backend: str,
    ) -> Dict[str, Optional[VideoInfo]]:
        """Probe multiple videos in parallel with a single backend."""
        self._ensure_backend_available(backend)

        items = list(video_paths.items())
        if len(items) <= 1:
            return {
                name: self._get_video_info_with_backend(path, backend)
                for name, path in items
            }

        results: Dict[str, Optional[VideoInfo]] = {}
        max_workers = min(len(items), self.MAX_PARALLEL_PROBES)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._get_video_info_with_backend, path, backend): name
                for name, path in items
            }
            for future in as_completed(future_map):
                results[future_map[future]] = future.result()

        return {name: results.get(name) for name, _ in items}

    def _get_video_info_with_backend(
        self,
        video_path: str,
        backend: str,
    ) -> Optional[VideoInfo]:
        """Probe a file using a specific backend with cache and single-flight."""
        fingerprint = self._get_file_fingerprint(video_path)
        if fingerprint is None:
            return None

        cache_key = (
            backend,
            self._get_backend_signature(backend),
            fingerprint.normalized_path,
            fingerprint.size,
            fingerprint.mtime_ns,
            fingerprint.ctime_ns,
        )

        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached

            inflight = self._inflight.get(cache_key)
            if inflight is None:
                inflight = _InflightProbe(event=threading.Event())
                self._inflight[cache_key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            inflight.event.wait()
            return inflight.value

        try:
            info = self._probe_with_backend(video_path, backend)
            if info is None:
                inflight.value = None
                return None

            fingerprint_after = self._get_file_fingerprint(video_path)
            if fingerprint_after != fingerprint:
                inflight.value = None
                return None

            with self._cache_lock:
                self._cache[cache_key] = info
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self.MAX_CACHE_ENTRIES:
                    self._cache.popitem(last=False)

            inflight.value = info
            return info
        finally:
            with self._cache_lock:
                inflight.event.set()
                self._inflight.pop(cache_key, None)

    def _probe_with_backend(self, video_path: str, backend: str) -> Optional[VideoInfo]:
        """Probe a single file using the selected backend."""
        try:
            if backend == self.BACKEND_PYAV:
                return self._probe_with_pyav(video_path)
            if backend == self.BACKEND_FFPROBE:
                return self._probe_with_ffprobe(video_path)
        except Exception as exc:
            print(f"Error getting video info via {backend}: {exc}")
            return None

        raise RuntimeError(f"Unknown metadata backend: {backend}")

    def _probe_with_pyav(self, video_path: str) -> Optional[VideoInfo]:
        """Probe metadata using the in-process PyAV bindings."""
        av_module = self._load_pyav_module()
        if av_module is None:
            raise RuntimeError("PyAV is not available")

        container = av_module.open(video_path)
        try:
            stream = next((stream for stream in container.streams if stream.type == "video"), None)
            if stream is None:
                return None

            codec_context = getattr(stream, "codec_context", None)
            width = int(getattr(stream, "width", 0) or getattr(codec_context, "width", 0) or 0)
            height = int(getattr(stream, "height", 0) or getattr(codec_context, "height", 0) or 0)
            fps = self._ratio_to_float(
                getattr(stream, "average_rate", None)
                or getattr(stream, "base_rate", None)
                or getattr(stream, "guessed_rate", None)
            )

            duration = 0.0
            stream_duration = getattr(stream, "duration", None)
            time_base = getattr(stream, "time_base", None)
            if stream_duration is not None and time_base is not None:
                duration = float(stream_duration * time_base)
            elif getattr(container, "duration", None):
                duration = float(container.duration / av_module.time_base)

            frame_count = int(getattr(stream, "frames", 0) or 0)
            if frame_count == 0 and duration > 0 and fps > 0:
                frame_count = int(round(duration * fps))
            if duration == 0.0 and frame_count > 0 and fps > 0:
                duration = frame_count / fps

            codec_name = "unknown"
            codec_name = getattr(codec_context, "name", None) or getattr(stream, "name", None) or codec_name

            return VideoInfo(
                path=video_path,
                width=width,
                height=height,
                frame_count=frame_count,
                duration=duration,
                fps=fps,
                codec=codec_name,
            )
        finally:
            container.close()

    def _probe_with_ffprobe(self, video_path: str) -> Optional[VideoInfo]:
        """Probe metadata using ffprobe."""
        ffprobe_path = self._resolve_ffprobe_path()
        if not ffprobe_path:
            raise RuntimeError("ffprobe not found")

        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_entries",
                "format=duration:stream=width,height,nb_frames,r_frame_rate,codec_name",
                "-select_streams",
                "v:0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        if not data.get("streams"):
            return None

        stream = data["streams"][0]
        format_info = data.get("format", {})
        duration = self._parse_float(format_info.get("duration", 0.0))
        fps = self._parse_fps(stream.get("r_frame_rate", "30/1"))
        frame_count = int(stream.get("nb_frames", 0) or 0)
        if frame_count == 0 and duration > 0 and fps > 0:
            frame_count = int(duration * fps)

        return VideoInfo(
            path=video_path,
            width=int(stream.get("width", 0) or 0),
            height=int(stream.get("height", 0) or 0),
            frame_count=frame_count,
            duration=duration,
            fps=fps,
            codec=stream.get("codec_name", "unknown"),
        )

    def _resolve_ffprobe_path(self) -> Optional[str]:
        """Resolve the current ffprobe binary path."""
        custom_path = self._ffprobe_path_override
        if custom_path is None:
            custom_path = self.settings.get("ffprobe_path")
        return self.finder.find_ffprobe(custom_path or "")

    def _load_pyav_module(self):
        """Import PyAV lazily so the app still works without it."""
        if self._pyav_loaded:
            return self._pyav_module

        with self._pyav_lock:
            if self._pyav_loaded:
                return self._pyav_module

            try:
                self._pyav_module = importlib.import_module("av")
            except ImportError:
                self._pyav_module = None
            self._pyav_loaded = True
            return self._pyav_module

    def _get_backend_order(self, preferred_backend: str) -> list[str]:
        """Return the backend order for a probe attempt."""
        if preferred_backend == self.BACKEND_PYAV:
            return [self.BACKEND_PYAV]
        if preferred_backend == self.BACKEND_FFPROBE:
            return [self.BACKEND_FFPROBE]
        return [self.BACKEND_PYAV, self.BACKEND_FFPROBE]

    def _ensure_backend_available(self, backend: str) -> None:
        """Raise when a backend cannot be used in the current environment."""
        if backend == self.BACKEND_PYAV and self._load_pyav_module() is None:
            raise RuntimeError("PyAV is not available")
        if backend == self.BACKEND_FFPROBE and not self._resolve_ffprobe_path():
            raise RuntimeError("ffprobe not found")

    def _get_backend_signature(self, backend: str) -> str:
        """Return a cache signature that invalidates when backend config changes."""
        if backend == self.BACKEND_PYAV:
            av_module = self._load_pyav_module()
            version = getattr(av_module, "__version__", "missing") if av_module else "missing"
            return f"pyav:{version}"
        if backend == self.BACKEND_FFPROBE:
            return f"ffprobe:{self._resolve_ffprobe_path() or 'missing'}"
        return backend

    def _get_file_fingerprint(self, video_path: str) -> Optional[_FileFingerprint]:
        """Build a cache fingerprint from the current file metadata."""
        try:
            path = Path(video_path)
            stat = path.stat()
        except FileNotFoundError:
            return None

        normalized_path = os.path.realpath(str(path))
        normalized_path = os.path.normcase(normalized_path)
        return _FileFingerprint(
            normalized_path=normalized_path,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            ctime_ns=stat.st_ctime_ns,
        )

    def _parse_fps(self, fps_value: str) -> float:
        """Parse ffprobe's r_frame_rate string."""
        numerator, denominator = self._split_ratio(fps_value)
        return numerator / denominator if denominator else 0.0

    def _ratio_to_float(self, value) -> float:
        """Convert a Fraction-like object to float."""
        if value is None:
            return 0.0

        if isinstance(value, str):
            return self._parse_fps(value)

        numerator = getattr(value, "numerator", None)
        denominator = getattr(value, "denominator", None)
        if numerator is not None and denominator is not None:
            return float(numerator) / float(denominator) if denominator else 0.0

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _split_ratio(self, value: str) -> tuple[float, float]:
        """Split a ratio string like '24000/1001'."""
        parts = str(value).split("/")
        if len(parts) == 2:
            return self._parse_float(parts[0]), self._parse_float(parts[1])
        return self._parse_float(parts[0]), 1.0

    def _parse_float(self, value) -> float:
        """Convert a generic value to float."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


# Global instance
_validator_instance: Optional[VideoValidator] = None


def get_video_validator() -> VideoValidator:
    """Get the global video validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = VideoValidator()
    return _validator_instance
