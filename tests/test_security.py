from __future__ import annotations

import os
from pathlib import Path

import pytest

from mid_mcp.config import AppConfig, ProjectConfig, Permissions, TerminalConfig
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.security import SecurityError, resolve_project_path, validate_command
from mid_mcp.tools.filesystem import FilesystemTools


@pytest.fixture()
def project(tmp_path: Path) -> ProjectConfig:
    root = tmp_path / "project"; root.mkdir(); (root / "safe.txt").write_text("one\ntwo\n", encoding="utf-8")
    return ProjectConfig(name="test", path=root, permissions=Permissions(read=True, write=True, delete=False, terminal=True), terminal=TerminalConfig(enabled=True, allowed_commands=["python3"]))


@pytest.fixture()
def config(project: ProjectConfig, tmp_path: Path) -> AppConfig:
    return AppConfig(projects={"test": project}, audit_log=tmp_path / "audit.log")


def test_blocks_path_traversal(project: ProjectConfig) -> None:
    with pytest.raises(SecurityError): resolve_project_path(project, "../../etc/passwd")


def test_blocks_absolute_path(project: ProjectConfig) -> None:
    with pytest.raises(SecurityError): resolve_project_path(project, "/etc/passwd")


def test_blocks_symlink_escape(project: ProjectConfig) -> None:
    link = project.path / "escape"
    try: link.symlink_to("/etc")
    except OSError: pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityError): resolve_project_path(project, "escape/passwd")


def test_write_and_deterministic_patch(project: ProjectConfig, config: AppConfig) -> None:
    tools = FilesystemTools(config)
    assert tools.patch_file(project, "safe.txt", "one", "ONE")["replaced"] == 1
    assert tools.read_file(project, "safe.txt")["content"].startswith("ONE")
    with pytest.raises(ValueError): tools.patch_file(project, "safe.txt", "missing", "x")


def test_delete_permission_is_enforced(project: ProjectConfig, config: AppConfig) -> None:
    with pytest.raises(SecurityError): FilesystemTools(config).delete(project, "safe.txt")


def test_command_allow_deny_and_sudo(project: ProjectConfig, config: AppConfig) -> None:
    validate_command(config, project, ["python3", "--version"])
    with pytest.raises(SecurityError): validate_command(config, project, ["sh", "-c", "id"])
    with pytest.raises(SecurityError): validate_command(config, project, ["sudo", "id"])


def test_output_truncation_and_timeout(project: ProjectConfig, config: AppConfig) -> None:
    config.terminal.max_output_chars = 10
    executor = CommandExecutor(config)
    output = executor.run(["python3", "-c", "print('x'*50)"], project.path)
    assert output["output_truncated"] is True
    timeout = executor.run(["python3", "-c", "import time; time.sleep(2)"], project.path, timeout=1)
    assert timeout["error"]["code"] == "COMMAND_TIMEOUT"
