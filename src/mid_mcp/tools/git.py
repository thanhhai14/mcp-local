from __future__ import annotations

from mid_mcp.config import ProjectConfig
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.security import require


class GitTools:
    def __init__(self, executor: CommandExecutor) -> None: self.executor = executor
    def run(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "git_read")
        return self.executor.run(["git", *args], project.path.resolve())
    def status(self, project: ProjectConfig) -> dict: return self.run(project, "status", "--short", "--branch")
    def diff(self, project: ProjectConfig) -> dict: return self.run(project, "diff", "--no-ext-diff")
    def log(self, project: ProjectConfig, limit: int = 20) -> dict: return self.run(project, "log", f"-{min(limit, 100)}", "--oneline")
    def branch(self, project: ProjectConfig) -> dict: return self.run(project, "branch", "--show-current")
    def show(self, project: ProjectConfig, revision: str) -> dict: return self.run(project, "show", "--no-ext-diff", revision)
