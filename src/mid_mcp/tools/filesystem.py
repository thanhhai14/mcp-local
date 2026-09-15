from __future__ import annotations

import shutil
import time
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig
from mid_mcp.core.security import SecurityError, is_sensitive_filename, require, resolve_project_path


class FilesystemTools:
    def __init__(self, config: AppConfig) -> None: self.config = config

    def list_files(self, project: ProjectConfig, path: str = ".", recursive: bool = False, max_depth: int = 4, limit: int = 500) -> list[dict]:
        require(project, "read"); root = resolve_project_path(project, path, must_exist=True)
        if not root.is_dir(): raise NotADirectoryError(path)
        entries: list[dict] = []
        for item in (root.rglob("*") if recursive else root.iterdir()):
            try:
                relative = item.relative_to(project.path.resolve())
                if len(relative.parts) > max_depth or len(entries) >= limit: continue
                if self.config.security.sensitive_files.hide_from_listing and is_sensitive_filename(self.config, item.name):
                    continue
                # A directory entry may be replaced by a symlink while it is being inspected.
                resolved = item.resolve(strict=True)
                resolved.relative_to(project.path.resolve())
                if self.config.security.sensitive_files.hide_from_listing and is_sensitive_filename(self.config, resolved.name):
                    continue
                stat = item.stat()
                entries.append({"name": item.name, "path": str(relative), "type": "directory" if item.is_dir() else "file", "size": stat.st_size, "modified_time": stat.st_mtime})
            except (OSError, ValueError): continue
        return entries

    def read_file(self, project: ProjectConfig, path: str, offset: int = 0, limit: int = 10000) -> dict:
        require(project, "read")
        if offset < 0 or limit < 0: raise ValueError("offset and limit must be non-negative")
        if is_sensitive_filename(self.config, path):
            raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        target = resolve_project_path(project, path, must_exist=True)
        if is_sensitive_filename(self.config, target):
            raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        if not target.is_file(): raise IsADirectoryError(path)
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content[offset:offset + limit], "offset": offset, "truncated": len(content) > offset + limit}

    def write_file(self, project: ProjectConfig, path: str, content: str) -> dict:
        require(project, "write"); target = resolve_project_path(project, path, reject_symlinks=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._backup(project, target)
        target.write_text(content, encoding="utf-8")
        if target.name == ".gitignore": self._ensure_gitignore(project.path.resolve())
        return {"path": path, "bytes_written": len(content.encode())}

    def patch_file(self, project: ProjectConfig, path: str, search: str, replace: str) -> dict:
        require(project, "write")
        if not search: raise ValueError("search cannot be empty")
        if is_sensitive_filename(self.config, path):
            raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        target = resolve_project_path(project, path, must_exist=True, reject_symlinks=True); content = target.read_text(encoding="utf-8")
        if content.count(search) != 1: raise ValueError("search must match exactly one location")
        self._backup(project, target); target.write_text(content.replace(search, replace, 1), encoding="utf-8")
        if target.name == ".gitignore": self._ensure_gitignore(project.path.resolve())
        return {"path": path, "replaced": 1}

    def mkdir(self, project: ProjectConfig, path: str) -> dict:
        require(project, "write"); target = resolve_project_path(project, path, reject_symlinks=True); target.mkdir(parents=True, exist_ok=True); return {"path": path}

    def delete(self, project: ProjectConfig, path: str) -> dict:
        require(project, "delete"); target = resolve_project_path(project, path, must_exist=True, reject_symlinks=True)
        if target.is_dir(): shutil.rmtree(target)
        else: target.unlink()
        return {"path": path, "deleted": True}

    def move(self, project: ProjectConfig, source: str, destination: str) -> dict:
        require(project, "write")
        if is_sensitive_filename(self.config, source):
            raise SecurityError("sensitive file operations are not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        src = resolve_project_path(project, source, must_exist=True, reject_symlinks=True)
        if is_sensitive_filename(self.config, src):
            raise SecurityError("sensitive file operations are not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        dst = resolve_project_path(project, destination, reject_symlinks=True); dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst)); return {"source": source, "destination": destination}

    def copy(self, project: ProjectConfig, source: str, destination: str) -> dict:
        require(project, "write")
        if is_sensitive_filename(self.config, source):
            raise SecurityError("sensitive file operations are not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        src = resolve_project_path(project, source, must_exist=True, reject_symlinks=True)
        if is_sensitive_filename(self.config, src):
            raise SecurityError("sensitive file operations are not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        dst = resolve_project_path(project, destination, reject_symlinks=True); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst); return {"source": source, "destination": destination}

    def _backup(self, project: ProjectConfig, target: Path) -> None:
        if not self.config.filesystem.backup_before_write or not target.exists() or not target.is_file(): return
        backups = resolve_project_path(project, ".mcp-backups", reject_symlinks=True); backups.mkdir(exist_ok=True)
        destination = backups / (target.name + f".{int(time.time() * 1000)}")
        if destination.is_symlink():
            raise SecurityError("backup destination cannot be a symlink", code="SYMLINK_PATH", policy="PROJECT_ISOLATION")
        shutil.copy2(target, destination)
        # A .gitignore edit is finalized after the caller writes the target,
        # otherwise the caller's content could overwrite this safety rule.
        if target.name != ".gitignore": self._ensure_gitignore(project.path.resolve())
        old = sorted(backups.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[self.config.filesystem.backup_retention:]
        for item in old: item.unlink(missing_ok=True)

    @staticmethod
    def _git_root(project_root: Path) -> Path | None:
        for candidate in (project_root, *project_root.parents):
            marker = candidate / ".git"
            if marker.is_dir() or marker.is_file(): return candidate
        return None

    @staticmethod
    def _has_backup_rule(content: str, *, project_is_repo_root: bool) -> bool:
        for raw_line in content.splitlines():
            rule = raw_line.strip()
            if not rule or rule.startswith("#") or rule.startswith("!"): continue
            if rule.endswith("/"): rule = rule[:-1]
            if rule in {".mcp-backups", "**/.mcp-backups"}: return True
            if project_is_repo_root and rule == "/.mcp-backups": return True
        return False

    def _ensure_gitignore(self, project_root: Path) -> None:
        git_root = self._git_root(project_root)
        if git_root is None: return
        project_gitignore = project_root / ".gitignore"
        gitignore = project_gitignore
        for candidate in (project_gitignore, git_root / ".gitignore"):
            if candidate.is_symlink():
                raise SecurityError(".gitignore cannot be a symlink", code="SYMLINK_PATH", policy="PROJECT_ISOLATION")
            if candidate.exists() and not candidate.is_file():
                raise SecurityError(".gitignore is not a regular file", code="GITIGNORE_INVALID", policy="PROJECT_ISOLATION")
            if not candidate.exists(): continue
            content = candidate.read_text(encoding="utf-8")
            if self._has_backup_rule(content, project_is_repo_root=candidate == project_gitignore or project_root == git_root): return
        # Keep writes inside the configured project, even when Git's worktree
        # root is an ancestor directory.
        if gitignore.is_symlink():
            raise SecurityError(".gitignore cannot be a symlink", code="SYMLINK_PATH", policy="PROJECT_ISOLATION")
        if gitignore.exists() and not gitignore.is_file():
            raise SecurityError(".gitignore is not a regular file", code="GITIGNORE_INVALID", policy="PROJECT_ISOLATION")
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        prefix = content if not content or content.endswith("\n") else content + "\n"
        gitignore.write_text(prefix + "# MCP file-write backups\n.mcp-backups/\n", encoding="utf-8")
