"""Tests for dependency detection and bootstrap logic."""

from __future__ import annotations

import importlib.metadata
import subprocess
from pathlib import Path

import pytest

from src import dependency_manager as dependency_manager_module
from src.dependency_manager import DependencyManager, check_and_install_dependencies


def test_check_dependencies_classifies_installed_missing_and_fallback(tmp_path, monkeypatch, capsys):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        "\n".join(
            [
                "# comment",
                "installedpkg>=1.0",
                "missingpkg>=2.0",
                "fallbackpkg==3.0",
            ]
        ),
        encoding="utf-8",
    )

    version_calls: dict[str, int] = {}

    def fake_version(package_name: str):
        version_calls[package_name] = version_calls.get(package_name, 0) + 1
        if package_name == "installedpkg":
            return "1.5"
        if package_name == "missingpkg":
            raise importlib.metadata.PackageNotFoundError(package_name)
        if package_name == "fallbackpkg":
            if version_calls[package_name] == 1:
                raise ValueError("metadata backend failed")
            raise importlib.metadata.PackageNotFoundError(package_name)
        raise importlib.metadata.PackageNotFoundError(package_name)

    monkeypatch.setattr(dependency_manager_module, "pkg_resources", None)
    monkeypatch.setattr(dependency_manager_module.importlib.metadata, "version", fake_version)

    manager = DependencyManager(requirements_path)
    missing, installed = manager.check_dependencies()

    assert missing == ["missingpkg>=2.0", "fallbackpkg==3.0"]
    assert installed == ["installedpkg>=1.0"]
    assert "Error checking requirement 'fallbackpkg==3.0'" in capsys.readouterr().out


def test_install_packages_uses_current_python_and_handles_failure(monkeypatch):
    commands: list[list[str]] = []

    def fake_check_call(cmd):
        commands.append(cmd)
        if cmd[-1] == "brokenpkg":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(dependency_manager_module.subprocess, "check_call", fake_check_call)

    manager = DependencyManager(Path("requirements.txt"))

    assert manager.install_packages(["goodpkg"]) is True
    assert commands[0][:3] == [dependency_manager_module.sys.executable, "-m", "pip"]
    assert manager.install_packages(["brokenpkg"]) is False


def test_check_dependencies_uses_pkg_resources_when_available(tmp_path, monkeypatch):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo>=1.0\noldpkg>=5.0\n", encoding="utf-8")

    class FakeParsedRequirement:
        def __init__(self, project_name: str, specs: list[tuple[str, str]], satisfied: bool):
            self.project_name = project_name
            self.specs = specs
            self._satisfied = satisfied

        def __contains__(self, dist):
            return self._satisfied

    class FakePkgResources:
        class DistributionNotFound(Exception):
            pass

        @staticmethod
        def parse_requirements(req: str):
            if req.startswith("demo"):
                return [FakeParsedRequirement("demo", [(">=", "1.0")], True)]
            return [FakeParsedRequirement("oldpkg", [(">=", "5.0")], False)]

        @staticmethod
        def get_distribution(package_name: str):
            return object()

    monkeypatch.setattr(dependency_manager_module, "pkg_resources", FakePkgResources)

    manager = DependencyManager(requirements_path)
    missing, installed = manager.check_dependencies()

    assert missing == ["oldpkg>=5.0"]
    assert installed == ["demo>=1.0"]


def test_install_packages_handles_empty_list_and_unexpected_exception(monkeypatch):
    manager = DependencyManager(Path("requirements.txt"))
    assert manager.install_packages([]) is True

    monkeypatch.setattr(
        dependency_manager_module.subprocess,
        "check_call",
        lambda cmd: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert manager.install_packages(["demo"]) is False


def test_check_and_install_dependencies_exits_on_failed_install(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    requirements_path = project_root / "requirements.txt"
    requirements_path.write_text("pytest\n", encoding="utf-8")

    monkeypatch.setattr(dependency_manager_module, "__file__", str(src_dir / "dependency_manager.py"))
    monkeypatch.setattr(DependencyManager, "check_dependencies", lambda self: (["pytest"], []))
    monkeypatch.setattr(DependencyManager, "install_packages", lambda self, packages: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    with pytest.raises(SystemExit) as excinfo:
        check_and_install_dependencies()

    assert excinfo.value.code == 1


def test_check_and_install_dependencies_handles_success_and_missing_requirements(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "project"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    requirements_path = project_root / "requirements.txt"
    requirements_path.write_text("pytest\n", encoding="utf-8")

    monkeypatch.setattr(dependency_manager_module, "__file__", str(src_dir / "dependency_manager.py"))
    monkeypatch.setattr(DependencyManager, "check_dependencies", lambda self: (["pytest"], []))
    monkeypatch.setattr(DependencyManager, "install_packages", lambda self, packages: True)

    check_and_install_dependencies()
    assert "Please restart the application" in capsys.readouterr().out

    missing_project_root = tmp_path / "missing_project"
    missing_src_dir = missing_project_root / "src"
    missing_src_dir.mkdir(parents=True)
    monkeypatch.setattr(dependency_manager_module, "__file__", str(missing_src_dir / "dependency_manager.py"))
    monkeypatch.chdir(tmp_path)

    check_and_install_dependencies()
    assert "Warning: requirements.txt not found. Skipping dependency check." in capsys.readouterr().out
