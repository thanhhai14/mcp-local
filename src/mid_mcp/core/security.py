"""Path and command policy.  This module is the only path resolver."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig


class SecurityError(PermissionError):
    def __init__(self, message: str, *, code: str = "PERMISSION_DENIED", policy: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.policy = policy


def project_root(project: ProjectConfig) -> Path:
    return project.path.resolve(strict=True)


def resolve_project_path(project: ProjectConfig, relative_path: str = ".", *, must_exist: bool = False, reject_symlinks: bool = False) -> Path:
    """Resolve path while rejecting absolute paths, traversal, and symlink escapes."""
    if not isinstance(relative_path, str) or "\x00" in relative_path:
        raise SecurityError("path must be a valid string without NUL bytes", code="INVALID_PATH", policy="PROJECT_ISOLATION")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise SecurityError("absolute paths are not permitted", code="ABSOLUTE_PATH", policy="PROJECT_ISOLATION")
    root = project_root(project)
    lexical = root / candidate
    if reject_symlinks:
        current = root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise SecurityError("symlink paths are not permitted for this operation", code="SYMLINK_PATH", policy="PROJECT_ISOLATION")
    resolved = lexical.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SecurityError("path is outside the project", code="PATH_OUTSIDE_PROJECT", policy="PROJECT_ISOLATION") from exc
    return resolved


def require(project: ProjectConfig, permission: str) -> None:
    if not getattr(project.permissions, permission, False):
        raise SecurityError(f"project does not allow {permission}", code="PERMISSION_DENIED", policy=permission)


def is_sensitive_filename(config: AppConfig, path: str | Path) -> bool:
    """Return whether a filename is sensitive, with explicit example exceptions."""
    name = Path(path).name
    policy = config.security.sensitive_files
    if any(fnmatch.fnmatch(name, pattern) for pattern in policy.allow):
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in policy.deny)


def validate_command(config: AppConfig, project: ProjectConfig | None, command: list[str], *, server: bool = False) -> None:
    if project is not None and not server:
        # Import lazily to keep this foundational module free of an import cycle.
        from .command_policy import CommandPolicyEngine

        CommandPolicyEngine(config).enforce(project, command, project_root(project))
        return
    if not command or not all(isinstance(arg, str) and arg for arg in command):
        raise SecurityError("command must be a non-empty argv list", code="INVALID_COMMAND", policy="ARGV")
    executable = Path(command[0]).name
    if executable == "sudo" and not config.terminal.allow_sudo:
        raise SecurityError("sudo is disabled", code="SUDO_DISABLED", policy="SUDO")
    if executable in config.terminal.denied_commands:
        raise SecurityError(f"command '{executable}' is globally denied", code="COMMAND_DENIED", policy="COMMAND_DENIED")
    allowed = config.server_terminal.allowed_commands if server else (project.terminal.allowed_commands if project else [])
    if not ("*" in allowed or executable in allowed):
        raise SecurityError(f"command '{executable}' is not allowed", code="COMMAND_NOT_ALLOWLISTED", policy="EXECUTABLE_ALLOWLIST")


def render_named_command(command: list[str], parameters: dict[str, str], patterns: dict[str, str]) -> list[str]:
    for key, value in parameters.items():
        pattern = patterns.get(key)
        if pattern is None or not re.fullmatch(pattern, value):
            raise SecurityError(f"invalid parameter: {key}")
    expected = set(patterns)
    if set(parameters) != expected:
        raise SecurityError("missing or unexpected command parameters")
    return [part.format(**parameters) for part in command]
