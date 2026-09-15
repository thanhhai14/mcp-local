from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from mid_mcp.config import AppConfig, ProjectConfig, Permissions, TerminalConfig
from mid_mcp.core.command_policy import CommandPolicyEngine
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.redaction import redact
from mid_mcp.core.security import SecurityError, is_sensitive_filename, resolve_project_path, validate_command
from mid_mcp.server import MidService
from mid_mcp.tools.docker import DockerTools
from mid_mcp.tools.filesystem import FilesystemTools
from mid_mcp.tools.search import SearchTools


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
    assert not (project.path / ".gitignore").exists()
    with pytest.raises(ValueError): tools.patch_file(project, "safe.txt", "missing", "x")


def test_backup_adds_gitignore_rule_for_git_project(project: ProjectConfig, config: AppConfig) -> None:
    (project.path / ".git").mkdir()
    FilesystemTools(config).write_file(project, "safe.txt", "changed")
    gitignore = (project.path / ".gitignore").read_text(encoding="utf-8")
    assert ".mcp-backups/" in gitignore
    assert len(list((project.path / ".mcp-backups").iterdir())) == 1


def test_backup_does_not_duplicate_existing_gitignore_rule(project: ProjectConfig, config: AppConfig) -> None:
    (project.path / ".git").mkdir()
    (project.path / ".gitignore").write_text("build/\n.mcp-backups/\n", encoding="utf-8")
    FilesystemTools(config).write_file(project, "safe.txt", "changed")
    gitignore = (project.path / ".gitignore").read_text(encoding="utf-8")
    assert gitignore.count(".mcp-backups/") == 1


def test_gitignore_target_keeps_auto_backup_rule(project: ProjectConfig, config: AppConfig) -> None:
    (project.path / ".git").mkdir()
    gitignore = project.path / ".gitignore"
    gitignore.write_text("build/\n", encoding="utf-8")
    FilesystemTools(config).write_file(project, ".gitignore", "dist/\n")
    assert gitignore.read_text(encoding="utf-8") == "dist/\n# MCP file-write backups\n.mcp-backups/\n"
    backups = list((project.path / ".mcp-backups").iterdir())
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "build/\n"


def test_nested_git_project_keeps_gitignore_write_inside_project(tmp_path: Path) -> None:
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    root = repo / "service"; root.mkdir(); (root / "safe.txt").write_text("one\n", encoding="utf-8")
    project = ProjectConfig(name="nested", path=root, permissions=Permissions(read=True, write=True))
    config = AppConfig(projects={"nested": project}, audit_log=tmp_path / "audit.log")
    FilesystemTools(config).write_file(project, "safe.txt", "two\n")
    assert (root / ".gitignore").read_text(encoding="utf-8").endswith(".mcp-backups/\n")
    assert not (repo / ".gitignore").exists()


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


def policy_project(tmp_path: Path, **permission_overrides) -> ProjectConfig:
    root = tmp_path / "policy-project"; root.mkdir(exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "test.py").write_text("print('ok')", encoding="utf-8")
    (root / "scripts" / "test.js").write_text("console.log('ok')", encoding="utf-8")
    permissions = Permissions(read=True, terminal=True, docker_read=True, git_read=True, **permission_overrides)
    return ProjectConfig(name="policy", path=root, permissions=permissions,
                         terminal=TerminalConfig(enabled=True, allowed_commands=[
                             "python3", "node", "bash", "sh", "docker", "git", "cat", "rg", "npm", "npx"
                         ]))


def decision(config: AppConfig, project: ProjectConfig, command: list[str]):
    return CommandPolicyEngine(config).authorize(project, command, project.path)


@pytest.mark.parametrize("command", [
    ["python3", "-c", "print('escape')"],
    ["python3", "--command=print('escape')"],
    ["python3", "-"],
    ["python3"],
    ["/usr/bin/python3", "-c", "print('escape')"],
    ["node", "-e", "require('fs').readFileSync('/etc/passwd')"],
    ["node", "--eval=console.log(1)"],
    ["node"],
    ["bash", "-c", "cat /etc/passwd"],
    ["sh", "-c", "id"],
])
def test_inline_interpreters_and_shells_are_denied(tmp_path: Path, command: list[str]) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    result = decision(config, project, command)
    assert result.allowed is False
    assert result.risk_level == "DENY"


def test_interpreter_scripts_are_project_bound(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    outside = tmp_path / "outside.py"; outside.write_text("print('outside')", encoding="utf-8")
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert decision(config, project, ["python3", "scripts/test.py"]).allowed
    assert not decision(config, project, ["python3", str(outside)]).allowed
    assert decision(config, project, ["node", "scripts/test.js"]).allowed
    assert not decision(config, project, ["python3", "-m", "compileall", "/tmp"]).allowed


@pytest.mark.parametrize("command", [
    ["docker", "restart", "abc"], ["docker", "container", "restart", "abc"],
    ["docker", "stop", "abc"], ["docker", "exec", "abc", "sh"],
    ["docker", "rm", "abc"], ["docker", "container", "rm", "abc"],
    ["docker", "run", "--rm", "alpine"], ["docker", "system", "prune"],
])
def test_docker_actions_honor_permissions(tmp_path: Path, command: list[str]) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    result = decision(config, project, command)
    assert result.allowed is False


def test_docker_read_is_allowed_but_write_is_denied_before_subprocess(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert decision(config, project, ["docker", "ps"]).allowed
    executor = Mock()
    executor.config = config
    tools = DockerTools(executor, config)
    with pytest.raises(SecurityError):
        tools.compose_action(project, "restart")
    executor.run.assert_not_called()


def test_docker_write_does_not_imply_run_or_destructive(tmp_path: Path) -> None:
    project = policy_project(tmp_path, docker_write=True)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert decision(config, project, ["docker", "restart", "abc"]).allowed
    assert not decision(config, project, ["docker", "run", "alpine"]).allowed
    assert not decision(config, project, ["docker", "rm", "abc"]).allowed


def test_generic_docker_exec_stays_blocked_even_if_flag_is_set(tmp_path: Path) -> None:
    project = policy_project(tmp_path, docker_exec=True)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    result = decision(config, project, ["docker", "exec", "abc", "sh"])
    assert result.allowed is False
    assert result.code == "DOCKER_EXEC_DISABLED"


def test_unknown_allowlisted_command_fails_closed(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    project.terminal.allowed_commands.append("make")
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    result = decision(config, project, ["make", "all"])
    assert result.allowed is False
    assert result.code == "COMMAND_POLICY_UNKNOWN"


def test_compose_run_rejects_host_escape_options(tmp_path: Path) -> None:
    project = policy_project(tmp_path, docker_run=True)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert not decision(config, project, ["docker", "compose", "run", "--volume=/:/host", "svc"]).allowed
    assert not decision(config, project, ["docker", "compose", "ps", "--env-file", "/tmp/.env"]).allowed


def test_npx_and_npm_prefix_do_not_escape_project(tmp_path: Path) -> None:
    project = policy_project(tmp_path, allow_npx=True)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    config.terminal.allow_npx = True
    assert not decision(config, project, ["npx", "--prefix", "/tmp", "tool"]).allowed
    assert not decision(config, project, ["npm", "--prefix", "/tmp", "run", "build"]).allowed
    assert not decision(config, project, ["npm", "install", "--global"]).allowed
    assert not decision(config, project, ["npm", "pack", "--pack-destination", "/tmp"]).allowed
    assert decision(config, project, ["npm", "--version"]).allowed


def test_git_permissions_and_network_are_separate(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert decision(config, project, ["git", "status"]).allowed
    assert decision(config, project, ["git", "branch"]).allowed
    assert not decision(config, project, ["git", "branch", "new-branch"]).allowed
    assert not decision(config, project, ["git", "commit", "-m", "x"]).allowed
    assert not decision(config, project, ["git", "push"]).allowed
    project.permissions.git_write = True
    assert decision(config, project, ["git", "commit", "-m", "x"]).allowed
    assert decision(config, project, ["git", "branch", "new-branch"]).allowed
    assert not decision(config, project, ["git", "push"]).allowed
    project.permissions.git_network = True
    assert decision(config, project, ["git", "push"]).allowed
    assert not decision(config, project, ["git", "-c", "core.sshCommand=evil", "status"]).allowed
    assert not decision(config, project, ["git", "clone", "https://example.invalid/repo", "/tmp/outside"]).allowed
    assert not decision(config, project, ["git", "diff", "--no-index", "/tmp/a", "/tmp/b"]).allowed
    assert not decision(config, project, ["git", "--config-env=core.sshCommand=GIT_SSH_COMMAND", "status"]).allowed


def test_file_commands_cannot_read_outside_project(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert not decision(config, project, ["cat", "/etc/passwd"]).allowed
    assert not decision(config, project, ["cat", "nested/../../etc/passwd"]).allowed
    assert not decision(config, project, ["rg", "hostname", "/etc"]).allowed
    assert not decision(config, project, ["pytest", "--basetemp=/tmp"]).allowed
    (project.path / ".env.local").write_text("TOKEN=hidden", encoding="utf-8")
    assert not decision(config, project, ["cat", ".env.local"]).allowed
    assert not decision(config, project, ["pytest", "-p", "external_plugin"]).allowed
    assert not decision(config, project, ["python3", "-m", "pytest", "--pyargs", "external_pkg"]).allowed


def test_generic_file_mutation_obeys_project_permissions(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    project.terminal.allowed_commands.append("rm")
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    assert not decision(config, project, ["rm", "scripts/test.py"]).allowed
    project.permissions.delete = True
    assert decision(config, project, ["rm", "scripts/test.py"]).allowed
    assert not decision(config, project, ["rm", "/tmp/outside"]).allowed


def test_sensitive_files_are_hidden_and_not_readable(project: ProjectConfig, config: AppConfig) -> None:
    secret = project.path / ".env.local"; secret.write_text("TOKEN=hidden", encoding="utf-8")
    example = project.path / ".env.example"; example.write_text("TOKEN=example", encoding="utf-8")
    tools = FilesystemTools(config)
    listed = {item["path"] for item in tools.list_files(project)}
    assert ".env.local" not in listed
    assert ".env.example" in listed
    with pytest.raises(SecurityError):
        tools.read_file(project, ".env.local")
    assert is_sensitive_filename(config, ".env.local")
    assert not is_sensitive_filename(config, ".env.example")


def test_sensitive_search_content_is_denied_even_when_names_are_visible(project: ProjectConfig, config: AppConfig) -> None:
    (project.path / ".env.local").write_text("TOKEN=hidden", encoding="utf-8")
    config.security.sensitive_files.hide_from_listing = False
    assert ".env.local" in {item["path"] for item in FilesystemTools(config).list_files(project)}
    assert all(".env.local" not in item.get("raw", "") and "hidden" not in item.get("raw", "") for item in SearchTools(config).text(project, "TOKEN"))


def test_sensitive_symlink_alias_cannot_bypass_read_policy(project: ProjectConfig, config: AppConfig) -> None:
    secret = project.path / ".env.local"; secret.write_text("TOKEN=hidden", encoding="utf-8")
    alias = project.path / "config.txt"
    try:
        alias.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityError):
        FilesystemTools(config).read_file(project, "config.txt")


def test_sensitive_file_cannot_be_copied_to_a_readable_alias(project: ProjectConfig, config: AppConfig) -> None:
    (project.path / ".env.local").write_text("TOKEN=hidden", encoding="utf-8")
    tools = FilesystemTools(config)
    with pytest.raises(SecurityError):
        tools.copy(project, ".env.local", "copied.txt")
    with pytest.raises(SecurityError):
        tools.move(project, ".env.local", "moved.txt")


def test_write_through_symlink_is_denied(project: ProjectConfig, config: AppConfig, tmp_path: Path) -> None:
    outside = tmp_path / "outside"; outside.write_text("original", encoding="utf-8")
    link = project.path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityError):
        FilesystemTools(config).write_file(project, "linked.txt", "changed")
    assert outside.read_text(encoding="utf-8") == "original"


def test_backup_directory_symlink_cannot_redirect_write_backup(project: ProjectConfig, config: AppConfig, tmp_path: Path) -> None:
    outside = tmp_path / "backup-outside"; outside.mkdir()
    link = project.path / ".mcp-backups"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SecurityError):
        FilesystemTools(config).write_file(project, "safe.txt", "changed")
    assert not list(outside.iterdir())


def test_dangerous_environment_overrides_are_denied(project: ProjectConfig, config: AppConfig) -> None:
    with pytest.raises(SecurityError):
        CommandExecutor(config).run(["python3", "--version"], project.path, env={"LD_PRELOAD": "evil.so"})
    with pytest.raises(SecurityError):
        CommandExecutor(config).run(["python3", "--version"], project.path, env={"PYTHONPATH": "/tmp"})
    with pytest.raises(SecurityError):
        CommandExecutor(config).run(["python3", "--version"], project.path, env={"GIT_CONFIG_COUNT": "1"})


def test_service_blocks_python_before_executor(tmp_path: Path) -> None:
    project = policy_project(tmp_path)
    config = AppConfig(projects={"policy": project}, audit_log=tmp_path / "audit.log")
    service = MidService(config)
    service.executor.run = Mock()
    result = service.run_project_command("policy", ["python3", "-c", "print('escape')"])
    assert result["success"] is False
    assert result["error"]["code"] == "INLINE_INTERPRETER_BLOCKED"
    service.executor.run.assert_not_called()


def test_redaction_covers_assignments_and_json_values() -> None:
    output = redact('PASSWORD=secret {"api_key":"abc", "database_url": "postgres://user:pw@db"} -----BEGIN PRIVATE KEY-----hidden-----END PRIVATE KEY-----')
    assert "secret" not in output
    assert "abc" not in output
    assert "postgres://" not in output
    assert "hidden" not in output
    assert "[REDACTED]" in output
