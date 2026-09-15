from __future__ import annotations

import fnmatch
import shutil
import subprocess

from mid_mcp.config import ProjectConfig
from mid_mcp.core.security import require, resolve_project_path


class SearchTools:
    def files(self, project: ProjectConfig, query: str, path: str = ".", limit: int = 100) -> list[str]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        return [str(item.relative_to(project.path.resolve())) for item in root.rglob("*") if fnmatch.fnmatch(item.name, query)][:limit]

    def text(self, project: ProjectConfig, query: str, path: str = ".", file_pattern: str = "*", max_results: int = 100) -> list[dict]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        if shutil.which("rg"):
            result = subprocess.run(["rg", "--json", "--glob", file_pattern, "--max-count", str(max_results), "--", query, str(root)], text=True, capture_output=True, check=False)
            return [{"raw": line} for line in result.stdout.splitlines()[:max_results]]
        results = []
        for file in root.rglob(file_pattern):
            if not file.is_file(): continue
            try:
                for number, line in enumerate(file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if query in line:
                        results.append({"path": str(file.relative_to(project.path.resolve())), "line": number, "text": line})
                        if len(results) >= max_results: return results
            except OSError: continue
        return results
