from __future__ import annotations

from mid_mcp.config import ProjectConfig
from mid_mcp.core.executor import CommandExecutor
from mid_mcp.core.command_policy import CommandPolicyEngine
from mid_mcp.core.security import require


class DockerTools:
    def __init__(self, executor: CommandExecutor, config=None) -> None:
        self.executor = executor
        self.policy = CommandPolicyEngine(config or executor.config)

    def read(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_read")
        command = ["docker", *args]
        self.policy.enforce(project, command, project.path.resolve())
        return self.executor.run(command, project.path.resolve(), sandbox_root=project.path.resolve())

    def compose(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_read")
        command = ["docker", "compose", *args]
        self.policy.enforce(project, command, project.path.resolve())
        return self.executor.run(command, project.path.resolve(), sandbox_root=project.path.resolve())

    def compose_action(self, project: ProjectConfig, *args: str) -> dict:
        require(project, "docker_write")
        command = ["docker", "compose", *args]
        self.policy.enforce(project, command, project.path.resolve())
        return self.executor.run(command, project.path.resolve(), sandbox_root=project.path.resolve())
