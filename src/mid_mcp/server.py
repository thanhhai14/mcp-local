"""MCP adapter. Business logic stays in testable modules."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import AppConfig, load_config
from .core.audit import AuditLog
from .core.executor import CommandExecutor
from .core.result import fail, ok
from .core.security import SecurityError, render_named_command, resolve_project_path, validate_command
from .core.project_manager import ProjectManager
from .tools.docker import DockerTools
from .tools.filesystem import FilesystemTools
from .tools.git import GitTools
from .tools.search import SearchTools
from .tools import system as system_tools


class MidService:
    def __init__(self, config: AppConfig) -> None:
        self.config, self.projects = config, ProjectManager(config)
        self.executor = CommandExecutor(config); self.files = FilesystemTools(config); self.search = SearchTools()
        self.git, self.docker, self.audit = GitTools(self.executor), DockerTools(self.executor), AuditLog(config.audit_log)

    def call(self, name: str, project_id: str | None, fn, *args, **kwargs) -> dict:
        try:
            project = self.projects.get(project_id) if project_id else None
            value = fn(project, *args, **kwargs) if project else fn(*args, **kwargs)
            self.audit.action(name, "success", project=project_id); return ok(value)
        except KeyError as exc: return fail("PROJECT_NOT_FOUND", str(exc))
        except SecurityError as exc: return fail("PERMISSION_DENIED", str(exc))
        except FileNotFoundError as exc: return fail("FILE_NOT_FOUND", str(exc))
        except (ValueError, IsADirectoryError) as exc: return fail("INVALID_ARGUMENT", str(exc))
        except Exception as exc: return fail("INTERNAL_ERROR", str(exc))

    def run_project_command(self, project_id: str, command: list[str], cwd: str = ".", timeout: int | None = None, env: dict[str, str] | None = None) -> dict:
        def operation(project):
            from .core.security import require
            require(project, "terminal")
            if not project.terminal.enabled: raise SecurityError("terminal is disabled")
            validate_command(self.config, project, command)
            return self.executor.run(command, resolve_project_path(project, cwd, must_exist=True), timeout, env)
        return self.call("run_project_command", project_id, operation)

    def run_named_command(self, project_id: str, command_name: str, parameters: dict[str, str] | None = None) -> dict:
        def operation(project):
            from .core.security import require
            require(project, "terminal")
            if not project.terminal.enabled: raise SecurityError("terminal is disabled")
            try: definition = project.commands[command_name]
            except KeyError as exc: raise ValueError(f"named command not found: {command_name}") from exc
            command = render_named_command(definition.command, parameters or {}, definition.parameters)
            validate_command(self.config, project, command)
            return self.executor.run(command, project.path.resolve())
        return self.call("run_project_named_command", project_id, operation)


def create_server(config: AppConfig) -> FastMCP:
    service = MidService(config)
    port = config.server.port
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}", *config.server.allowed_hosts],
        allowed_origins=[f"http://127.0.0.1:{port}", f"http://localhost:{port}", *config.server.allowed_origins],
    )
    mcp = FastMCP(config.server.name, host=config.server.host, port=port, transport_security=transport_security)
    @mcp.tool()
    def list_projects() -> dict: return ok([service.projects.info(project_id) for project_id in config.projects])
    @mcp.tool()
    def project_info(project: str) -> dict: return service.call("project_info", project, lambda p: service.projects.info(project))
    @mcp.tool()
    def list_project_files(project: str, path: str = ".", recursive: bool = False, max_depth: int = 4, limit: int = 500) -> dict: return service.call("list_project_files", project, service.files.list_files, path, recursive, max_depth, limit)
    @mcp.tool()
    def read_project_file(project: str, path: str, offset: int = 0, limit: int = 10000) -> dict: return service.call("read_project_file", project, service.files.read_file, path, offset, limit)
    @mcp.tool()
    def write_project_file(project: str, path: str, content: str) -> dict: return service.call("write_project_file", project, service.files.write_file, path, content)
    @mcp.tool()
    def patch_project_file(project: str, path: str, search: str, replace: str) -> dict: return service.call("patch_project_file", project, service.files.patch_file, path, search, replace)
    @mcp.tool()
    def create_project_directory(project: str, path: str) -> dict: return service.call("create_project_directory", project, service.files.mkdir, path)
    @mcp.tool()
    def delete_project_file(project: str, path: str) -> dict: return service.call("delete_project_file", project, service.files.delete, path)
    @mcp.tool()
    def move_project_file(project: str, source: str, destination: str) -> dict: return service.call("move_project_file", project, service.files.move, source, destination)
    @mcp.tool()
    def copy_project_file(project: str, source: str, destination: str) -> dict: return service.call("copy_project_file", project, service.files.copy, source, destination)
    @mcp.tool()
    def search_project_files(project: str, query: str, path: str = ".", limit: int = 100) -> dict: return service.call("search_project_files", project, service.search.files, query, path, limit)
    @mcp.tool()
    def search_project_text(project: str, query: str, path: str = ".", file_pattern: str = "*", max_results: int = 100) -> dict: return service.call("search_project_text", project, service.search.text, query, path, file_pattern, max_results)
    @mcp.tool()
    def run_project_command(project: str, command: list[str], cwd: str = ".", timeout: int | None = None, env: dict[str, str] | None = None) -> dict: return service.run_project_command(project, command, cwd, timeout, env)
    @mcp.tool()
    def list_project_commands(project: str) -> dict:
        return service.call("list_project_commands", project, lambda p: {name: {"parameters": list(item.parameters)} for name, item in p.commands.items()})
    @mcp.tool()
    def run_project_named_command(project: str, command_name: str, parameters: dict[str, str] | None = None) -> dict: return service.run_named_command(project, command_name, parameters)
    @mcp.tool()
    def git_status(project: str) -> dict: return service.call("git_status", project, service.git.status)
    @mcp.tool()
    def git_diff(project: str) -> dict: return service.call("git_diff", project, service.git.diff)
    @mcp.tool()
    def git_log(project: str, limit: int = 20) -> dict: return service.call("git_log", project, service.git.log, limit)
    @mcp.tool()
    def git_branch(project: str) -> dict: return service.call("git_branch", project, service.git.branch)
    @mcp.tool()
    def git_show(project: str, revision: str) -> dict: return service.call("git_show", project, service.git.show, revision)
    @mcp.tool()
    def docker_compose_ps(project: str) -> dict: return service.call("docker_compose_ps", project, service.docker.compose, "ps")
    @mcp.tool()
    def docker_compose_logs(project: str, lines: int = 200) -> dict: return service.call("docker_compose_logs", project, service.docker.compose, "logs", "--tail", str(lines))
    @mcp.tool()
    def docker_compose_config(project: str) -> dict: return service.call("docker_compose_config", project, service.docker.compose, "config")
    @mcp.tool()
    def docker_compose_up(project: str) -> dict: return service.call("docker_compose_up", project, service.docker.compose_action, "up", "-d")
    @mcp.tool()
    def docker_compose_restart(project: str) -> dict: return service.call("docker_compose_restart", project, service.docker.compose_action, "restart")
    @mcp.tool()
    def available_cli_tools() -> dict: return ok({name: shutil.which(name) for name in ["git", "docker", "python3", "npm", "rg", "ip", "ss"]})
    @mcp.tool()
    def get_system_info() -> dict: return ok(system_tools.system_info())
    @mcp.tool()
    def get_memory_info() -> dict: return ok(system_tools.memory_info())
    @mcp.tool()
    def get_disk_usage() -> dict: return ok(system_tools.disk_usage())
    @mcp.tool()
    def get_network_interfaces() -> dict: return ok(system_tools.network_interfaces())
    @mcp.tool()
    def get_listening_ports() -> dict: return ok(system_tools.listening_ports())
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(); config = load_config(Path(args.config)); server = create_server(config)
    if config.server.transport == "stdio": server.run(transport="stdio")
    elif config.server.transport == "streamable-http": server.run(transport="streamable-http")
    else: raise SystemExit("transport must be stdio or streamable-http")
