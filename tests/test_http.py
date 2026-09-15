from __future__ import annotations

import httpx
import pytest

from mid_mcp.config import AppConfig, ServerConfig
from mid_mcp.server import create_server


@pytest.mark.asyncio
async def test_http_initialize_and_host_allowlist(tmp_path) -> None:
    config = AppConfig(
        server=ServerConfig(transport="streamable-http", port=8124, allowed_hosts=["mcp.example.com"]),
        audit_log=tmp_path / "audit.log",
    )
    server = create_server(config)
    assert (server.settings.host, server.settings.port) == ("127.0.0.1", 8124)
    app = server.streamable_http_app()
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8124") as client:
            headers = {"accept": "application/json, text/event-stream"}
            local = await client.post("/mcp", json=initialize, headers=headers)
            assert local.status_code == 200
            assert '"serverInfo"' in local.text
            tunnel_host = await client.post("/mcp", json=initialize, headers={**headers, "host": "mcp.example.com"})
            assert tunnel_host.status_code == 200
            unknown_host = await client.post("/mcp", json=initialize, headers={**headers, "host": "other.example.com"})
            assert unknown_host.status_code == 421
