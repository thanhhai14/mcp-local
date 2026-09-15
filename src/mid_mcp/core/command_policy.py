"""Structured, fail-closed authorization for generic project commands.

The generic terminal is deliberately treated as a capability router.  Merely
allowing an executable is not enough: interpreters, Docker, Git and package
managers all have subcommands that change the authority of the process.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from mid_mcp.config import AppConfig, ProjectConfig

from .security import SecurityError, is_sensitive_filename, project_root, resolve_project_path


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    risk_level: str = "READ"
    policy: str | None = None
    code: str | None = None


_PYTHON = re.compile(r"^(?:python|python3|python3\.\d+|pypy(?:3)?)$")
_SHELLS = {"sh", "bash", "dash", "zsh", "fish", "ksh"}
_NODE = {"node", "nodejs"}
_NETWORK = {"curl", "wget", "ssh", "scp", "sftp", "nc", "netcat", "telnet", "ftp"}
_FILE_COMMANDS = {"cat", "head", "tail", "less", "more", "ls", "find", "stat", "du", "wc", "rg", "grep", "pytest"}
_FILE_MUTATIONS = {"rm", "mv", "cp", "mkdir", "rmdir", "touch", "install", "tee", "truncate"}
_SERVICE_COMMANDS = {"systemctl", "service", "mount", "umount", "kill", "pkill", "reboot", "shutdown"}
_EXECUTION_HELPERS = {"xargs", "env", "awk", "sed", "perl", "ruby", "php", "lua", "tar", "dd"}
_GENERIC_SAFE = _FILE_COMMANDS | {"pwd", "echo", "printf", "true", "false", "date", "uname", "whoami", "which"}
_SAFE_GIT_GLOBAL = {"--no-pager"}
_GIT_READ = {"status", "diff", "log", "show", "branch", "rev-parse", "ls-files", "tag"}
_GIT_WRITE = {"add", "commit", "checkout", "switch", "restore", "reset", "stash", "merge", "rebase", "tag"}
_GIT_NETWORK = {"push", "pull", "fetch", "clone"}
_DOCKER_READ = {"ps", "ls", "images", "inspect", "logs", "stats", "info", "version", "events", "top", "port"}
_DOCKER_WRITE = {"start", "stop", "restart", "pause", "unpause", "rename", "update", "kill", "create"}
_DOCKER_DESTRUCTIVE = {"rm", "rmi", "prune"}
_COMPOSE_READ = {"ps", "logs", "config", "images", "ls", "port", "top", "version"}
_COMPOSE_WRITE = {"up", "down", "restart", "start", "stop", "build", "create", "pull", "start"}
_COMPOSE_DESTRUCTIVE = {"rm"}


class CommandPolicyEngine:
    """Authorize an argv without converting it to a shell string."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def authorize(self, project: ProjectConfig, command: list[str], cwd: Path) -> PolicyDecision:
        try:
            self._validate_argv(command)
            root = project_root(project)
            self._inside(root, cwd.resolve(strict=True), "cwd")
            executable, resolved = self.resolve_executable(command[0])
            self._allowed_executable(project, executable, command[0])
            if executable in self.config.terminal.denied_commands:
                return self._deny("COMMAND_DENIED", f"command '{executable}' is globally denied", "COMMAND_DENIED")
            if executable == "sudo" and not self.config.terminal.allow_sudo:
                return self._deny("SUDO_DISABLED", "sudo is disabled", "SUDO_DISABLED")
            if executable in _NETWORK and not project.permissions.network:
                return self._deny("NETWORK_DISABLED", f"network command '{executable}' requires network permission", "NETWORK")
            if executable in _SERVICE_COMMANDS:
                return self._deny("SERVICE_ACTION_DISABLED", f"service/system action '{executable}' is not available through generic terminal", "SERVICE_ACTION")
            if executable in _EXECUTION_HELPERS:
                return self._deny("EXECUTION_HELPER_BLOCKED", f"execution helper '{executable}' is not allowed", "EXECUTION_HELPER")

            if _PYTHON.match(executable):
                return self._python(project, command[1:], root)
            if executable in _NODE:
                return self._node(project, command[1:], root)
            if executable in _SHELLS:
                return self._shell(project, command[1:], root)
            if executable == "docker":
                return self._docker(project, command[1:], root)
            if executable == "git":
                return self._git(project, command[1:], root)
            if executable in {"npm", "npm.cmd"}:
                return self._npm(project, command[1:], root)
            if executable == "npx":
                if not (self.config.terminal.allow_npx and project.permissions.allow_npx):
                    return self._deny("NPX_DISABLED", "npx is disabled by policy", "NPX")
                self._validate_path_like_arguments(project, command[1:], root, "npx path")
                return PolicyDecision(True, risk_level="NETWORK", policy="NPX")
            if executable in _FILE_MUTATIONS:
                return self._file_mutation(project, command[1:], root, executable)
            if executable not in _GENERIC_SAFE:
                return self._deny("COMMAND_POLICY_UNKNOWN", f"no safe policy exists for executable '{executable}'", "FAIL_CLOSED")
            self._validate_file_arguments(project, command[1:], root, executable)
            return PolicyDecision(True, risk_level="EXECUTE", policy="GENERIC_EXECUTABLE")
        except SecurityError as exc:
            return self._deny(getattr(exc, "code", "PERMISSION_DENIED"), str(exc), getattr(exc, "policy", None))
        except OSError as exc:
            return self._deny("DEPENDENCY_MISSING", str(exc), "EXECUTABLE_RESOLUTION")

    def enforce(self, project: ProjectConfig, command: list[str], cwd: Path) -> PolicyDecision:
        decision = self.authorize(project, command, cwd)
        if not decision.allowed:
            raise SecurityError(decision.reason or "command denied", code=decision.code or "PERMISSION_DENIED", policy=decision.policy)
        return decision

    def resolve_executable(self, raw: str) -> tuple[str, Path]:
        if not isinstance(raw, str) or not raw:
            raise SecurityError("command executable is empty", code="INVALID_COMMAND", policy="ARGV")
        name = Path(raw).name
        controlled_dirs = [Path(item).resolve() for item in self.config.terminal.controlled_path.split(":") if item]
        trusted_roots = [*controlled_dirs, Path("/usr"), Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64")]
        if "/" in raw:
            candidate = Path(raw)
            if not candidate.is_absolute():
                raise SecurityError("relative executable paths are not permitted", code="EXECUTABLE_PATH", policy="EXECUTABLE_RESOLUTION")
            resolved = candidate.resolve(strict=True)
            if not any(self._is_under(candidate.absolute(), directory) for directory in controlled_dirs) or not any(self._is_under(resolved, directory) for directory in trusted_roots):
                raise SecurityError("executable is outside the controlled system PATH", code="EXECUTABLE_PATH", policy="EXECUTABLE_RESOLUTION")
        else:
            found = shutil.which(raw, path=self.config.terminal.controlled_path)
            if not found:
                raise SecurityError(f"executable not found in controlled PATH: {raw}", code="DEPENDENCY_MISSING", policy="EXECUTABLE_RESOLUTION")
            found_path = Path(found)
            resolved = found_path.resolve(strict=True)
            if not any(self._is_under(found_path.absolute(), directory) for directory in controlled_dirs) or not any(self._is_under(resolved, directory) for directory in trusted_roots):
                raise SecurityError("executable resolved outside the controlled system PATH", code="EXECUTABLE_PATH", policy="EXECUTABLE_RESOLUTION")
        return name, resolved

    def _allowed_executable(self, project: ProjectConfig, executable: str, raw: str) -> None:
        allowed = project.terminal.allowed_commands
        if "*" not in allowed and executable not in {Path(item).name for item in allowed}:
            raise SecurityError(f"command '{executable}' is not allowed", code="COMMAND_NOT_ALLOWLISTED", policy="EXECUTABLE_ALLOWLIST")
        if raw.startswith("./") or raw.startswith("../"):
            raise SecurityError("project-local executable paths are not permitted", code="EXECUTABLE_PATH", policy="EXECUTABLE_RESOLUTION")

    @staticmethod
    def _validate_argv(command: list[str]) -> None:
        if not command or not all(isinstance(arg, str) and arg for arg in command):
            raise SecurityError("command must be a non-empty argv list", code="INVALID_COMMAND", policy="ARGV")
        if any("\x00" in arg for arg in command):
            raise SecurityError("command contains a NUL byte", code="INVALID_COMMAND", policy="ARGV")

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _inside(self, root: Path, path: Path, label: str) -> None:
        if not self._is_under(path, root):
            raise SecurityError(f"{label} is outside the project", code="PATH_OUTSIDE_PROJECT", policy="PROJECT_ISOLATION")

    def _script(self, project: ProjectConfig, value: str, root: Path) -> None:
        if value.startswith("-"):
            raise SecurityError("interpreter script must be a project file", code="SCRIPT_PATH_REQUIRED", policy="INTERPRETER_SCRIPT")
        path = resolve_project_path(project, value, must_exist=True)
        if not path.is_file():
            raise SecurityError("interpreter target is not a file", code="SCRIPT_PATH_REQUIRED", policy="INTERPRETER_SCRIPT")
        if is_sensitive_filename(self.config, value) or is_sensitive_filename(self.config, path):
            raise SecurityError("sensitive files cannot be executed", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
        self._inside(root, path, "script")

    def _python(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("INTERACTIVE_INTERPRETER_BLOCKED", "interactive Python execution is not allowed", "INTERPRETER_INTERACTIVE_EXECUTION")
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in {"-c", "--command", "-"} or arg.startswith("-c") or arg.startswith("--command="):
                return self._deny("INLINE_INTERPRETER_BLOCKED", "Python inline or stdin execution is not allowed", "INTERPRETER_INLINE_EXECUTION")
            if arg == "-m":
                if index + 1 >= len(args):
                    return self._deny("MODULE_REQUIRED", "python -m requires an allowlisted module", "PYTHON_MODULE")
                module = args[index + 1]
                if module not in set(project.terminal.allowed_python_modules):
                    return self._deny("PYTHON_MODULE_DENIED", f"python module '{module}' is not allowlisted", "PYTHON_MODULE")
                if module == "pytest":
                    self._validate_pytest_arguments(project, args[index + 2:], root)
                self._validate_path_like_arguments(project, args[index + 2:], root, "python module")
                return PolicyDecision(True, risk_level="EXECUTE", policy="PYTHON_MODULE")
            if arg == "--":
                if index + 1 >= len(args):
                    return self._deny("SCRIPT_PATH_REQUIRED", "Python script is required", "INTERPRETER_SCRIPT")
                self._script(project, args[index + 1], root)
                return PolicyDecision(True, risk_level="EXECUTE", policy="PYTHON_SCRIPT")
            if arg.startswith("-"):
                if arg in {"--version", "-V", "-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u"}:
                    index += 1
                    continue
                return self._deny("PYTHON_OPTION_DENIED", f"unsupported Python option '{arg}'", "PYTHON_OPTIONS")
            self._script(project, arg, root)
            return PolicyDecision(True, risk_level="EXECUTE", policy="PYTHON_SCRIPT")
        return PolicyDecision(True, risk_level="EXECUTE", policy="PYTHON")

    def _node(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("INTERACTIVE_INTERPRETER_BLOCKED", "interactive Node execution is not allowed", "INTERPRETER_INTERACTIVE_EXECUTION")
        blocked = {"-e", "--eval", "-p", "--print", "--check", "-r", "--require", "--import", "--loader", "--experimental-loader"}
        if any(arg in blocked or arg.startswith("--eval=") or arg.startswith("--require=") for arg in args):
            return self._deny("INLINE_INTERPRETER_BLOCKED", "Node inline/eval/loader execution is not allowed", "INTERPRETER_INLINE_EXECUTION")
        for arg in args:
            if arg == "--":
                continue
            if arg.startswith("-"):
                if arg in {"--version", "-v", "--help", "--no-warnings", "--trace-warnings"}:
                    continue
                return self._deny("NODE_OPTION_DENIED", f"unsupported Node option '{arg}'", "NODE_OPTIONS")
            self._script(project, arg, root)
            return PolicyDecision(True, risk_level="EXECUTE", policy="NODE_SCRIPT")
        return PolicyDecision(True, risk_level="EXECUTE", policy="NODE")

    def _shell(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("SHELL_SCRIPT_REQUIRED", "interactive shell execution is not allowed", "SHELL")
        if any(arg in {"-c", "--command", "-i", "--login"} or arg.startswith("-c") for arg in args):
            return self._deny("SHELL_INLINE_BLOCKED", "shell command-string execution is not allowed", "SHELL_INLINE_EXECUTION")
        for arg in args:
            if arg == "--":
                continue
            if arg.startswith("-"):
                if arg in {"-e", "-u", "-x", "-f", "--noprofile", "--norc"}:
                    continue
                return self._deny("SHELL_OPTION_DENIED", f"unsupported shell option '{arg}'", "SHELL_OPTIONS")
            self._script(project, arg, root)
            return PolicyDecision(True, risk_level="EXECUTE", policy="SHELL_SCRIPT")
        return self._deny("SHELL_SCRIPT_REQUIRED", "shell script is required", "SHELL")

    def _docker(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("DOCKER_SUBCOMMAND_REQUIRED", "Docker subcommand is required", "DOCKER")
        if args[0].startswith("-"):
            return self._deny("DOCKER_GLOBAL_OPTION_DENIED", "unsupported Docker global options are denied", "DOCKER_OPTIONS")
        if args[0] == "compose":
            return self._compose(project, args[1:], root)
        action_args = args[1:]
        group = args[0]
        action = group
        if group in {"container", "image", "volume", "network", "system", "builder"}:
            if not action_args:
                return self._deny("DOCKER_SUBCOMMAND_REQUIRED", "Docker resource action is required", "DOCKER")
            action = action_args[0]
        if action == "exec":
            # The generic terminal cannot inspect or constrain the command
            # executed inside a container. Keep this for a future dedicated,
            # sandboxed tool instead of making it an escape hatch.
            return self._deny("DOCKER_EXEC_DISABLED", "docker exec is unavailable in the generic terminal", "DOCKER_EXEC")
        if action == "run":
            if not project.permissions.docker_run:
                return self._deny("DOCKER_RUN_DISABLED", "docker run requires docker_run permission", "DOCKER_RUN")
            if self._has_dangerous_container_options(args):
                return self._deny("DOCKER_RUN_OPTION_DENIED", "privileged Docker run options are denied", "DOCKER_RUN")
            return PolicyDecision(True, risk_level="PRIVILEGED", policy="DOCKER_RUN")
        if action in _DOCKER_DESTRUCTIVE or (group in {"container", "image", "volume", "network", "system", "builder"} and action in _DOCKER_DESTRUCTIVE):
            return PolicyDecision(True, risk_level="DESTRUCTIVE", policy="DOCKER_DESTRUCTIVE") if project.permissions.docker_destructive else self._deny("DOCKER_DESTRUCTIVE_DISABLED", "Docker destructive action requires docker_destructive permission", "DOCKER_DESTRUCTIVE")
        if action in _DOCKER_WRITE:
            return PolicyDecision(True, risk_level="SERVICE_ACTION", policy="DOCKER_WRITE") if project.permissions.docker_write else self._deny("DOCKER_WRITE_DISABLED", "Docker write action requires docker_write permission", "DOCKER_WRITE")
        if action in _DOCKER_READ:
            self._validate_file_arguments(project, args[1:], root, "docker")
            return PolicyDecision(True, risk_level="READ", policy="DOCKER_READ") if project.permissions.docker_read else self._deny("DOCKER_READ_DISABLED", "Docker read action requires docker_read permission", "DOCKER_READ")
        return self._deny("DOCKER_ACTION_UNKNOWN", f"unsupported Docker action '{action}'", "DOCKER_ACTION")

    def _compose(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("COMPOSE_SUBCOMMAND_REQUIRED", "Docker Compose action is required", "DOCKER_COMPOSE")
        index = 0
        action = None
        while index < len(args):
            arg = args[index]
            if arg in {"-f", "--file", "--project-directory", "--env-file"}:
                if index + 1 >= len(args):
                    return self._deny("COMPOSE_PATH_REQUIRED", f"{arg} requires a path", "DOCKER_COMPOSE_PATH")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=arg != "--project-directory"), "compose path")
                index += 2
                continue
            if any(arg.startswith(item + "=") for item in {"--file", "--project-directory", "--env-file"}):
                option, value = arg.split("=", 1)
                self._inside(root, resolve_project_path(project, value, must_exist=option != "--project-directory"), "compose path")
                index += 1
                continue
            if arg.startswith("-"):
                if arg in {"--ansi", "--progress", "--profile", "--parallel", "--all-resources", "--dry-run"} or arg.startswith("--profile="):
                    index += 2 if arg in {"--ansi", "--progress", "--profile"} else 1
                    continue
                return self._deny("COMPOSE_OPTION_DENIED", f"unsupported Docker Compose option '{arg}'", "DOCKER_COMPOSE_OPTIONS")
            action = arg
            break
        if action is None:
            return self._deny("COMPOSE_SUBCOMMAND_REQUIRED", "Docker Compose action is required", "DOCKER_COMPOSE")
        remaining = args[index + 1:]
        self._validate_compose_paths(project, remaining, root)
        if action == "exec":
            return self._deny("DOCKER_EXEC_DISABLED", "docker compose exec is unavailable in the generic terminal", "DOCKER_EXEC")
        if action == "run":
            if not project.permissions.docker_run:
                return self._deny("DOCKER_RUN_DISABLED", "docker compose run requires docker_run permission", "DOCKER_RUN")
            if self._has_dangerous_container_options(remaining):
                return self._deny("DOCKER_RUN_OPTION_DENIED", "privileged Docker Compose run options are denied", "DOCKER_RUN")
            return PolicyDecision(True, risk_level="PRIVILEGED", policy="DOCKER_RUN")
        if action == "down" and any(item in {"-v", "--volumes"} for item in remaining):
            return PolicyDecision(True, risk_level="DESTRUCTIVE", policy="DOCKER_DESTRUCTIVE") if project.permissions.docker_destructive else self._deny("DOCKER_DESTRUCTIVE_DISABLED", "compose down --volumes requires docker_destructive permission", "DOCKER_DESTRUCTIVE")
        if action in _COMPOSE_DESTRUCTIVE:
            return PolicyDecision(True, risk_level="DESTRUCTIVE", policy="DOCKER_DESTRUCTIVE") if project.permissions.docker_destructive else self._deny("DOCKER_DESTRUCTIVE_DISABLED", "Docker Compose destructive action requires docker_destructive permission", "DOCKER_DESTRUCTIVE")
        if action in _COMPOSE_WRITE:
            return PolicyDecision(True, risk_level="SERVICE_ACTION", policy="DOCKER_WRITE") if project.permissions.docker_write else self._deny("DOCKER_WRITE_DISABLED", "Docker Compose write action requires docker_write permission", "DOCKER_WRITE")
        if action in _COMPOSE_READ:
            return PolicyDecision(True, risk_level="READ", policy="DOCKER_READ") if project.permissions.docker_read else self._deny("DOCKER_READ_DISABLED", "Docker Compose read action requires docker_read permission", "DOCKER_READ")
        return self._deny("DOCKER_COMPOSE_ACTION_UNKNOWN", f"unsupported Docker Compose action '{action}'", "DOCKER_COMPOSE_ACTION")

    def _git(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("GIT_SUBCOMMAND_REQUIRED", "Git subcommand is required", "GIT")
        index = 0
        while index < len(args) and args[index].startswith("-"):
            arg = args[index]
            if arg == "-C":
                if index + 1 >= len(args):
                    return self._deny("GIT_PATH_REQUIRED", "git -C requires a path", "GIT_OPTIONS")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=True), "git cwd")
                index += 2
                continue
            if arg in _SAFE_GIT_GLOBAL:
                index += 1
                continue
            if arg == "--":
                index += 1
                break
            if arg == "-c" or arg.startswith("-c") or arg in {"--config", "--config-env", "--exec-path", "--upload-pack", "--receive-pack", "--git-dir", "--work-tree"} or any(arg.startswith(item + "=") for item in {"--config", "--config-env", "--exec-path", "--upload-pack", "--receive-pack", "--git-dir", "--work-tree"}):
                return self._deny("GIT_EXTERNAL_ESCAPE", f"Git option '{arg}' is not allowed", "GIT_OPTIONS")
            return self._deny("GIT_OPTION_DENIED", f"unsupported Git global option '{arg}'", "GIT_OPTIONS")
        if index >= len(args):
            return self._deny("GIT_SUBCOMMAND_REQUIRED", "Git subcommand is required", "GIT")
        action = args[index]
        tail = args[index + 1:]
        for item in tail:
            if item.startswith(":(exclude)"):
                continue
            git_path = item.rsplit(":", 1)[-1] if ":" in item else item
            if not item.startswith("-") and is_sensitive_filename(self.config, git_path):
                return self._deny("SENSITIVE_FILE_DENIED", "sensitive file content is not available", "SENSITIVE_FILES")
        if any(item in {"-c", "--config", "--config-env", "--exec-path", "--upload-pack", "--receive-pack", "--git-dir", "--work-tree", "--no-index", "--output", "-o"} or item.startswith(("--config=", "--config-env=", "--exec-path=", "--upload-pack=", "--receive-pack=", "--git-dir=", "--work-tree=", "--output=")) or (item.startswith("-o") and not item.startswith("--")) for item in tail):
            return self._deny("GIT_EXTERNAL_ESCAPE", "Git external helper options are not allowed", "GIT_OPTIONS")
        self._validate_git_paths(project, tail, root)
        if action in _GIT_NETWORK:
            return PolicyDecision(True, risk_level="NETWORK", policy="GIT_NETWORK") if project.permissions.git_network else self._deny("GIT_NETWORK_DISABLED", "Git network action requires git_network permission", "GIT_NETWORK")
        if action == "branch":
            read_flags = {"-a", "-r", "--all", "--remotes", "--list", "--show-current", "-v", "-vv", "--verbose", "--contains", "--merged", "--no-merged", "--points-at"}
            branch_mutation = any(item in {"-d", "-D", "--delete", "--move", "-m", "-M", "-c", "-C", "--copy", "--edit-description", "--set-upstream-to", "-u"} for item in tail)
            branch_mutation = branch_mutation or any(not item.startswith("-") for item in tail)
            if branch_mutation:
                return PolicyDecision(True, risk_level="WRITE", policy="GIT_WRITE") if project.permissions.git_write else self._deny("GIT_WRITE_DISABLED", "Git branch mutation requires git_write permission", "GIT_WRITE")
            if all(item in read_flags or item.startswith(("--contains=", "--merged=", "--no-merged=", "--points-at=")) for item in tail):
                return PolicyDecision(True, risk_level="READ", policy="GIT_READ") if project.permissions.git_read else self._deny("GIT_READ_DISABLED", "Git read action requires git_read permission", "GIT_READ")
            return self._deny("GIT_OPTION_DENIED", "unsupported git branch option", "GIT_OPTIONS")
        if action == "tag":
            tag_read = not any(not item.startswith("-") for item in tail) and not any(item in {"-a", "-s", "-u", "-f", "-d", "--annotate", "--sign", "--delete", "--force"} for item in tail)
            if tag_read:
                return PolicyDecision(True, risk_level="READ", policy="GIT_READ") if project.permissions.git_read else self._deny("GIT_READ_DISABLED", "Git read action requires git_read permission", "GIT_READ")
            return PolicyDecision(True, risk_level="WRITE", policy="GIT_WRITE") if project.permissions.git_write else self._deny("GIT_WRITE_DISABLED", "Git tag mutation requires git_write permission", "GIT_WRITE")
        if action == "remote" and tail and tail[0] in {"add", "remove", "rename", "set-url", "set-branches", "prune"}:
            return PolicyDecision(True, risk_level="NETWORK", policy="GIT_NETWORK") if project.permissions.git_network else self._deny("GIT_NETWORK_DISABLED", "Git remote mutation requires git_network permission", "GIT_NETWORK")
        if action in _GIT_WRITE:
            return PolicyDecision(True, risk_level="WRITE", policy="GIT_WRITE") if project.permissions.git_write else self._deny("GIT_WRITE_DISABLED", "Git write action requires git_write permission", "GIT_WRITE")
        if action in _GIT_READ or action == "remote":
            return PolicyDecision(True, risk_level="READ", policy="GIT_READ") if project.permissions.git_read else self._deny("GIT_READ_DISABLED", "Git read action requires git_read permission", "GIT_READ")
        return self._deny("GIT_ACTION_UNKNOWN", f"unsupported Git action '{action}'", "GIT_ACTION")

    def _npm(self, project: ProjectConfig, args: list[str], root: Path) -> PolicyDecision:
        if not args:
            return self._deny("NPM_SUBCOMMAND_REQUIRED", "npm subcommand is required", "NPM")
        if args[0] in {"--version", "-v", "version", "help"}:
            return PolicyDecision(True, risk_level="READ", policy="NPM_READ")
        for position, item in enumerate(args):
            if item == "--prefix":
                if position + 1 >= len(args):
                    return self._deny("NPM_PATH_REQUIRED", "npm --prefix requires a path", "NPM_OPTIONS")
                self._inside(root, resolve_project_path(project, args[position + 1], must_exist=True), "npm prefix")
            elif item.startswith("--prefix="):
                self._inside(root, resolve_project_path(project, item.split("=", 1)[1], must_exist=True), "npm prefix")
        self._validate_npm_options(project, args, root)
        index = 0
        while index < len(args):
            if args[index] == "--prefix":
                if index + 1 >= len(args):
                    return self._deny("NPM_PATH_REQUIRED", "npm --prefix requires a path", "NPM_OPTIONS")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=True), "npm prefix")
                index += 2
                continue
            if args[index].startswith("--prefix="):
                self._inside(root, resolve_project_path(project, args[index].split("=", 1)[1], must_exist=True), "npm prefix")
                index += 1
                continue
            if args[index] in {"--cache", "--userconfig", "--globalconfig", "--pack-destination", "--logs-dir"}:
                if index + 1 >= len(args):
                    return self._deny("NPM_PATH_REQUIRED", f"{args[index]} requires a path", "NPM_OPTIONS")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=False), "npm path")
                index += 2
                continue
            if any(args[index].startswith(option + "=") for option in {"--cache", "--userconfig", "--globalconfig", "--pack-destination", "--logs-dir"}):
                self._inside(root, resolve_project_path(project, args[index].split("=", 1)[1], must_exist=False), "npm path")
                index += 1
                continue
            if args[index].startswith("-"):
                return self._deny("NPM_OPTION_DENIED", f"unsupported npm option '{args[index]}'", "NPM_OPTIONS")
            break
        if index >= len(args):
            return self._deny("NPM_SUBCOMMAND_REQUIRED", "npm subcommand is required", "NPM")
        action = args[index]
        if action in {"exec", "x"}:
            return PolicyDecision(True, risk_level="PRIVILEGED", policy="NPM_EXEC") if project.permissions.npm_exec else self._deny("NPM_EXEC_DISABLED", "npm exec requires npm_exec permission", "NPM_EXEC")
        if action == "run" or action in {"test", "ci", "install", "uninstall", "update", "pack"}:
            return PolicyDecision(True, risk_level="EXECUTE", policy="NPM_SCRIPT")
        if action in {"--version", "-v", "version", "help", "audit", "ls", "list", "outdated"}:
            return PolicyDecision(True, risk_level="READ", policy="NPM_READ")
        return self._deny("NPM_ACTION_UNKNOWN", f"unsupported npm action '{action}'", "NPM_ACTION")

    def _validate_npm_options(self, project: ProjectConfig, args: list[str], root: Path) -> None:
        path_options = {"--cache", "--userconfig", "--globalconfig", "--pack-destination", "--logs-dir"}
        blocked = {"-g", "--global", "--global-style", "--script-shell"}
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in blocked or any(arg.startswith(option + "=") for option in blocked if option.startswith("--")):
                raise SecurityError(f"npm option '{arg}' is not allowed", code="NPM_OPTION_DENIED", policy="NPM_OPTIONS")
            if arg in path_options:
                if index + 1 >= len(args):
                    raise SecurityError(f"{arg} requires a path", code="NPM_PATH_REQUIRED", policy="NPM_OPTIONS")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=False), "npm path")
                index += 2
                continue
            if any(arg.startswith(option + "=") for option in path_options):
                self._inside(root, resolve_project_path(project, arg.split("=", 1)[1], must_exist=False), "npm path")
            index += 1

    def _validate_file_arguments(self, project: ProjectConfig, args: list[str], root: Path, executable: str) -> None:
        if executable not in _FILE_COMMANDS:
            return
        for arg in args:
            if arg == "--" or arg.startswith("-"):
                if executable == "find" and arg in {"-exec", "-execdir", "-delete", "-ok", "-okdir", "--exec"}:
                    raise SecurityError("find execution/deletion predicates are not allowed", code="EXECUTION_HELPER_BLOCKED", policy="FILE_COMMAND")
                if executable == "rg" and (arg in {"--pre", "--pre-glob"} or arg.startswith("--pre=")):
                    raise SecurityError("rg external preprocessors are not allowed", code="EXECUTION_HELPER_BLOCKED", policy="FILE_COMMAND")
                if executable == "pytest":
                    self._validate_pytest_option(arg)
                if "=" in arg:
                    self._validate_option_path(project, arg.split("=", 1)[1], root, "command option path")
                continue
            looks_like_path = arg.startswith(("/", "./", "../", "~")) or ".." in Path(arg).parts or (root / arg).exists()
            if looks_like_path:
                resolved = resolve_project_path(project, arg, must_exist=True)
                if is_sensitive_filename(self.config, arg) or is_sensitive_filename(self.config, resolved):
                    raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
                self._inside(root, resolved, "command path")

    def _validate_pytest_arguments(self, project: ProjectConfig, args: list[str], root: Path) -> None:
        for arg in args:
            if arg.startswith("-"):
                self._validate_pytest_option(arg)
        self._validate_path_like_arguments(project, args, root, "pytest path")

    @staticmethod
    def _validate_pytest_option(arg: str) -> None:
        if arg in {"-p", "--pyargs", "--trace-config", "--pdb", "--trace", "-o", "--override-ini"} or arg.startswith(("--pdbcls=", "--override-ini=")):
            raise SecurityError(f"pytest option '{arg}' is not allowed", code="EXECUTION_HELPER_BLOCKED", policy="PYTEST_OPTIONS")

    def _validate_path_like_arguments(self, project: ProjectConfig, args: list[str], root: Path, label: str) -> None:
        for arg in args:
            if arg.startswith("-") and "=" in arg:
                self._validate_option_path(project, arg.split("=", 1)[1], root, label)
                continue
            if arg.startswith(("/", "./", "../", "~")) or ".." in Path(arg).parts or (root / arg).exists():
                resolved = resolve_project_path(project, arg, must_exist=True)
                if is_sensitive_filename(self.config, arg) or is_sensitive_filename(self.config, resolved):
                    raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
                self._inside(root, resolved, label)

    def _validate_option_path(self, project: ProjectConfig, value: str, root: Path, label: str) -> None:
        if value.startswith(("/", "./", "../", "~")) or ".." in Path(value).parts or (root / value).exists():
            resolved = resolve_project_path(project, value, must_exist=True)
            if is_sensitive_filename(self.config, value) or is_sensitive_filename(self.config, resolved):
                raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
            self._inside(root, resolved, label)

    def _validate_compose_paths(self, project: ProjectConfig, args: list[str], root: Path) -> None:
        path_options = {"-f", "--file", "--project-directory", "--env-file"}
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in path_options:
                if index + 1 >= len(args):
                    raise SecurityError(f"{arg} requires a path", code="COMPOSE_PATH_REQUIRED", policy="DOCKER_COMPOSE_PATH")
                self._inside(root, resolve_project_path(project, args[index + 1], must_exist=arg != "--project-directory"), "compose path")
                index += 2
                continue
            if any(arg.startswith(option + "=") for option in path_options):
                option, value = arg.split("=", 1)
                self._inside(root, resolve_project_path(project, value, must_exist=option != "--project-directory"), "compose path")
            index += 1

    def _validate_git_paths(self, project: ProjectConfig, args: list[str], root: Path) -> None:
        for arg in args:
            value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
            if value.startswith(("/", "./", "../", "~")) or ".." in Path(value).parts:
                resolved = resolve_project_path(project, value, must_exist=False)
                if is_sensitive_filename(self.config, value) or is_sensitive_filename(self.config, resolved):
                    raise SecurityError("sensitive file content is not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
                self._inside(root, resolved, "git path")

    def _file_mutation(self, project: ProjectConfig, args: list[str], root: Path, executable: str) -> PolicyDecision:
        permission = "delete" if executable in {"rm", "rmdir", "truncate"} else "write"
        if not getattr(project.permissions, permission, False):
            return self._deny("PERMISSION_DENIED", f"{executable} requires project {permission} permission", permission)
        if not args:
            return self._deny("FILE_PATH_REQUIRED", f"{executable} requires a project path", "FILE_MUTATION")
        for arg in args:
            if arg == "--" or arg.startswith("-"):
                if "=" in arg:
                    self._validate_option_path(project, arg.split("=", 1)[1], root, "command path")
                continue
            resolved = resolve_project_path(project, arg, must_exist=executable in {"rm", "rmdir", "truncate"})
            if is_sensitive_filename(self.config, arg) or is_sensitive_filename(self.config, resolved):
                raise SecurityError("sensitive file operations are not available", code="SENSITIVE_FILE_DENIED", policy="SENSITIVE_FILES")
            self._inside(root, resolved, "command path")
        return PolicyDecision(True, risk_level="DESTRUCTIVE" if permission == "delete" else "WRITE", policy="FILE_MUTATION")

    @staticmethod
    def _has_dangerous_container_options(args: list[str]) -> bool:
        exact = {"-v", "--volume", "--mount", "--privileged", "--pid=host", "--network=host", "--device"}
        prefixes = ("--volume=", "--mount=", "--pid=", "--network=", "--device=")
        return any(arg in exact or arg.startswith(prefixes) for arg in args)

    @staticmethod
    def _deny(code: str, reason: str, policy: str) -> PolicyDecision:
        return PolicyDecision(False, reason=reason, risk_level="DENY", policy=policy, code=code)
