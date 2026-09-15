from __future__ import annotations

import re
from typing import Any

_SECRET = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|database_url)")
_ASSIGNMENT = re.compile(r"(?im)(\b(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|database_url)\b\s*[=:]\s*)([^\s'\"]+)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _ASSIGNMENT.sub(r"\1[REDACTED]", value)
    return value
