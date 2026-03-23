"""Unit tests for release versioning and update selection."""

from pathlib import Path

from src.update_manager import (
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
        source_app=Path("/tmp/update/VideoDiffTool.app"),
        target_app=Path("/Applications/VideoDiffTool.app"),
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
