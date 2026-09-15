"""Path and command policy.  This module is the only path resolver."""
from __future__ import annotations

import re
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig


class SecurityError(PermissionError):
    pass


def project_root(project: ProjectConfig) -> Path:
    return project.path.resolve(strict=True)


def resolve_project_path(project: ProjectConfig, relative_path: str = ".", *, must_exist: bool = False) -> Path:
    """Resolve path while rejecting absolute paths, traversal, and symlink escapes."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise SecurityError("absolute paths are not permitted")
    root = project_root(project)
    resolved = (root / candidate).resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SecurityError("path is outside the project") from exc
    return resolved


def require(project: ProjectConfig, permission: str) -> None:
    if not getattr(project.permissions, permission, False):
        raise SecurityError(f"project does not allow {permission}")


def validate_command(config: AppConfig, project: ProjectConfig | None, command: list[str], *, server: bool = False) -> None:
    if not command or not all(isinstance(arg, str) and arg for arg in command):
        raise SecurityError("command must be a non-empty argv list")
    executable = Path(command[0]).name
    if executable == "sudo" and not config.terminal.allow_sudo:
        raise SecurityError("sudo is disabled")
    if executable in config.terminal.denied_commands:
        raise SecurityError(f"command '{executable}' is globally denied")
    allowed = config.server_terminal.allowed_commands if server else (project.terminal.allowed_commands if project else [])
    if not ("*" in allowed or executable in allowed):
        raise SecurityError(f"command '{executable}' is not allowed")


def render_named_command(command: list[str], parameters: dict[str, str], patterns: dict[str, str]) -> list[str]:
    for key, value in parameters.items():
        pattern = patterns.get(key)
        if pattern is None or not re.fullmatch(pattern, value):
            raise SecurityError(f"invalid parameter: {key}")
    expected = set(patterns)
    if set(parameters) != expected:
        raise SecurityError("missing or unexpected command parameters")
    return [part.format(**parameters) for part in command]
