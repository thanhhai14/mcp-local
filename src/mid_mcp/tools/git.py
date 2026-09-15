from __future__ import annotations

from mid_mcp.config import ProjectConfig
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.command_policy import CommandPolicyEngine
from mid_mcp.core.security import SecurityError, is_sensitive_filename, require, resolve_project_path


class GitTools:
    def __init__(self, executor: CommandExecutor, config=None) -> None:
        self.executor = executor
        self.config = config or executor.config
        self.policy = CommandPolicyEngine(self.config)

    def run(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "git_read")
        command = ["git", *args]
        self.policy.enforce(project, command, project.path.resolve())
        return self.executor.run(command, project.path.resolve(), sandbox_root=project.path.resolve())
    def status(self, project: ProjectConfig) -> dict: return self.run(project, "status", "--short", "--branch")
    def diff(self, project: ProjectConfig) -> dict:
        args = ["diff", "--no-ext-diff", "--", "."]
        for pattern in self.config.security.sensitive_files.deny:
            args.append(f":(exclude)**/{pattern}")
        return self.run(project, *args)
    def log(self, project: ProjectConfig, limit: int = 20) -> dict: return self.run(project, "log", f"-{min(limit, 100)}", "--oneline")
    def branch(self, project: ProjectConfig) -> dict: return self.run(project, "branch", "--show-current")
    def show(self, project: ProjectConfig, revision: str) -> dict:
        path_part = revision.rsplit(":", 1)[-1] if ":" in revision else revision
        if is_sensitive_filename(self.config, path_part):
            raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        if ":" in revision and (path_part.startswith(("/", "./", "../", "~")) or ".." in path_part.split("/")):
            resolve_project_path(project, path_part, must_exist=False)
        return self.run(project, "show", "--no-ext-diff", revision)
