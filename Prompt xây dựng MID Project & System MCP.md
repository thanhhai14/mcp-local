Bạn là Senior Software Engineer, DevOps Engineer, Linux System Administrator và MCP Engineer có kinh nghiệm sâu về:

- Model Context Protocol (MCP)
- Python
- Linux / Ubuntu
- Filesystem
- Shell / Terminal
- Docker / Docker Compose
- systemd / journalctl
- Git
- SSH
- PostgreSQL
- Node.js / npm / pnpm / yarn
- Python / pip / uv
- Odoo
- Nginx / Apache
- Networking
- CLI automation

Nhiệm vụ của bạn là KHỞI TẠO, CODE, TEST và HOÀN THIỆN một MCP Server thực tế có tên:

MID Project & System MCP

Đây không phải MCP demo.

Mục tiêu là xây dựng một MCP Server chạy trực tiếp trên máy Linux của người dùng, cho phép AI Agent làm việc với các dự án và máy chủ gần giống một coding/system administration agent thực tế.

# 1. MỤC TIÊU NGHIỆP VỤ CHÍNH

MCP phải cho phép AI:

1. Truy cập các PROJECT đã được administrator khai báo.
2. Xem cấu trúc thư mục của project.
3. Đọc file.
4. Tạo file.
5. Chỉnh sửa file.
6. Xóa file khi được cấu hình cho phép.
7. Tạo thư mục.
8. Tìm kiếm file.
9. Tìm kiếm nội dung source code.
10. Chạy terminal trong project.
11. Chạy CLI tools trong project.
12. Xem output command.
13. Xem log ứng dụng.
14. Xem Docker/container.
15. Xem Docker logs.
16. Chạy Git.
17. Chạy package manager.
18. Build project.
19. Test project.
20. Restart/reload application khi được cho phép.
21. Kiểm tra service trên server.
22. Kiểm tra CPU/RAM/disk/network/process.
23. Sử dụng các CLI tool đã được administrator cho phép.
24. Hỗ trợ troubleshooting server.
25. Cho phép mở rộng thêm các tool riêng theo project.

MCP này sẽ đóng vai trò như cầu nối:

AI Agent
    ↓
MCP
    ↓
Project Workspace + Terminal + Server Tools + CLI Tools
    ↓
Linux Server

# 2. KHÁI NIỆM PROJECT LÀ TRUNG TÂM

Không cho AI tự do truy cập toàn bộ filesystem.

Administrator phải khai báo project.

Ví dụ:

projects:

  odoo18:
    name: "Odoo 18"
    path: "/srv/docker/odoo18"

  website:
    name: "MID Website"
    path: "/srv/docker/mid-web"

  netbird:
    name: "NetBird"
    path: "/srv/docker/netbird"

  tools:
    name: "Internal Tools"
    path: "/opt/mid-tools"

AI làm việc thông qua project ID.

Ví dụ:

list_project_files(
    project="odoo18",
    path="addons"
)

read_project_file(
    project="odoo18",
    path="addons/my_module/models/test.py"
)

write_project_file(
    project="odoo18",
    path="addons/my_module/models/test.py",
    content="..."
)

run_project_command(
    project="odoo18",
    command=["git", "status"]
)

Mọi đường dẫn phải được resolve dựa trên root của project.

AI KHÔNG được gửi:

/etc/passwd

hoặc:

../../../etc/passwd

để thoát khỏi project.

# 3. PROJECT CONFIGURATION

Thiết kế config YAML.

Ví dụ:

server:
  name: "MID Project & System MCP"
  transport: "stdio"
  host: "127.0.0.1"
  port: 8000

projects:

  odoo18:
    name: "Odoo 18"
    path: "/srv/docker/odoo18"

    permissions:
      read: true
      write: true
      delete: true
      terminal: true
      git: true
      docker: true

  mid-web:
    name: "MID Website"
    path: "/srv/docker/mid-web"

    permissions:
      read: true
      write: true
      delete: true
      terminal: true
      git: true
      docker: true

Administrator có thể thêm project mà KHÔNG sửa source MCP.

# 4. PROJECT DISCOVERY

Implement:

list_projects()

Trả:

- project ID
- project name
- root path
- permissions
- project type nếu detect được

Ví dụ:

{
  "id": "odoo18",
  "name": "Odoo 18",
  "path": "/srv/docker/odoo18",
  "type": "odoo",
  "permissions": {
    "read": true,
    "write": true,
    "terminal": true
  }
}

Có thể detect project type dựa trên:

package.json
pyproject.toml
requirements.txt
docker-compose.yml
compose.yml
odoo.conf
addons/
.git/

Nhưng project config vẫn là authority chính.

# 5. FILESYSTEM TOOLS

Đây là nhóm tool rất quan trọng.

Implement:

list_project_files()

Parameters:

project
path
recursive
max_depth
limit

Trả:

- name
- relative path
- type
- size
- modified time


Implement:

read_project_file()

Parameters:

project
path
offset
limit

Phải hỗ trợ đọc:

- source code
- config
- JSON
- XML
- YAML
- logs
- Markdown
- text


Implement:

write_project_file()

Parameters:

project
path
content

Có thể:

- tạo file mới
- overwrite file

Chỉ hoạt động nếu:

permissions.write = true


Implement:

patch_project_file()

Đây là tool quan trọng.

Cho phép AI chỉnh sửa một phần file thay vì gửi lại toàn bộ file.

Có thể thiết kế theo:

- search/replace
- unified diff
- line range
- patch

Ưu tiên implementation an toàn và deterministic.

AI phải có khả năng sửa source code hiệu quả.


Implement:

create_project_directory()


Implement:

delete_project_file()

Chỉ nếu:

permissions.delete = true


Implement:

move_project_file()


Implement:

copy_project_file()


Implement:

file_info()


# 6. FILE SAFETY

Mọi path phải:

Path.resolve()

Sau khi resolve:

resolved_path phải nằm bên trong project root.

Phải chống:

../
symlink escape
absolute path escape

Ví dụ:

project:
/srv/docker/odoo18

AI gửi:

../../etc/shadow

=> DENY


Symlink:

/srv/docker/odoo18/test -> /etc

AI truy cập:

test/passwd

=> DENY


Tạo function trung tâm:

resolve_project_path(project_id, relative_path)

Không duplicate security logic.


# 7. FILE WRITE BACKUP

Cho phép optional automatic backup trước khi AI ghi file.

Config:

filesystem:
  backup_before_write: true

Có thể lưu:

.mcp-backups/

Nhưng phải tránh backup vô hạn.

Có retention:

backup_retention: 20

Nếu project sử dụng Git, ưu tiên Git diff để audit thay đổi.


# 8. SEARCH

Implement:

search_project_files()

Search filename/glob.


Implement:

search_project_text()

Parameters:

project
query
path
file_pattern
max_results

Ưu tiên sử dụng:

ripgrep (rg)

nếu được cài.

Nếu không có:

Python fallback.

KHÔNG concatenate raw input thành shell string.


# 9. TERMINAL TRONG PROJECT

Đây là chức năng CỐT LÕI.

Implement:

run_project_command()

Parameters:

project
command
timeout
env

Ví dụ:

run_project_command(
    project="mid-web",
    command=["npm", "run", "build"]
)

Hoặc:

run_project_command(
    project="odoo18",
    command=["git", "status"]
)

Command phải chạy với:

cwd = PROJECT_ROOT

hoặc subdirectory được xác định bên trong project.


Parameters:

project
command: list[str]
cwd: optional relative path
timeout: optional
env: optional dictionary


KHÔNG sử dụng:

shell=True

Mặc định:

shell=False


Command phải chạy trực tiếp bằng argv.

Ví dụ:

["npm", "run", "build"]

không phải:

"npm run build"


# 10. TERMINAL PERMISSION MODEL

Terminal phải có configurable permission.

Ví dụ:

projects:

  odoo18:

    terminal:
      enabled: true

      allowed_commands:
        - git
        - python
        - python3
        - pip
        - uv
        - docker
        - docker-compose
        - npm
        - npx
        - node
        - grep
        - rg
        - find
        - ls
        - cat
        - tail
        - head

Có thể hỗ trợ:

allowed_commands: ["*"]

để administrator chủ động cho AI dùng tất cả executable có sẵn.

Không mặc định "*".

Administrator phải chủ động bật.


# 11. COMMAND DENYLIST

Có global deny list.

Ví dụ:

terminal:

  denied_commands:
    - shutdown
    - reboot
    - poweroff
    - halt
    - mkfs
    - fdisk
    - parted

  allow_sudo: false

Không cho:

sudo

trừ khi administrator chủ động:

allow_sudo: true

Không tự động bật sudo.


# 12. COMMAND WORKING DIRECTORY

Đây là yêu cầu bắt buộc.

Command project phải chạy bên trong project.

cwd phải được resolve.

Ví dụ hợp lệ:

project root:

/srv/docker/mid-web

cwd:

frontend

=> 

/srv/docker/mid-web/frontend


Không được:

cwd="../../../"


# 13. TERMINAL OUTPUT

Tool phải trả:

{
  "success": true,
  "command": [...],
  "cwd": "...",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1234
}

Có:

max_output_chars

Nếu output quá lớn:

truncate có thông báo rõ ràng.


# 14. COMMAND TIMEOUT

Default:

30 seconds

Config:

terminal:
  default_timeout: 30
  max_timeout: 1800

Build/test có thể cần timeout dài.

AI có thể yêu cầu timeout nhưng không được vượt max.


# 15. CLI TOOL SUPPORT

MCP phải hỗ trợ các CLI tool được cài trên máy.

Ví dụ:

git
docker
docker compose
npm
npx
node
pnpm
yarn
python
python3
pip
uv
pytest
ruff
eslint
prettier
odoo
psql
pg_dump
curl
wget
jq
rg
grep
find
systemctl
journalctl
nginx
apachectl
netbird
wg
ip
ss
ping
dig
nslookup
openssl

Nhưng quyền sử dụng phụ thuộc config.


Implement:

available_cli_tools()

Tool kiểm tra executable bằng:

shutil.which()

Trả version nếu có thể lấy an toàn.


# 16. GIT

Git là chức năng rất quan trọng.

Implement dedicated tools:

git_status(project)

git_diff(project)

git_log(project)

git_branch(project)

git_show(project, revision)

Có thể implement write operations nếu:

project.permissions.git_write = true

Ví dụ:

git_add()

git_commit()

git_checkout()

git_create_branch()

Không mặc định:

git push

Nếu muốn push phải config:

git:
  allow_push: true


# 17. BUILD & TEST

AI phải có thể build/test project.

Có thể dùng generic terminal.

Nhưng nên implement helper:

detect_project_commands(project)

Ví dụ đọc package.json:

scripts:
  dev
  build
  test
  lint

Python:

pytest
ruff

Docker:

docker compose config


Implement:

project_info(project)

Trả:

language/framework
package manager
Git info
Docker info
available scripts


# 18. NPM / NODE SUPPORT

Nếu project có package.json:

Implement hoặc hỗ trợ:

npm install
npm ci
npm run
npm test
npm build

AI phải có thể chạy:

npm run build

và nhận toàn bộ result.


# 19. PYTHON SUPPORT

AI có thể:

python
python3
pip
uv
pytest

Phải detect:

.venv
venv
pyproject.toml
requirements.txt

Có thể expose:

python_project_info(project)


# 20. DOCKER

Docker là chức năng rất quan trọng.

Implement:

docker_containers()

docker_images()

docker_networks()

docker_volumes()

docker_stats()

docker_inspect()

docker_logs()


Nếu project có compose:

docker_compose_ps(project)

docker_compose_logs(project)

docker_compose_config(project)


Nếu permission:

docker_write = true

cho phép:

docker_compose_up()

docker_compose_down()

docker_compose_restart()

docker_restart_container()

docker_stop_container()

docker_start_container()


Tuy nhiên:

docker rm
docker volume rm
docker system prune

phải có permission riêng:

docker_destructive = true


# 21. DOCKER COMPOSE PROJECT DETECTION

Detect:

compose.yml
compose.yaml
docker-compose.yml
docker-compose.yaml

Khi chạy Docker Compose:

cwd phải là project root hoặc compose directory.

Không cho project A điều khiển compose của project B.


# 22. LOG SUPPORT

AI cần có khả năng troubleshooting.

Implement:

read_project_log()

tail_project_log()

search_project_log()


Docker:

docker_logs()


Systemd:

service_logs()


Có thể hỗ trợ:

since
until
lines
filter


Ví dụ:

service_logs(
    service="nginx",
    lines=200
)


# 23. SYSTEM TOOLS

Ngoài project, MCP phải hỗ trợ system administration.

Implement:

system_info()

cpu_info()

memory_info()

disk_usage()

filesystem_mounts()

process_list()

network_interfaces()

network_routes()

listening_ports()

dns_lookup()

ping_host()


# 24. SYSTEMD

Implement:

systemd_services()

systemd_status(service)

systemd_logs(service)


Nếu:

system_tools.allow_service_actions = true

cho phép:

systemd_start()

systemd_stop()

systemd_restart()

systemd_reload()


Có service allowlist:

allowed_services:
  - nginx
  - apache2
  - docker
  - netbird
  - postgresql


# 25. SERVER CLI TOOLS

MCP phải hỗ trợ CLI system administration.

Ví dụ AI có thể cần:

ip addr
ip route
ss -lntup
wg show
netbird status
docker ps
systemctl status nginx
journalctl
nginx -t
apachectl configtest
openssl
curl


Thiết kế:

run_server_command()

RIÊNG với:

run_project_command()


run_server_command() phải có permission riêng.

Không mặc định full shell.


Config:

server_terminal:
  enabled: true

  allowed_commands:
    - ip
    - ss
    - ping
    - dig
    - nslookup
    - wg
    - netbird
    - systemctl
    - journalctl
    - nginx
    - apachectl
    - docker
    - curl
    - openssl


# 26. KHÔNG DÙNG SHELL STRING NẾU KHÔNG CẦN THIẾT

Ưu tiên:

subprocess.run(
    ["git", "status"],
    cwd=...
)

không:

subprocess.run(
    "git status",
    shell=True
)


Nếu sau này muốn hỗ trợ bash pipeline thì phải là feature riêng:

run_shell_command

và:

allow_shell = false

mặc định.

Không enable trong initial configuration.


# 27. ENVIRONMENT VARIABLES

run_project_command có thể nhận env bổ sung.

Nhưng không cho AI mặc định đọc toàn bộ secret environment.

Output phải REDACT:

PASSWORD
PASSWD
SECRET
TOKEN
API_KEY
PRIVATE_KEY
ACCESS_KEY
DATABASE_URL

Tạo reusable secret redaction layer.


# 28. ODOO SUPPORT

Odoo là một trong các workload quan trọng.

Nếu project được detect là Odoo:

Implement:

odoo_project_info()

odoo_logs()

odoo_recent_errors()

odoo_config()

odoo_modules()

odoo_find_module()


Có thể hỗ trợ khi permission cho phép:

odoo_upgrade_module()

Ví dụ thực tế:

docker compose exec odoo \
odoo \
-d database \
-u module \
--stop-after-init


Nhưng command phải được xây dựng từ validated arguments.

Không nhận raw shell string.


AI cũng vẫn có thể sửa source Odoo thông qua:

read_project_file
patch_project_file
write_project_file


# 29. DATABASE TOOLS

Có thể detect PostgreSQL.

Version đầu nên hỗ trợ:

postgres_status()

postgres_version()

postgres_databases()

Nếu administrator bật:

database.allow_query = true

có thể implement:

postgres_query()

Nhưng chỉ thông qua project/database configuration.

Không để AI tự truyền password arbitrary.

Credentials lấy từ config/environment của MCP.


# 30. PROJECT-SPECIFIC CUSTOM COMMANDS

Đây là tính năng quan trọng.

Cho phép administrator định nghĩa command alias trong YAML.

Ví dụ:

projects:

  odoo18:

    commands:

      upgrade_module:
        command:
          - docker
          - compose
          - exec
          - odoo
          - odoo
          - "-d"
          - "{database}"
          - "-u"
          - "{module}"
          - "--stop-after-init"

        parameters:
          database:
            regex: "^[A-Za-z0-9_-]+$"

          module:
            regex: "^[A-Za-z0-9_]+$"


Hoặc:

mid-web:

  commands:

    build:
      command:
        - npm
        - run
        - build

    test:
      command:
        - npm
        - test


Implement:

list_project_commands(project)

run_project_named_command(project, command_name, parameters)


Đây sẽ giúp MCP mở rộng mà không cần sửa Python source.


# 31. PROJECT PERMISSIONS

Permission có thể gồm:

read
write
delete
terminal
git_read
git_write
docker_read
docker_write
docker_destructive
service_control
database_read
database_write


Ví dụ:

permissions:
  read: true
  write: true
  delete: true
  terminal: true

  git_read: true
  git_write: true

  docker_read: true
  docker_write: true
  docker_destructive: false


# 32. TOOL RISK LEVEL

Mỗi tool nên có metadata/risk classification.

READ

Ví dụ:

read_file
git_status
docker_logs


WRITE

Ví dụ:

write_file
patch_file
git_commit


EXECUTE

Ví dụ:

run_project_command
npm build


SERVICE_ACTION

Ví dụ:

docker_restart
systemctl_restart


DESTRUCTIVE

Ví dụ:

delete_file
docker_rm
volume_rm


Architecture phải cho phép policy engine kiểm tra risk trước khi execute.


# 33. AUDIT LOG

Mọi action cần được log.

Ví dụ:

2026-09-15 13:10:21
tool=write_project_file
project=odoo18
path=addons/test/models/test.py
status=success


Terminal:

tool=run_project_command
project=mid-web
command=["npm","run","build"]
cwd=/srv/docker/mid-web
exit_code=0
duration=12.4


Không log secret.


# 34. CONCURRENCY

MCP có thể nhận nhiều request.

File write cần tránh corruption.

Cân nhắc:

asyncio.Lock

theo project hoặc file.


Long-running command cần quản lý timeout.


# 35. OPTIONAL SESSION COMMANDS

Nếu implementation hợp lý, thiết kế support command session.

Ví dụ:

start_command()

command_status()

command_output()

stop_command()


Dùng cho:

npm run dev
docker compose logs -f
long build


Nhưng không bắt buộc V1 nếu làm tăng complexity quá nhiều.

Ưu tiên synchronous command + timeout hoạt động tốt trước.


# 36. MCP TRANSPORT

Hỗ trợ:

stdio

và:

Streamable HTTP


Config:

server:
  transport: "streamable-http"
  host: "127.0.0.1"
  port: 8000


Mặc định:

127.0.0.1

Không expose public ngoài ý muốn.


# 37. TECH STACK

Sử dụng:

Python 3.11+

MCP Python SDK chính thức

Pydantic

PyYAML

asyncio

pathlib

subprocess / asyncio subprocess

logging

pytest


Không thêm dependency không cần thiết.


# 38. PROJECT STRUCTURE

Thiết kế modular.

Gợi ý:

mid-project-system-mcp/

├── README.md
├── pyproject.toml
├── .gitignore
├── config.example.yaml

├── src/
│   └── mid_mcp/
│
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│
│       ├── core/
│       │   ├── project_manager.py
│       │   ├── permissions.py
│       │   ├── security.py
│       │   ├── executor.py
│       │   ├── result.py
│       │   ├── redaction.py
│       │   └── audit.py
│
│       ├── tools/
│       │   ├── projects.py
│       │   ├── filesystem.py
│       │   ├── terminal.py
│       │   ├── search.py
│       │   ├── git.py
│       │   ├── docker.py
│       │   ├── logs.py
│       │   ├── system.py
│       │   ├── systemd.py
│       │   ├── network.py
│       │   ├── odoo.py
│       │   └── database.py
│
│       └── utils/
│
├── tests/
│
└── deploy/
    └── mid-mcp.service


Bạn có thể cải thiện structure nếu có thiết kế tốt hơn.


# 39. STANDARD TOOL RESULT

Chuẩn hóa response.

Success:

{
  "success": true,
  "data": ...
}


Failure:

{
  "success": false,
  "error": {
    "code": "...",
    "message": "...",
    "details": {}
  }
}


Error codes:

PROJECT_NOT_FOUND

PERMISSION_DENIED

PATH_OUTSIDE_PROJECT

INVALID_ARGUMENT

COMMAND_NOT_ALLOWED

COMMAND_TIMEOUT

COMMAND_FAILED

FILE_NOT_FOUND

DEPENDENCY_MISSING

SERVICE_NOT_ALLOWED

OUTPUT_TOO_LARGE

INTERNAL_ERROR


# 40. TESTING

Viết unit test đầy đủ.

Đặc biệt test SECURITY.


Test:

project traversal bị block

../../../etc/passwd


Absolute path escape bị block.


Symlink escape bị block.


Project read permission.


Project write permission.


Delete permission.


Terminal disabled.


Command allowlist.


Command denylist.


sudo disabled.


cwd traversal.


Command timeout.


Output truncation.


Secret redaction.


File patch.


Git command.


Named project command parameter validation.


Mock external command khi phù hợp.


# 41. INTEGRATION TEST

Nếu máy development có:

git
docker
node

có thể chạy optional integration tests.

Nhưng unit tests không được phụ thuộc Docker.


# 42. SYSTEMD DEPLOYMENT

Tạo:

deploy/mid-mcp.service


Không mặc định chạy root.

Nên chạy bằng user riêng hoặc user administrator cấu hình.


Service:

Restart=on-failure

NoNewPrivileges=true nếu không xung đột chức năng.


README phải giải thích rõ:

Docker socket permission

filesystem permission

systemctl permission

sudo


# 43. DOCKER SOCKET

README phải cảnh báo:

quyền truy cập Docker daemon có khả năng tương đương quyền root.


Không tự:

chmod 666 /var/run/docker.sock


Không tự thêm user vào docker group.


Chỉ hướng dẫn administrator quyết định.


# 44. README

README phải bao gồm:

Architecture

Installation

Configuration

Adding a project

Project permission

Running server

stdio

Streamable HTTP

Testing with MCP Inspector

Filesystem tools

Terminal tools

Docker tools

Git tools

System tools

Custom CLI commands

Security

Audit logs

Systemd deployment

Troubleshooting


# 45. NGHIỆP VỤ MẪU

MCP sau khi hoàn thành phải hỗ trợ các workflow kiểu:


WORKFLOW 1

User:

"Kiểm tra project Odoo xem module attendance đang lỗi gì."


AI:

list_projects

search_project_text

read_project_file

docker_compose_ps

docker_compose_logs

odoo_recent_errors


Sau đó AI có đủ context để phân tích.


WORKFLOW 2

User:

"Sửa lỗi module attendance."


AI:

git_status

read_project_file

patch_project_file

run_project_command:
python syntax check

hoặc:

odoo upgrade module

docker logs


AI có thể tự edit -> test -> đọc log -> sửa tiếp.


WORKFLOW 3

User:

"Build project web."


AI:

project_info

read package.json

run:

npm ci

npm run build


Nếu lỗi:

đọc output

search source

patch file

build lại.


WORKFLOW 4

User:

"Kiểm tra vì sao Docker container bị restart."


AI:

docker_inspect

docker_logs

docker_stats

system_info

memory_info


WORKFLOW 5

User:

"Kiểm tra route của server."


AI:

network_routes

network_interfaces

run_server_command nếu cần


WORKFLOW 6

User:

"Kiểm tra WireGuard."


AI có thể dùng:

wg show

ip addr

ip route

ping


WORKFLOW 7

User:

"Sửa file docker-compose rồi restart Odoo."


Nếu permission cho phép:

read_project_file

patch_project_file

docker compose config

docker compose up -d

docker logs


# 46. DESIGN PHILOSOPHY

Đây không phải monitoring MCP.

Đây là:

AI DEVELOPMENT + SERVER ADMINISTRATION MCP.


Nó phải cho phép AI thực sự:

READ

EDIT

EXECUTE

TEST

BUILD

DEBUG

INSPECT

RESTART

VERIFY


nhưng chỉ trong boundary do administrator cấu hình.


Mục tiêu:

POWERFUL nhưng CONTROLLED.


Không bó MCP tới read-only.


Không bó terminal quá mức đến mức coding agent không thể làm việc.


Thay vào đó:

- Project isolation
- Permission system
- command policy
- audit log
- path validation
- secret redaction

là lớp kiểm soát chính.


# 47. KHÔNG TẠO MỘT TOOL KHỔNG LỒ

Không tạo:

do_everything()


Mỗi capability nên rõ ràng.


Tuy nhiên vẫn phải có generic:

run_project_command()

vì coding agent cần chạy các command thực tế.


Dedicated tools dùng cho:

filesystem
Git
Docker
systemd
system status


Generic terminal dùng cho các tình huống chưa có dedicated tool.


# 48. CÁCH THỰC HIỆN TASK

Bạn KHÔNG chỉ giải thích cách làm.

Bạn phải trực tiếp build project trong workspace hiện tại.


Thứ tự:

1. Kiểm tra OS.
2. Kiểm tra Python.
3. Kiểm tra MCP SDK hiện tại.
4. Xác nhận APIs của phiên bản MCP SDK đang cài.
5. Khởi tạo project.
6. Tạo pyproject.toml.
7. Tạo package structure.
8. Implement config.
9. Implement ProjectManager.
10. Implement security layer.
11. Implement permission layer.
12. Implement command executor.
13. Implement filesystem tools.
14. Implement terminal tools.
15. Implement search tools.
16. Implement Git tools.
17. Implement Docker tools.
18. Implement system tools.
19. Implement networking tools.
20. Implement systemd/log tools.
21. Implement Odoo helpers.
22. Implement custom project command.
23. Register MCP tools.
24. Viết tests.
25. Chạy pytest.
26. Fix lỗi.
27. Chạy lint/import check.
28. Start MCP Server.
29. Verify tool discovery.
30. Test một project sandbox.
31. Viết README.
32. Tạo systemd unit.
33. Security review.
34. Báo cáo kết quả.


Không dừng ở skeleton.


Không tạo TODO cho core feature.


Không chỉ output code trong chat nếu bạn có quyền tạo file.

Hãy thực sự tạo project.


# 49. KHI GẶP VẤN ĐỀ

Không hỏi user những câu có thể tự giải quyết.


Nếu thiếu:

Docker

Node.js

ripgrep


hãy:

- graceful degradation
- báo dependency missing
- tiếp tục build các phần khác


Không tự cài package hệ thống bằng sudo nếu chưa được phép.


# 50. DEFINITION OF DONE

Project chỉ hoàn thành khi:


MCP Server start được.

list_projects hoạt động.

File list/read/write hoạt động.

File patch hoạt động.

Path isolation hoạt động.

Terminal project hoạt động.

Command timeout hoạt động.

CLI allow/deny policy hoạt động.

Git tools hoạt động.

Docker read tools hoạt động nếu Docker available.

Docker action tools obey permissions.

System tools hoạt động.

Network tools hoạt động.

Logs hoạt động.

Custom project commands hoạt động.

Secret redaction hoạt động.

Audit logging hoạt động.

Tests security pass.

Server mặc định bind localhost.

README đầy đủ.

config.example.yaml đầy đủ.

systemd service được cung cấp.


# 51. BÁO CÁO CUỐI

Sau khi hoàn thành hãy báo:


1. Project structure.

2. MCP SDK/version sử dụng.

3. Danh sách toàn bộ MCP tools.

4. Configuration model.

5. Project permission model.

6. Terminal permission model.

7. File safety mechanism.

8. Docker capabilities.

9. Git capabilities.

10. System/server capabilities.

11. Odoo capabilities.

12. Tests đã chạy.

13. Test results.

14. Cách start MCP.

15. Cách dùng MCP Inspector.

16. Ví dụ khai báo project mới.

17. Security considerations.

18. Những giới hạn hiện tại.

19. Những đề xuất cho V2.


Quan trọng nhất:

Hãy thiết kế MID Project & System MCP như một backend dành cho AI coding/system-administration agent thực tế.

AI phải có đủ khả năng để:

đọc source → hiểu lỗi → sửa source → chạy command → build/test → đọc log → sửa tiếp → verify kết quả.

Đồng thời AI chỉ được hoạt động trong những project, command và system capability mà administrator đã chủ động cấp quyền.