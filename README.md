# MID Project & System MCP

An MCP server for controlled AI-assisted development and Linux administration. It exposes only projects, commands, and system capabilities an administrator explicitly enables.

## Install and run

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp config.example.yaml config.yaml
# edit config.yaml and replace the example project path
.venv/bin/mid-mcp --config config.yaml
```

The default `stdio` transport is suitable for desktop MCP clients. To use Streamable HTTP, set `server.transport: streamable-http`; the example remains bound to `127.0.0.1`.

For a Cloudflare Tunnel, set the local service URL to `http://localhost:8123`
when `cloudflared` runs on the same host and set `server.port: 8123`. MCP clients
connect to `https://your-public-hostname/mcp`. If Cloudflare forwards the public
Host header, add that exact hostname to `server.allowed_hosts`. HTTP requests
with unlisted Host headers receive `421`. If a browser-based client sends an
Origin header, add its exact `https://...` origin to `server.allowed_origins`.

Before publishing a server with file write or terminal permissions, protect
the tunnel hostname with Cloudflare Access (or equivalent authentication) and
restrict access to intended clients. Tunnel routing alone is not authentication.
The MCP HTTP transport in this version does not provide application-level auth.
Use an Access service token only with clients that can send the required headers.
After Access is active, switch `server.transport` from `stdio` to
`streamable-http`, restart the server, and connect an authorized MCP client to
the public `/mcp` URL. A browser address-bar GET is not an MCP protocol test.

For MCP Inspector, when the server configuration is named `config.yaml` in the
current directory, run `npx @modelcontextprotocol/inspector .venv/bin/mid-mcp`.
Inspector v2 reserves `--config` for its own read-only session file, so it must
not be used to pass the MCP server's configuration argument. For a differently
named server config, create a small wrapper executable that runs
`mid-mcp --config /absolute/path/to/file.yaml`, then give that wrapper to
Inspector.

## Configuration and permissions

Projects are administrator-owned YAML entries. `path` must be absolute. Permissions are deny-by-default for write, delete, terminal, Docker mutation, Git mutation, service control and database access. Terminal additionally requires `terminal.enabled` and an `allowed_commands` allowlist. `*` is allowed only as an explicit administrator decision.

Named project commands keep complex commands in configuration and validate each supplied parameter against its configured regular expression.

## Tools

Current MCP tools include project discovery/info; list/read/write/patch files; filename and text search; generic project commands; Git status/diff/log; Docker Compose ps/logs; available executable discovery; and basic system/memory/disk/network inspection.

The implementation is deliberately modular: additional Docker actions, systemd controls, PostgreSQL, and Odoo helpers can reuse the same executor, policy and audit layers without granting raw shell access.

## Security model

- Every project-relative path goes through one resolver, rejecting absolute paths, traversal, and symlink escapes.
- Commands always run as argv with `shell=False`; global denylist and `sudo` policy apply before execution.
- Project `cwd` and command policy do not confine a process to the project filesystem. For example, an allowed Python command can read paths outside the project that the MCP operating-system user can access. Give terminal permission only to trusted clients and run the MCP under a dedicated, minimally privileged OS account.
- Output and audit payloads redact common secret names/assignments.
- Writes may create bounded backups in `.mcp-backups`; audit records do not include secrets.
- Docker socket access can effectively grant root-equivalent power. This project never changes socket permissions or Docker group membership.

## Testing

```bash
.venv/bin/pytest
```

Security tests cover traversal, absolute/symlink escape, permissions, command policy, deterministic patching, truncation, and timeout. They do not need Docker.

## systemd

`deploy/mid-mcp.service` is a template. Create the dedicated `mid-mcp` account, install the project under `/opt`, place the config under `/etc/mid-mcp`, then review filesystem, Docker socket and systemctl privileges before enabling it. Do not run it as root by default.
# mcp-local
