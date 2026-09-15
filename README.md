# MID Project & System MCP

MID Project & System MCP là MCP server cho Linux, hỗ trợ AI xem dự án, thao tác tệp, tìm kiếm, chạy các lệnh được cho phép và đọc thông tin hệ thống. Quyền được khai báo theo từng project trong `config.yaml`. Đây không phải sandbox hệ điều hành.

> **Tình trạng kết nối ChatGPT:** server hiện **chưa triển khai OAuth cho người dùng MCP**. Cấu hình trên máy này có quyền đọc mã nguồn riêng, ghi tệp và chạy lệnh trong FCFund. Vì vậy, **không chọn No authentication cho toàn bộ server chỉ để vượt lỗi kết nối**. Secure MCP Tunnel giữ server khỏi Internet công khai và xác thực đường hầm, nhưng không thay thế xác thực người dùng hay phân quyền từng tool.

## 1. Cài đặt MID MCP

Yêu cầu: Linux, Python 3 và quyền truy cập tới các thư mục project cần quản lý. Chạy từ thư mục chứa README:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp config.example.yaml config.yaml
```

Sửa `config.yaml` trước khi chạy:

- `projects.<id>.path` là đường dẫn tuyệt đối tới project có thật.
- Rà soát `permissions`, đặc biệt `write`, `delete`, `terminal`, `docker_write` và `docker_destructive`.
- Nếu bật terminal, kiểm tra cả `terminal.enabled` và `terminal.allowed_commands`. Chỉ cho phép executable thật sự cần.
- Giữ `server_terminal.enabled: false` và `system_tools.allow_service_actions: false` khi không cần quản trị hệ thống.
- Không đặt API key, mật khẩu hoặc token vào YAML.

Cấu hình hiện tại của máy này dùng `server.transport: "stdio"`, port khai báo `8123`, và project FCFund có `read: true`, `write: true`, `terminal: true`. Port **không được lắng nghe** khi transport vẫn là `stdio`.

Khởi động:

```bash
.venv/bin/mid-mcp --config config.yaml
```

Ở chế độ `stdio`, không thấy thông báo khởi động thường là **bình thường**: server chờ MCP client trao đổi qua stdin/stdout. Không in log thông thường lên stdout vì có thể làm hỏng giao thức. Nhấn `Ctrl+C` để dừng nếu đang chạy thủ công.

## 2. Kiểm tra local bằng MCP Inspector

Khi cấu hình tên `config.yaml` nằm ở thư mục hiện tại:

```bash
npx @modelcontextprotocol/inspector .venv/bin/mid-mcp
```

Mở URL mà Inspector in ra, kết nối rồi kiểm tra `tools/list`. Lần đầu chỉ nên gọi tool chỉ đọc.

Không dùng `npx @modelcontextprotocol/inspector .venv/bin/mid-mcp --config config.yaml`: Inspector dành `--config` cho session file của **chính Inspector**, nên có thể báo `--config cannot be combined with an ad-hoc server URL/command`. Nếu MID MCP dùng tên file cấu hình khác, dùng một wrapper executable riêng gọi `mid-mcp --config /đường/dẫn/tuyệt/đối.yaml`.

Chạy bộ kiểm thử:

```bash
.venv/bin/pytest
```

## 3. Kết nối ChatGPT web bằng OpenAI Secure MCP Tunnel

Đây là đường truyền **outbound** cho server riêng tư. Tunnel dành cho thử nghiệm trong developer mode, không thay thế endpoint HTTPS công khai để xuất bản plugin. [OpenAI Docs — Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

### Chuẩn bị trên OpenAI

1. Trong ChatGPT, vào **Settings → Security and login → Developer mode** và bật chế độ này. Tính năng phụ thuộc gói và chính sách workspace.
2. Vào [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels), tạo hoặc chọn tunnel; ghi lại `tunnel_id` dạng `tunnel_...`.
3. Kiểm tra tunnel được liên kết với Platform organization quản lý nó và ChatGPT workspace sẽ dùng nó. Tài khoản cá nhân có thể không thấy ô workspace riêng: dùng đúng tài khoản/organization và thử dán `tunnel_id` khi tạo kết nối. Nếu không nhận tunnel, kiểm tra association và quyền **Tunnels Read + Use**. Enterprise/Edu có thể cần quản trị viên cấp developer mode và liên kết workspace.
4. Tạo **runtime API key** tại [Platform API keys](https://platform.openai.com/settings/organization/api-keys). Key này dành cho `tunnel-client`, **không phải** OAuth của MID MCP. Không dùng admin key cho daemon và không gửi key vào chat.

Quyền quản lý tunnel (**Read + Manage**) khác quyền chạy/chọn tunnel (**Read + Use**). Xem [OpenAI Docs — quyền và association](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

### Dùng `tunnel-client` trên máy Linux này

Tải bản Linux phù hợp từ Platform tunnel settings. Nếu đã giải nén, dùng binary `tunnel-client`, **không phải** `tunnel-client-runtime`. Đặt binary vào project theo mục **Chạy nhanh bằng script** bên dưới (khuyến nghị); cách này không cần thêm `PATH`. Bản đã tải trên máy này hiện nằm tại `/home/thanhhai14/Downloads/tunnel-client-v0.0.14-linux-amd64/tunnel-client` và có thể được sao chép vào `tunnel-client/tunnel-client` trong project.

```bash
./tunnel-client/tunnel-client help quickstart
```

Nếu binary vẫn ở thư mục tải xuống, gọi bằng đường dẫn tuyệt đối tương ứng. Không cần cài vào thư mục hệ thống hoặc sửa `PATH`.

Tạo profile cho MID MCP đang dùng `stdio` (thay `TUNNEL_ID_CUA_BAN`):

```bash
./tunnel-client/tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile mid-project-system \
  --tunnel-id "TUNNEL_ID_CUA_BAN" \
  --mcp-command "/home/thanhhai14/Data/Code/mcp-local/.venv/bin/mid-mcp --config /home/thanhhai14/Data/Code/mcp-local/config.yaml"
```

`--mcp-command` chứa tham số `--config` của **MID MCP**, không phải tùy chọn `--config` của Inspector. Tunnel-client sẽ tự khởi chạy MID MCP `stdio` khi cần; không phải chạy `mid-mcp` ở terminal khác. Nếu di chuyển repo, cập nhật hai đường dẫn tuyệt đối.

Nhập runtime API key trong **cùng terminal** sẽ chạy `doctor` và `run`. Chạy dòng `read` **riêng**, dán key dù màn hình không hiện ký tự, rồi nhấn Enter:

```bash
read -rsp 'Runtime API key: ' CONTROL_PLANE_API_KEY
```

Sau đó:

```bash
export CONTROL_PLANE_API_KEY
printf '\nĐộ dài key: %s\n' "${#CONTROL_PLANE_API_KEY}"
./tunnel-client/tunnel-client doctor --profile mid-project-system --explain
./tunnel-client/tunnel-client run --profile mid-project-system
```

Độ dài key phải lớn hơn `0`; lệnh trên không in nội dung key. Chỉ chạy `run` khi `doctor` PASS. Giữ terminal chạy `run` mở trong lúc tạo kết nối và gọi tool từ ChatGPT. Giao diện quản trị local tại URL `/ui` mà `run` thông báo cho biết trạng thái **healthy/ready**. Đóng terminal thì tunnel dừng. Tunnel-client cần HTTPS outbound tới OpenAI. [OpenAI Docs — setup và health](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

#### Chạy nhanh bằng script

Đặt binary tunnel-client trong project theo cấu trúc mặc định:

```text
mcp-local/
├── .env
├── config.yaml
├── scripts/run-tunnel.sh
└── tunnel-client/tunnel-client
```

Binary cũng có thể nằm trực tiếp tại `tunnel-client` hoặc trong thư mục `tunnel-client-*` bên trong project. Không cần thêm `PATH`.

Lưu runtime key trong file `/home/thanhhai14/Data/Code/mcp-local/.env`:

```dotenv
CONTROL_PLANE_API_KEY=YOUR_RUNTIME_KEY
```

Đặt quyền chỉ chủ sở hữu được đọc rồi chạy:

```bash
chmod 600 .env
chmod +x scripts/run-tunnel.sh
scripts/run-tunnel.sh
```

Script tự xác định thư mục project dựa trên vị trí của chính nó, nên có thể chạy từ thư mục bất kỳ. Script chỉ đọc dòng `CONTROL_PLANE_API_KEY`; nó **không `source` toàn bộ `.env`**, không in key và chạy `doctor` trước `tunnel-client run`. Nếu muốn dùng binary ở vị trí khác, có thể ghi đè:

```bash
TUNNEL_CLIENT_BIN=/đường/dẫn/tunnel-client scripts/run-tunnel.sh
```

Có thể dùng profile hoặc file môi trường khác:

```bash
TUNNEL_PROFILE=mid-project-system ENV_FILE=/đường/dẫn/.env scripts/run-tunnel.sh
```

### Thêm MCP trong ChatGPT

Khi `tunnel-client run` còn chạy:

1. Mở [ChatGPT Plugins](https://chatgpt.com/#settings/Plugins), nhấn `+`, nhập tên và mô tả.
2. Ở **Connection**, chọn **Tunnel**; chọn tunnel trong danh sách hoặc dán `tunnel_id`. **Không** dùng URL nội bộ `tunnel-service.gateway...` như MCP server URL.
3. Tạo kết nối, kiểm tra danh sách tool và metadata ChatGPT tìm được.
4. Mở chat mới, bật kết nối trong menu công cụ và thử một tác vụ **chỉ đọc** trước. [OpenAI Docs — connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt).

**Giới hạn hiện tại:** MID MCP chưa có OAuth và chưa công bố `securitySchemes` theo từng tool. Tool đọc dữ liệu riêng, ghi tệp hay chạy lệnh cần xác thực/ủy quyền trước khi dùng qua ChatGPT. Không chọn **No authentication** cho cấu hình FCFund hiện tại chỉ để vượt lỗi. No authentication chỉ phù hợp một server thử nghiệm **riêng biệt** với dữ liệu công khai và tool chỉ đọc. Để dùng đầy đủ, cần OAuth 2.1 theo MCP: protected-resource metadata, authorization-server metadata, authorization-code + PKCE, kiểm tra token/scope/audience và `securitySchemes` cho tool. [OpenAI Docs — authentication](https://developers.openai.com/plugins/build/auth).

## 4. Cloudflare Tunnel và Streamable HTTP: nhánh khác

Cloudflare Tunnel đưa HTTP server ra hostname HTTPS công khai; nó **khác** OpenAI Secure MCP Tunnel ở mục 3. Cloudflare trỏ tới `http://localhost:8123` chỉ có tác dụng khi MID MCP chạy `server.transport: "streamable-http"` trên port `8123` và `cloudflared` chạy cùng máy. Ở `stdio` hiện tại, MID MCP không lắng nghe port 8123.

Nếu triển khai HTTP **sau khi đã có lớp xác thực phù hợp**, sửa `config.yaml`:

```yaml
server:
  transport: "streamable-http"
  host: "127.0.0.1"
  port: 8123
  allowed_hosts: [mcp-local.hailab.cloud]
  allowed_origins: [https://mcp-local.hailab.cloud]
```

Khởi động lại `.venv/bin/mid-mcp --config config.yaml`; Cloudflare Tunnel trỏ service tới `http://localhost:8123`. MCP client kết nối `https://mcp-local.hailab.cloud/mcp`. Nếu proxy chuyển tiếp `Host`/`Origin` khác, chỉ thêm đúng giá trị cần dùng. Host không được cho phép có thể nhận HTTP `421`.

`https://localhost:8123/mcp` **không đúng** với cấu hình này: MID MCP không cung cấp TLS tại localhost; local là `http://localhost:8123/mcp`. Gõ `/mcp` trong thanh địa chỉ browser cũng **không phải** phép kiểm thử MCP. Dùng Inspector hoặc client MCP tương thích.

Cloudflare Tunnel tự nó **không xác thực người dùng**. Cloudflare Access có thể bảo vệ hostname cho các client hỗ trợ cơ chế Access, nhưng trang đăng nhập Access hay service token riêng không tự trở thành OAuth MCP mà ChatGPT hỗ trợ. Muốn ChatGPT dùng endpoint công khai phải thiết kế OAuth tương thích và đảm bảo request MCP/OAuth discovery đi qua proxy/Access. Không mở cấu hình hiện tại ra HTTP công khai khi chưa bảo vệ. [OpenAI Docs — authentication](https://developers.openai.com/plugins/build/auth).

## 5. Lỗi thường gặp

- **MID MCP chạy nhưng không in gì:** hành vi thường gặp của `stdio`. Dùng Inspector kiểm tra `tools/list`; muốn thử HTTP phải đổi transport và khởi động lại.
- **Inspector báo `--config cannot be combined with an ad-hoc server URL/command`:** bỏ `--config config.yaml` khỏi lệnh Inspector. `mid-mcp` tự tìm `config.yaml` trong thư mục hiện tại.
- **`doctor` báo `CONTROL_PLANE_API_KEY` is empty:** chạy `read -rsp` riêng một dòng, dán key, nhấn Enter, `export`, kiểm tra độ dài lớn hơn `0` và chạy lại `doctor` **trong cùng terminal**. Biến môi trường không tự chuyển sang terminal khác. Không in key để debug.
- **`codex_plugin SKIP`:** plugin Codex tùy chọn; không phải lỗi kết nối ChatGPT. Không cần chạy `tunnel-client codex plugin install` cho quy trình này.
- **ChatGPT báo “Đã xảy ra lỗi khi tải cấu hình OAuth” / `MCP server ... does not implement OAuth`:** ChatGPT đang yêu cầu OAuth, còn MID MCP hiện không có OAuth. Runtime API key của tunnel không giải quyết lỗi. Kiểm tra Authentication/Auth ở màn tạo kết nối; **không** chuyển server có quyền ghi/terminal sang No authentication. Hướng an toàn là bổ sung OAuth 2.1 và phân quyền từng tool, hoặc dùng server thử nghiệm tách biệt, chỉ đọc dữ liệu công khai. Nếu đã chọn No authentication mà vẫn lỗi, thu thập thông báo ChatGPT và log tunnel-client (che key) để chẩn đoán. [OpenAI Docs — authentication](https://developers.openai.com/plugins/build/auth).
- **Tunnel không hiện trong ChatGPT:** kiểm tra `run` còn chạy, `/ui` healthy/ready, association với ChatGPT workspace và quyền Tunnels Read + Use; chạy lại `doctor --explain`. Enterprise/Edu không liên kết tự động được có thể cần quản trị viên hoặc OpenAI account team. [OpenAI Docs — troubleshooting](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

## 6. Bảo mật và phạm vi triển khai

- Generic terminal đi qua `CommandPolicyEngine` trước khi tạo subprocess. Engine chuẩn hóa executable theo controlled `PATH`, kiểm tra `cwd`, parse semantic subcommand và fail-closed. `python -c`/stdin, Node eval, shell `-c`, `docker run`/`exec`, Docker write/destructive, Git write/network, `npx` và `npm exec` đều có policy riêng; đường dẫn absolute tới `/usr/bin/...` không bypass được policy. `docker exec` hiện bị chặn hoàn toàn trong generic terminal vì chưa có bộ kiểm tra lệnh bên trong container đủ an toàn.
- `git_read`, `git_write`, `git_network`, `docker_read`, `docker_write`, `docker_destructive`, `docker_exec`, `docker_run`, `allow_npx` và `npm_exec` là các capability độc lập. `docker_exec` được dành cho dedicated tool trong tương lai; generic terminal vẫn chặn nó. Generic terminal không được cấp nhiều quyền hơn permission project.
- Sensitive-file policy mặc định ẩn và từ chối đọc `.env*`, key/certificate, credentials/secrets và các file tương tự (trừ `.env.example`/`.env.sample`). Search và directory listing cũng áp dụng policy này. Dữ liệu output/audit được redaction.
- Environment override nguy hiểm như `PATH`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONPATH`, `NODE_OPTIONS`, `GIT_SSH_COMMAND`, `BASH_ENV` và `SHELLOPTS` bị từ chối; subprocess luôn dùng controlled `PATH` và `shell=False`.
- Có thể bật sandbox tùy chọn bằng `sandbox.enabled: true` và `backend: bubblewrap`. Khi bật mà bubblewrap không khả dụng, execution bị từ chối (không âm thầm chạy unsandboxed). Hãy kiểm tra kỹ distro, quyền user và dependency trước khi bật production.
- Đường dẫn tệp tương đối đi qua bộ kiểm tra traversal, đường dẫn tuyệt đối và symlink escape. Ghi tệp có thể tạo backup trong `.mcp-backups`; hành động được ghi trong `audit_log`.
- Khi tạo `.mcp-backups` trong một project thuộc Git, filesystem tools kiểm tra quy tắc ignore và tự thêm `.mcp-backups/` nếu cần. Với project nằm trong repository cha, MCP chỉ ghi `.gitignore` trong phạm vi project được cấu hình; nếu repository đã có rule phù hợp thì không tạo thêm dòng trùng.
- Command policy và path policy không thể thay thế OS sandbox. Nếu sandbox tắt, `python3 scripts/test.py`, `npm run build` và project code vẫn có thể đọc tài nguyên mà tài khoản Linux có quyền truy cập. Đây là trusted-code execution boundary.
- Docker socket có thể cấp quyền gần tương đương root. Không chạy MCP bằng root hoặc cấp Docker/systemd khi không thật sự cần.
- Tool hiện có gồm thông tin project, thao tác tệp, tìm kiếm, lệnh project, Git đọc, Docker Compose và thông tin hệ thống cơ bản. Một số khả năng trong prompt thiết kế gốc như quản trị Docker/systemd đầy đủ, PostgreSQL và Odoo **chưa được triển khai**.
- Để chạy lâu dài, dùng tài khoản OS riêng với quyền tối thiểu, giới hạn project/command, thêm xác thực người dùng và kiểm tra scope cho từng tool nhạy cảm. `deploy/mid-mcp.service` chỉ là mẫu systemd; cần rà soát đường dẫn, filesystem, Docker socket và quyền service trước khi bật.

## 7. Kiểm chứng security regression

Suite hiện có **49 tests**, gồm regression test cho Python/Node/shell escape, script ngoài project, Docker permission bypass, Docker `exec`/`run`, Git write/network, absolute executable resolution, file command đọc ngoài project, traversal, symlink write, sensitive files, environment injection, secret redaction, backup `.gitignore` và chứng minh policy từ chối trước khi executor được gọi:

```bash
.venv/bin/pytest -q
# 49 passed
```

Các probe an toàn tương ứng trả về denial theo policy trước subprocess. Residual risks chính là code project được tin cậy khi chạy build/test, quyền OS của tài khoản chạy MCP, Docker socket và việc server hiện chưa có OAuth cho ChatGPT.

Tài liệu OpenAI có thể thay đổi: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), [kết nối ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt), [xác thực MCP](https://developers.openai.com/plugins/build/auth).
