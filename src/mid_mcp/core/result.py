from __future__ import annotations

from typing import Any


def ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def fail(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message, "details": details or {}}}
