Bạn đang bảo trì project:

MID Project & System MCP

Đây là một MCP Server chạy trên Linux, cho phép AI:

- đọc/sửa file trong các project đã khai báo
- chạy terminal trong project
- dùng Git
- dùng Docker
- chạy CLI tools
- xem log
- kiểm tra system/network
- thao tác với project theo permission được cấu hình

Hiện tại MCP hoạt động nhưng đã phát hiện một số LỖ HỔNG SECURITY NGHIÊM TRỌNG.

Nhiệm vụ của bạn là:

1. Audit security architecture hiện tại.
2. Fix toàn bộ các bypass đã biết.
3. Bổ sung policy layer cho generic terminal.
4. Viết regression tests.
5. Tự chạy tests.
6. Chứng minh các bypass cũ đã bị chặn.
7. Không làm mất các capability hợp lệ của coding agent.

Không chỉ giải thích.
Hãy trực tiếp sửa code trong project hiện tại.

---

# 1. VẤN ĐỀ ĐÃ PHÁT HIỆN THỰC TẾ

## VULNERABILITY 1 — Interpreter escape qua Python

Project có permission kiểu:

```yaml
permissions:
  read: true
  write: true
  terminal: true
```

Filesystem tool có project isolation.

Ví dụ:

```text
read_project_file(project, relative_path)
```

được giới hạn trong project root.

Nhưng generic terminal:

```text
run_project_command()
```

cho phép:

```bash
python3 -c "..."
```

Và đã test thành công:

```python
from pathlib import Path
p = Path("/etc/hostname")
print(p.exists())
```

Kết quả:

```text
True
```

Nghĩa là Python có thể truy cập file nằm ngoài project.

Thậm chí đã test:

```python
Path("/tmp/mid_mcp_security_probe").write_text("probe")
```

và ghi file ngoài project thành công.

=> PROJECT ISOLATION BỊ BYPASS.

---

# 2. VULNERABILITY 2 — Docker permission bypass

Project đang có:

```yaml
docker_read: true
docker_write: false
docker_destructive: false
```

Nhưng:

```text
run_project_command()
```

cho phép gọi Docker CLI.

Test:

```bash
docker restart __mcp_security_probe_nonexistent__
```

MCP cho phép command chạy.

Docker trả:

```text
No such container
```

Điều này chứng minh MCP đã cho phép action:

```text
docker restart
```

đi tới Docker daemon.

Nếu dùng container thật thì có thể restart container dù:

```yaml
docker_write: false
```

=> PERMISSION MODEL BỊ BYPASS.

---

# 3. NGUYÊN NHÂN KIẾN TRÚC

Hiện có hai lớp capability:

```text
Dedicated MCP tools
       ↓
Permission checks
       ↓
Operation
```

nhưng song song lại có:

```text
run_project_command
       ↓
arbitrary CLI
       ↓
same operations
```

Generic terminal hiện có thể bypass permission của dedicated tools.

Ví dụ:

```yaml
git_write: false
```

nhưng nếu terminal cho:

```bash
git commit
git reset
git checkout
```

thì git_write=false vô nghĩa.

Tương tự:

```yaml
docker_write: false
```

nhưng terminal cho:

```bash
docker restart
docker stop
docker exec
docker compose down
```

thì docker permission cũng vô nghĩa.

---

# 4. MỤC TIÊU FIX

Không được xóa:

```text
run_project_command()
```

vì đây là capability quan trọng của coding agent.

Thay vào đó cần tạo:

COMMAND POLICY ENGINE

Policy engine phải authorize dựa trên:

- project
- executable
- arguments
- subcommand
- permissions
- cwd
- risk level

Flow đúng phải là:

```text
run_project_command
       ↓
resolve executable
       ↓
parse command
       ↓
CommandPolicyEngine
       ↓
project permissions
       ↓
command-specific policy
       ↓
execute
```

Không được chỉ kiểm tra:

```text
command[0] in allowed_commands
```

vì cách này không đủ an toàn.

---

# 5. IMPLEMENT COMMAND POLICY ENGINE

Tạo module riêng, ví dụ:

```text
core/command_policy.py
```

Có class:

```python
class CommandPolicyEngine:
    def authorize(
        self,
        project,
        command: list[str],
        cwd: Path,
    ) -> PolicyDecision:
        ...
```

Result:

```python
PolicyDecision(
    allowed=True,
    reason=None,
    risk_level="EXECUTE",
)
```

hoặc:

```python
PolicyDecision(
    allowed=False,
    reason="docker restart requires docker_write permission",
)
```

Policy engine phải được gọi BẮT BUỘC trước mọi generic terminal command.

---

# 6. EXECUTABLE RESOLUTION

Không chỉ kiểm tra literal:

```text
python3
```

Phải resolve executable thực tế.

Ví dụ:

```python
shutil.which()
Path.resolve()
```

Phải xử lý alias executable như:

```text
python
python3
python3.14
/usr/bin/python3
/usr/bin/python3.14
```

Tất cả phải map về Python interpreter family.

Tương tự:

```text
node
/usr/bin/node
```

và:

```text
docker
/usr/bin/docker
```

Không được bypass policy bằng absolute executable path.

---

# 7. PYTHON SECURITY POLICY

Python interpreter là một shell-equivalent capability.

BLOCK:

```text
python -c
python3 -c
python --command
python3 --command
python -
python3 -
```

Và mọi variant tương đương.

Ví dụ sau phải bị deny:

```bash
python3 -c "open('/etc/passwd').read()"
```

```bash
python3 -c "import subprocess; subprocess.run(...)"
```

```bash
echo code | python3 -
```

Nếu stdin execution chưa được MCP hỗ trợ thì vẫn phải explicitly block `-`.

ALLOW:

```bash
python3 script.py
```

chỉ khi:

```text
script.py
```

resolve vào bên trong project.

Ví dụ:

```bash
python3 scripts/test.py
```

=> allowed

Nhưng:

```bash
python3 /tmp/test.py
```

=> denied

```bash
python3 ../../test.py
```

=> denied

---

# 8. PYTHON MODULE MODE

Phải kiểm soát:

```bash
python3 -m ...
```

Không được cho arbitrary module.

Tạo allowlist.

Ví dụ:

```text
pytest
compileall
unittest
pip
```

Nhưng pip phải có policy riêng.

Ví dụ:

```bash
python3 -m pytest
```

allowed

```bash
python3 -m compileall .
```

allowed

Không mặc định cho:

```bash
python3 -m http.server
```

hoặc module có thể execute arbitrary behavior.

Thiết kế module allowlist configurable.

---

# 9. NODE SECURITY POLICY

Node cũng là interpreter escape.

BLOCK:

```text
node -e
node --eval
node -p
node --print
```

và các variant tương đương có thể chạy inline JavaScript.

Ví dụ phải bị deny:

```bash
node -e "require('fs').readFileSync('/etc/passwd')"
```

ALLOW:

```bash
node scripts/test.js
```

nhưng script phải resolve trong project.

Block:

```bash
node /tmp/test.js
```

---

# 10. CÁC INTERPRETER KHÁC

Thiết kế policy extensible để block hoặc kiểm soát:

```text
perl -e
ruby -e
php -r
lua -e
awk
sed với execute capability nếu có
```

Không nhất thiết support hết trong V1.

Nhưng architecture phải cho phép định nghĩa:

```text
interpreter policy
```

Không dùng blacklist string đơn giản.

---

# 11. SHELL POLICY

Tiếp tục block:

```text
bash
sh
zsh
dash
fish
```

khi dùng:

```text
-c
```

hoặc tương đương.

Nếu project thực sự cần chạy script shell:

```bash
bash scripts/build.sh
```

chỉ được allow nếu:

```text
scripts/build.sh
```

nằm trong project.

Tuyệt đối block:

```bash
bash /tmp/x.sh
bash ../../x.sh
```

Nếu không cần shell scripts trong V1 thì có thể block toàn bộ shell executable.

---

# 12. DOCKER COMMAND POLICY

Docker CLI phải parse subcommand.

Không chỉ:

```text
docker allowed
```

Phải map từng action sang permission.

Ví dụ:

## docker_read

Nếu:

```yaml
docker_read: true
```

ALLOW:

```text
docker ps
docker container ls
docker images
docker image ls
docker inspect
docker logs
docker stats --no-stream
docker network ls
docker volume ls
docker compose ps
docker compose logs
docker compose config
```

---

## docker_write

Chỉ nếu:

```yaml
docker_write: true
```

ALLOW:

```text
docker start
docker stop
docker restart
docker compose up
docker compose down
docker compose restart
docker compose start
docker compose stop
```

---

## docker_destructive

Chỉ nếu:

```yaml
docker_destructive: true
```

ALLOW:

```text
docker rm
docker rmi
docker container rm
docker image rm
docker volume rm
docker network rm
docker system prune
docker volume prune
docker image prune
docker builder prune
```

---

# 13. DOCKER EXEC

`docker exec` là capability cực mạnh.

Không coi nó đơn giản là docker_write.

Tạo permission riêng hoặc policy riêng:

```yaml
docker_exec: false
```

Mặc định:

```text
false
```

Nếu enabled:

```text
docker exec
```

vẫn phải kiểm tra command bên trong container nếu khả thi.

Nếu chưa implement sandbox đủ tốt:

block docker exec hoàn toàn trong generic terminal.

Dedicated tool có thể được implement sau.

---

# 14. DOCKER RUN

`docker run` cũng rất nguy hiểm.

Ví dụ:

```bash
docker run -v /:/host ...
```

có thể mount toàn bộ host filesystem.

Mặc định:

```text
docker run
```

MUST BE DENIED.

Ngay cả khi:

```yaml
docker_write: true
```

Không enable trừ khi có permission riêng:

```yaml
docker_run: true
```

Nếu hỗ trợ sau này phải validate:

```text
-v
--volume
--mount
--privileged
--pid=host
--network=host
--device
```

Trong V1 nên BLOCK toàn bộ docker run.

---

# 15. DOCKER COMPOSE

Docker Compose command phải chạy chỉ từ project.

Compose file phải nằm trong:

```text
project root
```

hoặc subdirectory bên trong project.

Không cho:

```text
-f /tmp/docker-compose.yml
```

Không cho:

```text
-f ../../compose.yml
```

Validate:

```text
-f
--file
--project-directory
```

để không escape project.

---

# 16. GIT COMMAND POLICY

Generic terminal phải tôn trọng:

```yaml
git_read
git_write
```

## git_read

Allow:

```text
git status
git diff
git log
git show
git branch
git rev-parse
git ls-files
```

---

## git_write

Chỉ nếu:

```yaml
git_write: true
```

Allow:

```text
git add
git commit
git checkout
git switch
git restore
git reset
git stash
git merge
git rebase
git tag
```

---

# 17. GIT REMOTE OPERATIONS

Tạo permission riêng:

```yaml
git_network: false
```

Mặc định deny:

```text
git push
git pull
git fetch
git clone
```

Vì đây là network/external mutation.

Không để git_write tự động imply git push.

---

# 18. GIT EXTERNAL COMMAND ESCAPES

Git có nhiều option có thể execute external commands.

Audit và chặn các option nguy hiểm như:

```text
-c core.sshCommand=...
--exec-path
--upload-pack
--receive-pack
```

và các mechanism có thể trigger external helper.

Không cần support tất cả Git CLI option trong generic terminal.

Ưu tiên explicit allowlist.

---

# 19. NPM SECURITY

npm là một execution framework.

Phải hiểu rằng:

```bash
npm run xxx
```

có thể execute arbitrary script khai báo trong package.json.

Nhưng đây là capability cần thiết cho coding agent.

Policy:

```yaml
terminal: true
```

có thể cho phép:

```text
npm run <script>
npm test
npm ci
npm install
```

Nhưng chỉ khi cwd nằm trong project.

---

# 20. NPX

`npx` có thể tải và execute arbitrary package từ internet.

Mặc định:

```text
npx
```

BLOCK.

Tạo permission:

```yaml
allow_npx: false
```

Nếu enabled thì phải document rõ risk.

---

# 21. NPM EXEC

Block:

```text
npm exec
```

mặc định.

Vì tương đương arbitrary execution.

Có permission riêng nếu cần.

---

# 22. PACKAGE SCRIPT RISK

Không cần cố sandbox:

```text
npm run build
```

khỏi filesystem project hoàn toàn vì build tool thực chất có thể execute code.

Nhưng phải coi capability này là EXECUTE/TRUSTED_PROJECT_CODE.

Document rõ:

Nếu AI được phép chạy project code, project code có thể truy cập tài nguyên của Linux user.

Điều này là boundary khác với MCP tool boundary.

---

# 23. QUAN TRỌNG — OS-LEVEL SANDBOX

Command policy không thể tạo filesystem sandbox thật sự.

Ví dụ ngay cả:

```bash
python3 script.py
```

với script nằm trong project, script đó vẫn có thể:

```python
open("/etc/passwd")
```

Nếu mục tiêu security là:

"process tuyệt đối không được truy cập ngoài project"

thì COMMAND POLICY KHÔNG ĐỦ.

Hãy đánh giá và implement hoặc document một OS-level sandbox option.

Ưu tiên nghiên cứu giải pháp available trên Linux:

```text
bubblewrap / bwrap
```

hoặc:

```text
systemd-run sandbox
```

hoặc:

```text
Landlock
```

hoặc container sandbox.

---

# 24. BUBBLEWRAP MODE

Nếu hợp lý, implement optional:

```yaml
sandbox:
  enabled: true
  backend: "bubblewrap"
```

Khi enabled, project command chạy với:

- project bind read-write
- system dirs cần thiết read-only
- /tmp private
- HOME controlled
- không truy cập arbitrary home directories
- no unexpected filesystem write outside project

Ví dụ conceptual:

```text
bwrap
--ro-bind /usr /usr
--ro-bind /bin /bin
--ro-bind /lib /lib
--ro-bind /lib64 /lib64
--bind PROJECT_ROOT PROJECT_ROOT
--tmpfs /tmp
--proc /proc
--dev /dev
--chdir PROJECT_ROOT
COMMAND...
```

Không copy ví dụ một cách mù quáng.

Phải implement đúng theo distro/environment.

Nếu bubblewrap không có:

graceful fallback theo config.

Config có thể:

```yaml
sandbox:
  required: false
```

Nếu:

```text
required=true
```

mà sandbox backend unavailable:

DENY execution.

Không silently chạy unsandboxed.

---

# 25. SANDBOX VÀ DOCKER SOCKET

Nếu sandbox chạy Docker CLI thì cần access:

```text
/var/run/docker.sock
```

Điều này phá vỡ một phần isolation vì Docker daemon rất privileged.

Do đó:

Docker commands nên có execution path riêng.

Không blindly expose docker.sock cho mọi project process.

---

# 26. PATH SECURITY

Audit lại function:

```text
resolve_project_path()
```

Phải chống:

```text
../
absolute path
symlink escape
```

Test:

```text
../../../etc/passwd
/etc/passwd
```

và symlink:

```text
project/test-link -> /etc
```

sau đó:

```text
read test-link/passwd
```

phải deny.

---

# 27. WRITE TO SYMLINK

Đặc biệt test:

```text
project/file -> /tmp/outside
```

Sau đó:

```text
write_project_file(file)
```

phải DENY.

Không chỉ kiểm tra parent directory trước resolve.

---

# 28. SENSITIVE FILE POLICY

Hiện list_project_files có thể expose:

```text
.env.local
.env.production.local
```

Cần tạo sensitive file policy.

Mặc định deny content read cho:

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials
secrets
*.p12
*.pfx
```

Ngoại lệ:

```text
.env.example
.env.sample
```

có thể đọc.

---

# 29. DIRECTORY LISTING

Có thể cho thấy filename sensitive hoặc cấu hình:

```yaml
hide_sensitive_filenames: true
```

Nếu true:

không return sensitive filenames trong directory listing.

Nếu false:

có thể show tên nhưng không content.

Default nên cân nhắc:

```text
true
```

---

# 30. SECRET REDACTION

Output terminal, Docker inspect, Git, logs phải đi qua redaction layer.

Redact pattern:

```text
PASSWORD
PASS
PASSWD
SECRET
TOKEN
API_KEY
PRIVATE_KEY
ACCESS_KEY
DATABASE_URL
AUTH_TOKEN
```

Cả dạng:

```text
KEY=value
```

và JSON.

Không log secret vào audit logs.

---

# 31. ENV PARAMETER SECURITY

Hiện:

```text
run_project_command(..., env={...})
```

có thể nhận environment.

Audit để đảm bảo AI không thể override các biến nhạy cảm như:

```text
PATH
LD_PRELOAD
LD_LIBRARY_PATH
PYTHONPATH
NODE_OPTIONS
GIT_SSH_COMMAND
BASH_ENV
ENV
SHELLOPTS
```

Mặc định deny overriding các environment variables có khả năng code injection/hijacking.

Tạo safe env allowlist hoặc denylist mạnh.

---

# 32. PATH EXECUTABLE HIJACKING

Không trust project-local executable chỉ vì command tên:

```text
git
python
docker
```

Resolve qua controlled PATH.

Ví dụ:

```text
/usr/bin
/usr/local/bin
```

Không prepend project directory vào PATH.

Không cho file:

```text
./git
```

giả executable nếu policy đang nghĩ đó là system Git.

---

# 33. COMMAND OPTION PARSING

Không chỉ kiểm tra:

```text
args[1]
```

một cách ngây thơ.

Ví dụ Git/Docker có global flags trước subcommand:

```bash
docker --context x ps
git -C path status
```

Policy phải:

- parse supported safe global options
- hoặc deny unsupported forms

Không cố viết full Docker/Git CLI parser nếu không cần.

Better:

Explicitly support known safe syntax.

Unknown form:

DENY.

---

# 34. FAIL CLOSED

Security policy phải:

FAIL CLOSED.

Nếu parser không hiểu command:

```text
DENY
```

Không:

```text
ALLOW because executable is whitelisted
```

Đây là yêu cầu quan trọng.

---

# 35. DEDICATED TOOL VS GENERIC TERMINAL

Dedicated tools vẫn phải tồn tại.

Generic terminal không được có quyền cao hơn dedicated tool.

Invariant:

```text
Generic terminal capability
<=
Project configured permissions
```

Ví dụ:

```yaml
docker_write: false
```

thì cả:

```text
docker_compose_restart()
```

và:

```text
run_project_command(["docker","compose","restart"])
```

đều phải deny.

---

# 36. CENTRALIZED AUTHORIZATION

Không duplicate permission logic.

Ví dụ:

```text
DockerPolicy
GitPolicy
InterpreterPolicy
ShellPolicy
PackageManagerPolicy
```

Dedicated tools và generic terminal phải dùng cùng core permission model nếu có thể.

---

# 37. RISK LEVELS

Giữ hoặc bổ sung:

```text
READ
WRITE
EXECUTE
SERVICE_ACTION
DESTRUCTIVE
NETWORK
PRIVILEGED
```

Map command sang risk.

Ví dụ:

```text
docker ps
READ

docker restart
SERVICE_ACTION

docker rm
DESTRUCTIVE

git push
NETWORK + WRITE

python script.py
EXECUTE
```

---

# 38. REGRESSION TESTS BẮT BUỘC

Viết tests tái hiện chính xác các vulnerability.

## Test Python escape

Phải fail:

```text
python3 -c "..."
```

Expected:

```text
PERMISSION_DENIED
```

---

## Test Node escape

Phải fail:

```text
node -e "..."
```

---

## Test shell escape

Phải fail:

```text
bash -c "..."
sh -c "..."
```

---

## Test Python script outside project

Phải fail:

```text
python3 /tmp/x.py
```

---

## Test Python script inside project

Phải allow nếu terminal=true:

```text
python3 scripts/test.py
```

---

# 39. DOCKER REGRESSION TEST

Config:

```yaml
docker_read: true
docker_write: false
docker_destructive: false
```

Expected:

ALLOW:

```text
docker ps
docker logs abc
docker inspect abc
```

DENY:

```text
docker restart abc
docker stop abc
docker start abc
docker exec abc sh
docker rm abc
docker system prune
```

---

# 40. DOCKER WRITE TEST

Config:

```yaml
docker_write: true
docker_destructive: false
```

Expected:

ALLOW:

```text
docker restart abc
docker compose up -d
docker compose restart
```

DENY:

```text
docker rm abc
docker volume rm abc
docker system prune
docker run ...
```

---

# 41. GIT TEST

Config:

```yaml
git_read: true
git_write: false
```

ALLOW:

```text
git status
git diff
git log
git show
```

DENY:

```text
git add
git commit
git reset
git checkout
git push
```

---

# 42. GIT WRITE TEST

Config:

```yaml
git_write: true
git_network: false
```

ALLOW:

```text
git add
git commit
```

DENY:

```text
git push
git pull
git fetch
```

---

# 43. PATH TEST

Must deny:

```text
../../../etc/passwd
/etc/passwd
```

Must deny symlink escape.

Must deny write-through-symlink.

---

# 44. ENV TEST

Must deny or strip:

```text
LD_PRELOAD
PYTHONPATH
NODE_OPTIONS
GIT_SSH_COMMAND
```

unless explicitly configured.

---

# 45. COMMAND RESOLUTION TEST

These must receive same policy:

```text
python3
/usr/bin/python3
```

and:

```text
docker
/usr/bin/docker
```

Cannot bypass by absolute executable path.

---

# 46. SAFE COMMAND TEST

Do not over-fix MCP so that normal development breaks.

Must continue supporting legitimate operations such as:

```text
git status
git diff

npm run build
npm test

python3 scripts/test.py
python3 -m pytest

docker ps
docker logs

rg
grep
```

subject to project permissions.

---

# 47. CONFIG MODEL

Extend config cleanly.

Example target:

```yaml
security:

  terminal:
    enabled: true

    blocked_shells:
      - sh
      - bash
      - dash
      - zsh

    block_inline_interpreters: true

    safe_environment:
      deny_override:
        - LD_PRELOAD
        - LD_LIBRARY_PATH
        - PYTHONPATH
        - NODE_OPTIONS
        - GIT_SSH_COMMAND

  sensitive_files:
    hide_from_listing: true

    deny:
      - ".env"
      - ".env.*"
      - "*.pem"
      - "*.key"
      - "id_rsa"
      - "id_ed25519"
      - "*.p12"
      - "*.pfx"

    allow:
      - ".env.example"
      - ".env.sample"

sandbox:
  enabled: false
  backend: "bubblewrap"
  required: false
```

Project:

```yaml
permissions:

  read: true
  write: true
  delete: false

  terminal: true

  git_read: true
  git_write: false
  git_network: false

  docker_read: true
  docker_write: false
  docker_destructive: false
  docker_exec: false
  docker_run: false
```

Bạn có thể cải thiện schema nếu cần.

---

# 48. AUDIT LOG

Security deny phải được audit.

Ví dụ:

```text
tool=run_project_command
project=example
command=["python3","-c","..."]
decision=DENY
reason=INLINE_INTERPRETER_BLOCKED
```

Không log nguyên content code nếu có khả năng chứa secret.

Có thể sanitize/truncate argument trong audit.

---

# 49. ERROR RESPONSE

Khi block command:

```json
{
  "success": false,
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "python inline execution is not allowed",
    "details": {
      "policy": "INTERPRETER_INLINE_EXECUTION"
    }
  }
}
```

Không leak internal stack traces.

---

# 50. SECURITY DOCUMENTATION

Update README.

Giải thích rõ hai security layer:

## Application-level command policy

Kiểm soát:

- command nào được phép
- Docker permission
- Git permission
- inline interpreter
- project paths

## OS-level sandbox

Nếu enabled:

kiểm soát filesystem/network/process ở mức OS.

Nhấn mạnh:

Command policy KHÔNG THỂ hoàn toàn sandbox code được execute.

Ví dụ:

```text
npm run build
python script.py
```

vẫn là trusted-code execution nếu không có OS sandbox.

---

# 51. DOCKER SECURITY WARNING

README phải nói rõ:

Access tới Docker socket có thể tương đương root privilege trên Linux host.

Không được mô tả:

```text
docker_read
```

như security boundary tuyệt đối nếu process có direct unrestricted Docker socket access qua cách khác.

MCP phải giảm các bypass qua tool layer nhưng document OS-level implication.

---

# 52. REVIEW TOÀN BỘ TOOL SET

Sau khi fix hai vulnerability đã biết, audit toàn bộ MCP tools để tìm bypass tương tự.

Đặc biệt:

```text
run_project_command
run_project_named_command
docker tools
git tools
write tools
move/copy tools
search tools
system tools
CLI discovery
```

Kiểm tra permission consistency.

---

# 53. KHÔNG LÀM CÁC FIX GIẢ

Không coi các cách sau là fix:

```text
block string "/etc"
```

```text
block substring ".."
```

```text
block chỉ python3 -c nhưng để /usr/bin/python3 -c
```

```text
block docker restart nhưng để docker container restart
```

```text
block docker rm nhưng để docker container rm
```

```text
block git commit nhưng cho git -c ... commit
```

Fix phải dựa trên semantic command policy.

---

# 54. KHÔNG DÙNG REGEX DUY NHẤT CHO TOÀN BỘ TERMINAL

Command parsing nên structured.

Input hiện tại:

```python
list[str]
```

Giữ nguyên ưu điểm này.

Không join thành shell string để parse lại.

Không dùng:

```text
shell=True
```

---

# 55. IMPLEMENTATION ORDER

Thực hiện theo thứ tự:

1. Đọc architecture hiện tại.
2. Tìm executor của run_project_command.
3. Tìm permission model hiện tại.
4. Tìm Docker/Git policy hiện tại.
5. Viết regression tests cho vulnerability hiện tại.
6. Xác nhận tests fail trước fix.
7. Implement CommandPolicyEngine.
8. Implement executable normalization.
9. Implement interpreter policy.
10. Implement shell policy.
11. Implement Docker policy.
12. Implement Git policy.
13. Implement npm/node policy.
14. Implement env policy.
15. Integrate vào run_project_command.
16. Integrate policy với named command nếu cần.
17. Audit dedicated tools.
18. Fix path/symlink protection nếu thiếu.
19. Implement sensitive-file policy.
20. Implement secret redaction improvements.
21. Chạy unit tests.
22. Chạy security tests.
23. Chạy integration tests an toàn.
24. Test MCP startup.
25. Test tool discovery.
26. Update README.
27. Báo cáo.

---

# 56. LIVE SECURITY VALIDATION

Sau khi tests pass, nếu môi trường cho phép hãy chạy các probe KHÔNG PHÁ HOẠI.

Ví dụ:

```text
python3 -c "print('probe')"
```

Expected:

DENY

```text
node -e "console.log('probe')"
```

Expected:

DENY

```text
docker restart __mcp_nonexistent_probe__
```

với:

```text
docker_write=false
```

Expected:

MCP DENY

không được để request tới Docker daemon rồi mới nhận:

```text
No such container
```

Điểm này rất quan trọng.

Policy phải chặn trước subprocess execution.

---

# 57. NEGATIVE TEST QUAN TRỌNG

Sau fix, test:

```text
docker restart __mcp_nonexistent_probe__
```

Expected MCP response:

```text
PERMISSION_DENIED
```

Nếu vẫn nhận:

```text
No such container
```

thì fix CHƯA ĐÚNG.

---

# 58. PYTHON NEGATIVE TEST

Sau fix:

```text
python3 -c ...
```

Expected:

```text
PERMISSION_DENIED
```

Process Python không được spawn.

Mock subprocess trong unit test để chứng minh executor không được gọi.

---

# 59. DEFINITION OF DONE

Security fix chỉ hoàn thành khi:

- Python inline escape bị block.
- Node inline escape bị block.
- Shell -c bị block.
- Absolute executable path không bypass.
- Python script ngoài project bị block.
- Docker write không bypass docker_write.
- Docker destructive không bypass docker_destructive.
- Docker run bị block mặc định.
- Docker exec bị block mặc định.
- Git write không bypass git_write.
- Git network operations có permission riêng.
- cwd không escape project.
- path traversal bị block.
- symlink escape bị block.
- write-through-symlink bị block.
- sensitive files được bảo vệ.
- environment injection được kiểm soát.
- unknown command syntax fail closed.
- subprocess vẫn shell=False.
- safe commands vẫn hoạt động.
- regression tests pass.
- MCP start được.
- existing normal workflows không bị phá.

---

# 60. KẾT QUẢ CUỐI CÙNG

Sau khi hoàn thành hãy báo:

1. Root cause của từng vulnerability.

2. File nào đã sửa.

3. CommandPolicyEngine architecture.

4. Interpreter policy.

5. Docker policy.

6. Git policy.

7. Node/npm policy.

8. Sensitive file policy.

9. Environment security.

10. OS sandbox support nếu có.

11. Regression tests mới thêm.

12. Tổng test count.

13. Test results.

14. Live security probes đã chạy.

15. Các command trước đây bypass được nhưng hiện đã bị block.

16. Các residual risks còn tồn tại.

17. Những security improvements nên làm tiếp.

---

Mục tiêu cuối cùng:

MID Project & System MCP phải vẫn đủ mạnh để AI thực hiện workflow:

```text
đọc source
→ sửa code
→ chạy build/test
→ đọc output
→ đọc log
→ sửa tiếp
→ verify
```

nhưng generic terminal TUYỆT ĐỐI không được trở thành đường vòng để bypass:

```text
project isolation
Docker permissions
Git permissions
filesystem permissions
service permissions
security policies
```

Security invariant quan trọng nhất:

```text
Generic terminal must never grant more authority
than the permissions explicitly assigned to the project.
```

Hãy sửa implementation hiện tại theo nguyên tắc này và chứng minh bằng automated regression tests.