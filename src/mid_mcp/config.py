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
    git_read: bool = True
    git_write: bool = False
    docker_read: bool = False
    docker_write: bool = False
    docker_destructive: bool = False
    service_control: bool = False
    database_read: bool = False
    database_write: bool = False


class TerminalConfig(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)


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
    server_terminal: ServerTerminalConfig = Field(default_factory=ServerTerminalConfig)
    system_tools: SystemToolsConfig = Field(default_factory=SystemToolsConfig)
    audit_log: Path = Path("audit.log")
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    """Load a YAML config; an empty YAML document is valid."""
    with Path(path).open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw)
