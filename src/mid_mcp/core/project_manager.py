from __future__ import annotations

import json
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig


class ProjectManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def get(self, project_id: str) -> ProjectConfig:
        try:
            return self.config.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"project not found: {project_id}") from exc

    def detect_type(self, project: ProjectConfig) -> str:
        root = project.path
        if (root / "odoo.conf").exists() or (root / "addons").is_dir(): return "odoo"
        if any((root / name).exists() for name in ("compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml")): return "docker-compose"
        if (root / "package.json").exists(): return "node"
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists(): return "python"
        return "unknown"

    def info(self, project_id: str) -> dict:
        project = self.get(project_id)
        root = project.path.resolve()
        scripts = {}
        package = root / "package.json"
        if package.exists():
            try: scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            except (json.JSONDecodeError, OSError): pass
        return {"id": project_id, "name": project.name, "path": str(root), "type": self.detect_type(project),
                "permissions": project.permissions.model_dump(), "git": (root / ".git").exists(), "scripts": scripts}
