from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess

from mid_mcp.core.redaction import redact

_CONTROLLED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def system_info() -> dict:
    return {"platform": platform.platform(), "python": platform.python_version(), "hostname": socket.gethostname(), "cpu_count": os.cpu_count()}

def memory_info() -> dict:
    data = {}
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            key, value = line.split(":", 1); data[key] = value.strip()
    except OSError: pass
    return data

def disk_usage() -> list[dict]:
    return [{"mount": mount, "total": usage.total, "used": usage.used, "free": usage.free} for mount, usage in [("/", shutil.disk_usage("/"))]]

def _run_readonly(command: list[str], controlled_path: str = _CONTROLLED_PATH) -> dict:
    executable = shutil.which(command[0], path=controlled_path)
    if executable is None:
        return {"success": False, "error": {"code": "DEPENDENCY_MISSING", "message": f"executable not found: {command[0]}"}}
    result = subprocess.run([executable, *command[1:]], env={"PATH": controlled_path}, shell=False, text=True, capture_output=True, check=False)
    return redact({"success": result.returncode == 0, "output": result.stdout, "stderr": result.stderr})


def network_interfaces(controlled_path: str = _CONTROLLED_PATH) -> dict:
    return _run_readonly(["ip", "-j", "addr"], controlled_path)

def listening_ports(controlled_path: str = _CONTROLLED_PATH) -> dict:
    return _run_readonly(["ss", "-lntup"], controlled_path)
