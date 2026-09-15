from __future__ import annotations

import fnmatch
import shutil
import subprocess

from mid_mcp.config import AppConfig
from mid_mcp.config import ProjectConfig
from mid_mcp.core.security import require, resolve_project_path
from mid_mcp.core.security import is_sensitive_filename
from mid_mcp.core.redaction import redact


class SearchTools:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def files(self, project: ProjectConfig, query: str, path: str = ".", limit: int = 100) -> list[str]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        results: list[str] = []
        project_root = project.path.resolve()
        for item in root.rglob("*"):
            try:
                resolved = item.resolve(strict=True)
                resolved.relative_to(project_root)
                if fnmatch.fnmatch(item.name, query) and not is_sensitive_filename(self.config, item) and not is_sensitive_filename(self.config, resolved):
                    results.append(str(item.relative_to(project_root)))
                    if len(results) >= limit:
                        break
            except (OSError, ValueError):
                continue
        return results

    def text(self, project: ProjectConfig, query: str, path: str = ".", file_pattern: str = "*", max_results: int = 100) -> list[dict]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        if shutil.which("rg", path=self.config.terminal.controlled_path):
            command = ["rg", "--json", "--glob", file_pattern, "--max-count", str(max_results)]
            for pattern in self.config.security.sensitive_files.deny:
                if pattern not in self.config.security.sensitive_files.allow:
                    command.extend(["--glob", f"!{pattern}"])
            for pattern in self.config.security.sensitive_files.allow:
                command.extend(["--glob", pattern])
            command.extend(["--", query, str(root)])
            result = subprocess.run(command, cwd=project.path.resolve(), env={"PATH": self.config.terminal.controlled_path}, shell=False, text=True, capture_output=True, check=False)
            return [{"raw": line} for line in redact(result.stdout).splitlines()[:max_results]]
        results = []
        project_root = project.path.resolve()
        for file in root.rglob(file_pattern):
            try:
                resolved = file.resolve(strict=True)
                resolved.relative_to(project_root)
            except (OSError, ValueError):
                continue
            if not file.is_file() or is_sensitive_filename(self.config, file) or is_sensitive_filename(self.config, resolved): continue
            try:
                for number, line in enumerate(file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if query in line:
                        results.append({"path": str(file.relative_to(project.path.resolve())), "line": number, "text": redact(line)})
                        if len(results) >= max_results: return results
            except OSError: continue
        return results
