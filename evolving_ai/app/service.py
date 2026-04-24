from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import threading
import uuid

from .agent import (
    AgentAction,
    AgentToolPermissions,
    build_agent_system_prompt,
    parse_agent_decision,
)
from .agent_runs import AgentRunStore, TERMINAL_RUN_STATUSES
from .approval_state import ApprovalStateDatabase
from .attachments import Attachment
from .cache import LruCache
from .change_history import WorkspaceChangeHistoryManager
from .config import AppConfig
from .execution import SandboxPolicy, WorkspaceManager
from .execution_backends import (
    DockerSandboxConfig,
    build_executor,
    filter_commands_by_tier,
)
from .files import FileParser
from .knowledge import KnowledgeIndex, SearchHit
from .memory import MemoryStore
from .model_switchboard import ModelRouteDecision, ModelSwitchboard
from .providers import ChatProvider, build_provider
from .projects import (
    WorkspaceImportConfig,
    WorkspaceProjectManager,
    WorkspaceTaskManager,
)
from .review import WorkspacePatchManager
from .tools import ToolResult, ToolRouter
from .workspace_intel import (
    WorkspaceProjectProfileManager,
    WorkspaceRepoMapConfig,
    WorkspaceRepoMapManager,
    WorkspaceSearchConfig,
    WorkspaceSearchManager,
    WorkspaceSnapshotConfig,
    WorkspaceSnapshotManager,
)


@dataclass(slots=True)
class MessageRecord:
    role: str
    content: str
    created_at: str


@dataclass(slots=True)
class ChatSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageRecord] = field(default_factory=list)


@dataclass(slots=True)
class AgentToolOutcome:
    observation: str
    approval: dict[str, object] | None = None


@dataclass(slots=True)
class PendingAgentApproval:
    id: str
    session_id: str
    kind: str
    title: str
    summary: str
    created_at: str
    step: int
    tool: str
    source: str = "agent"
    status: str = "pending"
    resume_available: bool = False
    details: dict[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        payload = {
            "id": self.id,
            "session_id": self.session_id,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "created_at": self.created_at,
            "step": self.step,
            "tool": self.tool,
            "source": self.source,
            "status": self.status,
            "resume_available": self.resume_available,
        }
        payload.update(self.details)
        return payload


@dataclass(slots=True)
class AgentResumeState:
    approval_id: str
    kind: str
    run_id: str
    session_id: str
    blocked_step: int
    next_step_index: int
    created_at: str
    workspace_fingerprint: str
    fast_mode: bool
    model: str
    attachments: list[Attachment]
    tool_messages: list[dict[str, str]]
    agent_max_command_tier: str
    agent_allowed_commands: tuple[str, ...]
    allow_python: bool
    allow_shell: bool
    allow_filesystem_read: bool
    allow_filesystem_write: bool


@dataclass(frozen=True, slots=True)
class AgentRunConfig:
    permissions: AgentToolPermissions
    max_command_tier: str
    allowed_commands: tuple[str, ...]


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, ChatSession] = {}
        self._lock = threading.RLock()
        self._load()

    def list_sessions(self) -> list[ChatSession]:
        with self._lock:
            return sorted(
                self.sessions.values(),
                key=lambda session: session.updated_at,
                reverse=True,
            )

    def get_or_create(self, session_id: str | None, title_seed: str) -> ChatSession:
        with self._lock:
            if session_id and session_id in self.sessions:
                return self.sessions[session_id]
            now = _utc_now()
            session = ChatSession(
                id=session_id or uuid.uuid4().hex,
                title=self._title_from_text(title_seed),
                created_at=now,
                updated_at=now,
            )
            self.sessions[session.id] = session
            self._save()
            return session

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        with self._lock:
            session = self.sessions[session_id]
            session.messages.append(
                MessageRecord(role=role, content=content, created_at=_utc_now())
            )
            session.updated_at = _utc_now()
            if role == "user" and len(session.messages) == 1:
                session.title = self._title_from_text(content)
            self._save()
            return session

    def _title_from_text(self, text: str) -> str:
        words = [word for word in text.strip().split() if word]
        return " ".join(words[:6]) or "New session"

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for item in raw:
            self.sessions[item["id"]] = ChatSession(
                id=item["id"],
                title=item["title"],
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                messages=[
                    MessageRecord(
                        role=message["role"],
                        content=message["content"],
                        created_at=message["created_at"],
                    )
                    for message in item["messages"]
                ],
            )

    def _save(self) -> None:
        payload = []
        for session in self.sessions.values():
            payload.append(
                {
                    "id": session.id,
                    "title": session.title,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": [asdict(message) for message in session.messages],
                }
            )
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ChatService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.knowledge = KnowledgeIndex(config.knowledge_dir)
        self.knowledge.refresh()
        self.sessions = SessionStore(config.sessions_path)
        self.memory = MemoryStore(config.memory_path)
        self.model_switchboard = ModelSwitchboard(
            config,
            state_path=config.sessions_path.parent / "model-switchboard.json",
        )
        self.tools = ToolRouter()
        self.file_parser = FileParser()
        self.workspace_manager = WorkspaceManager(config.workspaces_dir)
        self.sandbox_policy = SandboxPolicy(
            timeout_seconds=config.execution_timeout_seconds,
            max_code_chars=config.execution_max_code_chars,
            max_output_chars=config.execution_max_output_chars,
            max_files=config.execution_max_files,
            max_file_bytes=config.execution_max_file_bytes,
        )
        self.patch_manager = WorkspacePatchManager(
            workspace_manager=self.workspace_manager,
            policy=self.sandbox_policy,
        )
        self.change_history = WorkspaceChangeHistoryManager(
            workspace_manager=self.workspace_manager,
            policy=self.sandbox_policy,
        )
        self.project_manager = WorkspaceProjectManager(
            workspace_manager=self.workspace_manager,
            max_files=self.sandbox_policy.max_files,
            max_file_bytes=self.sandbox_policy.max_file_bytes,
            config=WorkspaceImportConfig(
                max_upload_bytes=config.repo_upload_max_bytes,
                max_archive_entries=config.repo_archive_max_entries,
                max_total_bytes=config.repo_max_total_bytes,
                clone_timeout_seconds=config.repo_clone_timeout_seconds,
                allowed_clone_hosts=config.repo_allowed_clone_hosts,
            ),
        )
        self.task_manager = WorkspaceTaskManager(
            workspace_manager=self.workspace_manager,
        )
        self.search_manager = WorkspaceSearchManager(
            workspace_manager=self.workspace_manager,
            max_file_bytes=self.sandbox_policy.max_file_bytes,
            config=WorkspaceSearchConfig(
                max_results=config.workspace_search_max_results,
                max_excerpt_chars=config.workspace_search_max_excerpt_chars,
            ),
        )
        self.snapshot_manager = WorkspaceSnapshotManager(
            workspace_manager=self.workspace_manager,
            config=WorkspaceSnapshotConfig(
                max_entries=config.workspace_snapshot_max_entries,
                max_total_bytes=config.workspace_snapshot_max_total_bytes,
                max_snapshots=config.workspace_snapshot_max_snapshots,
            ),
        )
        self.project_profile_manager = WorkspaceProjectProfileManager(
            workspace_manager=self.workspace_manager,
            max_file_bytes=self.sandbox_policy.max_file_bytes,
        )
        self.repo_map_manager = WorkspaceRepoMapManager(
            workspace_manager=self.workspace_manager,
            max_file_bytes=self.sandbox_policy.max_file_bytes,
            config=WorkspaceRepoMapConfig(),
        )
        self.executor = build_executor(
            workspace_manager=self.workspace_manager,
            policy=self.sandbox_policy,
            docker_config=DockerSandboxConfig(
                backend_preference=config.execution_backend,
                image=config.docker_image,
                memory=config.docker_memory,
                cpus=config.docker_cpus,
                pids_limit=config.docker_pids_limit,
                workdir=config.docker_workdir,
                tmpfs_size=config.docker_tmpfs_size,
                network_disabled=config.docker_network_disabled,
                read_only_root=config.docker_read_only_root,
                no_new_privileges=config.docker_no_new_privileges,
                user=config.docker_user,
            ),
        )
        self.cache = LruCache[str](capacity=config.cache_size)
        self.provider: ChatProvider = build_provider(config)
        self.agent_permissions = AgentToolPermissions(
            allow_python=config.agent_allow_python,
            allow_shell=config.agent_allow_shell,
            allow_filesystem_read=config.agent_allow_filesystem_read,
            allow_filesystem_write=config.agent_allow_filesystem_write,
        )
        self.agent_runs = AgentRunStore(config.agent_run_db_path)
        self._worker_threads: list[threading.Thread] = []
        self._worker_threads_lock = threading.Lock()
        self._worker_stop = threading.Event()
        self._worker_generation = 0
        self.approval_state = ApprovalStateDatabase(config.approval_db_path)
        self.approval_state.migrate_legacy_snapshot(config.legacy_approval_state_path)
        self.command_approvals: dict[str, dict[str, PendingAgentApproval]] = {}
        self.command_resume_states: dict[str, AgentResumeState] = {}
        self.patch_resume_states: dict[tuple[str, str], AgentResumeState] = {}
        self._load_approval_state()
        self.max_agent_steps = 6
        self._recover_leased_run_jobs()

    def _load_approval_state(self) -> None:
        command_approvals: dict[str, dict[str, PendingAgentApproval]] = {}
        snapshot = self.approval_state.load_snapshot()
        for item in snapshot.get("command_approvals", []):
            approval = self._deserialize_pending_approval(item)
            if approval is None:
                continue
            command_approvals.setdefault(approval.session_id, {})[approval.id] = approval

        command_resume_states: dict[str, AgentResumeState] = {}
        for item in snapshot.get("command_resume_states", []):
            state = self._deserialize_resume_state(item)
            if state is None:
                continue
            command_resume_states[state.approval_id] = state

        patch_resume_states: dict[tuple[str, str], AgentResumeState] = {}
        for item in snapshot.get("patch_resume_states", []):
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id", "")).strip()
            patch_id = str(item.get("patch_id", "")).strip()
            if not session_id or not patch_id:
                continue
            state = self._deserialize_resume_state(item.get("resume_state"))
            if state is None:
                continue
            patch_resume_states[(session_id, patch_id)] = state

        self.command_approvals = command_approvals
        self.command_resume_states = command_resume_states
        self.patch_resume_states = patch_resume_states
        self._prune_approval_state()
        self._save_approval_state()

    def _save_approval_state(self) -> None:
        self._prune_approval_state()
        snapshot = {
            "command_approvals": [
                self._serialize_pending_approval(approval)
                for approvals in self.command_approvals.values()
                for approval in approvals.values()
            ],
            "command_resume_states": [
                self._serialize_resume_state(state)
                for state in self.command_resume_states.values()
            ],
            "patch_resume_states": [
                {
                    "session_id": session_id,
                    "patch_id": patch_id,
                    "resume_state": self._serialize_resume_state(state),
                }
                for (session_id, patch_id), state in self.patch_resume_states.items()
            ],
        }
        self.approval_state.save_snapshot(snapshot=snapshot, updated_at=_utc_now())

    def _prune_approval_state(self) -> None:
        valid_command_ids = {
            approval.id
            for approvals in self.command_approvals.values()
            for approval in approvals.values()
        }
        self.command_resume_states = {
            approval_id: state
            for approval_id, state in self.command_resume_states.items()
            if approval_id in valid_command_ids
        }
        self.patch_resume_states = {
            key: state
            for key, state in self.patch_resume_states.items()
            if self._lookup_pending_patch(key[0], key[1]) is not None
        }

    def _serialize_pending_approval(
        self, approval: PendingAgentApproval
    ) -> dict[str, object]:
        return {
            "id": approval.id,
            "session_id": approval.session_id,
            "kind": approval.kind,
            "title": approval.title,
            "summary": approval.summary,
            "created_at": approval.created_at,
            "step": approval.step,
            "tool": approval.tool,
            "source": approval.source,
            "status": approval.status,
            "resume_available": approval.resume_available,
            "details": approval.details,
        }

    def _deserialize_pending_approval(
        self, item: object
    ) -> PendingAgentApproval | None:
        if not isinstance(item, dict):
            return None
        try:
            return PendingAgentApproval(
                id=str(item["id"]),
                session_id=str(item["session_id"]),
                kind=str(item["kind"]),
                title=str(item["title"]),
                summary=str(item["summary"]),
                created_at=str(item["created_at"]),
                step=int(item["step"]),
                tool=str(item["tool"]),
                source=str(item.get("source", "agent")),
                status=str(item.get("status", "pending")),
                resume_available=bool(item.get("resume_available", False)),
                details=dict(item.get("details", {}))
                if isinstance(item.get("details", {}), dict)
                else {},
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _serialize_resume_state(self, state: AgentResumeState) -> dict[str, object]:
        return {
            "approval_id": state.approval_id,
            "kind": state.kind,
            "run_id": state.run_id,
            "session_id": state.session_id,
            "blocked_step": state.blocked_step,
            "next_step_index": state.next_step_index,
            "created_at": state.created_at,
            "workspace_fingerprint": state.workspace_fingerprint,
            "fast_mode": state.fast_mode,
            "model": state.model,
            "attachments": [
                {
                    "name": attachment.name,
                    "mime_type": attachment.mime_type,
                    "content": attachment.content,
                    "kind": attachment.kind,
                }
                for attachment in state.attachments
            ],
            "tool_messages": [dict(message) for message in state.tool_messages],
            "agent_max_command_tier": state.agent_max_command_tier,
            "agent_allowed_commands": list(state.agent_allowed_commands),
            "allow_python": state.allow_python,
            "allow_shell": state.allow_shell,
            "allow_filesystem_read": state.allow_filesystem_read,
            "allow_filesystem_write": state.allow_filesystem_write,
        }

    def _deserialize_resume_state(self, item: object) -> AgentResumeState | None:
        if not isinstance(item, dict):
            return None
        try:
            attachments = [
                Attachment(
                    name=str(attachment["name"]),
                    mime_type=str(attachment["mime_type"]),
                    content=str(attachment["content"]),
                    kind=str(attachment["kind"]),
                )
                for attachment in item.get("attachments", [])
                if isinstance(attachment, dict)
            ]
            tool_messages = [
                {
                    "role": str(message.get("role", "")),
                    "content": str(message.get("content", "")),
                }
                for message in item.get("tool_messages", [])
                if isinstance(message, dict)
            ]
            return AgentResumeState(
                approval_id=str(item["approval_id"]),
                kind=str(item.get("kind", "command")).strip() or "command",
                run_id=str(item.get("run_id", "")).strip(),
                session_id=str(item["session_id"]),
                blocked_step=int(item["blocked_step"]),
                next_step_index=int(item["next_step_index"]),
                created_at=str(item.get("created_at", "")) or _utc_now(),
                workspace_fingerprint=str(item.get("workspace_fingerprint", "")).strip(),
                fast_mode=bool(item.get("fast_mode", False)),
                model=str(item.get("model", "")),
                attachments=attachments,
                tool_messages=tool_messages,
                agent_max_command_tier=str(
                    item.get("agent_max_command_tier", self.config.agent_max_command_tier)
                ).strip()
                or self.config.agent_max_command_tier,
                agent_allowed_commands=tuple(
                    str(command).strip()
                    for command in item.get("agent_allowed_commands", self._agent_allowed_commands())
                    if str(command).strip()
                ),
                allow_python=bool(item.get("allow_python", self.agent_permissions.allow_python)),
                allow_shell=bool(item.get("allow_shell", self.agent_permissions.allow_shell)),
                allow_filesystem_read=bool(
                    item.get(
                        "allow_filesystem_read",
                        self.agent_permissions.allow_filesystem_read,
                    )
                ),
                allow_filesystem_write=bool(
                    item.get(
                        "allow_filesystem_write",
                        self.agent_permissions.allow_filesystem_write,
                    )
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _workspace_fingerprint(self, session_id: str) -> str:
        workspace = self.workspace_manager.workspace_for(session_id)
        digest = hashlib.sha256()
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(workspace)
            if path.name.startswith(".forge_") or ".git" in relative_path.parts:
                continue
            relative = str(relative_path).replace("\\", "/")
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            try:
                digest.update(path.read_bytes())
            except OSError:
                continue
            digest.update(b"\0")
        return digest.hexdigest()

    def _resume_state_stale_reason(
        self,
        state: AgentResumeState | None,
        *,
        patch_id: str | None = None,
    ) -> str | None:
        if state is None:
            return "Saved agent resume state is no longer available."
        if state.workspace_fingerprint and (
            state.workspace_fingerprint != self._workspace_fingerprint(state.session_id)
        ):
            return "Workspace changed since this approval checkpoint was saved."
        if patch_id and self._lookup_pending_patch(state.session_id, patch_id) is None:
            return "Pending patch is no longer available."
        return None

    def _record_approval_audit(
        self,
        *,
        session_id: str,
        approval_id: str,
        kind: str,
        action: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.approval_state.append_audit(
            session_id=session_id,
            approval_id=approval_id,
            kind=kind,
            action=action,
            created_at=_utc_now(),
            details=details or {},
        )

    def _default_agent_run_config(self) -> AgentRunConfig:
        return AgentRunConfig(
            permissions=self.agent_permissions,
            max_command_tier=self.config.agent_max_command_tier,
            allowed_commands=self._agent_allowed_commands(self.config.agent_max_command_tier),
        )

    def _agent_run_config_from_state(self, state: AgentResumeState) -> AgentRunConfig:
        return AgentRunConfig(
            permissions=AgentToolPermissions(
                allow_python=state.allow_python,
                allow_shell=state.allow_shell,
                allow_filesystem_read=state.allow_filesystem_read,
                allow_filesystem_write=state.allow_filesystem_write,
            ),
            max_command_tier=state.agent_max_command_tier,
            allowed_commands=state.agent_allowed_commands or self._agent_allowed_commands(
                state.agent_max_command_tier
            ),
        )

    def config_payload(self) -> dict[str, object]:
        agent_allowed_commands = self._agent_allowed_commands()
        return {
            "app_name": self.config.app_name,
            "provider_mode": self.config.provider_mode,
            "model": self.config.model,
            "fast_model": self.config.fast_model,
            "quality_model": self.config.quality_model,
            "vision_model": self.config.vision_model,
            "general_model": self.config.general_model,
            "coding_model": self.config.coding_model,
            "light_coding_model": self.config.light_coding_model,
            "model_router": self.model_switchboard.status_payload(),
            "fast_mode_default": self.config.fast_mode_default,
            "knowledge_sources": self.knowledge.list_sources(),
            "capabilities": {
                "chat": True,
                "retrieval": True,
                "tools": True,
                "memory": True,
                "attachments": True,
                "vision": bool(self.config.vision_api_url or self.config.vision_model),
                "agent_mode": True,
                "background_agent_runs": True,
                "agent_run_history": True,
                "deep_research_mode": True,
                "remote_fetch": self.config.enable_remote_fetch,
                "code_interpreter": True,
                "sandboxed_code_interpreter": True,
                "shell_exec": self.config.execution_backend in {"auto", "docker"},
                "workspace_file_tools": True,
                "workspace_patch_review": True,
                "workspace_patch_editing": True,
                "workspace_change_history": True,
                "workspace_change_verification": True,
                "workspace_import": True,
                "workspace_repo_search": True,
                "workspace_symbols": True,
                "workspace_repo_map": True,
                "workspace_snapshots": True,
                "project_detection": True,
                "task_planning": True,
                "smart_execution_planner": True,
                "git_clone": True,
                "git_workflow": True,
                "task_runner": True,
                "agent_approvals": True,
                "agent_approval_audit": True,
                "file_parsing": True,
                "web_search": True,
            },
            "sandbox": self.executor.status_payload(),
            "exec": {
                "timeout_seconds": self.config.command_timeout_seconds,
                "allowed_commands": list(self.config.allowed_exec_commands),
                "agent_allowed_commands": list(agent_allowed_commands),
                "agent_max_command_tier": self.config.agent_max_command_tier,
            },
            "agent": {
                "permissions": self.agent_permissions.payload(),
                "approval_policy": {
                    "read_only_shell": "auto",
                    "patch_apply": "preview_recommended",
                    "test_commands": "approval_required",
                    "package_commands": "approval_required",
                    "resume_after_decision": True,
                },
                "approval_store": {
                    "backend": "sqlite",
                },
                "run_store": {
                    "backend": "sqlite",
                    "queue": "sqlite",
                    "worker": {
                        "enabled": self.config.agent_worker_enabled,
                        "concurrency": self.config.agent_worker_concurrency,
                        "lease_seconds": self.config.agent_worker_lease_seconds,
                        "heartbeat_seconds": self.config.agent_worker_heartbeat_seconds,
                        "retry_delay_seconds": self.config.agent_worker_retry_delay_seconds,
                        "max_attempts": self.config.agent_worker_max_attempts,
                    },
                },
            },
            "workspace": {
                "max_file_bytes": self.sandbox_policy.max_file_bytes,
                "max_files": self.sandbox_policy.max_files,
                "max_read_chars": min(self.sandbox_policy.max_output_chars, 12_000),
                "max_diff_chars": 12_000,
                "imports": self.project_manager.config.payload(),
                "search": self.search_manager.config.payload(),
                "repo_map": self.repo_map_manager.config.payload(),
                "snapshots": self.snapshot_manager.config.payload(),
            },
        }

    def model_router_payload(self) -> dict[str, object]:
        return self.model_switchboard.status_payload()

    def set_model_router(
        self,
        *,
        mode: str,
        pinned_system: str | None = None,
    ) -> dict[str, object]:
        payload = self.model_switchboard.set_mode(mode=mode, pinned_system=pinned_system)
        return {"ok": True, "model_router": payload}

    def list_sessions(self) -> list[dict[str, object]]:
        items = []
        for session in self.sessions.list_sessions():
            items.append(
                {
                    "id": session.id,
                    "title": session.title,
                    "updated_at": session.updated_at,
                    "message_count": len(session.messages),
                    "preview": session.messages[-1].content[:120] if session.messages else "",
                }
            )
        return items

    def list_approval_audit(
        self, session_id: str, *, limit: int = 50
    ) -> dict[str, object]:
        bounded_limit = max(1, min(int(limit), 200))
        return {
            "session_id": session_id,
            "entries": self.approval_state.list_audit(
                session_id=session_id,
                limit=bounded_limit,
            ),
        }

    def list_agent_runs(
        self, session_id: str, *, limit: int = 20
    ) -> dict[str, object]:
        bounded_limit = max(1, min(int(limit), 100))
        return {
            "ok": True,
            "session_id": session_id,
            "runs": self.agent_runs.list_runs(
                session_id=session_id,
                limit=bounded_limit,
            ),
        }

    def get_agent_run(self, run_id: str) -> dict[str, object]:
        run = self.agent_runs.get_run(run_id)
        if run is None:
            return {"ok": False, "error": f"Run `{run_id}` was not found."}
        return {"ok": True, "run": run}

    def cancel_agent_run(self, run_id: str) -> dict[str, object]:
        run = self.agent_runs.get_run(run_id)
        if run is None:
            return {"ok": False, "error": f"Run `{run_id}` was not found."}
        if str(run.get("status", "")).strip() in TERMINAL_RUN_STATUSES:
            return {"ok": False, "error": "Run is already finished.", "run": run}
        updated = self.agent_runs.request_cancel(run_id)
        return {"ok": True, "run": updated or run}

    async def stream_agent_run(
        self,
        *,
        run_id: str,
        after_event_id: int = 0,
    ) -> AsyncIterator[str]:
        run = self.agent_runs.get_run(run_id)
        if run is None:
            notice = f"Run `{run_id}` was not found."
            yield self._sse_event(
                "agent_step",
                {
                    "step": 0,
                    "kind": "error",
                    "content": notice,
                    "run_id": run_id,
                },
            )
            yield self._sse_event("done", {"run_id": run_id})
            return
        async for event in self._stream_persisted_run(
            run_id=run_id,
            after_event_id=after_event_id,
        ):
            yield event

    def list_knowledge(self) -> list[str]:
        return self.knowledge.list_sources()

    def add_knowledge(self, name: str, content: str) -> None:
        self.knowledge.add_document(name, content)

    def memory_payload(self) -> dict[str, object]:
        payload = {"facts": self.memory.facts(), "summary": self.memory.summary()}
        if hasattr(self.memory, "locked_entries"):
            payload["locked"] = self.memory.locked_entries()
        return payload

    def parse_attachment(
        self, *, filename: str, mime_type: str, payload: bytes
    ) -> dict[str, object]:
        parsed = self.file_parser.parse(
            filename=filename,
            mime_type=mime_type,
            payload=payload,
        )
        return {
            "attachment": {
                "name": parsed.attachment.name,
                "mime_type": parsed.attachment.mime_type,
                "content": parsed.attachment.content,
                "kind": parsed.attachment.kind,
            },
            "summary": parsed.summary,
        }

    def execute_code(self, *, session_id: str, code: str) -> dict[str, object]:
        result = self.executor.execute(session_id=session_id, code=code)
        return {
            "session_id": result.session_id,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "files": result.files,
            "timed_out": result.timed_out,
            "sandbox": result.sandbox,
        }

    def execute_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float | None,
        max_command_tier: str | None = None,
        request_source: str = "api",
    ) -> dict[str, object]:
        result = self.executor.execute_command(
            session_id=session_id,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds or self.config.command_timeout_seconds,
            allowed_commands=self.config.allowed_exec_commands,
            max_command_tier=max_command_tier,
            request_source=request_source,
        )
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

    async def stream_command(
        self,
        *,
        session_id: str | None,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float | None,
        max_command_tier: str | None = None,
        request_source: str = "api",
    ) -> AsyncIterator[str]:
        active_session_id = session_id or "scratchpad"
        for event in self.executor.stream_command(
            session_id=active_session_id,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds or self.config.command_timeout_seconds,
            allowed_commands=self.config.allowed_exec_commands,
            max_command_tier=max_command_tier,
            request_source=request_source,
        ):
            payload = dict(event["payload"])
            payload.setdefault("session_id", active_session_id)
            yield self._sse_event(event["event"], payload)

    def sandbox_payload(self, session_id: str | None = None) -> dict[str, object]:
        return self.executor.status_payload(session_id)

    def reset_sandbox(self, session_id: str) -> dict[str, object]:
        return self.executor.reset_session(session_id)

    def workspace_payload(self, session_id: str) -> dict[str, object]:
        project_profile = self.inspect_workspace_project(session_id)
        return {
            "session_id": session_id,
            "files": self.workspace_manager.list_files(session_id),
            "project": project_profile["project"],
            "git": self.inspect_workspace_git(session_id)["git"],
            "repo_map": self.inspect_workspace_repo_map(session_id)["repo_map"],
            "verification": self.workspace_verification_payload(
                session_id,
                project_profile=project_profile,
            )["verification"],
            "imports": self.project_manager.list_imports(session_id),
            "tasks": self.task_manager.list_tasks(session_id),
            "snapshots": self.snapshot_manager.list_snapshots(session_id),
            "pending_patches": self.patch_manager.list_pending(session_id),
            "applied_changes": self.change_history.list_changes(session_id),
            "pending_approvals": self.list_pending_approvals(session_id)["approvals"],
            "sandbox": self.executor.session_payload(session_id),
        }

    def import_workspace_upload(
        self,
        *,
        session_id: str,
        filename: str,
        payload: bytes,
        target_path: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        result = self.project_manager.import_upload(
            session_id=session_id,
            filename=filename,
            payload=payload,
            target_path=target_path,
            source=source,
        )
        result["tasks"] = self.task_manager.list_tasks(session_id)
        result["pending_patches"] = self.patch_manager.list_pending(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        return result

    def clone_workspace_repo(
        self,
        *,
        session_id: str,
        repo_url: str,
        branch: str | None = None,
        target_dir: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        result = self.project_manager.clone_repository(
            session_id=session_id,
            repo_url=repo_url,
            branch=branch,
            target_dir=target_dir,
            source=source,
        )
        result["tasks"] = self.task_manager.list_tasks(session_id)
        result["pending_patches"] = self.patch_manager.list_pending(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        return result

    def list_workspace_tasks(self, session_id: str) -> dict[str, object]:
        return {
            "ok": True,
            "session_id": session_id,
            "tasks": self.task_manager.list_tasks(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def plan_workspace_task(
        self,
        *,
        session_id: str,
        goal: str,
        cwd: str | None = None,
        test_commands: list[str] | None = None,
        title: str | None = None,
    ) -> dict[str, object]:
        task_goal = goal.strip()
        active_cwd = str(cwd or ".").strip() or "."
        active_tests = [
            command.strip() for command in (test_commands or []) if command.strip()
        ]
        project_profile = self.inspect_workspace_project(session_id)
        git_state = self.inspect_workspace_git(session_id, cwd=active_cwd)
        repo_map_state = self.inspect_workspace_repo_map(
            session_id,
            goal=task_goal,
            cwd=active_cwd,
        )
        plan = self._build_workspace_task_plan(
            goal=task_goal,
            title=title,
            cwd=active_cwd,
            test_commands=active_tests,
            project_profile=project_profile,
            git_state=git_state,
            repo_map=repo_map_state,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "goal": task_goal,
            "cwd": active_cwd,
            "test_commands": active_tests,
            "project": project_profile.get("project", {}),
            "git": git_state.get("git", {}),
            "repo_map": repo_map_state.get("repo_map", {}),
            "plan": plan,
            "files": self.workspace_manager.list_files(session_id),
        }

    def prepare_workspace_git_handoff(
        self,
        *,
        session_id: str,
        goal: str | None = None,
        task_id: str | None = None,
        cwd: str | None = None,
    ) -> dict[str, object]:
        task_payload = self.task_manager.get_task(session_id, task_id) if task_id else None
        if task_payload is None:
            tasks = self.task_manager.list_tasks(session_id)
            task_payload = tasks[0] if tasks else None
        active_cwd = (
            str(cwd or "").strip()
            or str((task_payload or {}).get("cwd", "")).strip()
            or "."
        )
        git_state = self.inspect_workspace_git(session_id, cwd=active_cwd)
        git = git_state.get("git", {})
        if not isinstance(git, dict) or not git.get("is_repo"):
            return {
                "ok": False,
                "session_id": session_id,
                "cwd": active_cwd,
                "error": "No Git repository was found for this workspace handoff.",
                "git": git if isinstance(git, dict) else {},
                "files": self.workspace_manager.list_files(session_id),
            }
        review = self.review_workspace(session_id=session_id, cwd=active_cwd)
        handoff = self._build_workspace_git_handoff(
            goal=goal,
            task=task_payload,
            cwd=active_cwd,
            git_state=git_state,
            review=review,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "cwd": active_cwd,
            "git": git,
            "handoff": handoff,
            "review": review,
            "files": self.workspace_manager.list_files(session_id),
        }

    def search_workspace(
        self,
        *,
        session_id: str,
        query: str,
        mode: str = "text",
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        try:
            result = self.search_manager.search(
                session_id=session_id,
                query=query,
                mode=mode,
                limit=limit,
                path_prefix=path_prefix,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "query": query,
                "mode": mode,
                "path_prefix": str(path_prefix or "").strip(),
                "error": str(exc),
                "results": [],
                "files": self.workspace_manager.list_files(session_id),
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def list_workspace_symbols(
        self,
        *,
        session_id: str,
        query: str | None = None,
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        try:
            result = self.search_manager.list_symbols(
                session_id=session_id,
                query=query,
                limit=limit,
                path_prefix=path_prefix,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "query": str(query or "").strip(),
                "path_prefix": str(path_prefix or "").strip(),
                "error": str(exc),
                "symbols": [],
                "files": self.workspace_manager.list_files(session_id),
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def read_workspace_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None = None,
    ) -> dict[str, object]:
        try:
            result = self.search_manager.read_symbol(
                session_id=session_id,
                symbol=symbol,
                path=path,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "symbol": symbol,
                "path": str(path or "").strip(),
                "error": str(exc),
                "files": self.workspace_manager.list_files(session_id),
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def find_workspace_references(
        self,
        *,
        session_id: str,
        symbol: str,
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        try:
            result = self.search_manager.find_references(
                session_id=session_id,
                symbol=symbol,
                limit=limit,
                path_prefix=path_prefix,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "symbol": symbol,
                "path_prefix": str(path_prefix or "").strip(),
                "error": str(exc),
                "results": [],
                "files": self.workspace_manager.list_files(session_id),
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def edit_workspace_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            before_exists, before_content, relative = self._read_workspace_text_state(
                session_id=session_id,
                path=path or "",
            ) if path else (True, "", "")
            symbol_state = self.read_workspace_symbol(
                session_id=session_id,
                symbol=symbol,
                path=path,
            )
            if not symbol_state.get("ok"):
                return {
                    "ok": False,
                    "session_id": session_id,
                    "symbol": symbol,
                    "path": str(path or "").strip(),
                    "error": str(symbol_state.get("error", "Unknown symbol lookup error.")),
                    "files": files,
                }
            resolved_path = str(
                ((symbol_state.get("symbol") or {}) if isinstance(symbol_state.get("symbol"), dict) else {}).get("path", "")
            ).strip()
            before_exists, before_content, relative = self._read_workspace_text_state(
                session_id=session_id,
                path=resolved_path,
            )
            result = self.search_manager.edit_symbol(
                session_id=session_id,
                symbol=symbol,
                path=path,
                content=content,
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                max_files=self.sandbox_policy.max_files,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "symbol": symbol,
                "path": str(path or "").strip(),
                "error": str(exc),
                "files": files,
            }
        _, after_content, _ = self._read_workspace_text_state(
            session_id=session_id,
            path=str(result.get("path", "")).strip() or relative,
        )
        change = self._record_applied_workspace_change(
            session_id=session_id,
            path=str(result.get("path", "")).strip() or relative,
            operation="symbol_edit",
            source=source,
            before_exists=before_exists,
            before_content=before_content,
            after_exists=True,
            after_content=after_content,
            summary=(
                f"Edit symbol {symbol} in "
                f"{str(result.get('path', '')).strip() or relative}"
            ),
        )
        result["files"] = self.workspace_manager.list_files(session_id)
        result["change"] = change
        return result

    def inspect_workspace_project(self, session_id: str) -> dict[str, object]:
        result = self.project_profile_manager.detect(session_id)
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def inspect_workspace_repo_map(
        self,
        session_id: str,
        *,
        goal: str | None = None,
        cwd: str | None = None,
        focus_path: str | None = None,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        try:
            result = self.repo_map_manager.inspect(
                session_id=session_id,
                goal=goal,
                cwd=cwd,
                focus_path=focus_path,
                symbol=symbol,
                limit=limit,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "goal": str(goal or "").strip(),
                "cwd": str(cwd or "").strip() or ".",
                "path": str(focus_path or "").strip(),
                "symbol": str(symbol or "").strip(),
                "error": str(exc),
                "repo_map": {
                    "summary": "",
                    "scope_path": str(cwd or "").strip() or ".",
                    "focus_paths": [],
                    "owner_paths": [],
                    "related_paths": [],
                    "likely_test_files": [],
                    "suggested_validation_commands": [],
                    "nodes": [],
                    "edges": [],
                    "node_count": 0,
                    "edge_count": 0,
                },
                "files": self.workspace_manager.list_files(session_id),
            }
        project_profile = self.inspect_workspace_project(session_id)
        repo_map_payload = (
            dict(result.get("repo_map", {}))
            if isinstance(result.get("repo_map", {}), dict)
            else {}
        )
        repo_map_payload["suggested_validation_commands"] = self._scoped_validation_commands(
            requested_commands=[],
            project_profile=project_profile,
            repo_map=repo_map_payload,
        )
        result["repo_map"] = repo_map_payload
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def inspect_workspace_git(
        self,
        session_id: str,
        *,
        cwd: str | None = None,
    ) -> dict[str, object]:
        result = self.project_manager.inspect_git(session_id, cwd=cwd)
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def create_workspace_git_branch(
        self,
        *,
        session_id: str,
        name: str,
        cwd: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        result = self.project_manager.create_branch(
            session_id,
            name=name,
            cwd=cwd,
            source=source,
        )
        result["files"] = self.workspace_manager.list_files(session_id)
        result["review"] = self.review_workspace(session_id=session_id, cwd=cwd)
        return result

    def workspace_verification_payload(
        self,
        session_id: str,
        *,
        project_profile: dict[str, object] | None = None,
    ) -> dict[str, object]:
        active_profile = (
            project_profile
            if isinstance(project_profile, dict)
            else self.inspect_workspace_project(session_id)
        )
        verification = self._workspace_verification_profile(active_profile)
        return {
            "ok": True,
            "session_id": session_id,
            "verification": verification,
            "files": self.workspace_manager.list_files(session_id),
        }

    def list_workspace_snapshots(self, session_id: str) -> dict[str, object]:
        return {
            "ok": True,
            "session_id": session_id,
            "snapshots": self.snapshot_manager.list_snapshots(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def create_workspace_snapshot(
        self,
        *,
        session_id: str,
        label: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        try:
            snapshot = self.snapshot_manager.create_snapshot(
                session_id=session_id,
                label=label,
                source=source,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "label": str(label or "").strip(),
                "error": str(exc),
                "snapshots": self.snapshot_manager.list_snapshots(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }
        return {
            "ok": True,
            "session_id": session_id,
            "snapshot": snapshot,
            "snapshots": self.snapshot_manager.list_snapshots(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def restore_workspace_snapshot(
        self,
        *,
        session_id: str,
        snapshot_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        try:
            snapshot = self.snapshot_manager.restore_snapshot(
                session_id=session_id,
                snapshot_id=snapshot_id,
                source=source,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "snapshot_id": snapshot_id,
                "error": str(exc),
                "snapshots": self.snapshot_manager.list_snapshots(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }
        return {
            "ok": True,
            "session_id": session_id,
            "snapshot": snapshot,
            "snapshots": self.snapshot_manager.list_snapshots(session_id),
            "files": self.workspace_manager.list_files(session_id),
            "imports": self.project_manager.list_imports(session_id),
            "tasks": self.task_manager.list_tasks(session_id),
            "pending_patches": self.patch_manager.list_pending(session_id),
            "applied_changes": self.change_history.list_changes(session_id),
            "pending_approvals": self.list_pending_approvals(session_id)["approvals"],
            "review": self.review_workspace(session_id=session_id),
        }

    def resolve_workspace_task(
        self,
        *,
        session_id: str,
        task_id: str,
        approved: bool,
        note: str = "",
    ) -> dict[str, object]:
        result = self.task_manager.resolve_task(
            session_id=session_id,
            task_id=task_id,
            approved=approved,
            note=note,
        )
        task_payload = result.get("task", {})
        active_cwd = (
            str(task_payload.get("cwd", "")).strip()
            if isinstance(task_payload, dict)
            else ""
        ) or "."
        result["files"] = self.workspace_manager.list_files(session_id)
        result["review"] = self.review_workspace(session_id=session_id, cwd=active_cwd)
        if isinstance(task_payload, dict):
            git_handoff = task_payload.get("git_handoff", {})
            if not isinstance(git_handoff, dict) or not git_handoff:
                handoff_result = self.prepare_workspace_git_handoff(
                    session_id=session_id,
                    goal=str(task_payload.get("goal", "")).strip() or None,
                    task_id=task_id,
                    cwd=active_cwd,
                )
                if handoff_result.get("ok"):
                    git_handoff = handoff_result.get("handoff", {})
                    updated_task = self.task_manager.update_task(
                        session_id=session_id,
                        task_id=task_id,
                        git_handoff=git_handoff if isinstance(git_handoff, dict) else {},
                    )
                    if updated_task is not None:
                        result["task"] = updated_task
                        task_payload = updated_task
            result["plan"] = (
                dict(task_payload.get("plan", {}))
                if isinstance(task_payload.get("plan", {}), dict)
                else {}
            )
            result["git_handoff"] = (
                dict(task_payload.get("git_handoff", {}))
                if isinstance(task_payload.get("git_handoff", {}), dict)
                else {}
            )
        return result

    def _read_workspace_text_state(
        self, *, session_id: str, path: str
    ) -> tuple[bool, str, str]:
        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id,
            path,
        )
        if not target.exists():
            return False, "", relative
        if not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")
        return True, target.read_text(encoding="utf-8"), relative

    def _record_applied_workspace_change(
        self,
        *,
        session_id: str,
        path: str,
        operation: str,
        source: str,
        before_exists: bool,
        before_content: str,
        after_exists: bool,
        after_content: str,
        summary: str | None = None,
    ) -> dict[str, object] | None:
        return self.change_history.record_change(
            session_id=session_id,
            path=path,
            operation=operation,
            source=source,
            before_exists=before_exists,
            before_content=before_content,
            after_exists=after_exists,
            after_content=after_content,
            summary=summary,
        )

    def read_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            result = self.workspace_manager.read_text_file(
                session_id,
                path,
                max_chars=min(self.sandbox_policy.max_output_chars, 12_000),
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                start_line=start_line,
                end_line=end_line,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
            }
        return {
            "ok": True,
            "session_id": session_id,
            "path": result.path,
            "content": result.content,
            "total_lines": result.total_lines,
            "start_line": result.start_line,
            "end_line": result.end_line,
            "truncated": result.truncated,
            "size_bytes": result.size_bytes,
            "files": self.workspace_manager.list_files(session_id),
        }

    def write_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            before_exists, before_content, relative = self._read_workspace_text_state(
                session_id=session_id,
                path=path,
            )
            result = self.workspace_manager.write_text_file(
                session_id,
                path,
                content,
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                max_files=self.sandbox_policy.max_files,
            )
        except (IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
            }
        change = self._record_applied_workspace_change(
            session_id=session_id,
            path=result.path,
            operation="write",
            source=source,
            before_exists=before_exists,
            before_content=before_content,
            after_exists=True,
            after_content=content,
            summary=(
                f"Create {relative}" if result.created else f"Replace full file contents in {relative}"
            ),
        )
        return {
            "ok": True,
            "session_id": session_id,
            "path": result.path,
            "created": result.created,
            "size_bytes": result.size_bytes,
            "files": self.workspace_manager.list_files(session_id),
            "change": change,
        }

    def replace_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        expected_occurrences: int | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            before_exists, before_content, relative = self._read_workspace_text_state(
                session_id=session_id,
                path=path,
            )
            result = self.workspace_manager.replace_text_in_file(
                session_id,
                path,
                old_text,
                new_text,
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                replace_all=replace_all,
                expected_occurrences=expected_occurrences,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
            }
        _, after_content, _ = self._read_workspace_text_state(
            session_id=session_id,
            path=result.path,
        )
        change = self._record_applied_workspace_change(
            session_id=session_id,
            path=result.path,
            operation="replace",
            source=source,
            before_exists=before_exists,
            before_content=before_content,
            after_exists=True,
            after_content=after_content,
            summary=f"Replace {result.replacements} occurrence(s) in {relative}",
        )
        return {
            "ok": True,
            "session_id": session_id,
            "path": result.path,
            "replacements": result.replacements,
            "size_bytes": result.size_bytes,
            "files": self.workspace_manager.list_files(session_id),
            "change": change,
        }

    def preview_workspace_patch(
        self,
        *,
        session_id: str,
        path: str,
        patch: str,
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            result = self.workspace_manager.preview_text_patch(
                session_id,
                path,
                patch,
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                max_files=self.sandbox_policy.max_files,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
            }
        return {
            "ok": True,
            "session_id": session_id,
            "path": result.path,
            "can_apply": result.can_apply,
            "creates_file": result.creates_file,
            "current_hash": result.current_hash,
            "patched_hash": result.patched_hash,
            "hunk_count": result.hunk_count,
            "additions": result.additions,
            "deletions": result.deletions,
            "size_bytes": result.size_bytes,
            "issues": result.issues,
            "preview": result.preview,
            "hunks": [
                {
                    "old_start": hunk.old_start,
                    "old_count": hunk.old_count,
                    "new_start": hunk.new_start,
                    "new_count": hunk.new_count,
                    "additions": hunk.additions,
                    "deletions": hunk.deletions,
                }
                for hunk in result.hunks
            ],
            "files": self.workspace_manager.list_files(session_id),
        }

    def apply_workspace_text_patch(
        self,
        *,
        session_id: str,
        path: str,
        patch: str,
        expected_hash: str | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            before_exists, before_content, relative = self._read_workspace_text_state(
                session_id=session_id,
                path=path,
            )
            result = self.workspace_manager.apply_text_patch(
                session_id,
                path,
                patch,
                max_file_bytes=self.sandbox_policy.max_file_bytes,
                max_files=self.sandbox_policy.max_files,
                expected_hash=expected_hash,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
            }
        _, after_content, _ = self._read_workspace_text_state(
            session_id=session_id,
            path=result.path,
        )
        change = self._record_applied_workspace_change(
            session_id=session_id,
            path=result.path,
            operation="patch_apply",
            source=source,
            before_exists=before_exists,
            before_content=before_content,
            after_exists=True,
            after_content=after_content,
            summary=f"Apply {result.hunk_count} patch hunk(s) to {relative}",
        )
        return {
            "ok": True,
            "session_id": session_id,
            "path": result.path,
            "created": result.created,
            "current_hash": result.current_hash,
            "patched_hash": result.patched_hash,
            "hunk_count": result.hunk_count,
            "additions": result.additions,
            "deletions": result.deletions,
            "size_bytes": result.size_bytes,
            "files": self.workspace_manager.list_files(session_id),
            "change": change,
        }

    def list_pending_workspace_patches(self, session_id: str) -> dict[str, object]:
        return {
            "ok": True,
            "session_id": session_id,
            "pending_patches": self.patch_manager.list_pending(session_id),
            "pending_approvals": self.list_pending_approvals(session_id)["approvals"],
            "files": self.workspace_manager.list_files(session_id),
        }

    def list_applied_workspace_changes(self, session_id: str) -> dict[str, object]:
        return {
            "ok": True,
            "session_id": session_id,
            "applied_changes": self.change_history.list_changes(session_id),
            "verification": self.workspace_verification_payload(session_id)["verification"],
            "files": self.workspace_manager.list_files(session_id),
        }

    def verify_workspace_change(
        self,
        *,
        session_id: str,
        change_id: str,
        preset_id: str | None = None,
        cwd: str | None = None,
    ) -> dict[str, object]:
        change = self.change_history.get_change(session_id, change_id)
        if change is None:
            return {
                "ok": False,
                "session_id": session_id,
                "change_id": change_id,
                "error": f"Applied change `{change_id}` was not found.",
                "applied_changes": self.change_history.list_changes(session_id),
                "verification": self.workspace_verification_payload(session_id)["verification"],
                "files": self.workspace_manager.list_files(session_id),
            }
        verification_payload = self.workspace_verification_payload(session_id)
        verification_profile = verification_payload["verification"]
        preset = self._resolve_verification_preset(
            verification_profile=verification_profile,
            preset_id=preset_id,
        )
        if preset is None:
            return {
                "ok": False,
                "session_id": session_id,
                "change_id": change_id,
                "error": "No verification preset is available for this workspace yet.",
                "verification": verification_profile,
                "applied_changes": self.change_history.list_changes(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }
        active_cwd = str(cwd or preset.get("cwd", ".")).strip() or "."
        command_texts = [
            str(item).strip()
            for item in preset.get("commands", [])
            if str(item).strip()
        ]
        if not command_texts:
            return {
                "ok": False,
                "session_id": session_id,
                "change_id": change_id,
                "error": "The selected verification preset does not contain any runnable commands.",
                "verification": verification_profile,
                "applied_changes": self.change_history.list_changes(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }

        results: list[dict[str, object]] = []
        overall_ok = True
        for command_text in command_texts:
            try:
                argv = shlex.split(command_text, posix=True)
            except ValueError as exc:
                argv = []
                results.append(
                    {
                        "command": command_text,
                        "cwd": active_cwd,
                        "returncode": 126,
                        "timed_out": False,
                        "ok": False,
                        "backend": "",
                        "stdout": "",
                        "stderr": str(exc),
                    }
                )
                overall_ok = False
                continue
            if not argv:
                results.append(
                    {
                        "command": command_text,
                        "cwd": active_cwd,
                        "returncode": 126,
                        "timed_out": False,
                        "ok": False,
                        "backend": "",
                        "stdout": "",
                        "stderr": "Command parsing produced an empty argv.",
                    }
                )
                overall_ok = False
                continue
            command_result = self.executor.execute_command(
                session_id=session_id,
                command=argv,
                cwd=active_cwd,
                timeout_seconds=self.config.command_timeout_seconds,
                allowed_commands=(str(argv[0]).strip(),),
                max_command_tier="package",
                request_source="verification",
            )
            command_ok = command_result.returncode == 0 and not command_result.timed_out
            results.append(
                {
                    "command": command_text,
                    "cwd": command_result.cwd,
                    "returncode": command_result.returncode,
                    "timed_out": command_result.timed_out,
                    "ok": command_ok,
                    "backend": str(command_result.sandbox.get("backend", "")).strip(),
                    "stdout": command_result.stdout,
                    "stderr": command_result.stderr,
                }
            )
            if not command_ok:
                overall_ok = False

        verification = self._build_change_verification_record(
            preset=preset,
            cwd=active_cwd,
            results=results,
            ok=overall_ok,
        )
        updated_change = self.change_history.record_verification(
            session_id=session_id,
            change_id=change_id,
            verification=verification,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "change_id": change_id,
            "change": updated_change,
            "verification": (
                updated_change.get("verification", verification)
                if isinstance(updated_change, dict)
                else verification
            ),
            "verification_profile": verification_profile,
            "applied_changes": self.change_history.list_changes(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def propose_workspace_write(
        self,
        *,
        session_id: str,
        path: str,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            result = self.patch_manager.propose_write(
                session_id=session_id,
                path=path,
                content=content,
                source=source,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
                "pending_patches": self.patch_manager.list_pending(session_id),
                "pending_approvals": self.list_pending_approvals(session_id)["approvals"],
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def propose_workspace_replace(
        self,
        *,
        session_id: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        expected_occurrences: int | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        try:
            result = self.patch_manager.propose_replace(
                session_id=session_id,
                path=path,
                old_text=old_text,
                new_text=new_text,
                replace_all=replace_all,
                expected_occurrences=expected_occurrences,
                source=source,
            )
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "path": path,
                "error": str(exc),
                "files": files,
                "pending_patches": self.patch_manager.list_pending(session_id),
                "pending_approvals": self.list_pending_approvals(session_id)["approvals"],
            }
        result["files"] = self.workspace_manager.list_files(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def apply_workspace_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        patch = self._lookup_pending_patch(session_id, patch_id)
        before_exists = False
        before_content = ""
        relative_path: str | None = None
        if patch is not None:
            try:
                before_exists, before_content, relative_path = self._read_workspace_text_state(
                    session_id=session_id,
                    path=str(patch.get("path", "")).strip() or patch_id,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                before_exists = False
                before_content = ""
                relative_path = str(patch.get("path", "")).strip() or None
        result = self.patch_manager.apply_patch(session_id=session_id, patch_id=patch_id)
        self.patch_resume_states.pop((session_id, patch_id), None)
        self._save_approval_state()
        if result.get("ok") and patch is not None:
            path = str(result.get("path", "")).strip() or str(patch.get("path", "")).strip()
            try:
                after_exists, after_content, relative = self._read_workspace_text_state(
                    session_id=session_id,
                    path=path,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                after_exists = False
                after_content = ""
                relative = relative_path or path
            result["change"] = self._record_applied_workspace_change(
                session_id=session_id,
                path=relative,
                operation=str(result.get("operation", "patch")).strip() or "patch",
                source=str(patch.get("source", "")).strip() or "approval",
                before_exists=before_exists,
                before_content=before_content,
                after_exists=after_exists,
                after_content=after_content,
                summary=str(result.get("summary", "")).strip() or None,
            )
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def accept_workspace_patch_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> dict[str, object]:
        patch = self._lookup_pending_patch(session_id, patch_id)
        before_exists = False
        before_content = ""
        relative_path: str | None = None
        if patch is not None:
            try:
                before_exists, before_content, relative_path = self._read_workspace_text_state(
                    session_id=session_id,
                    path=str(patch.get("path", "")).strip() or patch_id,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                before_exists = False
                before_content = ""
                relative_path = str(patch.get("path", "")).strip() or None
        result = self.patch_manager.accept_hunk(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            keep_when_empty=(session_id, patch_id) in self.patch_resume_states,
        )
        self._save_approval_state()
        if result.get("ok") and patch is not None:
            path = str(result.get("path", "")).strip() or str(patch.get("path", "")).strip()
            try:
                after_exists, after_content, relative = self._read_workspace_text_state(
                    session_id=session_id,
                    path=path,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                after_exists = False
                after_content = ""
                relative = relative_path or path
            result["change"] = self._record_applied_workspace_change(
                session_id=session_id,
                path=relative,
                operation=str(result.get("operation", "patch_hunk")).strip()
                or "patch_hunk",
                source=str(patch.get("source", "")).strip() or "approval",
                before_exists=before_exists,
                before_content=before_content,
                after_exists=after_exists,
                after_content=after_content,
                summary=str(result.get("summary", "")).strip() or None,
            )
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def reject_workspace_patch_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> dict[str, object]:
        result = self.patch_manager.reject_hunk(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            keep_when_empty=(session_id, patch_id) in self.patch_resume_states,
        )
        self._save_approval_state()
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def accept_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> dict[str, object]:
        patch = self._lookup_pending_patch(session_id, patch_id)
        before_exists = False
        before_content = ""
        relative_path: str | None = None
        if patch is not None:
            try:
                before_exists, before_content, relative_path = self._read_workspace_text_state(
                    session_id=session_id,
                    path=str(patch.get("path", "")).strip() or patch_id,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                before_exists = False
                before_content = ""
                relative_path = str(patch.get("path", "")).strip() or None
        result = self.patch_manager.accept_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
            keep_when_empty=(session_id, patch_id) in self.patch_resume_states,
        )
        self._save_approval_state()
        if result.get("ok") and patch is not None:
            path = str(result.get("path", "")).strip() or str(patch.get("path", "")).strip()
            try:
                after_exists, after_content, relative = self._read_workspace_text_state(
                    session_id=session_id,
                    path=path,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError):
                after_exists = False
                after_content = ""
                relative = relative_path or path
            result["change"] = self._record_applied_workspace_change(
                session_id=session_id,
                path=relative,
                operation=str(result.get("operation", "patch_line")).strip()
                or "patch_line",
                source=str(patch.get("source", "")).strip() or "approval",
                before_exists=before_exists,
                before_content=before_content,
                after_exists=after_exists,
                after_content=after_content,
                summary=str(result.get("summary", "")).strip() or None,
            )
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def edit_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        after_text: str,
    ) -> dict[str, object]:
        result = self.patch_manager.edit_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
            after_text=after_text,
            keep_when_empty=(session_id, patch_id) in self.patch_resume_states,
        )
        self._save_approval_state()
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def reject_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> dict[str, object]:
        result = self.patch_manager.reject_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
            keep_when_empty=(session_id, patch_id) in self.patch_resume_states,
        )
        self._save_approval_state()
        result["files"] = self.workspace_manager.list_files(session_id)
        result["applied_changes"] = self.change_history.list_changes(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def reject_workspace_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        result = self.patch_manager.reject_patch(session_id=session_id, patch_id=patch_id)
        self.patch_resume_states.pop((session_id, patch_id), None)
        self._save_approval_state()
        result["files"] = self.workspace_manager.list_files(session_id)
        result["pending_approvals"] = self.list_pending_approvals(session_id)["approvals"]
        return result

    def rollback_workspace_change(
        self,
        *,
        session_id: str,
        change_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        result = self.change_history.rollback_change(
            session_id=session_id,
            change_id=change_id,
            source=source,
        )
        result["files"] = self.workspace_manager.list_files(session_id)
        return result

    def list_pending_approvals(self, session_id: str) -> dict[str, object]:
        approvals: list[dict[str, object]] = []
        session_approvals = self.command_approvals.get(session_id, {})
        approvals.extend(
            self._build_command_approval_payload(item)
            for item in sorted(
                session_approvals.values(),
                key=lambda approval: approval.created_at,
                reverse=True,
            )
        )
        for patch in self.patch_manager.list_pending(session_id):
            if not isinstance(patch, dict):
                continue
            approvals.append(
                self._build_patch_approval_payload(session_id=session_id, patch=patch)
            )
        approvals.sort(
            key=lambda approval: str(approval.get("created_at", "")),
            reverse=True,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "approvals": approvals,
            "files": self.workspace_manager.list_files(session_id),
        }

    async def stream_approval_decision(
        self,
        *,
        session_id: str,
        approval_id: str,
        approved: bool,
    ) -> AsyncIterator[str]:
        session = self.sessions.get_or_create(session_id, "Approval follow-up")
        approval_payload = self._lookup_command_approval_payload(
            session_id=session.id,
            approval_id=approval_id,
        )
        if approval_payload is None:
            patch = self._lookup_pending_patch(session.id, approval_id)
            if patch is not None:
                approval_payload = self._build_patch_approval_payload(
                    session_id=session.id,
                    patch=patch,
                )

        if approval_payload is None:
            yield self._sse_event(
                "meta",
                {
                    "session_id": session.id,
                    "mode": "agent_resume",
                    "approval_id": approval_id,
                    "approved": approved,
                    "approval": approval_payload,
                },
            )
            notice = f"Pending approval `{approval_id}` was not found."
            self.sessions.append_message(session.id, "assistant", notice)
            yield self._sse_event(
                "agent_step",
                {
                    "step": 0,
                    "kind": "approval_missing",
                    "content": notice,
                },
            )
            for piece in self._chunk_text(notice):
                yield self._sse_event("token", {"content": piece})
            yield self._sse_event("done", {"session_id": session.id})
            return

        persistent_run = self._start_approval_resume_run(
            session=session,
            approval_id=approval_id,
            approved=approved,
            approval_payload=approval_payload,
        )
        if persistent_run is not None:
            run_id, after_event_id = persistent_run
            async for event in self._stream_persisted_run(
                run_id=run_id,
                after_event_id=after_event_id,
            ):
                yield event
            return

        yield self._sse_event(
            "meta",
            {
                "session_id": session.id,
                "mode": "agent_resume",
                "approval_id": approval_id,
                "approved": approved,
                "approval": approval_payload,
            },
        )
        if approval_payload.get("kind") == "command":
            async for event in self._stream_command_approval_resolution(
                session=session,
                approval_id=approval_id,
                approved=approved,
            ):
                yield event
            return

        async for event in self._stream_patch_approval_resolution(
            session=session,
            patch_id=approval_id,
            approved=approved,
        ):
            yield event

    def review_workspace(
        self,
        *,
        session_id: str,
        cwd: str | None = None,
    ) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        pending_patches = self.patch_manager.list_pending(session_id)
        applied_changes = self.change_history.list_changes(session_id)
        changed_files: list[str] = []
        changed_entries: list[dict[str, str]] = []
        diff_sections: list[str] = []
        summary_lines: list[str] = []

        if pending_patches:
            summary_lines.append(
                f"Pending review: {len(pending_patches)} patch(es) across "
                f"{len({str(item.get('path', '')) for item in pending_patches if isinstance(item, dict)})} file(s)."
            )
            for patch in pending_patches[:6]:
                if not isinstance(patch, dict):
                    continue
                path = str(patch.get("path", "")).strip()
                summary = str(patch.get("summary", "")).strip()
                if path:
                    changed_files.append(path)
                    changed_entries.append(
                        {
                            "path": path,
                            "status": "P",
                            "source": "pending_patch",
                            "summary": summary or f"Pending patch for {path}",
                        }
                    )
                if summary:
                    summary_lines.append(f"- {summary}")
                diff_text = str(patch.get("diff", "")).strip()
                if diff_text:
                    diff_sections.append(diff_text)
        else:
            summary_lines.append("No pending patches.")

        if applied_changes:
            summary_lines.append(
                f"Applied workspace edits: {len(applied_changes)} change(s) tracked locally."
            )
            for change in applied_changes[:6]:
                if not isinstance(change, dict):
                    continue
                path = str(change.get("path", "")).strip()
                summary = str(change.get("summary", "")).strip()
                if path:
                    changed_files.append(path)
                    changed_entries.append(
                        {
                            "path": path,
                            "status": "A",
                            "source": "applied_change",
                            "summary": summary or f"Applied change on {path}",
                        }
                    )
                diff_text = str(change.get("diff", "")).strip()
                if diff_text:
                    diff_sections.append(diff_text)

        git_review = self.project_manager.collect_git_review(session_id, cwd=cwd)
        if not any(str(git_review.get(field, "")).strip() for field in ("status", "diff_stat", "diff")):
            git_review = self._collect_git_review(session_id, cwd=cwd)
        git_changed = git_review.get("changed_files", [])
        if isinstance(git_changed, list):
            for item in git_changed:
                path = str(item).strip()
                if path:
                    changed_files.append(path)
        git_status_entries = git_review.get("status_entries", [])
        if isinstance(git_status_entries, list):
            for entry in git_status_entries:
                if not isinstance(entry, dict):
                    continue
                path = str(entry.get("path", "")).strip()
                if not path:
                    continue
                changed_entries.append(
                    {
                        "path": path,
                        "status": str(entry.get("status", "")).strip() or "?",
                        "source": "git",
                        "summary": str(entry.get("summary", "")).strip() or path,
                    }
                )
        git_status = str(git_review.get("status", "")).strip()
        if git_status:
            summary_lines.append(
                f"Git status reports {len(git_changed) if isinstance(git_changed, list) else 0} changed file(s)."
            )
        git_diff_stat = str(git_review.get("diff_stat", "")).strip()
        if git_diff_stat:
            summary_lines.append(git_diff_stat)
        git_diff = str(git_review.get("diff", "")).strip()
        if git_diff:
            diff_sections.append(git_diff)

        unique_changed_files = sorted({item for item in changed_files if item})
        if not unique_changed_files:
            summary_lines.append("Workspace looks clean right now.")

        diff_text = "\n\n".join(section for section in diff_sections if section).strip()
        if len(diff_text) > 12_000:
            diff_text = f"{diff_text[:12_000]}\n...[review diff truncated]..."

        return {
            "ok": True,
            "session_id": session_id,
            "summary": "\n".join(summary_lines),
            "changed_files": unique_changed_files,
            "changed_entries": _dedupe_changed_entries(changed_entries),
            "diff_stat": git_diff_stat,
            "diff": diff_text,
            "git": git_review,
            "pending_patches": pending_patches,
            "files": files,
        }

    def _collect_git_review(
        self,
        session_id: str,
        *,
        cwd: str | None = None,
    ) -> dict[str, object]:
        review = {
            "status": "",
            "diff_stat": "",
            "diff": "",
            "changed_files": [],
            "status_entries": [],
        }
        commands = (
            ("status", ["git", "status", "--short"]),
            ("diff_stat", ["git", "diff", "--stat"]),
            ("diff", ["git", "diff", "--no-ext-diff", "--unified=3"]),
        )
        for field, command in commands:
            result = self.execute_command(
                session_id=session_id,
                command=command,
                cwd=str(cwd or ".").strip() or ".",
                timeout_seconds=min(self.config.command_timeout_seconds, 15.0),
                max_command_tier="read_only",
                request_source="review",
            )
            if result.get("returncode") != 0:
                continue
            review[field] = str(result.get("stdout", "") or "").strip()
        status = str(review.get("status", "")).strip()
        if status:
            changed_files: list[str] = []
            status_entries: list[dict[str, str]] = []
            for line in status.splitlines():
                raw_line = line.rstrip()
                if not raw_line:
                    continue
                status_code = raw_line[:2].strip() or "?"
                path = raw_line[3:].strip() if len(raw_line) > 3 else raw_line.strip()
                if not path:
                    continue
                changed_files.append(path)
                status_entries.append(
                    {
                        "status": status_code,
                        "path": path,
                        "summary": f"{status_code} {path}".strip(),
                    }
                )
            review["changed_files"] = changed_files
            review["status_entries"] = status_entries
        return review

    async def stream_workspace_task(
        self,
        *,
        session_id: str | None,
        goal: str,
        cwd: str | None,
        test_commands: list[str],
        fast_mode: bool,
        title: str | None = None,
    ) -> AsyncIterator[str]:
        task_goal = goal.strip()
        active_cwd = str(cwd or ".").strip() or "."
        active_tests = [command.strip() for command in test_commands if command.strip()]
        session = self.sessions.get_or_create(session_id, title or task_goal)
        session_message = f"Workspace task: {task_goal}"
        self.sessions.append_message(session.id, "user", session_message)
        retrieval_hits = self.knowledge.search(
            task_goal,
            limit=max(1, min(self.config.retrieval_k, 4)),
        )
        run_config = AgentRunConfig(
            permissions=self.agent_permissions,
            max_command_tier="test",
            allowed_commands=self._agent_allowed_commands("test"),
        )
        project_profile = self.inspect_workspace_project(session.id)
        task_plan_payload = self.plan_workspace_task(
            session_id=session.id,
            goal=task_goal,
            cwd=active_cwd,
            test_commands=active_tests,
            title=title,
        )
        task_plan = (
            dict(task_plan_payload.get("plan", {}))
            if isinstance(task_plan_payload.get("plan", {}), dict)
            else {}
        )
        task_payload = self.task_manager.start_task(
            session_id=session.id,
            goal=task_goal,
            cwd=active_cwd,
            test_commands=active_tests,
            source="ui",
            title=title,
            plan=task_plan,
        )
        route = self._choose_model_decision(
            prompt=session_message,
            fast_mode=fast_mode,
            mode="agent",
            attachments=[],
        )
        model = route.model
        tool_messages = self._initial_agent_context(
            session=session,
            user_message=session_message,
            retrieval_hits=retrieval_hits,
            tool_results=[],
            attachments=[],
            run_config=run_config,
        )
        tool_messages.insert(
            1,
            {
                "role": "system",
                "content": self._build_task_runner_brief(
                    goal=task_goal,
                    cwd=active_cwd,
                    test_commands=active_tests,
                    project_profile=project_profile,
                    plan=task_plan,
                ),
            },
        )

        yield self._sse_event(
            "task_plan",
            {
                "session_id": session.id,
                "task_id": task_payload["id"],
                "goal": task_goal,
                "cwd": active_cwd,
                "plan": task_plan,
                "project": task_plan_payload.get("project", {}),
                "git": task_plan_payload.get("git", {}),
            },
        )
        yield self._sse_event(
            "meta",
            {
                "session_id": session.id,
                "mode": "task",
                "task": task_payload,
                "plan": task_plan,
                "retrieval": [asdict(hit) for hit in retrieval_hits],
                "model_route": model,
                "model_router": route.payload(),
            },
        )

        observed_tests: set[str] = set()
        final_message = ""
        blocked = False
        async for raw_event in self._run_agent_loop(
            session=session,
            tool_messages=tool_messages,
            fast_mode=fast_mode,
            attachments=[],
            model=model,
            cache_key=None,
            start_step_index=0,
            run_config=run_config,
        ):
            parsed_event = self._parse_sse_event(raw_event)
            if parsed_event is not None:
                event_name, payload = parsed_event
                if event_name == "agent_step":
                    kind = str(payload.get("kind", "")).strip()
                    if kind == "action":
                        tool = str(payload.get("tool", "")).strip()
                        args = payload.get("args", {})
                        phase = self._task_phase_for_action(
                            tool=tool,
                            args=args if isinstance(args, dict) else {},
                            test_commands=active_tests,
                        )
                        if phase:
                            self.task_manager.update_task(
                                session_id=session.id,
                                task_id=str(task_payload["id"]),
                                phase=phase,
                                status="running",
                                summary=self._task_phase_summary(
                                    phase=phase,
                                    tool=tool,
                                    args=args if isinstance(args, dict) else {},
                                ),
                            )
                        if tool == "run_command":
                            command_text = self._command_text_from_agent_args(args)
                            if self._matches_task_test_command(command_text, active_tests):
                                observed_tests.add(command_text)
                    elif kind == "approval_required":
                        blocked = True
                        self.task_manager.update_task(
                            session_id=session.id,
                            task_id=str(task_payload["id"]),
                            phase="approve",
                            status="blocked",
                            summary=str(payload.get("content", "")).strip()
                            or "Task paused for approval.",
                        )
                    elif kind == "final":
                        final_message = str(payload.get("content", "")).strip()
                    elif kind in {"fallback", "limit"}:
                        blocked = True
                        self.task_manager.update_task(
                            session_id=session.id,
                            task_id=str(task_payload["id"]),
                            phase="review",
                            status="blocked",
                            summary=str(payload.get("content", "")).strip()
                            or "Task stopped before completion.",
                        )
            yield raw_event

        if blocked:
            return

        review = self.review_workspace(session_id=session.id, cwd=active_cwd)
        changed_files = review.get("changed_files", [])
        if not isinstance(changed_files, list):
            changed_files = []
        missing_tests = [
            command
            for command in active_tests
            if not self._matches_task_test_command(command, list(observed_tests))
        ]
        if final_message:
            status = "ready_for_approval" if not missing_tests else "blocked"
            phase = "approve" if not missing_tests else "test"
            summary = (
                "Task finished. Review the diff and approve when ready."
                if not missing_tests
                else "Task finished, but one or more required test commands were not run."
            )
            updated_task = self.task_manager.update_task(
                session_id=session.id,
                task_id=str(task_payload["id"]),
                phase=phase,
                status=status,
                summary=summary,
                final_message=final_message,
                review_summary=str(review.get("summary", "")).strip(),
                changed_files=[str(item) for item in changed_files if str(item).strip()],
                approval_note=(
                    ""
                    if not missing_tests
                    else "Missing test commands: " + ", ".join(missing_tests)
                ),
                plan=task_plan,
            )
            git_handoff: dict[str, object] = {}
            handoff_payload = self.prepare_workspace_git_handoff(
                session_id=session.id,
                goal=task_goal,
                task_id=str(task_payload["id"]),
                cwd=active_cwd,
            )
            if handoff_payload.get("ok") and isinstance(
                handoff_payload.get("handoff", {}), dict
            ):
                git_handoff = dict(handoff_payload.get("handoff", {}))
                refreshed_task = self.task_manager.update_task(
                    session_id=session.id,
                    task_id=str(task_payload["id"]),
                    git_handoff=git_handoff,
                )
                if refreshed_task is not None:
                    updated_task = refreshed_task
            yield self._sse_event(
                "task_result",
                {
                    "session_id": session.id,
                    "task": updated_task,
                    "plan": task_plan,
                    "git_handoff": git_handoff,
                    "review": review,
                    "missing_tests": missing_tests,
                },
            )
            return

        self.task_manager.update_task(
            session_id=session.id,
            task_id=str(task_payload["id"]),
            phase="review",
            status="blocked",
            summary="Task ended without a final summary from the agent.",
            review_summary=str(review.get("summary", "")).strip(),
            changed_files=[str(item) for item in changed_files if str(item).strip()],
            plan=task_plan,
        )
        yield self._sse_event(
            "task_result",
            {
                "session_id": session.id,
                "task": self.task_manager.list_tasks(session.id)[0]
                if self.task_manager.list_tasks(session.id)
                else None,
                "plan": task_plan,
                "git_handoff": {},
                "review": review,
                "missing_tests": missing_tests,
            },
        )

    def _recover_leased_run_jobs(self) -> None:
        recovered_jobs = self.agent_runs.requeue_leased_jobs()
        for job in recovered_jobs:
            run_id = str(job.get("run_id", "")).strip()
            if not run_id:
                continue
            run = self.agent_runs.get_run(run_id)
            if run is None:
                continue
            if str(run.get("status", "")).strip() in TERMINAL_RUN_STATUSES:
                continue
            self.agent_runs.update_run(
                run_id,
                status="queued",
                error_text="",
                completed_at="",
                blocked_on_approval_id="",
                blocked_on_kind="",
            )
            self.agent_runs.append_event(
                run_id=run_id,
                event_name="agent_step",
                payload={
                    "step": 0,
                    "kind": "worker_recovered",
                    "content": "Run requeued after worker restart.",
                },
            )

    def start_background_workers(self) -> None:
        self._recover_leased_run_jobs()
        if not self.config.agent_worker_enabled:
            return
        with self._worker_threads_lock:
            alive = [thread for thread in self._worker_threads if thread.is_alive()]
            if alive:
                self._worker_threads = alive
                return
            self._worker_generation += 1
            generation = self._worker_generation
            stop_event = threading.Event()
            self._worker_stop = stop_event
            threads = [
                threading.Thread(
                    target=self._worker_loop,
                    args=(f"worker-{generation}-{index + 1}", stop_event),
                    name=f"forge-agent-worker-{generation}-{index + 1}",
                    daemon=True,
                )
                for index in range(max(1, self.config.agent_worker_concurrency))
            ]
            self._worker_threads = threads
        for thread in threads:
            thread.start()

    def stop_background_workers(self, *, timeout_seconds: float = 1.0) -> None:
        stop_event = self._worker_stop
        stop_event.set()
        with self._worker_threads_lock:
            threads = list(self._worker_threads)
            self._worker_threads = []
        deadline = max(0.0, float(timeout_seconds))
        for thread in threads:
            thread.join(timeout=deadline)

    def _ensure_background_workers_started(self) -> None:
        self.start_background_workers()

    def _worker_loop(self, worker_id: str, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            claimed = self.agent_runs.claim_next_job(
                worker_id=worker_id,
                lease_seconds=self.config.agent_worker_lease_seconds,
            )
            if claimed is None:
                stop_event.wait(self.config.agent_worker_poll_seconds)
                continue
            self._run_claimed_job(worker_id=worker_id, claimed=claimed)

    def _start_job_heartbeat(
        self,
        *,
        run_id: str,
        lease_token: str,
    ) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()

        def target() -> None:
            while not stop.wait(self.config.agent_worker_heartbeat_seconds):
                if not self.agent_runs.heartbeat_job(
                    run_id=run_id,
                    lease_token=lease_token,
                    lease_seconds=self.config.agent_worker_lease_seconds,
                ):
                    return

        thread = threading.Thread(
            target=target,
            name=f"forge-agent-heartbeat-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return stop, thread

    def _run_claimed_job(
        self,
        *,
        worker_id: str,
        claimed: dict[str, object],
    ) -> None:
        run_id = str(claimed.get("run_id", "")).strip()
        lease_token = str(claimed.get("lease_token", "")).strip()
        if not run_id or not lease_token:
            return
        heartbeat_stop, heartbeat_thread = self._start_job_heartbeat(
            run_id=run_id,
            lease_token=lease_token,
        )
        try:
            asyncio.run(self._process_claimed_job(worker_id=worker_id, claimed=claimed))
            run = self.agent_runs.get_run(run_id)
            queue_status = "completed"
            if run is not None:
                status = str(run.get("status", "")).strip()
                if status == "failed":
                    queue_status = "failed"
                elif status == "cancelled":
                    queue_status = "cancelled"
            self.agent_runs.complete_job(
                run_id=run_id,
                lease_token=lease_token,
                queue_status=queue_status,
                error_text=str(run.get("error_text", "")).strip() if run is not None else "",
            )
        except Exception as exc:  # pragma: no cover - defensive background safety
            notice = f"Agent worker failed unexpectedly: {exc}"
            next_job = self.agent_runs.release_job_for_retry(
                run_id=run_id,
                lease_token=lease_token,
                delay_seconds=self.config.agent_worker_retry_delay_seconds,
                error_text=notice,
            )
            if next_job is not None and str(next_job.get("queue_status", "")).strip() == "queued":
                self.agent_runs.update_run(
                    run_id,
                    status="queued",
                    error_text="",
                    completed_at="",
                    blocked_on_approval_id="",
                    blocked_on_kind="",
                )
                self.agent_runs.append_event(
                    run_id=run_id,
                    event_name="agent_step",
                    payload={
                        "step": 0,
                        "kind": "worker_retry",
                        "content": (
                            f"{notice} Retrying attempt "
                            f"{int(next_job.get('attempt_count', 0)) + 1} "
                            f"of {int(next_job.get('max_attempts', 1))}."
                        ),
                    },
                )
            else:
                session_id = str(claimed.get("payload", {}).get("session_id", "")).strip()
                if not session_id:
                    run = self.agent_runs.get_run(run_id)
                    session_id = str(run.get("session_id", "")).strip() if run is not None else ""
                if session_id:
                    self._record_background_run_failure(
                        run_id=run_id,
                        session_id=session_id,
                        error_text=notice,
                    )
                self.agent_runs.complete_job(
                    run_id=run_id,
                    lease_token=lease_token,
                    queue_status="failed",
                    error_text=notice,
                )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

    async def _process_claimed_job(
        self,
        *,
        worker_id: str,
        claimed: dict[str, object],
    ) -> None:
        del worker_id
        run_id = str(claimed.get("run_id", "")).strip()
        job_type = str(claimed.get("job_type", "")).strip()
        payload = claimed.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        run = self.agent_runs.get_run(run_id)
        if run is None:
            raise RuntimeError(f"Run `{run_id}` was not found.")
        status = str(run.get("status", "")).strip()
        if job_type == "agent_chat" and status in TERMINAL_RUN_STATUSES:
            return
        if job_type == "approval_resume" and status in {"completed", "failed", "cancelled", "interrupted"}:
            return
        if job_type == "agent_chat":
            await self._process_agent_chat_job(run=run, payload=payload)
            return
        if job_type == "approval_resume":
            await self._process_approval_resume_job(run=run, payload=payload)
            return
        raise RuntimeError(f"Unknown queued run job type `{job_type}`.")

    async def _process_agent_chat_job(
        self,
        *,
        run: dict[str, object],
        payload: dict[str, object],
    ) -> None:
        session_id = str(payload.get("session_id") or run.get("session_id") or "").strip()
        user_message = str(payload.get("message") or run.get("user_message") or "").strip()
        if not session_id or not user_message:
            raise RuntimeError("Queued agent chat job is missing its session or message.")
        session = self.sessions.get_or_create(session_id, user_message)
        fast_mode = bool(payload.get("fast_mode", run.get("fast_mode", False)))
        retrieval_k = max(1, int(payload.get("retrieval_k", self.config.retrieval_k) or self.config.retrieval_k))
        attachments = self._deserialize_attachments(payload.get("attachments"))
        retrieval_hits = self.knowledge.search(user_message, limit=max(1, retrieval_k))
        tool_results = await self.tools.run(
            user_message,
            enable_remote_fetch=self.config.enable_remote_fetch,
            mode="agent",
        )
        cache_key = self._cache_key(
            session=session,
            user_message=user_message,
            fast_mode=fast_mode,
            retrieval_hits=retrieval_hits,
            tool_results=tool_results,
            mode="agent",
            attachments=attachments,
        )
        run_config = self._default_agent_run_config()
        tool_messages = self._initial_agent_context(
            session=session,
            user_message=user_message,
            retrieval_hits=retrieval_hits,
            tool_results=tool_results,
            attachments=attachments,
            run_config=run_config,
        )
        await self._persist_run_stream(
            run_id=str(run.get("id", "")),
            session_id=session.id,
            event_stream=self._run_agent_loop(
                session=session,
                tool_messages=tool_messages,
                fast_mode=fast_mode,
                attachments=attachments,
                model=str(run.get("model", "")).strip()
                or self._choose_model(
                    prompt=str(payload.get("message", "")),
                    fast_mode=fast_mode,
                    mode="agent",
                    attachments=attachments,
                ),
                cache_key=cache_key,
                start_step_index=0,
                run_config=run_config,
                run_id=str(run.get("id", "")),
                cancel_requested=lambda: self.agent_runs.cancel_requested(str(run.get("id", ""))),
            ),
        )

    async def _process_approval_resume_job(
        self,
        *,
        run: dict[str, object],
        payload: dict[str, object],
    ) -> None:
        session_id = str(payload.get("session_id") or run.get("session_id") or "").strip()
        approval_id = str(payload.get("approval_id", "")).strip()
        approved = bool(payload.get("approved"))
        if not session_id or not approval_id:
            raise RuntimeError("Queued approval resume job is missing approval context.")
        session = self.sessions.get_or_create(session_id, "Approval follow-up")
        approval_payload = self._lookup_command_approval_payload(
            session_id=session.id,
            approval_id=approval_id,
        )
        if approval_payload is None:
            patch = self._lookup_pending_patch(session.id, approval_id)
            if patch is not None:
                approval_payload = self._build_patch_approval_payload(
                    session_id=session.id,
                    patch=patch,
                )
        if approval_payload is None:
            stream = self._stream_missing_approval_notice(
                session=session,
                approval_id=approval_id,
            )
        elif approval_payload.get("kind") == "command":
            stream = self._stream_command_approval_resolution(
                session=session,
                approval_id=approval_id,
                approved=approved,
            )
        else:
            stream = self._stream_patch_approval_resolution(
                session=session,
                patch_id=approval_id,
                approved=approved,
            )
        await self._persist_run_stream(
            run_id=str(run.get("id", "")),
            session_id=session.id,
            event_stream=stream,
        )

    def _deserialize_attachments(self, value: object) -> list[Attachment]:
        if not isinstance(value, list):
            return []
        items: list[Attachment] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            mime_type = str(item.get("mime_type", "")).strip()
            kind = str(item.get("kind", "")).strip()
            if not name or not mime_type or kind not in {"text", "image"}:
                continue
            items.append(
                Attachment(
                    name=name,
                    mime_type=mime_type,
                    content=str(item.get("content", "")),
                    kind=kind,
                )
            )
        return items

    def _enqueue_run_job(
        self,
        *,
        run_id: str,
        job_type: str,
        payload: dict[str, object],
    ) -> dict[str, object] | None:
        queued = self.agent_runs.enqueue_job(
            run_id=run_id,
            job_type=job_type,
            payload=payload,
            max_attempts=self.config.agent_worker_max_attempts,
        )
        self._ensure_background_workers_started()
        return queued

    def _record_background_run_failure(
        self,
        *,
        run_id: str,
        session_id: str,
        error_text: str,
    ) -> None:
        notice = error_text.strip() or "Agent run failed."
        self.sessions.append_message(session_id, "assistant", notice)
        self.agent_runs.append_event(
            run_id=run_id,
            event_name="agent_step",
            payload={
                "step": 0,
                "kind": "error",
                "content": notice,
            },
        )
        for piece in self._chunk_text(notice):
            self.agent_runs.append_event(
                run_id=run_id,
                event_name="token",
                payload={"content": piece},
            )
        self.agent_runs.append_event(
            run_id=run_id,
            event_name="done",
            payload={"session_id": session_id, "run_id": run_id},
        )
        self.agent_runs.update_run(
            run_id,
            status="failed",
            error_text=notice,
            final_message=notice,
            completed_at=_utc_now(),
        )

    async def _persist_run_stream(
        self,
        *,
        run_id: str,
        session_id: str,
        event_stream: AsyncIterator[str],
    ) -> None:
        run = self.agent_runs.get_run(run_id)
        if run is None:
            return
        started_at = str(run.get("started_at", "")).strip() or _utc_now()
        self.agent_runs.update_run(
            run_id,
            status="running",
            started_at=started_at,
            completed_at="",
            error_text="",
            blocked_on_approval_id="",
            blocked_on_kind="",
        )
        terminal_status = ""
        final_message = ""
        blocked_on_approval_id = ""
        blocked_on_kind = ""
        async for raw_event in event_stream:
            parsed_event = self._parse_sse_event(raw_event)
            if parsed_event is None:
                continue
            event_name, payload = parsed_event
            self.agent_runs.append_event(
                run_id=run_id,
                event_name=event_name,
                payload=payload,
            )
            if event_name == "agent_step":
                kind = str(payload.get("kind", "")).strip()
                content = str(payload.get("content", "")).strip()
                if kind == "approval_required":
                    terminal_status = "blocked"
                    approval = payload.get("approval", {})
                    if isinstance(approval, dict):
                        blocked_on_approval_id = str(approval.get("id", "")).strip()
                        blocked_on_kind = str(approval.get("kind", "")).strip()
                    final_message = content or final_message
                elif kind in {"final", "fallback", "limit"}:
                    terminal_status = "completed"
                    final_message = content or final_message
                elif kind == "cancelled":
                    terminal_status = "cancelled"
                    final_message = content or final_message
                elif kind in {"error", "approval_missing"}:
                    terminal_status = "failed"
                    final_message = content or final_message
        current = self.agent_runs.get_run(run_id)
        if current is None:
            return
        if not terminal_status:
            if current.get("cancel_requested"):
                terminal_status = "cancelled"
                final_message = final_message or "Agent run was cancelled."
            elif str(current.get("status", "")).strip() == "interrupted":
                terminal_status = "interrupted"
                final_message = (
                    final_message
                    or str(current.get("error_text", "")).strip()
                    or "Agent run was interrupted."
                )
            else:
                terminal_status = "completed"
        completed_at = _utc_now() if terminal_status in TERMINAL_RUN_STATUSES else ""
        self.agent_runs.update_run(
            run_id,
            status=terminal_status,
            final_message=final_message,
            error_text=(
                final_message
                if terminal_status in {"failed", "interrupted", "cancelled"}
                else ""
            ),
            blocked_on_approval_id=blocked_on_approval_id,
            blocked_on_kind=blocked_on_kind,
            completed_at=completed_at,
        )

    async def _stream_persisted_run(
        self,
        *,
        run_id: str,
        after_event_id: int = 0,
    ) -> AsyncIterator[str]:
        last_event_id = max(0, int(after_event_id))
        while True:
            events = self.agent_runs.list_events(
                run_id=run_id,
                after_id=last_event_id,
                limit=200,
            )
            for event in events:
                last_event_id = int(event["id"])
                payload = dict(event["payload"])
                payload["run_id"] = run_id
                payload["run_event_id"] = last_event_id
                yield self._sse_event(str(event["event"]), payload)
            run = self.agent_runs.get_run(run_id)
            if run is None:
                notice = f"Run `{run_id}` was not found."
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": 0,
                        "kind": "error",
                        "content": notice,
                        "run_id": run_id,
                    },
                )
                yield self._sse_event("done", {"run_id": run_id})
                return
            if str(run.get("status", "")).strip() in TERMINAL_RUN_STATUSES and not events:
                return
            await asyncio.sleep(0.05)

    def _start_agent_chat_run(
        self,
        *,
        session: ChatSession,
        user_message: str,
        fast_mode: bool,
        retrieval_k: int,
        retrieval_hits: list[SearchHit],
        tool_results: list[ToolResult],
        attachments: list[Attachment],
        cache_key: str,
        meta: dict[str, object],
    ) -> tuple[dict[str, object], int]:
        route = self._choose_model_decision(
            prompt=user_message,
            fast_mode=fast_mode,
            mode="agent",
            attachments=attachments,
        )
        model = route.model
        run = self.agent_runs.create_run(
            session_id=session.id,
            kind="agent_chat",
            title=session.title,
            mode="agent",
            user_message=user_message,
            fast_mode=fast_mode,
            model=model,
            request={
                "message": user_message,
                "fast_mode": fast_mode,
                "retrieval_k": retrieval_k,
                "attachments": [
                    {
                        "name": attachment.name,
                        "mime_type": attachment.mime_type,
                        "content": attachment.content,
                        "kind": attachment.kind,
                    }
                    for attachment in attachments
                ],
            },
        )
        run_id = str(run.get("id", "")).strip()
        meta_payload = dict(meta)
        meta_payload["run_id"] = run_id
        meta_payload["model_router"] = route.payload()
        meta_event_id = self.agent_runs.append_event(
            run_id=run_id,
            event_name="meta",
            payload=meta_payload,
        )
        self._enqueue_run_job(
            run_id=run_id,
            job_type="agent_chat",
            payload={
                "session_id": session.id,
                "message": user_message,
                "fast_mode": fast_mode,
                "retrieval_k": retrieval_k,
                "attachments": [
                    {
                        "name": attachment.name,
                        "mime_type": attachment.mime_type,
                        "content": attachment.content,
                        "kind": attachment.kind,
                    }
                    for attachment in attachments
                ],
                "cache_key_hint": cache_key,
            },
        )
        return run, meta_event_id

    def _approval_run_id(
        self, *, session_id: str, approval_id: str
    ) -> str:
        resume_state = self.command_resume_states.get(approval_id)
        if resume_state is None:
            resume_state = self.patch_resume_states.get((session_id, approval_id))
        return str(resume_state.run_id).strip() if resume_state is not None else ""

    def _start_approval_resume_run(
        self,
        *,
        session: ChatSession,
        approval_id: str,
        approved: bool,
        approval_payload: dict[str, object],
    ) -> tuple[str, int] | None:
        run_id = self._approval_run_id(session_id=session.id, approval_id=approval_id)
        if not run_id:
            return None
        run = self.agent_runs.get_run(run_id)
        if run is None:
            return None
        after_event_id = int(run.get("last_event_id", 0))
        self.agent_runs.append_event(
            run_id=run_id,
            event_name="meta",
            payload={
                "session_id": session.id,
                "mode": "agent_resume",
                "approval_id": approval_id,
                "approved": approved,
                "approval": approval_payload,
                "run_id": run_id,
            },
        )
        self.agent_runs.update_run(
            run_id,
            status="queued",
            error_text="",
            completed_at="",
            blocked_on_approval_id="",
            blocked_on_kind="",
        )
        self._enqueue_run_job(
            run_id=run_id,
            job_type="approval_resume",
            payload={
                "session_id": session.id,
                "approval_id": approval_id,
                "approved": approved,
            },
        )
        return run_id, after_event_id

    async def stream_chat(
        self,
        *,
        session_id: str | None,
        user_message: str,
        fast_mode: bool,
        retrieval_k: int,
        mode: str,
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        session = self.sessions.get_or_create(session_id, user_message)
        self.sessions.append_message(session.id, "user", user_message)
        self.memory.remember_from_user_text(user_message)

        retrieval_hits = self.knowledge.search(user_message, limit=max(1, retrieval_k))
        tool_results = await self.tools.run(
            user_message,
            enable_remote_fetch=self.config.enable_remote_fetch,
            mode=mode,
        )
        attachment_hits = self._attachment_context(attachments)
        cache_key = self._cache_key(
            session=session,
            user_message=user_message,
            fast_mode=fast_mode,
            retrieval_hits=retrieval_hits,
            tool_results=tool_results,
            mode=mode,
            attachments=attachments,
        )
        route = self._choose_model_decision(
            prompt=user_message,
            fast_mode=fast_mode,
            mode=mode,
            attachments=attachments,
        )
        meta = {
            "session_id": session.id,
            "retrieval": [asdict(hit) for hit in retrieval_hits],
            "tools": [asdict(result) for result in tool_results],
            "attachments": attachment_hits,
            "memory": self.memory.facts(),
            "mode": mode,
            "model_route": route.model,
            "model_router": route.payload(),
            "cache_hit": False,
        }

        cached = self.cache.get(cache_key)
        if cached is not None and mode != "agent":
            meta["cache_hit"] = True
            yield self._sse_event("meta", meta)
            for piece in self._chunk_text(cached):
                yield self._sse_event("token", {"content": piece})
            self.sessions.append_message(session.id, "assistant", cached)
            yield self._sse_event("done", {"session_id": session.id})
            return

        if mode == "agent":
            run, meta_event_id = self._start_agent_chat_run(
                session=session,
                user_message=user_message,
                fast_mode=fast_mode,
                retrieval_k=retrieval_k,
                retrieval_hits=retrieval_hits,
                tool_results=tool_results,
                attachments=attachments,
                cache_key=cache_key,
                meta=meta,
            )
            async for event in self._stream_persisted_run(
                run_id=str(run.get("id", "")),
                after_event_id=max(0, meta_event_id - 1),
            ):
                yield event
            return
        yield self._sse_event("meta", meta)
        messages = self._compose_messages(
            session=session,
            user_message=user_message,
            retrieval_hits=retrieval_hits,
            tool_results=tool_results,
            fast_mode=fast_mode,
            mode=mode,
            attachments=attachments,
        )
        chunks: list[str] = []
        async for chunk in self.provider.stream_reply(
            messages=messages,
            fast_mode=fast_mode,
            mode=mode,
            model=route.model,
            attachments=attachments,
        ):
            chunks.append(chunk)
            yield self._sse_event("token", {"content": chunk})
        reply = "".join(chunks).strip()
        if not reply:
            reply = "No response came back from your model endpoint."
        self.cache.put(cache_key, reply)
        self.sessions.append_message(session.id, "assistant", reply)
        yield self._sse_event("done", {"session_id": session.id})

    async def _stream_agent_chat(
        self,
        *,
        session: ChatSession,
        user_message: str,
        fast_mode: bool,
        retrieval_hits: list[SearchHit],
        tool_results: list[ToolResult],
        attachments: list[Attachment],
        cache_key: str,
    ) -> AsyncIterator[str]:
        run_config = self._default_agent_run_config()
        model = self._choose_model(
            prompt=user_message,
            fast_mode=fast_mode,
            mode="agent",
            attachments=attachments,
        )
        tool_messages = self._initial_agent_context(
            session=session,
            user_message=user_message,
            retrieval_hits=retrieval_hits,
            tool_results=tool_results,
            attachments=attachments,
            run_config=run_config,
        )

        async for event in self._run_agent_loop(
            session=session,
            tool_messages=tool_messages,
            fast_mode=fast_mode,
            attachments=attachments,
            model=model,
            cache_key=cache_key,
            start_step_index=0,
            run_config=run_config,
        ):
            yield event

    async def _run_agent_loop(
        self,
        *,
        session: ChatSession,
        tool_messages: list[dict[str, str]],
        fast_mode: bool,
        attachments: list[Attachment],
        model: str,
        cache_key: str | None,
        start_step_index: int,
        run_config: AgentRunConfig,
        run_id: str = "",
        cancel_requested: Callable[[], bool] | None = None,
    ) -> AsyncIterator[str]:
        active_messages = [dict(message) for message in tool_messages]

        for step_index in range(start_step_index, self.max_agent_steps):
            if cancel_requested is not None and cancel_requested():
                final_reply = "Agent run was cancelled before the next step started."
                self.sessions.append_message(session.id, "assistant", final_reply)
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": step_index + 1,
                        "kind": "cancelled",
                        "content": final_reply,
                    },
                )
                for piece in self._chunk_text(final_reply):
                    yield self._sse_event("token", {"content": piece})
                yield self._sse_event("done", {"session_id": session.id})
                return
            raw_reply = await self._collect_provider_reply(
                messages=active_messages,
                fast_mode=fast_mode,
                mode="agent",
                model=model,
                attachments=attachments,
            )
            decision = parse_agent_decision(raw_reply)
            if decision is None:
                final_reply = raw_reply.strip() or "The agent returned an empty response."
                if cache_key is not None:
                    self.cache.put(cache_key, final_reply)
                self.sessions.append_message(session.id, "assistant", final_reply)
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": step_index + 1,
                        "kind": "fallback",
                        "content": "Agent returned unstructured output and stopped.",
                    },
                )
                for piece in self._chunk_text(final_reply):
                    yield self._sse_event("token", {"content": piece})
                yield self._sse_event("done", {"session_id": session.id})
                return

            if decision.thought:
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": step_index + 1,
                        "kind": "thought",
                        "content": decision.thought,
                    },
                )

            if decision.final is not None:
                final_reply = decision.final.strip()
                if cache_key is not None:
                    self.cache.put(cache_key, final_reply)
                self.sessions.append_message(session.id, "assistant", final_reply)
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": step_index + 1,
                        "kind": "final",
                        "content": final_reply,
                    },
                )
                for piece in self._chunk_text(final_reply):
                    yield self._sse_event("token", {"content": piece})
                yield self._sse_event("done", {"session_id": session.id})
                return

            if decision.action is None:
                continue

            yield self._sse_event(
                "agent_step",
                {
                    "step": step_index + 1,
                    "kind": "action",
                    "tool": decision.action.tool,
                    "args": decision.action.args,
                },
            )
            if decision.action.tool == "run_command":
                command_stream = self._stream_agent_command_action(
                    session=session,
                    action=decision.action,
                    step=step_index + 1,
                    run_config=run_config,
                )
                while True:
                    try:
                        payload = next(command_stream)
                    except StopIteration as stream_result:
                        outcome = stream_result.value
                        break
                    if cancel_requested is not None and cancel_requested():
                        final_reply = "Agent run was cancelled while a command was in progress."
                        self.sessions.append_message(session.id, "assistant", final_reply)
                        yield self._sse_event(
                            "agent_step",
                            {
                                "step": step_index + 1,
                                "kind": "cancelled",
                                "content": final_reply,
                            },
                        )
                        for piece in self._chunk_text(final_reply):
                            yield self._sse_event("token", {"content": piece})
                        yield self._sse_event("done", {"session_id": session.id})
                        return
                    yield self._sse_event("agent_step", payload)
            else:
                outcome = await self._execute_agent_action(
                    session=session,
                    action=decision.action,
                    run_config=run_config,
                )
            if not isinstance(outcome, AgentToolOutcome):
                outcome = AgentToolOutcome(observation=str(outcome))
            observation = outcome.observation
            yield self._sse_event(
                "agent_step",
                {
                    "step": step_index + 1,
                    "kind": "observation",
                    "tool": decision.action.tool,
                    "content": observation,
                },
            )
            next_messages = list(active_messages)
            next_messages.append({"role": "assistant", "content": raw_reply.strip()})
            next_messages.append(
                {
                    "role": "system",
                    "content": f"Tool result for `{decision.action.tool}`:\n{observation}",
                }
            )
            if outcome.approval is not None:
                approval_payload = self._register_agent_approval(
                    session=session,
                    approval_data=outcome.approval,
                    blocked_step=step_index + 1,
                    next_step_index=step_index + 1,
                    tool_messages=next_messages,
                    fast_mode=fast_mode,
                    model=model,
                    attachments=attachments,
                    run_config=run_config,
                    run_id=run_id,
                )
                notice = self._approval_pause_notice(approval_payload)
                self.sessions.append_message(session.id, "assistant", notice)
                yield self._sse_event(
                    "agent_step",
                    {
                        "step": step_index + 1,
                        "kind": "approval_required",
                        "tool": decision.action.tool,
                        "content": notice,
                        "approval": approval_payload,
                    },
                )
                for piece in self._chunk_text(notice):
                    yield self._sse_event("token", {"content": piece})
                yield self._sse_event("done", {"session_id": session.id})
                return
            active_messages = next_messages

        final_reply = (
            "Agent hit the step limit before finishing. Ask it to continue or narrow the task."
        )
        if cache_key is not None:
            self.cache.put(cache_key, final_reply)
        self.sessions.append_message(session.id, "assistant", final_reply)
        yield self._sse_event(
            "agent_step",
            {
                "step": self.max_agent_steps,
                "kind": "limit",
                "content": final_reply,
            },
        )
        for piece in self._chunk_text(final_reply):
            yield self._sse_event("token", {"content": piece})
        yield self._sse_event("done", {"session_id": session.id})

    def _compose_messages(
        self,
        *,
        session: ChatSession,
        user_message: str,
        retrieval_hits: list[SearchHit],
        tool_results: list[ToolResult],
        fast_mode: bool,
        mode: str,
        attachments: list[Attachment],
    ) -> list[dict[str, str]]:
        system_prompt = (
            "You are ForgeChat, a sharp, high-agency assistant running behind the user's own APIs. "
            "Prefer concise, grounded answers. Use retrieved knowledge when available. "
            "If tool context is present, incorporate it directly instead of ignoring it. "
            "When you are unsure, say what information is missing."
        )
        if fast_mode:
            system_prompt += " Fast mode is enabled, so answer directly and avoid long preambles."
        if mode == "agent":
            system_prompt += (
                " Agent mode is enabled. Think in short steps, propose a plan when useful, and use available context aggressively."
            )
        elif mode == "deep":
            system_prompt += (
                " Deep research mode is enabled. Be more thorough, compare evidence, and organize the answer clearly."
            )
        elif mode == "vision":
            system_prompt += (
                " Vision mode is enabled. Use image attachments as first-class context."
            )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        summary = self._history_summary(session.messages[:-1])
        if summary:
            messages.append({"role": "system", "content": f"Conversation summary:\n{summary}"})
        memory_summary = self.memory.summary()
        if memory_summary:
            messages.append({"role": "system", "content": f"User memory:\n{memory_summary}"})
        if retrieval_hits:
            formatted_hits = "\n\n".join(
                f"[{hit.source}] {hit.snippet}" for hit in retrieval_hits
            )
            messages.append(
                {"role": "system", "content": f"Knowledge context:\n{formatted_hits}"}
            )
        if tool_results:
            tool_context = "\n".join(
                f"- {result.name}: {result.content}" for result in tool_results
            )
            messages.append({"role": "system", "content": f"Tool context:\n{tool_context}"})
        if attachments:
            attachment_context = "\n".join(
                f"- {attachment.compact_preview()}" for attachment in attachments
            )
            messages.append(
                {"role": "system", "content": f"Attachment context:\n{attachment_context}"}
            )

        recent = session.messages[-(self.config.max_context_messages * 2) :]
        for message in recent:
            messages.append({"role": message.role, "content": message.content})
        if not recent or recent[-1].content != user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def _initial_agent_context(
        self,
        *,
        session: ChatSession,
        user_message: str,
        retrieval_hits: list[SearchHit],
        tool_results: list[ToolResult],
        attachments: list[Attachment],
        run_config: AgentRunConfig | None = None,
    ) -> list[dict[str, str]]:
        active_run_config = run_config or self._default_agent_run_config()
        messages = [
            {
                "role": "system",
                "content": build_agent_system_prompt(
                    allow_remote_fetch=self.config.enable_remote_fetch,
                    agent_max_command_tier=active_run_config.max_command_tier,
                    allowed_commands=active_run_config.allowed_commands,
                    permissions=active_run_config.permissions,
                ),
            }
        ]
        memory_summary = self.memory.summary()
        if memory_summary:
            messages.append({"role": "system", "content": f"User memory:\n{memory_summary}"})
        project_profile = self.inspect_workspace_project(session.id)
        project_context = self._project_profile_context(project_profile)
        if project_context:
            messages.append(
                {"role": "system", "content": f"Workspace project profile:\n{project_context}"}
            )
        if retrieval_hits:
            formatted_hits = "\n\n".join(
                f"[{hit.source}] {hit.snippet}" for hit in retrieval_hits
            )
            messages.append(
                {"role": "system", "content": f"Knowledge context:\n{formatted_hits}"}
            )
        if tool_results:
            tool_context = "\n".join(
                f"- {result.name}: {result.content}" for result in tool_results
            )
            messages.append({"role": "system", "content": f"Immediate tool context:\n{tool_context}"})
        if attachments:
            attachment_context = "\n".join(
                f"- {attachment.compact_preview()}" for attachment in attachments
            )
            messages.append(
                {"role": "system", "content": f"Attachment context:\n{attachment_context}"}
            )
        recent = session.messages[-(self.config.max_context_messages * 2) :]
        for message in recent:
            messages.append({"role": message.role, "content": message.content})
        if not recent or recent[-1].content != user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def _history_summary(self, messages: list[MessageRecord]) -> str:
        if not messages:
            return ""
        older = messages[: -self.config.max_context_messages] if len(messages) > self.config.max_context_messages else []
        if not older:
            return ""
        lines = []
        for message in older[-6:]:
            compact = " ".join(message.content.split())
            lines.append(f"{message.role}: {compact[:140]}")
        return "\n".join(lines)

    def _cache_key(
        self,
        *,
        session: ChatSession,
        user_message: str,
        fast_mode: bool,
        retrieval_hits: list[SearchHit],
        tool_results: list[ToolResult],
        mode: str,
        attachments: list[Attachment],
    ) -> str:
        payload = {
            "session": session.id,
            "user": user_message.strip().lower(),
            "fast_mode": fast_mode,
            "mode": mode,
            "retrieval": [hit.id for hit in retrieval_hits],
            "tools": [result.content for result in tool_results],
            "attachments": [attachment.compact_preview() for attachment in attachments],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        return [word + " " for word in words]

    async def _collect_provider_reply(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> str:
        chunks: list[str] = []
        async for chunk in self.provider.stream_reply(
            messages=messages,
            fast_mode=fast_mode,
            mode=mode,
            model=model,
            attachments=attachments,
        ):
            chunks.append(chunk)
        return "".join(chunks).strip()

    def _sse_event(self, event: str, payload: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    def _choose_model_decision(
        self,
        *,
        prompt: str,
        fast_mode: bool,
        mode: str,
        attachments: list[Attachment],
    ) -> ModelRouteDecision:
        return self.model_switchboard.choose(
            prompt=prompt,
            fast_mode=fast_mode,
            mode=mode,
            attachments=attachments,
        )

    def _choose_model(
        self,
        *,
        prompt: str = "",
        fast_mode: bool,
        mode: str,
        attachments: list[Attachment],
    ) -> str:
        return self._choose_model_decision(
            prompt=prompt,
            fast_mode=fast_mode,
            mode=mode,
            attachments=attachments,
        ).model

    def _attachment_context(self, attachments: list[Attachment]) -> list[dict[str, str]]:
        return [
            {
                "name": attachment.name,
                "mime_type": attachment.mime_type,
                "kind": attachment.kind,
                "preview": attachment.compact_preview(),
            }
            for attachment in attachments
        ]

    def _project_profile_context(self, result: dict[str, object] | None) -> str:
        if not isinstance(result, dict) or not result.get("ok"):
            return ""
        project = result.get("project", {})
        if not isinstance(project, dict):
            return ""
        lines: list[str] = []
        languages = project.get("languages", [])
        if isinstance(languages, list) and languages:
            lines.append("Languages: " + ", ".join(str(item) for item in languages[:6]))
        frameworks = project.get("frameworks", [])
        if isinstance(frameworks, list) and frameworks:
            lines.append("Frameworks: " + ", ".join(str(item) for item in frameworks[:6]))
        package_managers = project.get("package_managers", [])
        if isinstance(package_managers, list) and package_managers:
            lines.append(
                "Package managers: "
                + ", ".join(str(item) for item in package_managers[:4])
            )
        entrypoints = project.get("entrypoints", [])
        if isinstance(entrypoints, list) and entrypoints:
            lines.append("Entrypoints: " + ", ".join(str(item) for item in entrypoints[:6]))
        test_commands = project.get("test_commands", [])
        if isinstance(test_commands, list) and test_commands:
            lines.append(
                "Suggested tests: " + ", ".join(str(item) for item in test_commands[:4])
            )
        lint_commands = project.get("lint_commands", [])
        if isinstance(lint_commands, list) and lint_commands:
            lines.append(
                "Suggested lint: " + ", ".join(str(item) for item in lint_commands[:4])
            )
        return "\n".join(lines)

    def _scoped_validation_commands(
        self,
        *,
        requested_commands: list[str],
        project_profile: dict[str, object] | None,
        repo_map: dict[str, object] | None,
    ) -> list[str]:
        if requested_commands:
            return [command.strip() for command in requested_commands if command.strip()]
        project = (
            project_profile.get("project", {})
            if isinstance(project_profile, dict)
            and isinstance(project_profile.get("project", {}), dict)
            else {}
        )
        likely_test_files = [
            str(item).strip()
            for item in (
                repo_map.get("likely_test_files", [])
                if isinstance(repo_map, dict)
                else []
            )
            if str(item).strip()
        ]
        test_commands = [
            str(item).strip()
            for item in project.get("test_commands", [])
            if str(item).strip()
        ]
        if likely_test_files:
            pytest_command = next(
                (
                    command
                    for command in test_commands
                    if "pytest" in command or command.startswith("python -m pytest")
                ),
                "",
            )
            if pytest_command:
                scoped_targets = " ".join(likely_test_files[:4])
                if scoped_targets:
                    return [f"{pytest_command} {scoped_targets}".strip()]
            scoped_runner = next(
                (
                    command
                    for command in test_commands
                    if command.startswith("vitest")
                    or command.startswith("jest")
                    or " vitest" in command
                    or " jest" in command
                ),
                "",
            )
            if scoped_runner:
                scoped_targets = " ".join(likely_test_files[:4])
                if scoped_targets:
                    return [f"{scoped_runner} {scoped_targets}".strip()]
        return test_commands[:3]

    def _build_workspace_task_plan(
        self,
        *,
        goal: str,
        title: str | None,
        cwd: str,
        test_commands: list[str],
        project_profile: dict[str, object] | None,
        git_state: dict[str, object] | None,
        repo_map: dict[str, object] | None,
    ) -> dict[str, object]:
        project = (
            project_profile.get("project", {})
            if isinstance(project_profile, dict)
            and isinstance(project_profile.get("project", {}), dict)
            else {}
        )
        git = (
            git_state.get("git", {})
            if isinstance(git_state, dict) and isinstance(git_state.get("git", {}), dict)
            else {}
        )
        repo_map_payload = (
            repo_map.get("repo_map", {})
            if isinstance(repo_map, dict)
            and isinstance(repo_map.get("repo_map", {}), dict)
            else {}
        )
        languages = [
            str(item).strip().lower()
            for item in project.get("languages", [])
            if str(item).strip()
        ]
        entrypoints = [
            str(item).strip() for item in project.get("entrypoints", []) if str(item).strip()
        ]
        suggested_tests = [
            command.strip()
            for command in (
                self._scoped_validation_commands(
                    requested_commands=test_commands,
                    project_profile=project_profile,
                    repo_map=repo_map_payload,
                )
            )
            if command.strip()
        ]
        focus_paths = [
            str(item).strip()
            for item in repo_map_payload.get("focus_paths", [])
            if str(item).strip()
        ]
        related_paths = [
            str(item).strip()
            for item in repo_map_payload.get("related_paths", [])
            if str(item).strip()
        ]
        likely_test_files = [
            str(item).strip()
            for item in repo_map_payload.get("likely_test_files", [])
            if str(item).strip()
        ]
        branch_suggestion = (
            self._suggest_git_branch_name(title or goal) if git.get("is_repo") else ""
        )
        symbol_tools = any(
            language in {"python", "typescript", "javascript", "tsx", "jsx"}
            for language in languages
        )
        steps: list[dict[str, object]] = [
            {
                "id": "inspect-project",
                "phase": "inspect",
                "title": "Inspect the project profile and repo state",
                "detail": (
                    f"Start in `{cwd}` with `inspect_project`, `inspect_git`, and "
                    "`review_workspace` so the stack, repo root, and current diff are clear first."
                ),
                "tools": ["inspect_project", "inspect_git", "review_workspace"],
            },
            {
                "id": "locate-scope",
                "phase": "inspect",
                "title": "Locate the owning implementation surface",
                "detail": (
                    (
                        "Start with the repo map focus files and use symbol-aware search to "
                        "find the narrowest function or class to edit."
                    )
                    if symbol_tools
                    else (
                        "Start with the repo map focus files, then use workspace search and "
                        "targeted file reads to narrow the change surface."
                    )
                ),
                "tools": (
                    [
                        "inspect_repo_map",
                        "search_workspace",
                        "find_symbol",
                        "read_symbol",
                        "find_references",
                    ]
                    if symbol_tools
                    else ["inspect_repo_map", "search_workspace", "read_file"]
                ),
                "focus_paths": focus_paths,
                "related_paths": related_paths[:6],
            },
            {
                "id": "apply-edit",
                "phase": "edit",
                "title": "Apply the smallest viable edit",
                "detail": (
                    "Prefer `edit_symbol`, `replace_in_file`, or a validated patch before broad rewrites."
                ),
                "tools": ["edit_symbol", "replace_in_file", "preview_patch", "apply_patch"],
            },
        ]
        if suggested_tests:
            steps.append(
                {
                    "id": "validate",
                    "phase": "test",
                    "title": "Run validation commands",
                    "detail": (
                        "Run the requested or detected validation commands after editing."
                    ),
                    "commands": suggested_tests,
                    "likely_test_files": likely_test_files,
                }
            )
        else:
            steps.append(
                {
                    "id": "validate",
                    "phase": "test",
                    "title": "Validate with the safest available checks",
                    "detail": (
                        "No explicit tests were supplied, so inspect the detected project "
                        "commands and the likely test files before finalizing."
                    ),
                    "commands": [],
                    "likely_test_files": likely_test_files,
                }
            )
        steps.append(
            {
                "id": "review",
                "phase": "review",
                "title": "Review the diff and workspace state",
                "detail": "Run `review_workspace` and confirm the final diff, changed files, and validation results.",
                "tools": ["review_workspace"],
            }
        )
        if git.get("is_repo"):
            steps.append(
                {
                    "id": "handoff",
                    "phase": "handoff",
                    "title": "Prepare the Git handoff",
                    "detail": (
                        f"Use `create_branch` for `{branch_suggestion}` if you want an isolated branch, "
                        "then generate commit and PR handoff text."
                    ),
                    "tools": ["create_branch", "prepare_handoff"],
                }
            )
        summary_parts = [
            "inspect the stack",
            "locate the owning code",
            "make a focused edit",
            "review the diff",
        ]
        if suggested_tests:
            summary_parts.insert(3, "run validation commands")
        else:
            summary_parts.insert(3, "choose the safest available validation")
        if git.get("is_repo"):
            summary_parts.append("prepare a Git handoff")
        return {
            "summary": ". ".join(summary_parts).strip().capitalize() + ".",
            "steps": steps,
            "suggested_test_commands": suggested_tests,
            "focus_paths": focus_paths,
            "related_paths": related_paths,
            "likely_test_files": likely_test_files,
            "branch_suggestion": branch_suggestion,
            "repo_path": str(git.get("repo_path", "")).strip(),
            "entrypoints": entrypoints[:8],
        }

    def _task_plan_context(self, plan: dict[str, object] | None) -> str:
        if not isinstance(plan, dict):
            return ""
        lines: list[str] = []
        summary = str(plan.get("summary", "")).strip()
        if summary:
            lines.append(summary)
        steps = plan.get("steps", [])
        if isinstance(steps, list):
            for index, step in enumerate(steps[:8], start=1):
                if not isinstance(step, dict):
                    continue
                title = str(step.get("title", "")).strip() or f"Step {index}"
                detail = str(step.get("detail", "")).strip()
                lines.append(f"{index}. {title}")
                if detail:
                    lines.append(f"   {detail}")
        branch = str(plan.get("branch_suggestion", "")).strip()
        if branch:
            lines.append(f"Suggested branch: {branch}")
        focus_paths = plan.get("focus_paths", [])
        if isinstance(focus_paths, list) and focus_paths:
            lines.append("Focus files: " + ", ".join(str(item) for item in focus_paths[:6]))
        related_paths = plan.get("related_paths", [])
        if isinstance(related_paths, list) and related_paths:
            lines.append(
                "Related files: " + ", ".join(str(item) for item in related_paths[:8])
            )
        likely_test_files = plan.get("likely_test_files", [])
        if isinstance(likely_test_files, list) and likely_test_files:
            lines.append(
                "Likely tests: "
                + ", ".join(str(item) for item in likely_test_files[:8])
            )
        suggested_test_commands = plan.get("suggested_test_commands", [])
        if isinstance(suggested_test_commands, list) and suggested_test_commands:
            lines.append(
                "Suggested validation: "
                + ", ".join(str(item) for item in suggested_test_commands[:4])
            )
        return "\n".join(lines)

    def _build_workspace_git_handoff(
        self,
        *,
        goal: str | None,
        task: dict[str, object] | None,
        cwd: str,
        git_state: dict[str, object] | None,
        review: dict[str, object] | None,
    ) -> dict[str, object]:
        git = (
            git_state.get("git", {})
            if isinstance(git_state, dict) and isinstance(git_state.get("git", {}), dict)
            else {}
        )
        review_payload = review if isinstance(review, dict) else {}
        changed_files = [
            str(item).strip()
            for item in (
                git.get("changed_files", [])
                if isinstance(git.get("changed_files", []), list)
                else review_payload.get("changed_files", [])
            )
            if str(item).strip()
        ]
        task_payload = task if isinstance(task, dict) else {}
        task_goal = (
            str(goal or "").strip()
            or str(task_payload.get("goal", "")).strip()
            or str(task_payload.get("title", "")).strip()
            or "workspace update"
        )
        branch_suggestion = self._suggest_git_branch_name(
            str(task_payload.get("title", "")).strip() or task_goal
        )
        review_summary = self._summary_line(str(review_payload.get("summary", "")).strip())
        task_summary = self._summary_line(
            str(task_payload.get("final_message", "")).strip()
            or str(task_payload.get("summary", "")).strip()
            or task_goal
        )
        validation_commands = self._task_validation_commands(task_payload)
        commit_subject = self._draft_commit_subject(task_goal, changed_files)
        summary_bullets: list[str] = []
        if task_summary:
            summary_bullets.append(task_summary)
        if review_summary and review_summary not in summary_bullets:
            summary_bullets.append(review_summary)
        if changed_files:
            summary_bullets.append("Touch files: " + ", ".join(changed_files[:5]))
        commit_body = "\n".join(f"- {bullet}" for bullet in summary_bullets[:3])
        pr_summary = "\n".join(f"- {bullet}" for bullet in summary_bullets[:4])
        validation_block = (
            "\n".join(f"- `{command}`" for command in validation_commands)
            if validation_commands
            else "- Validation command not captured."
        )
        changed_block = (
            "\n".join(f"- `{path}`" for path in changed_files[:12])
            if changed_files
            else "- No changed files detected."
        )
        pr_body = (
            "## Summary\n"
            f"{pr_summary or '- Update the workspace to satisfy the task goal.'}\n\n"
            "## Validation\n"
            f"{validation_block}\n\n"
            "## Changed Files\n"
            f"{changed_block}"
        )
        return {
            "repo_path": str(git.get("repo_path", "")).strip() or ".",
            "cwd": cwd,
            "current_branch": str(git.get("branch", "")).strip(),
            "branch_suggestion": branch_suggestion,
            "changed_files": changed_files,
            "diff_stat": str(git.get("diff_stat", "")).strip(),
            "commit_message": {
                "subject": commit_subject,
                "body": commit_body,
                "full": commit_subject if not commit_body else f"{commit_subject}\n\n{commit_body}",
            },
            "pull_request": {
                "title": commit_subject,
                "body": pr_body,
            },
            "validation_commands": validation_commands,
            "task_reference": {
                "id": str(task_payload.get("id", "")).strip(),
                "title": str(task_payload.get("title", "")).strip(),
            },
        }

    def _task_validation_commands(self, task: dict[str, object]) -> list[str]:
        commands = task.get("test_commands", [])
        if not isinstance(commands, list):
            return []
        return [str(command).strip() for command in commands if str(command).strip()]

    def _suggest_git_branch_name(self, text: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", text.lower())
        if not words:
            return "codex/workspace-update"
        slug = "-".join(words[:6]).strip("-")
        return f"codex/{slug or 'workspace-update'}"

    def _draft_commit_subject(self, goal: str, changed_files: list[str]) -> str:
        prefix = self._commit_prefix_for_goal(goal, changed_files)
        words = re.findall(r"[A-Za-z0-9]+", goal.lower())
        focus = " ".join(words[:6]).strip()
        if not focus:
            focus = "workspace update"
        return f"{prefix}: {focus}"

    def _commit_prefix_for_goal(self, goal: str, changed_files: list[str]) -> str:
        lowered_goal = goal.lower()
        if changed_files and all(
            path.lower().endswith((".md", ".mdx", ".txt", ".rst")) for path in changed_files
        ):
            return "docs"
        if any(token in lowered_goal for token in ("fix", "bug", "issue", "error", "repair")):
            return "fix"
        if any(token in lowered_goal for token in ("test", "assert", "pytest", "vitest")):
            return "test"
        if any(token in lowered_goal for token in ("refactor", "cleanup", "restructure")):
            return "refactor"
        if any(token in lowered_goal for token in ("add", "build", "create", "implement", "support")):
            return "feat"
        return "chore"

    def _summary_line(self, text: str, *, max_words: int = 14) -> str:
        words = [word for word in " ".join(text.split()).split(" ") if word]
        return " ".join(words[:max_words]).strip()

    def _workspace_verification_profile(
        self,
        project_profile: dict[str, object] | None,
    ) -> dict[str, object]:
        project = (
            project_profile.get("project", {})
            if isinstance(project_profile, dict)
            else {}
        )
        if not isinstance(project, dict):
            project = {}
        test_commands = _ordered_nonempty_strings(project.get("test_commands", []))
        lint_commands = _ordered_nonempty_strings(project.get("lint_commands", []))
        presets: list[dict[str, object]] = []
        if test_commands and lint_commands:
            presets.append(
                {
                    "id": "full",
                    "label": "Tests + Lint",
                    "short_label": "Full Verify",
                    "summary": "Run the detected test and lint commands in the workspace root.",
                    "cwd": ".",
                    "commands": _ordered_nonempty_strings(
                        [*test_commands, *lint_commands]
                    ),
                }
            )
        if test_commands:
            presets.append(
                {
                    "id": "tests",
                    "label": "Tests",
                    "short_label": "Tests",
                    "summary": "Run the detected test commands.",
                    "cwd": ".",
                    "commands": list(test_commands),
                }
            )
        if lint_commands:
            presets.append(
                {
                    "id": "lint",
                    "label": "Lint",
                    "short_label": "Lint",
                    "summary": "Run the detected lint commands.",
                    "cwd": ".",
                    "commands": list(lint_commands),
                }
            )
        default_preset_id = str(presets[0]["id"]).strip() if presets else ""
        return {
            "available": bool(presets),
            "default_preset_id": default_preset_id,
            "presets": presets,
            "test_commands": list(test_commands),
            "lint_commands": list(lint_commands),
        }

    def _resolve_verification_preset(
        self,
        *,
        verification_profile: dict[str, object],
        preset_id: str | None,
    ) -> dict[str, object] | None:
        presets = verification_profile.get("presets", [])
        if not isinstance(presets, list):
            return None
        requested = str(preset_id or "").strip().lower()
        if requested:
            for preset in presets:
                if not isinstance(preset, dict):
                    continue
                if str(preset.get("id", "")).strip().lower() == requested:
                    return preset
            return None
        default_id = str(verification_profile.get("default_preset_id", "")).strip().lower()
        for preset in presets:
            if not isinstance(preset, dict):
                continue
            if str(preset.get("id", "")).strip().lower() == default_id:
                return preset
        return next((preset for preset in presets if isinstance(preset, dict)), None)

    def _build_change_verification_record(
        self,
        *,
        preset: dict[str, object],
        cwd: str,
        results: list[dict[str, object]],
        ok: bool,
    ) -> dict[str, object]:
        passed_count = sum(1 for item in results if bool(item.get("ok", False)))
        failed = next((item for item in results if not bool(item.get("ok", False))), None)
        label = str(preset.get("label", "Verification")).strip() or "Verification"
        if not results:
            summary = f"{label} did not run any commands."
        elif ok:
            summary = (
                f"{label} passed across {len(results)} command(s)."
                if len(results) > 1
                else f"{label} passed."
            )
        else:
            failed_command = (
                str(failed.get("command", "")).strip()
                if isinstance(failed, dict)
                else ""
            )
            if failed_command:
                summary = f"{label} failed on `{failed_command}`."
            else:
                summary = f"{label} failed."
        return {
            "created_at": _utc_now(),
            "preset_id": str(preset.get("id", "")).strip(),
            "label": label,
            "cwd": cwd,
            "ok": ok,
            "status": "passed" if ok else "failed",
            "summary": summary,
            "command_count": len(results),
            "passed_count": passed_count,
            "failed_count": max(0, len(results) - passed_count),
            "results": results,
        }

    def _build_task_runner_brief(
        self,
        *,
        goal: str,
        cwd: str,
        test_commands: list[str],
        project_profile: dict[str, object] | None = None,
        plan: dict[str, object] | None = None,
    ) -> str:
        lines = [
            "You are running a repo task workflow inside the user's workspace.",
            f"Task goal: {goal}",
            f"Working directory: {cwd}",
            "Required phase order:",
            "1. Inspect the workspace with review and file reads before editing.",
            "2. Make the smallest code changes needed for the goal.",
            "3. Run the required test commands after editing.",
            "4. Run `review_workspace` before your final answer.",
            "5. Final answer must summarize the edits, test results, and review state.",
            "Do not install packages, change git configuration, or use package manager commands.",
        ]
        project_context = self._project_profile_context(project_profile)
        if project_context:
            lines.extend(["Detected project profile:", project_context])
        plan_context = self._task_plan_context(plan)
        if plan_context:
            lines.extend(["Execution plan:", plan_context])
        plan_commands = (
            plan.get("suggested_test_commands", [])
            if isinstance(plan, dict)
            else []
        )
        if test_commands:
            lines.append("Required test commands:")
            lines.extend(f"- {command}" for command in test_commands)
        elif isinstance(plan_commands, list) and plan_commands:
            lines.append("Suggested validation commands from the smart planner:")
            lines.extend(
                f"- {str(command)}"
                for command in plan_commands[:4]
                if str(command).strip()
            )
        else:
            lines.append("No explicit test commands were provided. Still inspect and review carefully.")
            suggested_tests = (
                ((project_profile or {}).get("project", {}) if isinstance(project_profile, dict) else {}).get("test_commands", [])
            )
            if isinstance(suggested_tests, list) and suggested_tests:
                lines.append("Suggested test commands from project detection:")
                lines.extend(
                    f"- {command}" for command in suggested_tests[:4] if str(command).strip()
                )
        return "\n".join(lines)

    def _parse_sse_event(self, raw_event: str) -> tuple[str, dict[str, object]] | None:
        if not raw_event:
            return None
        event_name = ""
        payload: dict[str, object] = {}
        for line in raw_event.splitlines():
            if line.startswith("event:"):
                event_name = line.partition(":")[2].strip()
            if line.startswith("data:"):
                data = line.partition(":")[2].strip()
                try:
                    loaded = json.loads(data)
                except json.JSONDecodeError:
                    return None
                if isinstance(loaded, dict):
                    payload = loaded
        if not event_name:
            return None
        return event_name, payload

    def _task_phase_for_action(
        self,
        *,
        tool: str,
        args: dict[str, object],
        test_commands: list[str],
    ) -> str | None:
        if tool in {
            "list_workspace",
            "read_file",
            "search_workspace",
            "find_symbol",
            "list_symbols",
            "read_symbol",
            "find_references",
            "inspect_repo_map",
            "inspect_project",
            "inspect_git",
            "prepare_handoff",
            "list_snapshots",
        }:
            return "inspect"
        if tool in {
            "write_file",
            "replace_in_file",
            "apply_patch",
            "edit_symbol",
            "propose_file_write",
            "propose_replace_in_file",
            "snapshot_workspace",
        }:
            return "edit"
        if tool == "run_command":
            command_text = self._command_text_from_agent_args(args)
            if self._matches_task_test_command(command_text, test_commands):
                return "test"
            return "inspect"
        if tool == "review_workspace":
            return "review"
        if tool == "create_branch":
            return "review"
        return None

    def _task_phase_summary(
        self,
        *,
        phase: str,
        tool: str,
        args: dict[str, object],
    ) -> str:
        if phase == "inspect":
            if tool == "run_command":
                command_text = self._command_text_from_agent_args(args)
                return f"Inspecting the workspace with `{command_text}`."
            if tool == "inspect_project":
                return "Inspecting the detected project stack, entrypoints, and suggested commands."
            if tool == "inspect_repo_map":
                return "Inspecting repo ownership, related files, and likely validation targets."
            if tool == "inspect_git":
                return "Inspecting repository state, changed files, and recent commits."
            if tool == "prepare_handoff":
                return "Preparing a Git handoff draft with commit and pull request notes."
            if tool in {"list_symbols", "find_symbol", "read_symbol", "find_references"}:
                return "Inspecting code structure through symbol-aware workspace tools."
            return "Inspecting the workspace and reading relevant files."
        if phase == "edit":
            if tool == "edit_symbol":
                return "Editing a focused function or class through symbol-aware code tools."
            return "Editing workspace files to satisfy the task goal."
        if phase == "test":
            command_text = self._command_text_from_agent_args(args)
            return f"Running validation command `{command_text}`."
        if phase == "review":
            if tool == "create_branch":
                return "Creating a dedicated Git branch for the task handoff."
            return "Reviewing workspace changes before finalizing the task."
        return "Working through the task."

    def _command_text_from_agent_args(self, args: object) -> str:
        if not isinstance(args, dict):
            return ""
        command = args.get("command")
        if isinstance(command, list):
            return " ".join(str(part).strip() for part in command if str(part).strip())
        if isinstance(command, str):
            return " ".join(command.split())
        return ""

    def _matches_task_test_command(
        self, command_text: str, candidates: list[str]
    ) -> bool:
        normalized = " ".join(command_text.split())
        if not normalized:
            return False
        return normalized in {" ".join(item.split()) for item in candidates if item.strip()}

    def _agent_tool_denial(
        self, tool: str, *, permissions: AgentToolPermissions | None = None
    ) -> str | None:
        active_permissions = permissions or self.agent_permissions
        denial = active_permissions.denial_reason(tool)
        if denial:
            return denial
        if tool in {"search_web", "fetch_url"} and not self.config.enable_remote_fetch:
            return "Remote web fetch is disabled for the agent."
        return None

    def _stream_agent_command_action(
        self,
        *,
        session: ChatSession,
        action: AgentAction,
        step: int,
        run_config: AgentRunConfig,
    ):
        denial = self._agent_tool_denial(
            action.tool,
            permissions=run_config.permissions,
        )
        if denial:
            return AgentToolOutcome(observation=denial)
        command, error = self._coerce_agent_command(action.args.get("command"))
        if error:
            return AgentToolOutcome(observation=error)
        cwd = str(action.args.get("cwd", ".")).strip() or "."
        final_payload: dict[str, object] | None = None
        for event in self.executor.stream_command(
            session_id=session.id,
            command=command,
            cwd=cwd,
            timeout_seconds=min(self.config.command_timeout_seconds, 45.0),
            allowed_commands=run_config.allowed_commands,
            max_command_tier=run_config.max_command_tier,
            request_source="agent",
        ):
            payload = dict(event.get("payload", {}))
            if event.get("event") == "exec_start":
                command_text = " ".join(str(part) for part in payload.get("command", command))
                location = str(payload.get("cwd", cwd))
                yield {
                    "step": step,
                    "kind": "command_start",
                    "tool": action.tool,
                    "content": f"$ {command_text}\n{location}",
                }
                continue
            if event.get("event") == "exec_chunk":
                content = str(payload.get("content", ""))
                if not content:
                    continue
                yield {
                    "step": step,
                    "kind": "command_chunk",
                    "tool": action.tool,
                    "stream": str(payload.get("stream", "stdout")),
                    "content": content,
                }
                continue
            if event.get("event") == "exec_done":
                final_payload = payload
        if final_payload is None:
            return AgentToolOutcome(
                observation="Command stream ended without a final result."
            )
        observation = self._format_command_result(final_payload)
        return AgentToolOutcome(
            observation=observation,
            approval=self._build_command_approval_candidate(
                result=final_payload,
                command=command,
                cwd=cwd,
            ),
        )

    async def _execute_agent_action(
        self,
        *,
        session: ChatSession,
        action: AgentAction,
        run_config: AgentRunConfig,
    ) -> str | AgentToolOutcome:
        tool = action.tool
        args = action.args
        denial = self._agent_tool_denial(
            tool,
            permissions=run_config.permissions,
        )
        if denial:
            return denial
        if tool == "search_web":
            query = str(args.get("query", "")).strip()
            limit = max(1, min(int(args.get("limit", 3)), 5))
            results = await self.tools.navigator.search(query, limit=limit)
            if not results:
                return "No web search results."
            return "\n".join(
                f"- {item.title} | {item.url} | {item.snippet}" for item in results
            )
        if tool == "fetch_url":
            url = str(args.get("url", "")).strip()
            if not url:
                return "Missing `url`."
            return await self.tools.navigator.fetch_page(url)
        if tool == "search_knowledge":
            query = str(args.get("query", "")).strip()
            limit = max(1, min(int(args.get("limit", 4)), 8))
            results = self.knowledge.search(query, limit=limit)
            if not results:
                return "No local knowledge results."
            return "\n".join(
                f"- [{item.source}] {item.snippet}" for item in results
            )
        if tool == "search_workspace":
            query = str(args.get("query", "")).strip()
            if not query:
                return "Missing `query`."
            limit, error = self._coerce_optional_positive_int(
                args.get("limit"),
                field_name="limit",
            )
            if error:
                return error
            result = self.search_workspace(
                session_id=session.id,
                query=query,
                mode=str(args.get("mode", "text")).strip() or "text",
                limit=limit,
                path_prefix=str(args.get("path_prefix", "")).strip() or None,
            )
            return self._format_workspace_search_result(result)
        if tool == "find_symbol":
            query = str(args.get("query", "")).strip()
            if not query:
                return "Missing `query`."
            limit, error = self._coerce_optional_positive_int(
                args.get("limit"),
                field_name="limit",
            )
            if error:
                return error
            result = self.search_workspace(
                session_id=session.id,
                query=query,
                mode="symbols",
                limit=limit,
                path_prefix=str(args.get("path_prefix", "")).strip() or None,
            )
            return self._format_workspace_search_result(result)
        if tool == "list_symbols":
            limit, error = self._coerce_optional_positive_int(
                args.get("limit"),
                field_name="limit",
            )
            if error:
                return error
            result = self.list_workspace_symbols(
                session_id=session.id,
                query=str(args.get("query", "")).strip() or None,
                limit=limit,
                path_prefix=str(args.get("path_prefix", "")).strip() or None,
            )
            return self._format_symbol_list_result(result)
        if tool == "read_symbol":
            symbol = str(args.get("symbol", "")).strip()
            if not symbol:
                return "Missing `symbol`."
            result = self.read_workspace_symbol(
                session_id=session.id,
                symbol=symbol,
                path=str(args.get("path", "")).strip() or None,
            )
            return self._format_symbol_read_result(result)
        if tool == "find_references":
            symbol = str(args.get("symbol", "")).strip()
            if not symbol:
                return "Missing `symbol`."
            limit, error = self._coerce_optional_positive_int(
                args.get("limit"),
                field_name="limit",
            )
            if error:
                return error
            result = self.find_workspace_references(
                session_id=session.id,
                symbol=symbol,
                limit=limit,
                path_prefix=str(args.get("path_prefix", "")).strip() or None,
            )
            return self._format_reference_result(result)
        if tool == "inspect_project":
            return self._format_project_profile_result(
                self.inspect_workspace_project(session.id)
            )
        if tool == "inspect_repo_map":
            limit, error = self._coerce_optional_positive_int(
                args.get("limit"),
                field_name="limit",
            )
            if error:
                return error
            result = self.inspect_workspace_repo_map(
                session.id,
                goal=str(args.get("goal", "")).strip() or None,
                cwd=str(args.get("cwd", "")).strip() or None,
                focus_path=str(args.get("path", "")).strip() or None,
                symbol=str(args.get("symbol", "")).strip() or None,
                limit=limit,
            )
            return self._format_repo_map_result(result)
        if tool == "inspect_git":
            result = self.inspect_workspace_git(
                session.id,
                cwd=str(args.get("cwd", "")).strip() or None,
            )
            return self._format_workspace_git_result(result)
        if tool == "prepare_handoff":
            result = self.prepare_workspace_git_handoff(
                session_id=session.id,
                goal=str(args.get("goal", "")).strip() or None,
                task_id=str(args.get("task_id", "")).strip() or None,
                cwd=str(args.get("cwd", "")).strip() or None,
            )
            return self._format_git_handoff_result(result)
        if tool == "read_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            start_line, error = self._coerce_optional_positive_int(
                args.get("start_line"),
                field_name="start_line",
            )
            if error:
                return error
            end_line, error = self._coerce_optional_positive_int(
                args.get("end_line"),
                field_name="end_line",
            )
            if error:
                return error
            result = self.read_workspace_file(
                session_id=session.id,
                path=path,
                start_line=start_line,
                end_line=end_line,
            )
            return self._format_file_read_result(result)
        if tool == "write_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            result = self.write_workspace_file(
                session_id=session.id,
                path=path,
                content=str(args.get("content", "")),
            )
            return self._format_file_write_result(result)
        if tool == "propose_file_write":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            result = self.propose_workspace_write(
                session_id=session.id,
                path=path,
                content=str(args.get("content", "")),
                source="agent",
            )
            return AgentToolOutcome(
                observation=self._format_patch_proposal_result(result),
                approval=self._build_patch_approval_candidate(result),
            )
        if tool == "replace_in_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            replace_all, error = self._coerce_bool(
                args.get("replace_all"),
                field_name="replace_all",
            )
            if error:
                return error
            expected_occurrences, error = self._coerce_optional_positive_int(
                args.get("expected_occurrences"),
                field_name="expected_occurrences",
            )
            if error:
                return error
            result = self.replace_workspace_file(
                session_id=session.id,
                path=path,
                old_text=str(args.get("old_text", "")),
                new_text=str(args.get("new_text", "")),
                replace_all=replace_all or False,
                expected_occurrences=expected_occurrences,
            )
            return self._format_file_replace_result(result)
        if tool == "propose_replace_in_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            replace_all, error = self._coerce_bool(
                args.get("replace_all"),
                field_name="replace_all",
            )
            if error:
                return error
            expected_occurrences, error = self._coerce_optional_positive_int(
                args.get("expected_occurrences"),
                field_name="expected_occurrences",
            )
            if error:
                return error
            result = self.propose_workspace_replace(
                session_id=session.id,
                path=path,
                old_text=str(args.get("old_text", "")),
                new_text=str(args.get("new_text", "")),
                replace_all=replace_all or False,
                expected_occurrences=expected_occurrences,
                source="agent",
            )
            return AgentToolOutcome(
                observation=self._format_patch_proposal_result(result),
                approval=self._build_patch_approval_candidate(result),
            )
        if tool == "preview_patch":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            result = self.preview_workspace_patch(
                session_id=session.id,
                path=path,
                patch=str(args.get("patch", "")),
            )
            return self._format_patch_preview_result(result)
        if tool == "apply_patch":
            path = str(args.get("path", "")).strip()
            if not path:
                return "Missing `path`."
            expected_hash = str(args.get("expected_hash", "")).strip() or None
            result = self.apply_workspace_text_patch(
                session_id=session.id,
                path=path,
                patch=str(args.get("patch", "")),
                expected_hash=expected_hash,
            )
            return self._format_patch_apply_result(result)
        if tool == "edit_symbol":
            symbol = str(args.get("symbol", "")).strip()
            if not symbol:
                return "Missing `symbol`."
            result = self.edit_workspace_symbol(
                session_id=session.id,
                symbol=symbol,
                path=str(args.get("path", "")).strip() or None,
                content=str(args.get("content", "")),
                source="agent",
            )
            return self._format_symbol_edit_result(result)
        if tool == "run_python":
            code = str(args.get("code", ""))
            result = self.execute_code(session_id=session.id, code=code)
            return json.dumps(result, indent=2)
        if tool == "run_command":
            command, error = self._coerce_agent_command(args.get("command"))
            if error:
                return error
            cwd = str(args.get("cwd", ".")).strip() or "."
            result = self.execute_command(
                session_id=session.id,
                command=command,
                cwd=cwd,
                timeout_seconds=min(self.config.command_timeout_seconds, 45.0),
                max_command_tier=run_config.max_command_tier,
                request_source="agent",
            )
            return AgentToolOutcome(
                observation=self._format_command_result(result),
                approval=self._build_command_approval_candidate(
                    result=result,
                    command=command,
                    cwd=cwd,
                ),
            )
        if tool == "create_branch":
            branch_name = str(args.get("name", "")).strip()
            if not branch_name:
                return "Missing `name`."
            result = self.create_workspace_git_branch(
                session_id=session.id,
                name=branch_name,
                cwd=str(args.get("cwd", "")).strip() or None,
                source="agent",
            )
            return self._format_git_branch_result(result)
        if tool == "list_workspace":
            return json.dumps(self.workspace_payload(session.id), indent=2)
        if tool == "list_snapshots":
            return self._format_snapshot_list_result(
                self.list_workspace_snapshots(session.id)
            )
        if tool == "snapshot_workspace":
            result = self.create_workspace_snapshot(
                session_id=session.id,
                label=str(args.get("label", "")).strip() or None,
                source="agent",
            )
            return self._format_snapshot_create_result(result)
        if tool == "list_pending_patches":
            return self._format_pending_patch_list(
                self.list_pending_workspace_patches(session.id)
            )
        if tool == "review_workspace":
            return self._format_workspace_review_result(
                self.review_workspace(session_id=session.id)
            )
        if tool == "save_knowledge":
            name = str(args.get("name", "")).strip() or "agent-note.md"
            content = str(args.get("content", "")).strip()
            self.add_knowledge(name, content)
            return f"Saved knowledge document `{name}`."
        if tool == "remember":
            text = str(args.get("text", "")).strip()
            self.memory.remember_from_user_text(text)
            return "Memory updated."
        return f"Unknown tool `{tool}`."

    def _build_command_approval_candidate(
        self,
        *,
        result: dict[str, object],
        command: list[str],
        cwd: str,
    ) -> dict[str, object] | None:
        sandbox = result.get("sandbox", {})
        if not isinstance(sandbox, dict):
            sandbox = {}
        command_policy = sandbox.get("command_policy", {})
        if not isinstance(command_policy, dict):
            command_policy = {}
        message = self._agent_approval_required_message(
            sandbox=sandbox,
            command_policy=command_policy,
        )
        if not message:
            return None
        command_text = " ".join(str(part) for part in command)
        requested_tier = str(command_policy.get("tier", "unknown")).strip() or "unknown"
        current_cap = str(command_policy.get("max_tier", "unknown")).strip() or "unknown"
        active_cwd = str(result.get("cwd", cwd)).strip() or cwd
        executable = (
            str(command_policy.get("executable", command[0] if command else "command"))
            .strip()
            or "command"
        )
        return {
            "kind": "command",
            "title": f"Approve {requested_tier} command",
            "summary": f"`{command_text}` needs `{requested_tier}` access in `{active_cwd}`.",
            "command": [str(part) for part in command],
            "command_text": command_text,
            "cwd": active_cwd,
            "requested_tier": requested_tier,
            "current_cap": current_cap,
            "executable": executable,
            "message": message,
            "violations": [
                str(item)
                for item in sandbox.get("violations", [])
                if str(item).strip()
            ]
            if isinstance(sandbox.get("violations", []), list)
            else [],
        }

    def _build_patch_approval_candidate(
        self, result: dict[str, object]
    ) -> dict[str, object] | None:
        if not result.get("ok"):
            return None
        patch = result.get("patch", {})
        if not isinstance(patch, dict):
            return None
        patch_id = str(patch.get("id", "")).strip()
        if not patch_id:
            return None
        path = str(patch.get("path", "")).strip() or "workspace file"
        return {
            "kind": "patch",
            "patch_id": patch_id,
            "title": f"Review patch for {path}",
            "summary": str(patch.get("summary", "")).strip()
            or f"Pending patch for {path}",
            "path": path,
            "operation": str(patch.get("operation", "")).strip() or "edit",
        }

    def _register_agent_approval(
        self,
        *,
        session: ChatSession,
        approval_data: dict[str, object],
        blocked_step: int,
        next_step_index: int,
        tool_messages: list[dict[str, str]],
        fast_mode: bool,
        model: str,
        attachments: list[Attachment],
        run_config: AgentRunConfig,
        run_id: str = "",
    ) -> dict[str, object]:
        kind = str(approval_data.get("kind", "")).strip().lower()
        resume_state = AgentResumeState(
            approval_id="",
            kind=kind or "command",
            run_id=run_id,
            session_id=session.id,
            blocked_step=blocked_step,
            next_step_index=next_step_index,
            created_at=_utc_now(),
            workspace_fingerprint=self._workspace_fingerprint(session.id),
            fast_mode=fast_mode,
            model=model,
            attachments=list(attachments),
            tool_messages=[dict(message) for message in tool_messages],
            agent_max_command_tier=run_config.max_command_tier,
            agent_allowed_commands=run_config.allowed_commands,
            allow_python=run_config.permissions.allow_python,
            allow_shell=run_config.permissions.allow_shell,
            allow_filesystem_read=run_config.permissions.allow_filesystem_read,
            allow_filesystem_write=run_config.permissions.allow_filesystem_write,
        )
        if kind == "patch":
            patch_id = str(approval_data.get("patch_id", "")).strip()
            if patch_id:
                resume_state.approval_id = patch_id
                self.patch_resume_states[(session.id, patch_id)] = resume_state
                self._save_approval_state()
                self._record_approval_audit(
                    session_id=session.id,
                    approval_id=patch_id,
                    kind="patch",
                    action="requested",
                    details={
                        "title": str(approval_data.get("title", "Review patch")).strip(),
                        "summary": str(
                            approval_data.get("summary", "Pending patch proposal")
                        ).strip(),
                        "step": blocked_step,
                        "tool": "patch",
                        "path": str(approval_data.get("path", "")).strip(),
                        "operation": str(approval_data.get("operation", "")).strip(),
                    },
                )
                patch = self._lookup_pending_patch(session.id, patch_id)
                if patch is not None:
                    return self._build_patch_approval_payload(
                        session_id=session.id,
                        patch=patch,
                    )
            return {
                "id": patch_id,
                "session_id": session.id,
                "kind": "patch",
                "title": str(approval_data.get("title", "Review patch")).strip(),
                "summary": str(approval_data.get("summary", "Pending patch proposal")).strip(),
                "created_at": _utc_now(),
                "step": blocked_step,
                "tool": "patch",
                "resume_available": True,
            }

        approval_id = uuid.uuid4().hex
        resume_state.approval_id = approval_id
        approval = PendingAgentApproval(
            id=approval_id,
            session_id=session.id,
            kind="command",
            title=str(approval_data.get("title", "Approve command")).strip()
            or "Approve command",
            summary=str(approval_data.get("summary", "Agent command requires approval.")).strip()
            or "Agent command requires approval.",
            created_at=_utc_now(),
            step=blocked_step,
            tool=str(approval_data.get("tool", "run_command")).strip() or "run_command",
            source="agent",
            status="pending",
            resume_available=True,
            details={
                key: value
                for key, value in approval_data.items()
                if key not in {"kind", "title", "summary", "tool"}
            },
        )
        self.command_approvals.setdefault(session.id, {})[approval_id] = approval
        self.command_resume_states[approval_id] = resume_state
        self._save_approval_state()
        self._record_approval_audit(
            session_id=session.id,
            approval_id=approval_id,
            kind="command",
            action="requested",
            details={
                "title": approval.title,
                "summary": approval.summary,
                "step": blocked_step,
                "tool": approval.tool,
                "command_text": str(approval.details.get("command_text", "")).strip(),
                "requested_tier": str(
                    approval.details.get("requested_tier", "")
                ).strip(),
                "cwd": str(approval.details.get("cwd", "")).strip(),
            },
        )
        return approval.payload()

    def _lookup_command_approval_payload(
        self, *, session_id: str, approval_id: str
    ) -> dict[str, object] | None:
        approval = self.command_approvals.get(session_id, {}).get(approval_id)
        if approval is None:
            return None
        return self._build_command_approval_payload(approval)

    def _build_command_approval_payload(
        self, approval: PendingAgentApproval
    ) -> dict[str, object]:
        payload = approval.payload()
        resume_state = self.command_resume_states.get(approval.id)
        stale_reason = self._resume_state_stale_reason(resume_state)
        payload["resume_available"] = stale_reason is None
        payload["run_id"] = resume_state.run_id if resume_state is not None else ""
        if stale_reason:
            payload["stale_reason"] = stale_reason
        return payload

    def _lookup_pending_patch(
        self, session_id: str, patch_id: str
    ) -> dict[str, object] | None:
        for patch in self.patch_manager.list_pending(session_id):
            if not isinstance(patch, dict):
                continue
            if str(patch.get("id", "")).strip() == patch_id:
                return patch
        return None

    def _build_patch_approval_payload(
        self, *, session_id: str, patch: dict[str, object]
    ) -> dict[str, object]:
        patch_id = str(patch.get("id", "")).strip()
        path = str(patch.get("path", "")).strip() or "workspace file"
        resume_state = self.patch_resume_states.get((session_id, patch_id))
        source = str(patch.get("source", "")).strip() or "api"
        stale_reason = (
            self._resume_state_stale_reason(resume_state, patch_id=patch_id)
            if source == "agent"
            else None
        )
        return {
            "id": patch_id,
            "session_id": session_id,
            "kind": "patch",
            "title": f"Review patch for {path}",
            "summary": str(patch.get("summary", "")).strip()
            or f"Pending patch for {path}",
            "created_at": str(patch.get("created_at", "")).strip() or _utc_now(),
            "step": resume_state.blocked_step if resume_state is not None else 0,
            "tool": "patch",
            "source": source,
            "status": "pending",
            "resume_available": source == "agent" and stale_reason is None,
            "run_id": resume_state.run_id if resume_state is not None else "",
            "stale_reason": stale_reason,
            "path": path,
            "operation": str(patch.get("operation", "")).strip() or "edit",
            "diff": str(patch.get("diff", "")),
            "diff_truncated": bool(patch.get("diff_truncated", False)),
        }

    def _approval_pause_notice(self, approval: dict[str, object]) -> str:
        kind = str(approval.get("kind", "")).strip().lower()
        title = str(approval.get("title", "")).strip()
        if kind == "patch":
            return (
                f"{title or 'Patch review required.'} "
                "Review it in the Approvals panel, then approve or reject to continue."
            )
        return (
            f"{title or 'Approval required.'} "
            "Open the Approvals panel to approve or reject this step, and I will continue from there."
        )

    async def _stream_command_approval_resolution(
        self,
        *,
        session: ChatSession,
        approval_id: str,
        approved: bool,
    ) -> AsyncIterator[str]:
        approval = self.command_approvals.get(session.id, {}).pop(approval_id, None)
        if approval is None:
            async for event in self._stream_missing_approval_notice(session=session, approval_id=approval_id):
                yield event
            return
        if not self.command_approvals.get(session.id):
            self.command_approvals.pop(session.id, None)
        resume_state = self.command_resume_states.pop(approval_id, None)
        stale_reason = self._resume_state_stale_reason(resume_state)
        self._save_approval_state()
        command = approval.details.get("command", [])
        command_list = (
            [str(part) for part in command]
            if isinstance(command, list)
            else []
        )
        command_text = str(approval.details.get("command_text", "")).strip() or "command"
        decision_text = "approved" if approved else "rejected"
        self._record_approval_audit(
            session_id=session.id,
            approval_id=approval.id,
            kind="command",
            action=decision_text,
            details={
                "title": approval.title,
                "step": approval.step,
                "tool": approval.tool,
                "command_text": command_text,
                "requested_tier": str(
                    approval.details.get("requested_tier", "")
                ).strip(),
                "resume_available": stale_reason is None,
            },
        )
        self.sessions.append_message(
            session.id,
            "user",
            f"{decision_text.title()} agent approval: {approval.title}",
        )
        yield self._sse_event(
            "agent_step",
            {
                "step": approval.step,
                "kind": "approval_decision",
                "tool": approval.tool,
                "approval_id": approval.id,
                "approved": approved,
                "content": (
                    f"User {decision_text} `{command_text}`."
                    if command_text
                    else f"User {decision_text} the pending command."
                ),
            },
        )
        if stale_reason is not None:
            self._record_approval_audit(
                session_id=session.id,
                approval_id=approval.id,
                kind="command",
                action="resume_stale",
                details={
                    "reason": stale_reason,
                    "approved": approved,
                },
            )
            notice = (
                "Approval was recorded, but the saved agent checkpoint could not be resumed. "
                f"{stale_reason}"
            )
            self.sessions.append_message(session.id, "assistant", notice)
            for piece in self._chunk_text(notice):
                yield self._sse_event("token", {"content": piece})
            yield self._sse_event("done", {"session_id": session.id})
            return

        if approved:
            final_payload: dict[str, object] | None = None
            cwd = str(approval.details.get("cwd", ".")).strip() or "."
            max_tier = str(approval.details.get("requested_tier", "")).strip() or None
            for event in self.executor.stream_command(
                session_id=session.id,
                command=command_list,
                cwd=cwd,
                timeout_seconds=min(self.config.command_timeout_seconds, 45.0),
                allowed_commands=self.config.allowed_exec_commands,
                max_command_tier=max_tier,
                request_source="agent_approved",
            ):
                payload = dict(event.get("payload", {}))
                if event.get("event") == "exec_start":
                    executed_command = " ".join(
                        str(part) for part in payload.get("command", command_list)
                    )
                    yield self._sse_event(
                        "agent_step",
                        {
                            "step": resume_state.blocked_step,
                            "kind": "command_start",
                            "tool": approval.tool,
                            "content": f"$ {executed_command}\n{str(payload.get('cwd', cwd))}",
                        },
                    )
                    continue
                if event.get("event") == "exec_chunk":
                    content = str(payload.get("content", ""))
                    if not content:
                        continue
                    yield self._sse_event(
                        "agent_step",
                        {
                            "step": resume_state.blocked_step,
                            "kind": "command_chunk",
                            "tool": approval.tool,
                            "stream": str(payload.get("stream", "stdout")),
                            "content": content,
                        },
                    )
                    continue
                if event.get("event") == "exec_done":
                    final_payload = payload
            if final_payload is None:
                observation = "Approved command stream ended without a final result."
            else:
                observation = self._format_command_result(final_payload)
            resume_observation = (
                "User approved the higher-tier command request.\n"
                f"{observation}"
            )
        else:
            resume_observation = (
                f"User rejected the higher-tier command request for `{command_text}`. "
                "Do not retry the same higher-tier command unless the user explicitly changes their decision."
            )

        yield self._sse_event(
            "agent_step",
            {
                "step": resume_state.blocked_step,
                "kind": "observation",
                "tool": approval.tool,
                "content": resume_observation,
            },
        )
        async for event in self._continue_agent_after_approval(
            session=session,
            resume_state=resume_state,
            resume_observation=resume_observation,
        ):
            yield event

    async def _stream_patch_approval_resolution(
        self,
        *,
        session: ChatSession,
        patch_id: str,
        approved: bool,
    ) -> AsyncIterator[str]:
        patch = self._lookup_pending_patch(session.id, patch_id)
        if patch is None:
            async for event in self._stream_missing_approval_notice(session=session, approval_id=patch_id):
                yield event
            return
        resume_state = self.patch_resume_states.pop((session.id, patch_id), None)
        stale_reason = self._resume_state_stale_reason(resume_state, patch_id=patch_id)
        self._save_approval_state()
        decision_text = "approved" if approved else "rejected"
        self._record_approval_audit(
            session_id=session.id,
            approval_id=patch_id,
            kind="patch",
            action=decision_text,
            details={
                "path": str(patch.get("path", "")).strip(),
                "summary": str(patch.get("summary", "")).strip(),
                "step": resume_state.blocked_step if resume_state is not None else 0,
                "resume_available": stale_reason is None,
            },
        )
        self.sessions.append_message(
            session.id,
            "user",
            f"{decision_text.title()} patch review: {str(patch.get('summary', 'Pending patch')).strip()}",
        )
        yield self._sse_event(
            "agent_step",
            {
                "step": resume_state.blocked_step if resume_state is not None else 0,
                "kind": "approval_decision",
                "tool": "patch",
                "approval_id": patch_id,
                "approved": approved,
                "content": f"User {decision_text} patch `{str(patch.get('path', '')).strip() or patch_id}`.",
            },
        )
        verification_result: dict[str, object] | None = None
        if approved:
            result = self.apply_workspace_patch(session_id=session.id, patch_id=patch_id)
            if result.get("ok"):
                verification_result = self._maybe_auto_verify_applied_patch_change(
                    session_id=session.id,
                    apply_result=result,
                )
                resume_parts = [
                    f"User approved patch `{str(result.get('path', patch.get('path', patch_id))).strip()}`.",
                    f"Patch apply result:\n{json.dumps(result, indent=2)}",
                ]
                verification_observation = self._format_agent_verification_observation(
                    verification_result
                )
                if verification_observation:
                    resume_parts.append(verification_observation)
                resume_observation = "\n\n".join(resume_parts)
            else:
                resume_observation = (
                    "User approved the patch, but applying it failed.\n"
                    f"{result.get('error', 'Unknown patch apply error.')}"
                )
        else:
            result = self.reject_workspace_patch(session_id=session.id, patch_id=patch_id)
            resume_observation = (
                f"User rejected patch `{str(patch.get('path', patch_id)).strip()}`.\n"
                "Do not assume those file changes were applied."
            )
            if not result.get("ok"):
                resume_observation += (
                    "\nReject failed: "
                    f"{result.get('error', 'Unknown patch rejection error.')}"
                )

        yield self._sse_event(
            "agent_step",
            {
                "step": resume_state.blocked_step if resume_state is not None else 0,
                "kind": "observation",
                "tool": "patch",
                "content": resume_observation,
            },
        )

        if stale_reason is not None:
            self._record_approval_audit(
                session_id=session.id,
                approval_id=patch_id,
                kind="patch",
                action="resume_stale",
                details={
                    "reason": stale_reason,
                    "approved": approved,
                    "result_ok": bool(result.get("ok")),
                },
            )
            notice = (
                "Patch review has been recorded, but the saved agent checkpoint could not be resumed."
                if result.get("ok")
                else str(result.get("error", "Patch review could not be completed."))
            )
            if result.get("ok"):
                notice = f"{notice} {stale_reason}"
            self.sessions.append_message(session.id, "assistant", notice)
            for piece in self._chunk_text(notice):
                yield self._sse_event("token", {"content": piece})
            yield self._sse_event("done", {"session_id": session.id})
            return

        async for event in self._continue_agent_after_approval(
            session=session,
            resume_state=resume_state,
            resume_observation=resume_observation,
        ):
            yield event

    def _maybe_auto_verify_applied_patch_change(
        self,
        *,
        session_id: str,
        apply_result: dict[str, object],
    ) -> dict[str, object] | None:
        if not apply_result.get("ok"):
            return None
        change = apply_result.get("change", {})
        if not isinstance(change, dict):
            return None
        change_id = str(change.get("id", "")).strip()
        if not change_id:
            return None
        verification_profile = self.workspace_verification_payload(session_id).get(
            "verification",
            {},
        )
        if not isinstance(verification_profile, dict) or not bool(
            verification_profile.get("available", False)
        ):
            return None
        default_preset_id = (
            str(verification_profile.get("default_preset_id", "")).strip() or None
        )
        return self.verify_workspace_change(
            session_id=session_id,
            change_id=change_id,
            preset_id=default_preset_id,
        )

    def _format_agent_verification_observation(
        self, verification_result: dict[str, object] | None
    ) -> str:
        if verification_result is None:
            return ""
        if not verification_result.get("ok"):
            return (
                "Automatic verification could not run after patch approval.\n"
                f"Error: {str(verification_result.get('error', 'Unknown verification error.')).strip()}"
            )
        verification = verification_result.get("verification", {})
        if not isinstance(verification, dict):
            return (
                "Automatic verification ran after patch approval, but no structured "
                "verification result was returned."
            )
        label = str(verification.get("label", "Verification")).strip() or "Verification"
        status = str(verification.get("status", "unknown")).strip() or "unknown"
        summary = (
            str(verification.get("summary", "")).strip()
            or "No verification summary was returned."
        )
        lines = [
            "Automatic verification ran after patch approval.",
            f"Automatic verification preset: {label}",
            f"Automatic verification status: {status}",
            f"Automatic verification summary: {summary}",
        ]
        results = verification.get("results", [])
        if isinstance(results, list) and results:
            lines.append("Automatic verification command results:")
            for item in results[:4]:
                if not isinstance(item, dict):
                    continue
                command_text = str(item.get("command", "command")).strip() or "command"
                lines.append(
                    "Command "
                    f"`{command_text}` -> ok={bool(item.get('ok', False))}, "
                    f"returncode={item.get('returncode', '')}, "
                    f"timed_out={bool(item.get('timed_out', False))}"
                )
                stdout = _truncate_agent_text(
                    str(item.get("stdout", "")).strip(),
                    max_chars=800,
                )
                stderr = _truncate_agent_text(
                    str(item.get("stderr", "")).strip(),
                    max_chars=800,
                )
                if stdout:
                    lines.extend([f"STDOUT for `{command_text}`:", stdout])
                if stderr:
                    lines.extend([f"STDERR for `{command_text}`:", stderr])
        lines.append(
            "If verification failed, inspect the failing checks and propose the next "
            "patch automatically unless you need user input."
        )
        return "\n".join(lines)

    async def _continue_agent_after_approval(
        self,
        *,
        session: ChatSession,
        resume_state: AgentResumeState,
        resume_observation: str,
    ) -> AsyncIterator[str]:
        self._record_approval_audit(
            session_id=session.id,
            approval_id=resume_state.approval_id,
            kind=resume_state.kind,
            action="resumed",
            details={
                "blocked_step": resume_state.blocked_step,
                "next_step_index": resume_state.next_step_index,
            },
        )
        resumed_messages = [dict(message) for message in resume_state.tool_messages]
        resumed_messages.append(
            {
                "role": "system",
                "content": f"Approval decision:\n{resume_observation}",
            }
        )
        async for event in self._run_agent_loop(
            session=session,
            tool_messages=resumed_messages,
            fast_mode=resume_state.fast_mode,
            attachments=resume_state.attachments,
            model=resume_state.model,
            cache_key=None,
            start_step_index=resume_state.next_step_index,
            run_config=self._agent_run_config_from_state(resume_state),
            run_id=resume_state.run_id,
            cancel_requested=(
                (lambda run_id=resume_state.run_id: self.agent_runs.cancel_requested(run_id))
                if resume_state.run_id
                else None
            ),
        ):
            yield event

    async def _stream_missing_approval_notice(
        self, *, session: ChatSession, approval_id: str
    ) -> AsyncIterator[str]:
        notice = f"Pending approval `{approval_id}` was not found."
        self.sessions.append_message(session.id, "assistant", notice)
        yield self._sse_event(
            "agent_step",
            {
                "step": 0,
                "kind": "approval_missing",
                "content": notice,
            },
        )
        for piece in self._chunk_text(notice):
            yield self._sse_event("token", {"content": piece})
        yield self._sse_event("done", {"session_id": session.id})

    def _coerce_agent_command(
        self, command_value: object
    ) -> tuple[list[str] | None, str | None]:
        if isinstance(command_value, str):
            try:
                command = [part for part in shlex.split(command_value) if part]
            except ValueError as exc:
                return None, f"Invalid command string: {exc}"
            if not command:
                return None, "Missing `command`."
            return command, None
        if isinstance(command_value, list):
            command: list[str] = []
            for item in command_value:
                if isinstance(item, (dict, list, tuple, set)):
                    return None, "Command arguments must be plain strings."
                text = str(item).strip()
                if not text:
                    return None, "Command arguments cannot be empty."
                command.append(text)
            if not command:
                return None, "Missing `command`."
            return command, None
        return None, "Missing `command`."

    def _coerce_optional_positive_int(
        self,
        value: object,
        *,
        field_name: str,
    ) -> tuple[int | None, str | None]:
        if value is None or value == "":
            return None, None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None, f"`{field_name}` must be an integer."
        if number < 1:
            return None, f"`{field_name}` must be at least 1."
        return number, None

    def _coerce_bool(
        self,
        value: object,
        *,
        field_name: str,
    ) -> tuple[bool | None, str | None]:
        if value is None:
            return None, None
        if isinstance(value, bool):
            return value, None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True, None
        if text in {"0", "false", "no", "off"}:
            return False, None
        return None, f"`{field_name}` must be a boolean."

    def _agent_allowed_commands(
        self, max_command_tier: str | None = None
    ) -> tuple[str, ...]:
        return filter_commands_by_tier(
            allowed_commands=self.config.allowed_exec_commands,
            max_command_tier=max_command_tier or self.config.agent_max_command_tier,
        )

    def _format_command_result(self, result: dict[str, object]) -> str:
        sandbox = result.get("sandbox", {})
        if not isinstance(sandbox, dict):
            sandbox = {}
        command_policy = sandbox.get("command_policy", {})
        if not isinstance(command_policy, dict):
            command_policy = {}
        lines = [
            f"Command: {' '.join(str(part) for part in result.get('command', []))}",
            f"CWD: {result.get('cwd', '.')}",
            (
                "Policy: "
                f"tier={command_policy.get('tier', 'unknown')}, "
                f"max={command_policy.get('max_tier', 'unknown')}, "
                f"source={command_policy.get('source', 'unknown')}"
            ),
            f"Return code: {result.get('returncode', '')}",
            f"Timed out: {bool(result.get('timed_out', False))}",
        ]
        stdout = str(result.get("stdout", "") or "").rstrip()
        stderr = str(result.get("stderr", "") or "").rstrip()
        if stdout:
            lines.extend(["STDOUT:", stdout])
        if stderr:
            lines.extend(["STDERR:", stderr])
        files = result.get("files", [])
        if isinstance(files, list) and files:
            lines.append(f"Workspace files: {', '.join(str(item) for item in files[:12])}")
        violations = sandbox.get("violations", [])
        if isinstance(violations, list) and violations:
            lines.append(
                "Violations: "
                + "; ".join(str(item) for item in violations if str(item).strip())
            )
        approval_required = self._agent_approval_required_message(
            sandbox=sandbox,
            command_policy=command_policy,
        )
        if approval_required:
            lines.append(approval_required)
        return "\n".join(lines)

    def _agent_approval_required_message(
        self,
        *,
        sandbox: dict[str, object],
        command_policy: dict[str, object],
    ) -> str | None:
        if str(command_policy.get("source", "")).strip().lower() != "agent":
            return None
        violations = sandbox.get("violations", [])
        if not isinstance(violations, list):
            return None
        if not any("allowed maximum" in str(item) for item in violations):
            return None
        executable = str(command_policy.get("executable", "command")).strip() or "command"
        tier = str(command_policy.get("tier", "unknown"))
        max_tier = str(command_policy.get("max_tier", "unknown"))
        return (
            "Approval required: "
            f"`{executable}` is a `{tier}` command but the agent is capped at "
            f"`{max_tier}`. Ask the user before retrying a higher-tier command."
        )

    def _format_file_read_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return f"Read failed: {result.get('error', 'Unknown workspace read error.')}"
        lines = [
            f"Path: {result.get('path', '')}",
            (
                f"Lines: {result.get('start_line', 0)}-{result.get('end_line', 0)} "
                f"of {result.get('total_lines', 0)}"
            ),
            f"Size bytes: {result.get('size_bytes', 0)}",
            f"Truncated: {bool(result.get('truncated', False))}",
            "Content:",
        ]
        content = str(result.get("content", ""))
        start_line = int(result.get("start_line", 0) or 0)
        if not content:
            lines.append("(empty file)")
            return "\n".join(lines)
        for offset, line in enumerate(content.splitlines(), start=start_line or 1):
            lines.append(f"{offset}: {line}")
        return "\n".join(lines)

    def _format_file_write_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return f"Write failed: {result.get('error', 'Unknown workspace write error.')}"
        lines = [
            f"Path: {result.get('path', '')}",
            f"Created: {bool(result.get('created', False))}",
            f"Size bytes: {result.get('size_bytes', 0)}",
        ]
        files = result.get("files", [])
        if isinstance(files, list) and files:
            lines.append(f"Workspace files: {', '.join(str(item) for item in files[:12])}")
        return "\n".join(lines)

    def _format_file_replace_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return f"Edit failed: {result.get('error', 'Unknown workspace edit error.')}"
        lines = [
            f"Path: {result.get('path', '')}",
            f"Replacements: {result.get('replacements', 0)}",
            f"Size bytes: {result.get('size_bytes', 0)}",
        ]
        files = result.get("files", [])
        if isinstance(files, list) and files:
            lines.append(f"Workspace files: {', '.join(str(item) for item in files[:12])}")
        return "\n".join(lines)

    def _format_patch_proposal_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Patch proposal failed: "
                f"{result.get('error', 'Unknown workspace patch error.')}"
            )
        patch = result.get("patch", {})
        if not isinstance(patch, dict):
            patch = {}
        lines = [
            "Review required before apply.",
            f"Patch ID: {patch.get('id', '')}",
            f"Path: {patch.get('path', '')}",
            f"Operation: {patch.get('operation', '')}",
            f"Summary: {patch.get('summary', '')}",
            "Diff:",
            str(patch.get("diff", "")) or "(empty diff)",
        ]
        pending_patches = result.get("pending_patches", [])
        if isinstance(pending_patches, list):
            lines.append(f"Pending patches: {len(pending_patches)}")
        return "\n".join(lines)

    def _format_patch_preview_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Patch preview failed: "
                f"{result.get('error', 'Unknown workspace patch preview error.')}"
            )
        lines = [
            f"Path: {result.get('path', '')}",
            f"Can apply: {bool(result.get('can_apply', False))}",
            f"Creates file: {bool(result.get('creates_file', False))}",
            f"Current hash: {result.get('current_hash', '')}",
            f"Patched hash: {result.get('patched_hash', '')}",
            (
                f"Hunks: {result.get('hunk_count', 0)} | "
                f"+{result.get('additions', 0)} / -{result.get('deletions', 0)}"
            ),
            f"Size bytes: {result.get('size_bytes', 0)}",
        ]
        issues = result.get("issues", [])
        if isinstance(issues, list) and issues:
            lines.append(
                "Issues: "
                + "; ".join(str(item) for item in issues if str(item).strip())
            )
        preview = str(result.get("preview", ""))
        if len(preview) > 4_000:
            preview = f"{preview[:4_000]}\n...[patch preview truncated]..."
        lines.extend(["Preview:", preview or "(empty patch)"])
        return "\n".join(lines)

    def _format_patch_apply_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Patch apply failed: "
                f"{result.get('error', 'Unknown workspace patch apply error.')}"
            )
        lines = [
            f"Path: {result.get('path', '')}",
            f"Created: {bool(result.get('created', False))}",
            f"Current hash: {result.get('current_hash', '')}",
            f"Patched hash: {result.get('patched_hash', '')}",
            (
                f"Hunks: {result.get('hunk_count', 0)} | "
                f"+{result.get('additions', 0)} / -{result.get('deletions', 0)}"
            ),
            f"Size bytes: {result.get('size_bytes', 0)}",
        ]
        files = result.get("files", [])
        if isinstance(files, list) and files:
            lines.append(f"Workspace files: {', '.join(str(item) for item in files[:12])}")
        return "\n".join(lines)

    def _format_symbol_list_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Symbol listing failed: "
                f"{result.get('error', 'Unknown symbol listing error.')}"
            )
        symbols = result.get("symbols", [])
        if not isinstance(symbols, list) or not symbols:
            return "No matching symbols found in the workspace."
        lines = []
        for item in symbols[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                (
                    f"- {item.get('qualname', item.get('name', 'symbol'))} "
                    f"| {item.get('kind', 'symbol')} "
                    f"| {item.get('path', '')}:{item.get('start_line', 0)}"
                )
            )
            signature = str(item.get("signature", "")).strip()
            if signature:
                lines.append(f"  {signature}")
        return "\n".join(lines)

    def _format_symbol_read_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Read symbol failed: "
                f"{result.get('error', 'Unknown symbol read error.')}"
            )
        symbol = result.get("symbol", {})
        if not isinstance(symbol, dict):
            symbol = {}
        lines = [
            f"Symbol: {symbol.get('qualname', symbol.get('name', ''))}",
            f"Kind: {symbol.get('kind', 'symbol')}",
            f"Path: {symbol.get('path', '')}",
            (
                f"Lines: {symbol.get('start_line', 0)}-{symbol.get('end_line', 0)}"
            ),
            "Content:",
            str(symbol.get("content", "")),
        ]
        return "\n".join(lines)

    def _format_reference_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Reference search failed: "
                f"{result.get('error', 'Unknown reference search error.')}"
            )
        references = result.get("results", [])
        if not isinstance(references, list) or not references:
            return f"No references found for `{result.get('symbol', '')}`."
        lines = [f"References for `{result.get('symbol', '')}`:"]
        for item in references[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('path', '')}:{item.get('line', 0)}")
            snippet = str(item.get("snippet", "")).strip()
            if snippet:
                lines.append(f"  {snippet}")
        return "\n".join(lines)

    def _format_symbol_edit_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Symbol edit failed: "
                f"{result.get('error', 'Unknown symbol edit error.')}"
            )
        symbol = result.get("symbol", {})
        if not isinstance(symbol, dict):
            symbol = {}
        lines = [
            f"Edited symbol: {symbol.get('qualname', symbol.get('name', ''))}",
            f"Path: {result.get('path', '')}",
            f"Kind: {symbol.get('kind', 'symbol')}",
            f"Size bytes: {result.get('size_bytes', 0)}",
        ]
        files = result.get("files", [])
        if isinstance(files, list) and files:
            lines.append(f"Workspace files: {', '.join(str(item) for item in files[:12])}")
        return "\n".join(lines)

    def _format_project_profile_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Project inspection failed: "
                f"{result.get('error', 'Unknown project inspection error.')}"
            )
        project = result.get("project", {})
        if not isinstance(project, dict):
            project = {}
        lines = []
        for label, key in [
            ("Languages", "languages"),
            ("Frameworks", "frameworks"),
            ("Package managers", "package_managers"),
            ("Entrypoints", "entrypoints"),
            ("Install", "install_commands"),
            ("Tests", "test_commands"),
            ("Lint", "lint_commands"),
            ("Run", "run_commands"),
        ]:
            values = project.get(key, [])
            if isinstance(values, list) and values:
                lines.append(f"{label}: {', '.join(str(item) for item in values[:8])}")
        signals = project.get("signals", [])
        if isinstance(signals, list) and signals:
            lines.append("Signals:")
            lines.extend(f"- {str(item)}" for item in signals[:6])
        return "\n".join(lines) or "No project profile signals detected yet."

    def _format_repo_map_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Repo map inspection failed: "
                f"{result.get('error', 'Unknown repo map inspection error.')}"
            )
        repo_map = result.get("repo_map", {})
        if not isinstance(repo_map, dict):
            repo_map = {}
        lines: list[str] = []
        summary = str(repo_map.get("summary", "")).strip()
        if summary:
            lines.append(summary)
        focus_paths = repo_map.get("focus_paths", [])
        if isinstance(focus_paths, list) and focus_paths:
            lines.append("Focus files: " + ", ".join(str(item) for item in focus_paths[:6]))
        related_paths = repo_map.get("related_paths", [])
        if isinstance(related_paths, list) and related_paths:
            lines.append(
                "Related files: " + ", ".join(str(item) for item in related_paths[:8])
            )
        likely_test_files = repo_map.get("likely_test_files", [])
        if isinstance(likely_test_files, list) and likely_test_files:
            lines.append(
                "Likely tests: "
                + ", ".join(str(item) for item in likely_test_files[:8])
            )
        suggested_validation = repo_map.get("suggested_validation_commands", [])
        if isinstance(suggested_validation, list) and suggested_validation:
            lines.append(
                "Suggested validation: "
                + ", ".join(str(item) for item in suggested_validation[:4])
            )
        nodes = repo_map.get("nodes", [])
        if isinstance(nodes, list) and nodes:
            lines.append("Top repo nodes:")
            for item in nodes[:8]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    (
                        f"- {item.get('path', '')} | {item.get('language', '')} | "
                        f"symbols={item.get('symbol_count', 0)} | "
                        f"imports={item.get('import_count', 0)} | "
                        f"imported_by={item.get('imported_by_count', 0)}"
                    )
                )
        return "\n".join(lines) or "No repo-map signals were detected."

    def _format_workspace_git_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Git inspection failed: "
                f"{result.get('error', 'Unknown Git inspection error.')}"
            )
        git = result.get("git", {})
        if not isinstance(git, dict) or not git.get("is_repo"):
            return "No Git repository detected in the current workspace scope."
        lines = [
            f"Repo path: {git.get('repo_path', '.')}",
            f"Branch: {git.get('branch', '') or '(unknown)'}",
            f"HEAD: {git.get('head', '') or '(unknown)'}",
        ]
        changed_files = git.get("changed_files", [])
        if isinstance(changed_files, list):
            lines.append(f"Changed files: {len(changed_files)}")
            if changed_files:
                lines.append(
                    "Files: " + ", ".join(str(item) for item in changed_files[:12])
                )
        diff_stat = str(git.get("diff_stat", "")).strip()
        if diff_stat:
            lines.extend(["Diff stat:", diff_stat])
        recent_commits = git.get("recent_commits", [])
        if isinstance(recent_commits, list) and recent_commits:
            lines.append("Recent commits:")
            lines.extend(f"- {str(item)}" for item in recent_commits[:5])
        repo_candidates = git.get("repo_candidates", [])
        if isinstance(repo_candidates, list) and len(repo_candidates) > 1:
            lines.append(
                "Repo candidates: "
                + ", ".join(str(item) for item in repo_candidates[:8] if str(item).strip())
            )
        return "\n".join(lines)

    def _format_workspace_search_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Workspace search failed: "
                f"{result.get('error', 'Unknown workspace search error.')}"
            )
        results = result.get("results", [])
        if not isinstance(results, list) or not results:
            return (
                f"No workspace search results for `{result.get('query', '')}` "
                f"in `{result.get('mode', 'text')}` mode."
            )
        lines = [
            (
                f"Workspace search for `{result.get('query', '')}` "
                f"in `{result.get('mode', 'text')}` mode:"
            )
        ]
        for item in results[:12]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            line_number = item.get("line")
            symbol = str(item.get("symbol", "")).strip()
            symbol_kind = str(item.get("symbol_kind", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if symbol:
                location = f"{path}:{line_number}" if line_number else path
                lines.append(
                    f"- {symbol_kind or 'symbol'} `{symbol}` at {location}"
                )
            elif line_number:
                lines.append(f"- {path}:{line_number}")
            else:
                lines.append(f"- {path}")
            if snippet:
                lines.append(f"  {snippet}")
        return "\n".join(lines)

    def _format_snapshot_create_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Workspace snapshot failed: "
                f"{result.get('error', 'Unknown workspace snapshot error.')}"
            )
        snapshot = result.get("snapshot", {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        lines = [
            "Workspace snapshot created.",
            f"Snapshot ID: {snapshot.get('id', '')}",
            f"Label: {snapshot.get('label', '') or '(none)'}",
            f"Files captured: {snapshot.get('file_count', 0)}",
            f"Total bytes: {snapshot.get('total_bytes', 0)}",
        ]
        sample_files = snapshot.get("sample_files", [])
        if isinstance(sample_files, list) and sample_files:
            lines.append(
                "Sample files: " + ", ".join(str(item) for item in sample_files[:8])
            )
        return "\n".join(lines)

    def _format_snapshot_list_result(self, result: dict[str, object]) -> str:
        snapshots = result.get("snapshots", [])
        if not isinstance(snapshots, list) or not snapshots:
            return "No workspace snapshots yet."
        lines = []
        for item in snapshots[:10]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip() or "(no label)"
            lines.append(
                (
                    f"- {item.get('id', '')} | {label} | "
                    f"{item.get('file_count', 0)} files | {item.get('total_bytes', 0)} bytes"
                )
            )
        return "\n".join(lines)

    def _format_pending_patch_list(self, result: dict[str, object]) -> str:
        pending_patches = result.get("pending_patches", [])
        if not isinstance(pending_patches, list) or not pending_patches:
            return "No pending workspace patches."
        lines = []
        for patch in pending_patches[:8]:
            if not isinstance(patch, dict):
                continue
            lines.extend(
                [
                    f"- {patch.get('id', '')} | {patch.get('path', '')} | {patch.get('summary', '')}",
                    str(patch.get("diff", "")) or "(empty diff)",
                ]
            )
        return "\n".join(lines)

    def _format_workspace_review_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Workspace review failed: "
                f"{result.get('error', 'Unknown workspace review error.')}"
            )
        lines = [str(result.get("summary", "")).strip() or "Workspace review is empty."]
        diff_stat = str(result.get("diff_stat", "")).strip()
        if diff_stat:
            lines.append("Diff stat:")
            lines.append(diff_stat)
        changed_files = result.get("changed_files", [])
        if isinstance(changed_files, list) and changed_files:
            lines.append("Changed files: " + ", ".join(str(item) for item in changed_files[:20]))
        diff_text = str(result.get("diff", "")).strip()
        if diff_text:
            if len(diff_text) > 4_000:
                diff_text = f"{diff_text[:4_000]}\n...[review diff truncated]..."
            lines.extend(["Unified diff:", diff_text])
        else:
            lines.append("Unified diff: none")
        pending_patches = result.get("pending_patches", [])
        if isinstance(pending_patches, list):
            lines.append(f"Pending patches: {len(pending_patches)}")
        return "\n".join(lines)

    def _format_git_branch_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Git branch creation failed: "
                f"{result.get('error', 'Unknown Git branch error.')}"
            )
        git = result.get("git", {})
        if not isinstance(git, dict):
            git = {}
        lines = [
            f"Created branch: {result.get('branch', '') or git.get('branch', '')}",
            f"Repo path: {git.get('repo_path', '.')}",
            f"Active branch: {git.get('branch', '') or '(unknown)'}",
        ]
        review = result.get("review", {})
        if isinstance(review, dict):
            review_summary = str(review.get("summary", "")).strip()
            if review_summary:
                lines.extend(["Review summary:", review_summary])
        return "\n".join(lines)

    def _format_git_handoff_result(self, result: dict[str, object]) -> str:
        if not result.get("ok"):
            return (
                "Git handoff preparation failed: "
                f"{result.get('error', 'Unknown Git handoff error.')}"
            )
        handoff = result.get("handoff", {})
        git = result.get("git", {})
        if not isinstance(handoff, dict):
            handoff = {}
        if not isinstance(git, dict):
            git = {}
        lines = [
            f"Repo path: {handoff.get('repo_path', git.get('repo_path', '.'))}",
            f"Current branch: {handoff.get('current_branch', git.get('branch', '')) or '(unknown)'}",
        ]
        branch_suggestion = str(handoff.get("branch_suggestion", "")).strip()
        if branch_suggestion:
            lines.append(f"Suggested branch: {branch_suggestion}")
        changed_files = handoff.get("changed_files", [])
        if isinstance(changed_files, list) and changed_files:
            lines.append(
                "Changed files: " + ", ".join(str(item) for item in changed_files[:12])
            )
        commit_message = handoff.get("commit_message", {})
        if isinstance(commit_message, dict):
            subject = str(commit_message.get("subject", "")).strip()
            body = str(commit_message.get("body", "")).strip()
            if subject:
                lines.append(f"Commit subject: {subject}")
            if body:
                lines.extend(["Commit body:", body])
        pull_request = handoff.get("pull_request", {})
        if isinstance(pull_request, dict):
            pr_title = str(pull_request.get("title", "")).strip()
            pr_body = str(pull_request.get("body", "")).strip()
            if pr_title:
                lines.append(f"PR title: {pr_title}")
            if pr_body:
                preview = pr_body if len(pr_body) <= 1200 else f"{pr_body[:1200]}\n...[truncated]..."
                lines.extend(["PR body:", preview])
        validation_commands = handoff.get("validation_commands", [])
        if isinstance(validation_commands, list) and validation_commands:
            lines.append("Validation commands:")
            lines.extend(f"- {str(command)}" for command in validation_commands[:8])
        return "\n".join(lines)


def _ordered_nonempty_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _truncate_agent_text(value: str, *, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n...[truncated]..."


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _dedupe_changed_entries(
    entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        path = str(entry.get("path", "")).strip()
        status = str(entry.get("status", "")).strip()
        source = str(entry.get("source", "")).strip()
        if not path:
            continue
        key = (source, status, path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "path": path,
                "status": status or "?",
                "source": source or "unknown",
                "summary": str(entry.get("summary", "")).strip() or path,
            }
        )
    return unique
