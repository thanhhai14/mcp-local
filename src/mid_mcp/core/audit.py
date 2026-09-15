from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .redaction import redact


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("mid_mcp.audit")
        if not self.logger.handlers:
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def action(self, tool: str, status: str, **details: Any) -> None:
        self.logger.info("%s", json.dumps(redact({"tool": tool, "status": status, **details}), default=str))
