"""Unit tests for release versioning and update selection."""

import io
import sys
from pathlib import Path, PurePosixPath

from src.update_manager import (
    ReleaseInfo,
    ReleaseVersion,
    UpdateManager,
    _build_macos_update_script,
    _build_windows_update_script,
)


def test_release_version_ordering():
    assert ReleaseVersion.parse("1.4.0-rc1") < ReleaseVersion.parse("1.4.0-rc2")
    assert ReleaseVersion.parse("1.4.0-rc2") < ReleaseVersion.parse("1.4.0")
    assert ReleaseVersion.parse("1.4.0") < ReleaseVersion.parse("1.4.1-rc1")


def test_latest_compatible_release_selects_newest_matching_asset(monkeypatch):
    manager = UpdateManager()
    monkeypatch.setattr(
        UpdateManager,
        "current_version",
        property(lambda self: ReleaseVersion.parse("1.4.0-rc1")),
    )
    monkeypatch.setattr(manager, "get_release_asset_suffix", lambda: "-windows-x64.zip")
    monkeypatch.setattr(
        manager,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v1.4.0-rc2",
                "draft": False,
                "prerelease": True,
                "published_at": "2026-03-24T00:00:00Z",
                "assets": [
                    {
                        "name": "VideoDiffTool-v1.4.0-rc2-windows-x64.zip",
                        "browser_download_url": "https://example.invalid/rc2.zip",
                    }
                ],
            },
            {
                "tag_name": "v1.4.0",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-03-25T00:00:00Z",
                "assets": [
                    {
                        "name": "VideoDiffTool-v1.4.0-windows-x64.zip",
                        "browser_download_url": "https://example.invalid/stable.zip",
                    }
                ],
            },
        ],
    )

    release = manager.get_latest_compatible_release()

    assert release is not None
    assert release.tag_name == "v1.4.0"
    assert release.asset_name.endswith("-windows-x64.zip")


def test_latest_compatible_release_skips_missing_assets(monkeypatch):
    manager = UpdateManager()
    monkeypatch.setattr(
        UpdateManager,
        "current_version",
        property(lambda self: ReleaseVersion.parse("1.4.0-rc1")),
    )
    monkeypatch.setattr(manager, "get_release_asset_suffix", lambda: "-macos-arm64.zip")
    monkeypatch.setattr(
        manager,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v1.4.0-rc2",
                "draft": False,
                "prerelease": True,
                "published_at": "2026-03-24T00:00:00Z",
                "assets": [],
            }
        ],
    )

    assert manager.get_latest_compatible_release() is None


def test_latest_compatible_release_skips_prerelease_for_stable_build(monkeypatch):
    manager = UpdateManager()
    monkeypatch.setattr(
        UpdateManager,
        "current_version",
        property(lambda self: ReleaseVersion.parse("1.4.0")),
    )
    monkeypatch.setattr(manager, "get_release_asset_suffix", lambda: "-windows-x64.zip")
    monkeypatch.setattr(
        manager,
        "_fetch_releases",
        lambda: [
            {
                "tag_name": "v1.4.1-rc1",
                "draft": False,
                "prerelease": True,
                "published_at": "2026-03-24T00:00:00Z",
                "assets": [
                    {
                        "name": "VideoDiffTool-v1.4.1-rc1-windows-x64.zip",
                        "browser_download_url": "https://example.invalid/rc1.zip",
                    }
                ],
            }
        ],
    )

    assert manager.get_latest_compatible_release() is None


def test_macos_update_script_contains_expected_paths():
    script = _build_macos_update_script(
        current_pid=123,
        source_app=PurePosixPath("/tmp/update/VideoDiffTool.app"),
        target_app=PurePosixPath("/Applications/VideoDiffTool.app"),
    )

    assert 'PID="123"' in script
    assert 'SOURCE_APP="/tmp/update/VideoDiffTool.app"' in script
    assert 'TARGET_APP="/Applications/VideoDiffTool.app"' in script
    assert 'open "$TARGET_APP"' in script


def test_windows_update_script_contains_expected_paths():
    script = _build_windows_update_script(
        current_pid=456,
        source_dir=Path(r"C:\temp\VideoDiffTool"),
        target_dir=Path(r"C:\Program Files\VideoDiffTool"),
        executable_name="VideoDiffTool.exe",
    )

    assert "$pidToWait = 456" in script
    assert r'$sourceDir = "C:\temp\VideoDiffTool"' in script
    assert r'$targetDir = "C:\Program Files\VideoDiffTool"' in script
    assert 'Start-Process -FilePath $launchExe' in script


def test_supports_auto_update_requires_packaged_supported_platform(monkeypatch):
    manager = UpdateManager()
    monkeypatch.setattr(manager, "system", "Windows")
    monkeypatch.setattr(manager, "machine", "amd64")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert manager.supports_auto_update() is True

    monkeypatch.setattr(manager, "machine", "arm64")
    assert manager.supports_auto_update() is False


def test_download_release_asset_writes_archive_and_reports_progress(monkeypatch):
    manager = UpdateManager()
    release = ReleaseInfo(
        tag_name="v1.4.0-rc2",
        version=ReleaseVersion.parse("1.4.0-rc2"),
        published_at="2026-03-24T00:00:00Z",
        prerelease=True,
        asset_name="VideoDiffTool-v1.4.0-rc2-windows-x64.zip",
        asset_url="https://example.invalid/download.zip",
    )

    class FakeResponse(io.BytesIO):
        def __init__(self, payload: bytes):
            super().__init__(payload)
            self.headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "src.update_manager.urlopen",
        lambda request, timeout=30: FakeResponse(b"abcdef"),
    )

    progress: list[tuple[int, int]] = []
    archive = manager.download_release_asset(release, lambda downloaded, total: progress.append((downloaded, total)))

    assert archive.name == release.asset_name
    assert archive.read_bytes() == b"abcdef"
    assert progress[-1] == (6, 6)


def test_prepare_update_and_restart_dispatches_to_platform_helper(tmp_path, monkeypatch):
    archive_path = tmp_path / "update.zip"
    archive_path.write_text("placeholder", encoding="utf-8")

    manager = UpdateManager()
    monkeypatch.setattr(manager, "supports_auto_update", lambda: True)
    unpacked_to = archive_path.parent / "extracted"
    helper_calls: list[Path] = []

    monkeypatch.setattr(
        "src.update_manager.shutil.unpack_archive",
        lambda source, target: helper_calls.append(Path(target)),
    )
    monkeypatch.setattr(manager, "_prepare_macos_update", lambda extracted_root: helper_calls.append(extracted_root))
    monkeypatch.setattr(manager, "system", "Darwin")

    manager.prepare_update_and_restart(archive_path)

    assert helper_calls == [unpacked_to, unpacked_to]


def test_prepare_macos_update_writes_script_and_launches_helper(tmp_path, monkeypatch):
    extracted_root = tmp_path / "extract"
    source_app = extracted_root / "VideoDiffTool.app"
    source_app.mkdir(parents=True)

    executable = tmp_path / "Applications" / "VideoDiffTool.app" / "Contents" / "MacOS" / "VideoDiffTool"
    executable.parent.mkdir(parents=True)
    executable.write_text("x", encoding="utf-8")

    script_path = tmp_path / "apply_update.sh"
    popen_calls = []

    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr("src.update_manager.os.access", lambda path, mode: True)
    monkeypatch.setattr("src.update_manager.archive_helper_path", lambda extension: script_path)
    monkeypatch.setattr(
        "src.update_manager.subprocess.Popen",
        lambda cmd, **kwargs: popen_calls.append((cmd, kwargs)),
    )

    manager = UpdateManager()
    manager._prepare_macos_update(extracted_root)

    script_content = script_path.read_text(encoding="utf-8")
    assert f'SOURCE_APP="{source_app}"' in script_content
    assert f'TARGET_APP="{executable.parents[2]}"' in script_content
    assert popen_calls and popen_calls[0][0][0] == "/bin/bash"


def test_prepare_windows_update_writes_script_and_launches_helper(tmp_path, monkeypatch):
    extracted_root = tmp_path / "extract"
    source_dir = extracted_root / "VideoDiffTool"
    source_dir.mkdir(parents=True)
    (source_dir / "VideoDiffTool.exe").write_text("x", encoding="utf-8")

    executable = tmp_path / "Program Files" / "VideoDiffTool" / "VideoDiffTool.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("x", encoding="utf-8")

    script_path = tmp_path / "apply_update.ps1"
    popen_calls = []

    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr("src.update_manager.os.access", lambda path, mode: True)
    monkeypatch.setattr("src.update_manager.archive_helper_path", lambda extension: script_path)
    monkeypatch.setattr(
        "src.update_manager.subprocess.Popen",
        lambda cmd, **kwargs: popen_calls.append((cmd, kwargs)),
    )

    manager = UpdateManager()
    manager._prepare_windows_update(extracted_root)

    script_content = script_path.read_text(encoding="utf-8")
    assert f'$sourceDir = "{source_dir}"' in script_content
    assert f'$targetDir = "{executable.parent}"' in script_content
    assert popen_calls and popen_calls[0][0][0] == "powershell"
