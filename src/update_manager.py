"""GitHub release update helpers for packaged desktop builds."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .app_metadata import APP_BUNDLE_NAME, APP_VERSION, GITHUB_REPOSITORY


_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class ReleaseVersion:
    """Comparable release version parsed from semantic tags."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[tuple[int, object], ...]
    raw_prerelease: Optional[str]

    @classmethod
    def parse(cls, value: str) -> "ReleaseVersion":
        """Parse a version or tag string."""
        match = _VERSION_RE.match(value.strip())
        if not match:
            raise ValueError(f"Unsupported version format: {value}")

        raw_prerelease = match.group("prerelease")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=_parse_prerelease(raw_prerelease),
            raw_prerelease=raw_prerelease,
        )

    def _compare(self, other: "ReleaseVersion") -> int:
        left = (self.major, self.minor, self.patch)
        right = (other.major, other.minor, other.patch)
        if left != right:
            return -1 if left < right else 1

        if not self.prerelease and not other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1

        for left_part, right_part in zip(self.prerelease, other.prerelease):
            if left_part == right_part:
                continue
            return -1 if left_part < right_part else 1

        if len(self.prerelease) == len(other.prerelease):
            return 0
        return -1 if len(self.prerelease) < len(other.prerelease) else 1

    def __lt__(self, other: "ReleaseVersion") -> bool:
        return self._compare(other) < 0

    def __le__(self, other: "ReleaseVersion") -> bool:
        return self._compare(other) <= 0

    def __gt__(self, other: "ReleaseVersion") -> bool:
        return self._compare(other) > 0

    def __ge__(self, other: "ReleaseVersion") -> bool:
        return self._compare(other) >= 0

    def __str__(self) -> str:
        suffix = f"-{self.raw_prerelease}" if self.raw_prerelease else ""
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"


@dataclass(frozen=True)
class ReleaseInfo:
    """Release asset metadata used by the updater."""

    tag_name: str
    version: ReleaseVersion
    published_at: str
    prerelease: bool
    asset_name: str
    asset_url: str


def _parse_prerelease(value: Optional[str]) -> tuple[tuple[int, object], ...]:
    """Parse prerelease segments into a comparable tuple."""

    if not value:
        return ()

    parts = []
    for token in value.split("."):
        if token.isdigit():
            parts.append((0, int(token)))
            continue

        match = re.match(r"^(?P<label>[A-Za-z-]+?)(?P<number>\d+)?$", token)
        if match:
            parts.append((1, match.group("label").lower()))
            if match.group("number") is not None:
                parts.append((0, int(match.group("number"))))
            continue

        parts.append((2, token.lower()))

    return tuple(parts)


class UpdateManager:
    """Checks GitHub releases and applies packaged app updates."""

    RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"

    def __init__(self) -> None:
        self.system = platform.system()
        self.machine = platform.machine().lower()

    @property
    def current_version(self) -> ReleaseVersion:
        """Get the current application version."""

        return ReleaseVersion.parse(APP_VERSION)

    def supports_auto_update(self) -> bool:
        """Whether the running app can replace itself."""

        return self.get_release_asset_suffix() is not None and getattr(sys, "frozen", False)

    def get_release_asset_suffix(self) -> Optional[str]:
        """Get the release zip suffix for the current platform."""

        if self.system == "Darwin" and self.machine in {"arm64", "aarch64"}:
            return "-macos-arm64.zip"
        if self.system == "Windows" and self.machine in {"amd64", "x86_64", "x64"}:
            return "-windows-x64.zip"
        return None

    def get_latest_compatible_release(self) -> Optional[ReleaseInfo]:
        """Find the newest GitHub release compatible with this platform."""

        suffix = self.get_release_asset_suffix()
        if suffix is None:
            return None

        current_version = self.current_version
        releases = self._fetch_releases()
        best_release: Optional[ReleaseInfo] = None

        for release in releases:
            if release.get("draft"):
                continue

            tag_name = release.get("tag_name", "")
            try:
                version = ReleaseVersion.parse(tag_name)
            except ValueError:
                continue

            if version <= current_version:
                continue

            # Stable builds should only auto-update to stable releases.
            if current_version.raw_prerelease is None and release.get("prerelease"):
                continue

            asset = self._find_asset(release.get("assets", []), suffix)
            if asset is None:
                continue

            candidate = ReleaseInfo(
                tag_name=tag_name,
                version=version,
                published_at=release.get("published_at", ""),
                prerelease=bool(release.get("prerelease")),
                asset_name=asset["name"],
                asset_url=asset["browser_download_url"],
            )

            if best_release is None or candidate.version > best_release.version:
                best_release = candidate

        return best_release

    def download_release_asset(
        self,
        release: ReleaseInfo,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """Download the selected release asset to a temporary location."""

        request = Request(
            release.asset_url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": f"{APP_BUNDLE_NAME}-updater",
            },
        )

        download_dir = Path(tempfile.mkdtemp(prefix="videodifftool-update-"))
        target_path = download_dir / release.asset_name

        with urlopen(request, timeout=30) as response, open(target_path, "wb") as target:
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0

            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                target.write(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    progress_callback(downloaded, total)

        return target_path

    def prepare_update_and_restart(self, archive_path: Path) -> None:
        """Extract the downloaded archive, replace the app, and relaunch it."""

        if not self.supports_auto_update():
            raise RuntimeError("Automatic updates are only supported in packaged macOS and Windows builds.")

        extracted_root = archive_path.parent / "extracted"
        extracted_root.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(archive_path), str(extracted_root))

        if self.system == "Darwin":
            self._prepare_macos_update(extracted_root)
            return
        if self.system == "Windows":
            self._prepare_windows_update(extracted_root)
            return

        raise RuntimeError(f"Automatic updates are not supported on {self.system}.")

    def _fetch_releases(self) -> list[dict]:
        """Load GitHub releases JSON."""

        request = Request(
            self.RELEASES_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_BUNDLE_NAME}-update-checker",
            },
        )

        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to check GitHub releases: {exc}") from exc

    def _find_asset(self, assets: list[dict], suffix: str) -> Optional[dict]:
        """Find the platform-specific asset in a release."""

        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(suffix):
                return asset
        return None

    def _prepare_macos_update(self, extracted_root: Path) -> None:
        """Launch the macOS update helper."""

        source_app = extracted_root / f"{APP_BUNDLE_NAME}.app"
        if not source_app.exists():
            raise RuntimeError(f"Downloaded archive does not contain {APP_BUNDLE_NAME}.app")

        executable = Path(sys.executable).resolve()
        target_app = executable.parents[2]
        target_parent = target_app.parent
        if not os.access(target_parent, os.W_OK):
            raise RuntimeError(f"Cannot write to {target_parent}")

        script_path = archive_helper_path("sh")
        script_path.write_text(
            _build_macos_update_script(
                current_pid=os.getpid(),
                source_app=source_app,
                target_app=target_app,
            ),
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        subprocess.Popen(
            ["/bin/bash", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _prepare_windows_update(self, extracted_root: Path) -> None:
        """Launch the Windows update helper."""

        source_dir = extracted_root / APP_BUNDLE_NAME
        source_exe = source_dir / f"{APP_BUNDLE_NAME}.exe"
        if not source_exe.exists():
            raise RuntimeError(f"Downloaded archive does not contain {APP_BUNDLE_NAME}.exe")

        executable = Path(sys.executable).resolve()
        target_dir = executable.parent
        if not os.access(target_dir.parent, os.W_OK):
            raise RuntimeError(f"Cannot write to {target_dir.parent}")

        script_path = archive_helper_path("ps1")
        script_path.write_text(
            _build_windows_update_script(
                current_pid=os.getpid(),
                source_dir=source_dir,
                target_dir=target_dir,
                executable_name=executable.name,
            ),
            encoding="utf-8",
        )
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )


def archive_helper_path(extension: str) -> Path:
    """Create a temporary helper script path."""

    directory = Path(tempfile.mkdtemp(prefix="videodifftool-update-script-"))
    return directory / f"apply_update.{extension}"


def _build_macos_update_script(current_pid: int, source_app: Path, target_app: Path) -> str:
    """Build the macOS helper script."""

    target_parent = target_app.parent
    backup_app = target_parent / f"{target_app.name}.old"
    return f"""#!/bin/bash
set -euo pipefail

PID="{current_pid}"
SOURCE_APP="{source_app}"
TARGET_APP="{target_app}"
TARGET_PARENT="{target_parent}"
BACKUP_APP="{backup_app}"

while kill -0 "$PID" 2>/dev/null; do
  sleep 1
done

rm -rf "$BACKUP_APP"
if [ -d "$TARGET_APP" ]; then
  mv "$TARGET_APP" "$BACKUP_APP"
fi

cp -R "$SOURCE_APP" "$TARGET_APP"
open "$TARGET_APP"
rm -rf "$BACKUP_APP"
"""


def _build_windows_update_script(
    current_pid: int,
    source_dir: Path,
    target_dir: Path,
    executable_name: str,
) -> str:
    """Build the Windows helper script."""

    backup_dir = target_dir.parent / f"{target_dir.name}.old"
    launch_exe = target_dir / executable_name
    return f"""$ErrorActionPreference = 'Stop'
$pidToWait = {current_pid}
$sourceDir = "{source_dir}"
$targetDir = "{target_dir}"
$backupDir = "{backup_dir}"
$launchExe = "{launch_exe}"

for ($i = 0; $i -lt 120; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{
        break
    }}
    Start-Sleep -Seconds 1
}}

if (Test-Path $backupDir) {{
    Remove-Item $backupDir -Recurse -Force
}}

if (Test-Path $targetDir) {{
    Rename-Item $targetDir $backupDir
}}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
robocopy $sourceDir $targetDir /E /NFL /NDL /NJH /NJS /NP | Out-Null
Start-Process -FilePath $launchExe
if (Test-Path $backupDir) {{
    Remove-Item $backupDir -Recurse -Force
}}
"""
