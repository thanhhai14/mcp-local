from __future__ import annotations

import subprocess
import time
import os
import shutil
import fnmatch
from pathlib import Path
from typing import Mapping

from mid_mcp.config import AppConfig
from .security import SecurityError
from .redaction import redact


class CommandExecutor:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(self, command: list[str], cwd: Path, timeout: int | None = None, env: Mapping[str, str] | None = None, *, sandbox_root: Path | None = None) -> dict:
        requested = timeout or self.config.terminal.default_timeout
        effective_timeout = min(requested, self.config.terminal.max_timeout)
        started = time.monotonic()
        try:
            safe_env = self._safe_environment(env)
            wrapped = self._sandbox_command(command, cwd, sandbox_root or cwd)
            completed = subprocess.run(wrapped, cwd=cwd, env=safe_env,
                                     shell=False, text=True, capture_output=True, timeout=effective_timeout, check=False)
            if self.config.sandbox.enabled and wrapped != command and completed.returncode != 0 and "bwrap:" in (completed.stderr or "").lower():
                return redact({"success": False, "error": {"code": "SANDBOX_RUNTIME_FAILED", "message": "bubblewrap could not start the sandbox"}, "command": command, "cwd": str(cwd), "stderr": completed.stderr})
            stdout, stdout_truncated = self._truncate(completed.stdout)
            stderr, stderr_truncated = self._truncate(completed.stderr)
            return redact({"success": completed.returncode == 0, "command": command, "cwd": str(cwd),
                           "exit_code": completed.returncode, "stdout": stdout, "stderr": stderr,
                           "duration_ms": round((time.monotonic() - started) * 1000),
                           "output_truncated": stdout_truncated or stderr_truncated})
        except subprocess.TimeoutExpired as exc:
            stdout, _ = self._truncate(exc.stdout or "")
            stderr, _ = self._truncate(exc.stderr or "")
            return redact({"success": False, "error": {"code": "COMMAND_TIMEOUT", "message": f"command exceeded {effective_timeout}s"},
                           "command": command, "cwd": str(cwd), "stdout": stdout, "stderr": stderr,
                           "duration_ms": round((time.monotonic() - started) * 1000)})
        except FileNotFoundError:
            return {"success": False, "error": {"code": "DEPENDENCY_MISSING", "message": f"executable not found: {command[0]}"}}

    def _safe_environment(self, overrides: Mapping[str, str] | None) -> dict[str, str]:
        denied = tuple(item.upper() for item in self.config.terminal.denied_environment)
        is_denied = lambda key: any(fnmatch.fnmatchcase(key.upper(), pattern) for pattern in denied)
        safe = {key: value for key, value in os.environ.items() if not is_denied(key)}
        safe["PATH"] = self.config.terminal.controlled_path
        for key, value in (overrides or {}).items():
            if not isinstance(key, str) or not key or not isinstance(value, str):
                raise SecurityError("environment keys and values must be strings", code="INVALID_ENVIRONMENT", policy="ENVIRONMENT")
            if is_denied(key):
                raise SecurityError(f"environment override '{key}' is denied", code="ENVIRONMENT_OVERRIDE_DENIED", policy="ENVIRONMENT")
            safe[key] = value
        return safe

    def _sandbox_command(self, command: list[str], cwd: Path, root: Path) -> list[str]:
        sandbox = self.config.sandbox
        if sandbox.required and not sandbox.enabled:
            raise SecurityError("sandbox is required but not enabled", code="SANDBOX_UNAVAILABLE", policy="SANDBOX")
        if not sandbox.enabled:
            return command
        if sandbox.backend != "bubblewrap":
            raise SecurityError(f"unsupported sandbox backend: {sandbox.backend}", code="SANDBOX_UNAVAILABLE", policy="SANDBOX")
        bwrap = next((item for item in ("bwrap", "bubblewrap") if shutil.which(item, path=self.config.terminal.controlled_path)), None)
        if bwrap is None:
            raise SecurityError("bubblewrap is not available; execution denied", code="SANDBOX_UNAVAILABLE", policy="SANDBOX")
        root = root.resolve(strict=True)
        cwd = cwd.resolve(strict=True)
        try:
            cwd.relative_to(root)
        except ValueError as exc:
            raise SecurityError("sandbox cwd is outside project", code="PATH_OUTSIDE_PROJECT", policy="SANDBOX") from exc
        wrapped = [bwrap, "--die-with-parent", "--new-session", "--ro-bind", "/usr", "/usr"]
        for system_dir in ("/bin", "/sbin", "/lib", "/lib64", "/etc"):
            if Path(system_dir).exists():
                wrapped.extend(["--ro-bind", system_dir, system_dir])
        wrapped.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", str(root), str(root), "--chdir", str(cwd)])
        if not sandbox.network:
            wrapped.append("--unshare-net")
        wrapped.extend(["--"])
        wrapped.extend(command)
        return wrapped

    def _truncate(self, value: str | bytes) -> tuple[str, bool]:
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        limit = self.config.terminal.max_output_chars
        return (value[:limit] + "\n[output truncated]", True) if len(value) > limit else (value, False)
