from __future__ import annotations

from dataclasses import dataclass
import posixpath
import queue
import subprocess
import threading
import time

from .docker_workspace import (
    DockerSandboxConfig,
    DockerSessionContainerManager,
)
from .execution import ExecutionResult, PythonExecutor, SandboxPolicy, WorkspaceManager

_BLOCKED_EXEC_BINARIES = frozenset({"bash", "cmd", "powershell", "pwsh", "rm", "sh"})
_ALLOWED_GIT_SUBCOMMANDS = frozenset(
    {"diff", "log", "ls-files", "rev-parse", "show", "status"}
)
_COMMAND_TIER_ORDER = {"read_only": 0, "test": 1, "package": 2}
_COMMAND_TIER_BY_EXECUTABLE = {
    "cat": "read_only",
    "echo": "read_only",
    "find": "read_only",
    "git": "read_only",
    "grep": "read_only",
    "head": "read_only",
    "ls": "read_only",
    "pwd": "read_only",
    "tail": "read_only",
    "wc": "read_only",
    "python": "test",
    "python3": "test",
    "pytest": "test",
    "pip": "package",
    "pip3": "package",
    "uv": "package",
}
_MAX_EXEC_ARGS = 24
_MAX_ARG_CHARS = 2048


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    session_id: str
    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    files: list[str]
    sandbox: dict[str, object]


class DockerSandboxExecutor:
    def __init__(
        self,
        local_executor: PythonExecutor,
        workspace_manager: WorkspaceManager,
        policy: SandboxPolicy,
        config: DockerSandboxConfig,
    ) -> None:
        self.local_executor = local_executor
        self.workspace_manager = workspace_manager
        self.policy = policy
        self.config = config
        self.container_manager = DockerSessionContainerManager(
            workspace_manager=workspace_manager,
            config=config,
        )

    def availability(self) -> tuple[bool, str]:
        return self.container_manager.availability()

    def session_payload(self, session_id: str) -> dict[str, object]:
        payload = self.container_manager.status(session_id).payload()
        payload["docker"] = self.config.payload()
        return payload

    def reset_session(self, session_id: str) -> dict[str, object]:
        payload = self.container_manager.destroy_container(session_id)
        payload["docker"] = self.config.payload()
        return payload

    def execute(self, *, session_id: str, code: str) -> ExecutionResult:
        workspace = self.workspace_manager.workspace_for(session_id)
        try:
            container = self.container_manager.ensure_container(session_id)
        except RuntimeError as exc:
            inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
            return ExecutionResult(
                session_id=session_id,
                returncode=127,
                stdout="",
                stderr=str(exc),
                files=inspection.files,
                timed_out=False,
                sandbox={
                    "backend": "docker",
                    "requested_backend": self.config.backend_preference,
                    "fallback": {"used": False, "reason": ""},
                    "blocked": True,
                    "violations": [str(exc)],
                    "policy": self.policy.payload(),
                    "docker": self.config.payload(),
                    "container": self.container_manager.status(session_id).payload(),
                },
            )

        payload_path, bootstrap_path, _, _ = self.local_executor.prepare_runtime_files(
            workspace=workspace,
            code=code,
            runtime_workspace=self.config.workdir,
        )
        try:
            completed = subprocess.run(
                self.container_manager.build_exec_command(
                    session_id=session_id,
                    argv=[
                        "python",
                        "-I",
                        "-S",
                        "-B",
                        f"{self.config.workdir.rstrip('/') or '/workspace'}/{bootstrap_path.name}",
                    ],
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.policy.timeout_seconds + 10,
                creationflags=_creation_flags(),
            )
            returncode = completed.returncode
            stdout = _clip_output(completed.stdout, self.policy.max_output_chars)
            stderr = _clip_output(
                _clean_docker_stderr(completed.stderr, returncode),
                self.policy.max_output_chars,
            )
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = _clip_output(exc.stdout or "", self.policy.max_output_chars)
            stderr = _clip_output(
                f"{exc.stderr or ''}\nContainer execution timed out.",
                self.policy.max_output_chars,
            )
            timed_out = True
        finally:
            self.local_executor.cleanup_runtime_files(payload_path, bootstrap_path)

        inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
        violations = list(inspection.violations)
        if timed_out:
            violations.append("Container execution timed out.")
        blocked = bool(violations) or returncode in {124, 126}
        if inspection.violations and returncode == 0:
            returncode = 125
        sandbox = {
            "backend": "docker",
            "requested_backend": self.config.backend_preference,
            "fallback": {"used": False, "reason": ""},
            "blocked": blocked,
            "violations": violations,
            "policy": self.policy.payload(),
            "docker": self.config.payload(),
            "container": container.payload(),
        }
        return ExecutionResult(
            session_id=session_id,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            files=inspection.files,
            timed_out=timed_out,
            sandbox=sandbox,
        )

    def execute_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str,
        timeout_seconds: float,
        requested_backend: str,
        command_policy: dict[str, object],
    ) -> CommandExecutionResult:
        workspace = self.workspace_manager.workspace_for(session_id)
        try:
            container = self.container_manager.ensure_container(session_id)
        except RuntimeError as exc:
            inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
            return CommandExecutionResult(
                session_id=session_id,
                command=command,
                cwd=cwd,
                returncode=127,
                stdout="",
                stderr=str(exc),
                timed_out=False,
                files=inspection.files,
                sandbox={
                    "backend": "docker",
                    "requested_backend": requested_backend,
                    "fallback": {"used": False, "reason": ""},
                    "blocked": True,
                    "violations": [str(exc)],
                    "policy": self.policy.payload(),
                    "command_policy": command_policy,
                    "docker": self.config.payload(),
                    "container": self.container_manager.status(session_id).payload(),
                },
            )

        try:
            completed = subprocess.run(
                self.container_manager.build_exec_command(
                    session_id=session_id,
                    argv=command,
                    cwd=cwd,
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_seconds + 10,
                creationflags=_creation_flags(),
            )
            returncode = completed.returncode
            stdout = _clip_output(completed.stdout, self.policy.max_output_chars)
            stderr = _clip_output(
                _clean_docker_stderr(completed.stderr, returncode),
                self.policy.max_output_chars,
            )
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = _clip_output(exc.stdout or "", self.policy.max_output_chars)
            stderr = _clip_output(
                f"{exc.stderr or ''}\nCommand execution timed out.",
                self.policy.max_output_chars,
            )
            timed_out = True

        inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
        violations = list(inspection.violations)
        if timed_out:
            violations.append("Command execution timed out.")
        blocked = bool(violations)
        if inspection.violations and returncode == 0:
            returncode = 125
        return CommandExecutionResult(
            session_id=session_id,
            command=command,
            cwd=cwd,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            files=inspection.files,
            sandbox={
                "backend": "docker",
                "requested_backend": requested_backend,
                "fallback": {"used": False, "reason": ""},
                "blocked": blocked,
                "violations": violations,
                "policy": self.policy.payload(),
                "command_policy": command_policy,
                "docker": self.config.payload(),
                "container": container.payload(),
            },
        )

    def stream_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str,
        timeout_seconds: float,
        requested_backend: str,
        command_policy: dict[str, object],
    ):
        try:
            container = self.container_manager.ensure_container(session_id)
        except RuntimeError as exc:
            inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
            detail = str(exc)
            yield {
                "event": "exec_chunk",
                "payload": {"stream": "stderr", "content": f"{detail}\n"},
            }
            yield {
                "event": "exec_done",
                "payload": {
                    "session_id": session_id,
                    "command": command,
                    "cwd": cwd,
                    "returncode": 127,
                    "timed_out": False,
                    "files": inspection.files,
                    "sandbox": {
                        "backend": "docker",
                        "requested_backend": requested_backend,
                        "fallback": {"used": False, "reason": ""},
                        "blocked": True,
                        "violations": [detail],
                        "policy": self.policy.payload(),
                        "command_policy": command_policy,
                        "docker": self.config.payload(),
                        "container": self.container_manager.status(session_id).payload(),
                    },
                },
            }
            return

        process = subprocess.Popen(
            self.container_manager.build_exec_command(
                session_id=session_id,
                argv=command,
                cwd=cwd,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=_creation_flags(),
        )
        stream_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        readers = [
            threading.Thread(
                target=_pump_stream,
                args=("stdout", process.stdout, stream_queue),
                daemon=True,
            ),
            threading.Thread(
                target=_pump_stream,
                args=("stderr", process.stderr, stream_queue),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        completed_streams = set()
        deadline = time.monotonic() + max(1.0, timeout_seconds)
        timed_out = False
        while len(completed_streams) < 2 or process.poll() is None or not stream_queue.empty():
            if not timed_out and time.monotonic() > deadline and process.poll() is None:
                timed_out = True
                process.kill()
                yield {
                    "event": "exec_chunk",
                    "payload": {
                        "stream": "stderr",
                        "content": "Command execution timed out.\n",
                    },
                }
            try:
                stream_name, chunk = stream_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                completed_streams.add(stream_name)
                continue
            yield {
                "event": "exec_chunk",
                "payload": {"stream": stream_name, "content": chunk},
            }

        process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=1)

        inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
        violations = list(inspection.violations)
        if timed_out:
            violations.append("Command execution timed out.")
        returncode = -1 if timed_out else int(process.returncode or 0)
        if inspection.violations and returncode == 0:
            returncode = 125
        yield {
            "event": "exec_done",
            "payload": {
                "session_id": session_id,
                "command": command,
                "cwd": cwd,
                "returncode": returncode,
                "timed_out": timed_out,
                "files": inspection.files,
                "sandbox": {
                    "backend": "docker",
                    "requested_backend": requested_backend,
                    "fallback": {"used": False, "reason": ""},
                    "blocked": bool(violations),
                    "violations": violations,
                    "policy": self.policy.payload(),
                    "command_policy": command_policy,
                    "docker": self.config.payload(),
                    "container": container.payload(),
                },
            },
        }


class ManagedSandboxExecutor:
    def __init__(
        self,
        local_executor: PythonExecutor,
        docker_executor: DockerSandboxExecutor,
        backend_preference: str,
    ) -> None:
        self.local_executor = local_executor
        self.docker_executor = docker_executor
        self.backend_preference = _normalize_backend_preference(backend_preference)
        self.policy = local_executor.policy

    def execute(self, *, session_id: str, code: str) -> ExecutionResult:
        docker_available, docker_detail = self.docker_executor.availability()
        if self.backend_preference == "local":
            return self.local_executor.execute(session_id=session_id, code=code)
        if self.backend_preference == "docker":
            validation_error = self._validate_for_requested_backend(
                session_id=session_id,
                code=code,
                requested_backend="docker",
            )
            if validation_error is not None:
                return validation_error
            if docker_available:
                return self.docker_executor.execute(session_id=session_id, code=code)
            return self._unavailable_result(session_id=session_id, detail=docker_detail)
        if docker_available:
            validation_error = self._validate_for_requested_backend(
                session_id=session_id,
                code=code,
                requested_backend="auto",
            )
            if validation_error is not None:
                return validation_error
            return self.docker_executor.execute(session_id=session_id, code=code)
        result = self.local_executor.execute(session_id=session_id, code=code)
        result.sandbox["requested_backend"] = "auto"
        result.sandbox["fallback"] = {"used": True, "reason": docker_detail}
        return result

    def execute_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float,
        allowed_commands: tuple[str, ...],
        max_command_tier: str | None = None,
        request_source: str = "api",
    ) -> CommandExecutionResult:
        requested_backend = self.backend_preference
        docker_available, docker_detail = self.docker_executor.availability()
        command_policy = _command_policy(
            command=command,
            max_command_tier=max_command_tier,
            request_source=request_source,
        )
        normalized_cwd, violations = _validate_exec_request(
            command=command,
            cwd=cwd or ".",
            allowed_commands=allowed_commands,
            runtime_workspace=self.docker_executor.config.workdir,
        )
        tier_violation = _command_tier_violation(command_policy)
        if tier_violation:
            violations.append(tier_violation)
        if violations:
            inspection = self.local_executor.workspace_manager.inspect(
                session_id, policy=self.policy
            )
            return CommandExecutionResult(
                session_id=session_id,
                command=command,
                cwd=normalized_cwd,
                returncode=126,
                stdout="",
                stderr="\n".join(violations),
                timed_out=False,
                files=inspection.files,
                sandbox={
                    "backend": "docker",
                    "requested_backend": requested_backend,
                    "fallback": {"used": False, "reason": ""},
                    "blocked": True,
                    "violations": violations,
                    "policy": self.policy.payload(),
                    "command_policy": command_policy,
                    "docker": self.docker_executor.config.payload(),
                },
            )

        if self.backend_preference == "local":
            return self._command_unavailable_result(
                session_id=session_id,
                command=command,
                cwd=normalized_cwd,
                detail="Shell execution requires the Docker backend.",
                requested_backend="local",
                command_policy=command_policy,
            )

        if not docker_available:
            return self._command_unavailable_result(
                session_id=session_id,
                command=command,
                cwd=normalized_cwd,
                detail=docker_detail,
                requested_backend=requested_backend,
                command_policy=command_policy,
            )

        capped_timeout = max(1.0, min(timeout_seconds, 120.0))
        return self.docker_executor.execute_command(
            session_id=session_id,
            command=command,
            cwd=normalized_cwd,
            timeout_seconds=capped_timeout,
            requested_backend=requested_backend,
            command_policy=command_policy,
        )

    def stream_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float,
        allowed_commands: tuple[str, ...],
        max_command_tier: str | None = None,
        request_source: str = "api",
    ):
        requested_backend = self.backend_preference
        command_policy = _command_policy(
            command=command,
            max_command_tier=max_command_tier,
            request_source=request_source,
        )
        normalized_cwd, violations = _validate_exec_request(
            command=command,
            cwd=cwd or ".",
            allowed_commands=allowed_commands,
            runtime_workspace=self.docker_executor.config.workdir,
        )
        yield {
            "event": "exec_start",
            "payload": {
                "session_id": session_id,
                "command": command,
                "cwd": normalized_cwd,
                "requested_backend": requested_backend,
                "command_policy": command_policy,
            },
        }
        tier_violation = _command_tier_violation(command_policy)
        if tier_violation:
            violations.append(tier_violation)
        if violations:
            inspection = self.local_executor.workspace_manager.inspect(
                session_id, policy=self.policy
            )
            detail = "\n".join(violations)
            yield {
                "event": "exec_chunk",
                "payload": {"stream": "stderr", "content": f"{detail}\n"},
            }
            yield {
                "event": "exec_done",
                "payload": {
                    "session_id": session_id,
                    "command": command,
                    "cwd": normalized_cwd,
                    "returncode": 126,
                    "stdout": "",
                    "stderr": detail,
                    "timed_out": False,
                    "files": inspection.files,
                    "sandbox": {
                        "backend": "docker",
                        "requested_backend": requested_backend,
                        "fallback": {"used": False, "reason": ""},
                        "blocked": True,
                        "violations": violations,
                        "policy": self.policy.payload(),
                        "command_policy": command_policy,
                        "docker": self.docker_executor.config.payload(),
                    },
                },
            }
            return

        if self.backend_preference == "local":
            detail = "Shell execution requires the Docker backend."
            yield {
                "event": "exec_chunk",
                "payload": {"stream": "stderr", "content": f"{detail}\n"},
            }
            yield {
                "event": "exec_done",
                "payload": _command_result_payload(
                    self._command_unavailable_result(
                        session_id=session_id,
                        command=command,
                        cwd=normalized_cwd,
                        detail=detail,
                        requested_backend="local",
                        command_policy=command_policy,
                    )
                ),
            }
            return

        docker_available, docker_detail = self.docker_executor.availability()
        if not docker_available:
            yield {
                "event": "exec_chunk",
                "payload": {"stream": "stderr", "content": f"{docker_detail}\n"},
            }
            yield {
                "event": "exec_done",
                "payload": _command_result_payload(
                    self._command_unavailable_result(
                        session_id=session_id,
                        command=command,
                        cwd=normalized_cwd,
                        detail=docker_detail,
                        requested_backend=requested_backend,
                        command_policy=command_policy,
                    )
                ),
            }
            return

        capped_timeout = max(1.0, min(timeout_seconds, 120.0))
        for event in self.docker_executor.stream_command(
            session_id=session_id,
            command=command,
            cwd=normalized_cwd,
            timeout_seconds=capped_timeout,
            requested_backend=requested_backend,
            command_policy=command_policy,
        ):
            yield event

    def status_payload(self, session_id: str | None = None) -> dict[str, object]:
        docker_available, docker_detail = self.docker_executor.availability()
        active_backend = "local"
        if self.backend_preference == "docker":
            active_backend = "docker" if docker_available else "docker-unavailable"
        elif self.backend_preference == "auto" and docker_available:
            active_backend = "docker"
        payload = {
            "requested_backend": self.backend_preference,
            "active_backend": active_backend,
            "docker_available": docker_available,
            "docker_detail": docker_detail,
            "policy": self.policy.payload(),
            "docker": self.docker_executor.config.payload(),
        }
        if session_id:
            payload["session"] = self.session_payload(session_id)
        return payload

    def session_payload(self, session_id: str) -> dict[str, object]:
        if self.backend_preference == "local":
            return {
                "backend": "local",
                "session_id": session_id,
                "workspace": str(
                    self.local_executor.workspace_manager.workspace_for(session_id)
                ),
                "container_name": "",
                "exists": False,
                "running": False,
                "status": "local-only",
            }
        return self.docker_executor.session_payload(session_id)

    def reset_session(self, session_id: str) -> dict[str, object]:
        if self.backend_preference == "local":
            return {
                "session_id": session_id,
                "removed": False,
                "detail": "Local backend has no persistent Docker container to remove.",
            }
        return self.docker_executor.reset_session(session_id)

    def _unavailable_result(self, *, session_id: str, detail: str) -> ExecutionResult:
        return ExecutionResult(
            session_id=session_id,
            returncode=127,
            stdout="",
            stderr=detail,
            files=self.local_executor.workspace_manager.list_files(session_id),
            timed_out=False,
            sandbox={
                "backend": "docker",
                "requested_backend": "docker",
                "fallback": {"used": False, "reason": ""},
                "blocked": True,
                "violations": [detail],
                "policy": self.policy.payload(),
                "docker": self.docker_executor.config.payload(),
            },
        )

    def _command_unavailable_result(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str,
        detail: str,
        requested_backend: str,
        command_policy: dict[str, object],
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            session_id=session_id,
            command=command,
            cwd=cwd,
            returncode=127,
            stdout="",
            stderr=detail,
            timed_out=False,
            files=self.local_executor.workspace_manager.list_files(session_id),
            sandbox={
                "backend": "docker" if requested_backend != "local" else "local",
                "requested_backend": requested_backend,
                "fallback": {"used": False, "reason": ""},
                "blocked": True,
                "violations": [detail],
                "policy": self.policy.payload(),
                "command_policy": command_policy,
                "docker": self.docker_executor.config.payload(),
            },
        )

    def _validate_for_requested_backend(
        self, *, session_id: str, code: str, requested_backend: str
    ) -> ExecutionResult | None:
        workspace = self.local_executor.workspace_manager.workspace_for(session_id)
        violations = self.local_executor._validate_code(workspace=workspace, code=code)
        if not violations:
            return None
        inspection = self.local_executor.workspace_manager.inspect(
            session_id, policy=self.policy
        )
        return ExecutionResult(
            session_id=session_id,
            returncode=126,
            stdout="",
            stderr="\n".join(violations),
            files=inspection.files,
            timed_out=False,
            sandbox={
                "backend": "docker",
                "requested_backend": requested_backend,
                "fallback": {"used": False, "reason": ""},
                "blocked": True,
                "violations": violations,
                "policy": self.policy.payload(),
                "docker": self.docker_executor.config.payload(),
            },
        )


def build_executor(
    *,
    workspace_manager: WorkspaceManager,
    policy: SandboxPolicy,
    docker_config: DockerSandboxConfig,
) -> ManagedSandboxExecutor:
    local_executor = PythonExecutor(
        workspace_manager,
        policy.timeout_seconds,
        policy=policy,
    )
    docker_executor = DockerSandboxExecutor(
        local_executor=local_executor,
        workspace_manager=workspace_manager,
        policy=policy,
        config=docker_config,
    )
    return ManagedSandboxExecutor(
        local_executor=local_executor,
        docker_executor=docker_executor,
        backend_preference=docker_config.backend_preference,
    )


def _normalize_backend_preference(value: str) -> str:
    normalized = value.strip().lower() or "auto"
    if normalized not in {"auto", "local", "docker"}:
        return "auto"
    return normalized


def _normalize_command_tier(value: str | None) -> str:
    normalized = (value or "package").strip().lower()
    if normalized not in _COMMAND_TIER_ORDER:
        return "package"
    return normalized


def filter_commands_by_tier(
    *,
    allowed_commands: tuple[str, ...],
    max_command_tier: str | None,
) -> tuple[str, ...]:
    max_tier = _normalize_command_tier(max_command_tier)
    visible: list[str] = []
    for command in allowed_commands:
        executable = str(command).strip()
        if not executable:
            continue
        tier = _COMMAND_TIER_BY_EXECUTABLE.get(executable, "package")
        if _COMMAND_TIER_ORDER[tier] <= _COMMAND_TIER_ORDER[max_tier]:
            visible.append(executable)
    return tuple(dict.fromkeys(visible))


def _command_policy(
    *,
    command: list[str],
    max_command_tier: str | None,
    request_source: str,
) -> dict[str, object]:
    executable = str(command[0]).strip() if command else ""
    tier = _COMMAND_TIER_BY_EXECUTABLE.get(executable, "package")
    return {
        "source": request_source,
        "executable": executable,
        "tier": tier,
        "max_tier": _normalize_command_tier(max_command_tier),
    }


def _command_tier_violation(command_policy: dict[str, object]) -> str | None:
    tier = str(command_policy.get("tier", "package"))
    max_tier = str(command_policy.get("max_tier", "package"))
    if _COMMAND_TIER_ORDER[tier] <= _COMMAND_TIER_ORDER[max_tier]:
        return None
    return (
        f"Command tier `{tier}` exceeds the allowed maximum `{max_tier}` for "
        f"{command_policy.get('source', 'this request')} execution."
    )


def _validate_exec_request(
    *,
    command: list[str],
    cwd: str,
    allowed_commands: tuple[str, ...],
    runtime_workspace: str,
) -> tuple[str, list[str]]:
    violations: list[str] = []
    if not command:
        return runtime_workspace, ["Command cannot be empty."]
    if len(command) > _MAX_EXEC_ARGS:
        violations.append(f"Command exceeds the {_MAX_EXEC_ARGS} argument limit.")
    cleaned: list[str] = []
    for part in command:
        item = str(part).strip()
        cleaned.append(item)
        if not item:
            violations.append("Command arguments cannot be empty.")
            continue
        if len(item) > _MAX_ARG_CHARS:
            violations.append(
                f"Command argument `{item[:32]}` exceeds the {_MAX_ARG_CHARS} character limit."
            )
        if any(char in item for char in ("\x00", "\n", "\r")):
            violations.append("Command arguments cannot contain control characters.")

    executable = cleaned[0] if cleaned else ""
    if executable in _BLOCKED_EXEC_BINARIES:
        violations.append(f"Executable `{executable}` is blocked.")
    if executable and executable not in allowed_commands:
        violations.append(f"Executable `{executable}` is not in the allowed command list.")
    if executable == "git":
        subcommand = cleaned[1] if len(cleaned) > 1 else ""
        if subcommand not in _ALLOWED_GIT_SUBCOMMANDS:
            violations.append(
                f"Git subcommand `{subcommand or '(missing)'}` is not allowed."
            )

    normalized_cwd = _normalize_exec_cwd(cwd, runtime_workspace)
    if not (
        normalized_cwd == runtime_workspace
        or normalized_cwd.startswith(f"{runtime_workspace}/")
    ):
        violations.append("Command working directory must stay inside the workspace.")
    return normalized_cwd, sorted(set(violations))


def _normalize_exec_cwd(cwd: str, runtime_workspace: str) -> str:
    base = runtime_workspace.rstrip("/") or "/workspace"
    raw = (cwd or ".").strip()
    if not raw or raw == ".":
        return base
    if raw.startswith("/"):
        return posixpath.normpath(raw)
    return posixpath.normpath(posixpath.join(base, raw))


def _clip_output(text: str, limit: int) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    clipped = text.encode("utf-8")[:limit].decode("utf-8", errors="replace")
    return f"{clipped}\n...[output truncated to {limit} bytes]..."


def _command_result_payload(result: CommandExecutionResult) -> dict[str, object]:
    return {
        "session_id": result.session_id,
        "command": result.command,
        "cwd": result.cwd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "files": result.files,
        "sandbox": result.sandbox,
    }


def _clean_docker_stderr(text: str, returncode: int) -> str:
    if returncode != 0:
        return text
    noisy_fragments = (
        "Unable to find image",
        "Pulling from",
        "Pulling fs layer",
        "Download complete",
        "Pull complete",
        "Digest:",
        "Status: Downloaded newer image for",
    )
    lines = [
        line
        for line in text.splitlines()
        if line and not any(fragment in line for fragment in noisy_fragments)
    ]
    return "\n".join(lines).strip()


def _pump_stream(
    stream_name: str,
    handle,
    stream_queue: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        if handle is None:
            return
        for line in iter(handle.readline, ""):
            if not line:
                break
            stream_queue.put((stream_name, line))
    finally:
        if handle is not None:
            handle.close()
        stream_queue.put((stream_name, None))


def _creation_flags() -> int:
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    return flags
