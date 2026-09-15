from __future__ import annotations

import re
from typing import Any

_SECRET = re.compile(r"(?i)(password|passwd|passphrase|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|database[_-]?url|authorization|credential)")
_ASSIGNMENT = re.compile(r"(?im)(\b(?:password|passwd|passphrase|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|database[_-]?url|authorization|credential)\b['\"]?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,}]+)")
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(r"(?is)-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----")


def _redact_assignment(match: re.Match[str]) -> str:
    value = match.group(2)
    if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
        return f"{match.group(1)}{value[0]}[REDACTED]{value[0]}"
    return f"{match.group(1)}[REDACTED]"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
        return _ASSIGNMENT.sub(_redact_assignment, _BEARER.sub(r"\1[REDACTED]", value))
    return value
