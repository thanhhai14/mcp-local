#!/usr/bin/env bash
# Start the configured OpenAI Secure MCP Tunnel without exposing the runtime key.
set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="${SCRIPT_PATH%/*}"
[[ "$SCRIPT_DIR" == "$SCRIPT_PATH" ]] && SCRIPT_DIR="."
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
PROFILE="${TUNNEL_PROFILE:-mid-project-system}"
MCP_CONFIG="${MCP_CONFIG:-$PROJECT_DIR/config.yaml}"

die() {
  printf 'Lỗi: %s\n' "$*" >&2
  exit 1
}

[[ -r "$ENV_FILE" ]] || die "không đọc được $ENV_FILE"
[[ -r "$MCP_CONFIG" ]] || die "không đọc được $MCP_CONFIG"

if [[ -n "${TUNNEL_CLIENT_BIN:-}" ]]; then
  TUNNEL_BIN="$TUNNEL_CLIENT_BIN"
elif [[ -x "$PROJECT_DIR/tunnel-client/tunnel-client" ]]; then
  TUNNEL_BIN="$PROJECT_DIR/tunnel-client/tunnel-client"
elif [[ -x "$PROJECT_DIR/tunnel-client" ]]; then
  TUNNEL_BIN="$PROJECT_DIR/tunnel-client"
else
  TUNNEL_BIN=""
  for candidate in "$PROJECT_DIR"/tunnel-client*/tunnel-client; do
    if [[ -x "$candidate" ]]; then
      TUNNEL_BIN="$candidate"
      break
    fi
  done
  [[ -n "$TUNNEL_BIN" ]] || die "không tìm thấy tunnel-client trong project; đặt binary tại tunnel-client/tunnel-client"
fi

if [[ "$TUNNEL_BIN" == */* ]]; then
  [[ -x "$TUNNEL_BIN" ]] || die "tunnel-client không executable: $TUNNEL_BIN"
else
  command -v "$TUNNEL_BIN" >/dev/null 2>&1 || die "không tìm thấy tunnel-client: $TUNNEL_BIN"
fi

# Read only this key/value. Do not source .env: sourcing would execute arbitrary
# shell expressions stored in that file.
key_line=""
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?CONTROL_PLANE_API_KEY[[:space:]]*= ]]; then
    key_line="$line"
  fi
done < "$ENV_FILE"
[[ -n "$key_line" ]] || die "thiếu CONTROL_PLANE_API_KEY trong $ENV_FILE"

CONTROL_PLANE_API_KEY="${key_line#*=}"
CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY#"${CONTROL_PLANE_API_KEY%%[![:space:]]*}"}"
CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY%"${CONTROL_PLANE_API_KEY##*[![:space:]]}"}"
if [[ ${#CONTROL_PLANE_API_KEY} -ge 2 ]]; then
  if [[ ${CONTROL_PLANE_API_KEY:0:1} == '"' && ${CONTROL_PLANE_API_KEY: -1} == '"' ]]; then
    CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY:1:${#CONTROL_PLANE_API_KEY}-2}"
  elif [[ ${CONTROL_PLANE_API_KEY:0:1} == "'" && ${CONTROL_PLANE_API_KEY: -1} == "'" ]]; then
    CONTROL_PLANE_API_KEY="${CONTROL_PLANE_API_KEY:1:${#CONTROL_PLANE_API_KEY}-2}"
  fi
fi
[[ -n "$CONTROL_PLANE_API_KEY" ]] || die "CONTROL_PLANE_API_KEY đang rỗng"

export CONTROL_PLANE_API_KEY
printf '[mid-mcp] kiểm tra profile %s...\n' "$PROFILE"
"$TUNNEL_BIN" doctor --profile "$PROFILE" --explain
printf '[mid-mcp] khởi động tunnel; nhấn Ctrl+C để dừng.\n'
exec "$TUNNEL_BIN" run --profile "$PROFILE"
