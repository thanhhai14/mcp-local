from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess


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

def network_interfaces() -> dict:
    result = subprocess.run(["ip", "-j", "addr"], text=True, capture_output=True, check=False)
    return {"success": result.returncode == 0, "output": result.stdout, "stderr": result.stderr}

def listening_ports() -> dict:
    result = subprocess.run(["ss", "-lntup"], text=True, capture_output=True, check=False)
    return {"success": result.returncode == 0, "output": result.stdout, "stderr": result.stderr}
