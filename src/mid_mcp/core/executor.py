from __future__ import annotations

import subprocess
import time
import os
from pathlib import Path
from typing import Mapping

from mid_mcp.config import AppConfig
from .redaction import redact


class CommandExecutor:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(self, command: list[str], cwd: Path, timeout: int | None = None, env: Mapping[str, str] | None = None) -> dict:
        requested = timeout or self.config.terminal.default_timeout
        effective_timeout = min(requested, self.config.terminal.max_timeout)
        started = time.monotonic()
        try:
            safe_env = ({**os.environ, **dict(env)} if env is not None else None)
            completed = subprocess.run(command, cwd=cwd, env=safe_env,
                                     shell=False, text=True, capture_output=True, timeout=effective_timeout, check=False)
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

    def _truncate(self, value: str | bytes) -> tuple[str, bool]:
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        limit = self.config.terminal.max_output_chars
        return (value[:limit] + "\n[output truncated]", True) if len(value) > limit else (value, False)
