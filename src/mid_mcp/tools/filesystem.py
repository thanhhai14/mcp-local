from __future__ import annotations

import shutil
import time
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig
from mid_mcp.core.security import require, resolve_project_path


class FilesystemTools:
    def __init__(self, config: AppConfig) -> None: self.config = config

    def list_files(self, project: ProjectConfig, path: str = ".", recursive: bool = False, max_depth: int = 4, limit: int = 500) -> list[dict]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        entries: list[dict] = []
        for item in (root.rglob("*") if recursive else root.iterdir()):
            try:
                relative = item.relative_to(project.path.resolve())
                if len(relative.parts) > max_depth or len(entries) >= limit: continue
                stat = item.stat()
                entries.append({"name": item.name, "path": str(relative), "type": "directory" if item.is_dir() else "file", "size": stat.st_size, "modified_time": stat.st_mtime})
            except (OSError, ValueError): continue
        return entries

    def read_file(self, project: ProjectConfig, path: str, offset: int = 0, limit: int = 10000) -> dict:
        require(project, "read"); target = resolve_project_path(project, path, must_exist=True)
        if not target.is_file(): raise IsADirectoryError(path)
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content[offset:offset + limit], "offset": offset, "truncated": len(content) > offset + limit}

    def write_file(self, project: ProjectConfig, path: str, content: str) -> dict:
        require(project, "write"); target = resolve_project_path(project, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._backup(project, target)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes_written": len(content.encode())}

    def patch_file(self, project: ProjectConfig, path: str, search: str, replace: str) -> dict:
        require(project, "write")
        if not search: raise ValueError("search cannot be empty")
        target = resolve_project_path(project, path, must_exist=True); content = target.read_text(encoding="utf-8")
        if content.count(search) != 1: raise ValueError("search must match exactly one location")
        self._backup(project, target); target.write_text(content.replace(search, replace, 1), encoding="utf-8")
        return {"path": path, "replaced": 1}

    def mkdir(self, project: ProjectConfig, path: str) -> dict:
        require(project, "write"); target = resolve_project_path(project, path); target.mkdir(parents=True, exist_ok=True); return {"path": path}

    def delete(self, project: ProjectConfig, path: str) -> dict:
        require(project, "delete"); target = resolve_project_path(project, path, must_exist=True)
        if target.is_dir(): shutil.rmtree(target)
        else: target.unlink()
        return {"path": path, "deleted": True}

    def move(self, project: ProjectConfig, source: str, destination: str) -> dict:
        require(project, "write"); src = resolve_project_path(project, source, must_exist=True); dst = resolve_project_path(project, destination); dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst)); return {"source": source, "destination": destination}

    def copy(self, project: ProjectConfig, source: str, destination: str) -> dict:
        require(project, "write"); src = resolve_project_path(project, source, must_exist=True); dst = resolve_project_path(project, destination); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst); return {"source": source, "destination": destination}

    def _backup(self, project: ProjectConfig, target: Path) -> None:
        if not self.config.filesystem.backup_before_write or not target.exists() or not target.is_file(): return
        backups = project.path.resolve() / ".mcp-backups"; backups.mkdir(exist_ok=True)
        destination = backups / (target.name + f".{int(time.time() * 1000)}")
        shutil.copy2(target, destination)
        old = sorted(backups.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[self.config.filesystem.backup_retention:]
        for item in old: item.unlink(missing_ok=True)
