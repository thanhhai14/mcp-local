from __future__ import annotations

from mid_mcp.config import ProjectConfig
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.security import require


class DockerTools:
    def __init__(self, executor: CommandExecutor) -> None: self.executor = executor
    def read(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_read"); return self.executor.run(["docker", *args], project.path.resolve())
    def compose(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_read"); return self.executor.run(["docker", "compose", *args], project.path.resolve())
    def compose_action(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_write"); return self.executor.run(["docker", "compose", *args], project.path.resolve())
