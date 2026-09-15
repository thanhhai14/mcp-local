"""Strict, administrator-owned configuration model."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class Permissions(BaseModel):
    read: bool = True
    write: bool = False
    delete: bool = False
    terminal: bool = False
    network: bool = False
    git_read: bool = True
    git_write: bool = False
    git_network: bool = False
    docker_read: bool = False
    docker_write: bool = False
    docker_destructive: bool = False
    docker_exec: bool = False
    docker_run: bool = False
    allow_npx: bool = False
    npm_exec: bool = False
    service_control: bool = False
    database_read: bool = False
    database_write: bool = False


class TerminalConfig(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    allowed_python_modules: list[str] = Field(default_factory=lambda: ["pytest", "compileall", "unittest"])


class NamedCommand(BaseModel):
    command: list[str]
    parameters: dict[str, str] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    name: str
    path: Path
    permissions: Permissions = Field(default_factory=Permissions)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    commands: dict[str, NamedCommand] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("project path must be absolute")
        return value


class FilesystemConfig(BaseModel):
    backup_before_write: bool = True
    backup_retention: int = Field(default=20, ge=0, le=1000)


class GlobalTerminalConfig(BaseModel):
    default_timeout: int = Field(default=30, ge=1)
    max_timeout: int = Field(default=1800, ge=1)
    max_output_chars: int = Field(default=50000, ge=1000)
    denied_commands: list[str] = Field(default_factory=lambda: ["shutdown", "reboot", "poweroff", "halt", "mkfs", "fdisk", "parted"])
    allow_sudo: bool = False
    allow_npx: bool = False
    denied_environment: list[str] = Field(default_factory=lambda: [
        "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "GLIBC_TUNABLES",
        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONWARNINGS",
        "NODE_OPTIONS", "NODE_PATH", "RUBYOPT", "PERL5OPT", "GIT_SSH_COMMAND", "GIT_SSH",
        "GIT_PROXY_COMMAND", "GIT_EXTERNAL_DIFF", "GIT_PAGER", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR",
        "GIT_ASKPASS", "GIT_EXEC_PATH", "GIT_CONFIG_*", "GIT_TEMPLATE_DIR",
        "BASH_ENV", "ENV", "SHELLOPTS", "CDPATH", "NPM_CONFIG_*", "COREPACK_HOME",
        "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PAGER", "MANPAGER", "LESSOPEN", "EDITOR", "VISUAL",
    ])
    controlled_path: str = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


class SensitiveFilesConfig(BaseModel):
    hide_from_listing: bool = True
    deny: list[str] = Field(default_factory=lambda: [
        ".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519",
        "credentials", "credentials.*", "secrets", "secrets.*", "*.p12", "*.pfx",
    ])
    allow: list[str] = Field(default_factory=lambda: [".env.example", ".env.sample"])


class SecurityConfig(BaseModel):
    sensitive_files: SensitiveFilesConfig = Field(default_factory=SensitiveFilesConfig)


class SandboxConfig(BaseModel):
    enabled: bool = False
    backend: str = "bubblewrap"
    required: bool = False
    network: bool = False


class ServerTerminalConfig(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)


class SystemToolsConfig(BaseModel):
    allow_service_actions: bool = False
    allowed_services: list[str] = Field(default_factory=list)


class ServerConfig(BaseModel):
    name: str = "MID Project & System MCP"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)

    @field_validator("allowed_hosts")
    @classmethod
    def explicit_hosts(cls, values: list[str]) -> list[str]:
        if any(not value or "*" in value or "/" in value or any(char.isspace() for char in value) for value in values):
            raise ValueError("allowed_hosts must contain exact Host header values")
        return values

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, values: list[str]) -> list[str]:
        if any(not value or "*" in value or not value.startswith(("http://", "https://")) or any(char.isspace() for char in value) for value in values):
            raise ValueError("allowed_origins must contain exact HTTP origins")
        return values


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    terminal: GlobalTerminalConfig = Field(default_factory=GlobalTerminalConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    server_terminal: ServerTerminalConfig = Field(default_factory=ServerTerminalConfig)
    system_tools: SystemToolsConfig = Field(default_factory=SystemToolsConfig)
    audit_log: Path = Path("audit.log")
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    """Load a YAML config; an empty YAML document is valid."""
    with Path(path).open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)
