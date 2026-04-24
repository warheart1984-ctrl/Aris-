from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess

from .execution import WorkspaceManager


@dataclass(frozen=True, slots=True)
class DockerSandboxConfig:
    backend_preference: str = "auto"
    image: str = "python:3.11-alpine"
    memory: str = "256m"
    cpus: str = "1.0"
    pids_limit: int = 64
    workdir: str = "/workspace"
    tmpfs_size: str = "64m"
    network_disabled: bool = True
    read_only_root: bool = True
    no_new_privileges: bool = True
    user: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "backend_preference": self.backend_preference,
            "image": self.image,
            "memory": self.memory,
            "cpus": self.cpus,
            "pids_limit": self.pids_limit,
            "workdir": self.workdir,
            "tmpfs_size": self.tmpfs_size,
            "network_disabled": self.network_disabled,
            "read_only_root": self.read_only_root,
            "no_new_privileges": self.no_new_privileges,
            "user": self.user,
        }


@dataclass(frozen=True, slots=True)
class DockerSessionInfo:
    session_id: str
    container_name: str
    exists: bool
    running: bool
    status: str
    workspace: str
    image: str
    detail: str

    def payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "container_name": self.container_name,
            "exists": self.exists,
            "running": self.running,
            "status": self.status,
            "workspace": self.workspace,
            "image": self.image,
            "detail": self.detail,
        }


class DockerSessionContainerManager:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        config: DockerSandboxConfig,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.config = config
        self._availability: tuple[bool, str] | None = None

    def availability(self) -> tuple[bool, str]:
        if self._availability is None:
            self._availability = self._detect_availability()
        return self._availability

    def status(self, session_id: str) -> DockerSessionInfo:
        workspace = self.workspace_manager.workspace_for(session_id)
        name = self.container_name(session_id)
        completed = self._run(
            ["inspect", name],
            timeout=10,
        )
        if completed.returncode != 0:
            return DockerSessionInfo(
                session_id=session_id,
                container_name=name,
                exists=False,
                running=False,
                status="missing",
                workspace=str(workspace),
                image=self.config.image,
                detail=(completed.stderr or completed.stdout).strip(),
            )

        payload = json.loads(completed.stdout)[0]
        state = payload.get("State", {})
        status = str(state.get("Status", "unknown"))
        running = bool(state.get("Running", False))
        image = str(payload.get("Config", {}).get("Image", self.config.image))
        return DockerSessionInfo(
            session_id=session_id,
            container_name=name,
            exists=True,
            running=running,
            status=status,
            workspace=str(workspace),
            image=image,
            detail=f"Container status is {status}.",
        )

    def ensure_container(self, session_id: str) -> DockerSessionInfo:
        info = self.status(session_id)
        if info.running:
            return info
        if info.exists:
            completed = self._run(["start", info.container_name], timeout=30)
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(detail or "Failed to start the Docker workspace.")
            return self.status(session_id)

        workspace = self.workspace_manager.workspace_for(session_id)
        completed = subprocess.run(
            self.build_create_command(
                session_id=session_id,
                workspace=workspace,
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            creationflags=_creation_flags(),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or "Failed to create the Docker workspace.")
        return self.status(session_id)

    def destroy_container(self, session_id: str) -> dict[str, object]:
        info = self.status(session_id)
        if not info.exists:
            return {
                "session_id": session_id,
                "removed": False,
                "container": info.payload(),
            }
        completed = self._run(["rm", "-f", info.container_name], timeout=30)
        removed = completed.returncode == 0
        detail = (completed.stderr or completed.stdout).strip()
        return {
            "session_id": session_id,
            "removed": removed,
            "detail": detail,
            "container": info.payload(),
        }

    def container_name(self, session_id: str) -> str:
        safe_session = "".join(
            char.lower() for char in session_id if char.isalnum()
        )[:24] or "default"
        workspace_hash = hashlib.sha1(
            str(self.workspace_manager.root.resolve()).encode("utf-8")
        ).hexdigest()[:10]
        return f"forge-{workspace_hash}-{safe_session}"

    def build_create_command(self, *, session_id: str, workspace: Path) -> list[str]:
        runtime_workspace = self.config.workdir.rstrip("/") or "/workspace"
        command = ["docker", "run", "-d", "--name", self.container_name(session_id)]
        command.extend(["--label", "forge.chat.workspace=true"])
        command.extend(["--label", f"forge.chat.session={session_id}"])
        if self.config.network_disabled:
            command.extend(["--network", "none"])
        if self.config.read_only_root:
            command.append("--read-only")
        if self.config.no_new_privileges:
            command.extend(["--security-opt", "no-new-privileges"])
        command.extend(["--cap-drop", "ALL"])
        command.extend(["--memory", self.config.memory])
        command.extend(["--cpus", self.config.cpus])
        command.extend(["--pids-limit", str(self.config.pids_limit)])
        command.extend(
            ["--tmpfs", f"/tmp:rw,noexec,nosuid,size={self.config.tmpfs_size}"]
        )
        command.extend(
            [
                "--mount",
                f"type=bind,source={workspace.resolve()},target={runtime_workspace}",
            ]
        )
        command.extend(["--workdir", runtime_workspace])
        if self.config.user:
            command.extend(["--user", self.config.user])
        command.extend(["-e", "PYTHONIOENCODING=utf-8"])
        command.extend(["-e", "PYTHONUNBUFFERED=1"])
        command.extend(["-e", f"HOME={runtime_workspace}"])
        command.extend(["-e", "TMPDIR=/tmp"])
        command.append(self.config.image)
        command.extend(
            [
                "sh",
                "-lc",
                "trap 'exit 0' TERM INT; while true; do sleep 3600; done",
            ]
        )
        return command

    def build_exec_command(
        self,
        *,
        session_id: str,
        argv: list[str],
        cwd: str | None = None,
    ) -> list[str]:
        runtime_workspace = cwd or (self.config.workdir.rstrip("/") or "/workspace")
        command = ["docker", "exec", "--workdir", runtime_workspace]
        if self.config.user:
            command.extend(["--user", self.config.user])
        command.append(self.container_name(session_id))
        command.extend(argv)
        return command

    def _detect_availability(self) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=8,
                creationflags=_creation_flags(),
            )
        except FileNotFoundError:
            return False, "Docker CLI is not installed."
        except subprocess.TimeoutExpired:
            return False, "Docker health check timed out."
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            return False, detail or "Docker is unavailable."
        return True, f"Docker server {completed.stdout.strip() or 'unknown'} is available."

    def _run(self, args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            creationflags=_creation_flags(),
        )


def _creation_flags() -> int:
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    return flags
