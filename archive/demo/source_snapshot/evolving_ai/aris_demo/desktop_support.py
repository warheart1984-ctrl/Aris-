from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog
from typing import Any

from evolving_ai.app.attachments import Attachment
from evolving_ai.app.config import AppConfig
from evolving_ai.app.model_switchboard import build_model_router_payload

from .feedback import build_feedback_packet, feedback_form_url, write_feedback_packet
from .profiles import DEFAULT_PROFILE_ID, resolve_profile
from .service import ArisDemoChatService
from .workspace_registry import WorkspaceRegistry


_ALLOWED_CHAT_MODES = {"chat", "deep", "agent"}


def _platform_key(platform_name: str | None = None) -> str:
    value = str(platform_name or sys.platform).strip().lower()
    if value.startswith("win"):
        return "windows"
    if value in {"darwin", "mac", "macos"}:
        return "macos"
    return "linux"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _model_router_payload(
    *,
    config_payload: dict[str, Any] | None = None,
    status_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_router = _dict(_dict(config_payload).get("model_router"))
    status_router = _dict(_dict(status_payload).get("model_router"))
    payload = status_router or config_router
    if payload.get("systems"):
        return payload
    return build_model_router_payload(
        mode=str(payload.get("mode", "auto")).strip().lower() or "auto",
        pinned_system=str(payload.get("pinned_system", "")).strip().lower() or None,
        general_model=str(_dict(config_payload).get("general_model", "")).strip() or None,
        coding_model=str(_dict(config_payload).get("coding_model", "")).strip() or None,
        light_coding_model=str(_dict(config_payload).get("light_coding_model", "")).strip() or None,
    )


def _model_router_summary(model_router: dict[str, Any] | None) -> tuple[str, ...]:
    payload = _dict(model_router)
    systems = [
        f"{str(item.get('label', item.get('id', 'system'))).strip()}: {str(item.get('model', 'unknown')).strip()}"
        for item in list(payload.get("systems", []))
        if isinstance(item, dict)
    ]
    return tuple(system for system in systems if system.strip())


def default_desktop_data_root(
    platform_name: str | None = None,
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
) -> Path:
    override = str(os.getenv("ARIS_DEMO_DESKTOP_ROOT", "")).strip()
    if override:
        return Path(override).expanduser().resolve()

    profile = resolve_profile(profile_id)
    platform_key = _platform_key(platform_name)
    if platform_key == "windows":
        base = Path(
            os.getenv("LOCALAPPDATA", os.getenv("APPDATA", str(Path.home() / "AppData" / "Local")))
        )
        return (base / profile.data_dir_name).resolve()
    if platform_key == "macos":
        return (Path.home() / "Library" / "Application Support" / profile.data_dir_name).resolve()

    xdg_data_home = str(os.getenv("XDG_DATA_HOME", "")).strip()
    linux_name = profile.data_dir_name.lower().replace(" ", "-")
    if xdg_data_home:
        return (Path(xdg_data_home) / linux_name).resolve()
    return (Path.home() / ".local" / "share" / linux_name).resolve()


def select_project_folder() -> str | None:
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    try:
        folder_path = filedialog.askdirectory(title="Select Project Folder")
    finally:
        root.destroy()

    if not folder_path:
        return None
    return str(Path(folder_path).expanduser().resolve())


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed or "item"


def _display_time(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Now"
    if "T" in text and len(text) >= 16:
        return text[11:16]
    if len(text) > 16:
        return text[-16:]
    return text


def _workspace_task_status(raw_status: object) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"running", "queued"}:
        return "Running"
    if normalized in {"approved", "completed", "done"}:
        return "Done"
    if normalized in {"ready_for_approval", "needs_changes", "blocked", "failed", "review"}:
        return "Review"
    return "Review"


def _workspace_task_priority(raw_status: object) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"blocked", "failed"}:
        return "Critical"
    if normalized in {"ready_for_approval", "needs_changes"}:
        return "High"
    if normalized in {"running", "queued"}:
        return "Medium"
    return "Medium"


def build_workspace_surface(
    *,
    session_id: str | None,
    current_project_path: str | None,
    workspace: dict[str, Any] | None,
    activity: tuple[dict[str, Any], ...],
    status_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_payload = _dict(workspace)
    status = _dict(status_payload)
    git = _dict(workspace_payload.get("git"))
    verification = _dict(workspace_payload.get("verification"))
    forge = _dict(status.get("forge"))
    forge_eval = _dict(status.get("forge_eval"))
    pending_approvals = (
        list(workspace_payload.get("pending_approvals", []))
        if isinstance(workspace_payload.get("pending_approvals", []), list)
        else []
    )
    task_entries = (
        list(workspace_payload.get("tasks", []))
        if isinstance(workspace_payload.get("tasks", []), list)
        else []
    )

    repos: list[dict[str, Any]] = []
    seen_repo_names: set[str] = set()

    def add_repo(
        *,
        name: str,
        path: str,
        branch: str,
        status: str,
        detail: str,
        last_sync: str,
        source: str,
    ) -> None:
        key = str(name).strip().lower()
        if not key or key in seen_repo_names:
            return
        seen_repo_names.add(key)
        repos.append(
            {
                "id": f"repo-{_slug(name)}",
                "name": name,
                "path": path,
                "branch": branch,
                "status": status,
                "detail": detail,
                "last_sync": last_sync,
                "source": source,
            }
        )

    if current_project_path:
        project_path = str(Path(current_project_path))
        add_repo(
            name=Path(project_path).name or "Selected Project",
            path=project_path,
            branch=str(git.get("branch", "")).strip() or "workspace/selected",
            status="Connected",
            detail="Selected through the native folder picker and scoped into the ARIS workspace.",
            last_sync="Selected",
            source="selected_folder",
        )

    if git.get("is_repo") and str(git.get("repo_path", "")).strip():
        repo_path = str(git.get("repo_path", "")).strip()
        changed_files = git.get("changed_files", [])
        changed_count = len(changed_files) if isinstance(changed_files, list) else 0
        add_repo(
            name=Path(repo_path).name or "Workspace Repo",
            path=repo_path,
            branch=str(git.get("branch", "")).strip() or "workspace/active",
            status="Connected",
            detail=(
                f"Git workspace is live with {changed_count} changed file(s) visible to ARIS."
                if changed_count
                else "Git workspace is live and available to ARIS for repo-aware work."
            ),
            last_sync="Live",
            source="workspace_git",
        )

    fallback_repos = (
        {
            "name": "AAIS-main",
            "path": "C:/workspace/AAIS-main",
            "branch": str(git.get("branch", "")).strip() or "runtime/extraction",
            "status": "Connected",
            "detail": "AAIS-main is connected. I found the likely routing and approval seams.",
            "last_sync": "2m ago",
            "source": "demo_seed",
        },
        {
            "name": "ARIS-runtime",
            "path": "C:/workspace/ARIS-runtime",
            "branch": "workspace/operator-shell",
            "status": "Syncing",
            "detail": "Branch metadata is refreshing for runtime and governance files.",
            "last_sync": "Syncing now",
            "source": "demo_seed",
        },
        {
            "name": "Repo-AI",
            "path": "C:/workspace/Repo-AI",
            "branch": "feature/task-board",
            "status": "Error",
            "detail": "Credential refresh is required before execution can resume.",
            "last_sync": "14m ago",
            "source": "demo_seed",
        },
    )
    for repo in fallback_repos:
        add_repo(**repo)

    if not repos:
        add_repo(
            name="Workspace",
            path=current_project_path or ".",
            branch="workspace/default",
            status="Connected",
            detail="ARIS can use this workspace as the current repo scope.",
            last_sync="Now",
            source="fallback",
        )

    primary_repo_id = repos[0]["id"]
    repo_ids = [repo["id"] for repo in repos]

    tasks: list[dict[str, Any]] = []
    if task_entries:
        for index, item in enumerate(task_entries):
            if not isinstance(item, dict):
                continue
            raw_status = str(item.get("status", "")).strip()
            title = str(item.get("title", "")).strip() or "Workspace task"
            summary = (
                str(item.get("goal", "")).strip()
                or str(item.get("summary", "")).strip()
                or title
            )
            latest_update = (
                str(item.get("summary", "")).strip()
                or str(item.get("review_summary", "")).strip()
                or str(item.get("final_message", "")).strip()
                or "ARIS is tracking this task inside the workspace."
            )
            tasks.append(
                {
                    "id": str(item.get("id", f"task-{index + 1}")).strip() or f"task-{index + 1}",
                    "title": title,
                    "repo_id": repo_ids[min(index, len(repo_ids) - 1)] if repo_ids else primary_repo_id,
                    "status": _workspace_task_status(raw_status),
                    "priority": _workspace_task_priority(raw_status),
                    "latest_update": latest_update,
                    "summary": summary,
                    "raw_status": raw_status or "unknown",
                }
            )
    else:
        fallback_tasks = (
            (
                "Build repo connection manager",
                repo_ids[0] if repo_ids else primary_repo_id,
                "Running",
                "High",
                "Forge is indexing repo seams while ARIS keeps the approval boundary closed.",
                "Establish repo registration, branch awareness, and context handoff into ARIS.",
            ),
            (
                "Create task board with approvals",
                repo_ids[min(1, len(repo_ids) - 1)] if repo_ids else primary_repo_id,
                "Review",
                "Critical",
                "Execution finished. Diff and validation output are waiting in review.",
                "Expose running, review, and done states without letting the worker lane own the voice.",
            ),
            (
                "Add branch and environment controls",
                repo_ids[0] if repo_ids else primary_repo_id,
                "Running",
                "Medium",
                "Runtime branch controls are mapped and ready for a governed build route.",
                "Make branch, environment, and workspace controls visible from the operator surface.",
            ),
            (
                "Expose Forge as worker status only",
                repo_ids[min(1, len(repo_ids) - 1)] if repo_ids else primary_repo_id,
                "Done",
                "High",
                "Completed. Worker output is visible, but ARIS remains the only speaker.",
                "Keep Forge in execution lanes while ARIS preserves identity and narration.",
            ),
            (
                "Inspect protected execution boundaries",
                repo_ids[min(2, len(repo_ids) - 1)] if repo_ids else primary_repo_id,
                "Review",
                "Critical",
                "Protected route checks are staged around Forge, approvals, and locked boundaries.",
                "Verify that no evolving-core path is visible, routable, or callable from the demo workspace.",
            ),
        )
        for index, (title, repo_id, status, priority, latest_update, summary) in enumerate(fallback_tasks, start=1):
            tasks.append(
                {
                    "id": f"AR-{100 + index * 7}",
                    "title": title,
                    "repo_id": repo_id,
                    "status": status,
                    "priority": priority,
                    "latest_update": latest_update,
                    "summary": summary,
                    "raw_status": status.lower(),
                }
            )

    activity_items: list[dict[str, Any]] = []
    for index, entry in enumerate(activity):
        if not isinstance(entry, dict):
            continue
        label = (
            str(entry.get("title", "")).strip()
            or str(entry.get("event", "")).strip()
            or str(entry.get("kind", "")).strip()
            or "Runtime event"
        )
        detail = (
            str(entry.get("summary", "")).strip()
            or str(entry.get("detail", "")).strip()
            or str(entry.get("message", "")).strip()
            or "ARIS recorded a workspace event."
        )
        raw_status = str(entry.get("status", "")).strip().lower()
        tone = "connected" if raw_status in {"ok", "ready", "active"} else "warning" if raw_status in {"pending", "waiting"} else "neutral"
        activity_items.append(
            {
                "id": f"activity-{index + 1}",
                "time": _display_time(entry.get("created_at", "") or entry.get("timestamp", "") or entry.get("time", "")),
                "label": label,
                "detail": detail,
                "tone": tone,
            }
        )

    if not activity_items:
        activity_items = [
            {
                "id": "activity-seed-1",
                "time": "14:12",
                "label": "Repo connected",
                "detail": "AAIS-main returned a healthy branch map and approval seam inventory.",
                "tone": "connected",
            },
            {
                "id": "activity-seed-2",
                "time": "14:08",
                "label": "Task ready for review",
                "detail": "ARIS moved the workspace shell task into Review after validation completed.",
                "tone": "warning",
            },
            {
                "id": "activity-seed-3",
                "time": "14:02",
                "label": "Governed apply held",
                "detail": "Patch output is waiting for operator approval before apply.",
                "tone": "warning",
            },
        ]

    worker_status = "Ready"
    worker_title = "Worker Surface"
    worker_lines = [
        "Forge is available as a worker, but ARIS keeps the conversation here in the operator workspace.",
        "Logs, patch output, and validation will surface here when execution runs.",
    ]
    if pending_approvals:
        worker_status = "Review"
        worker_title = "Approval Gate"
        worker_lines = [
            str(item.get("title", "Approval required")).strip() or "Approval required"
            for item in pending_approvals[:3]
            if isinstance(item, dict)
        ] or ["Approval is required before execution can proceed."]
    elif forge.get("connected"):
        worker_status = "Ready"
        worker_title = "Forge Worker Lane"
        worker_lines = [
            "Forge is connected as the active worker lane for this profile.",
            (
                "Forge Eval is connected for validation and review."
                if forge_eval.get("connected")
                else "Forge Eval is not connected for this profile."
            ),
            "ARIS remains the only speaking surface while Forge stays in execution, diff, and validation lanes.",
        ]
    elif verification.get("available"):
        worker_status = "Ready"
        worker_title = "Validation Lane"
        worker_lines = [
            "Verification presets are available for this workspace.",
            "ARIS can route test and lint output through the worker surface when needed.",
        ]
    elif git.get("is_repo"):
        worker_status = "Ready"
        worker_title = "Repo Worker Lane"
        worker_lines = [
            f"Git repo detected at {str(git.get('repo_path', '')).strip() or '.'}.",
            "ARIS can stage worker execution, diffs, and validation against the active branch.",
        ]

    return {
        "session_id": session_id,
        "repos": repos,
        "tasks": tasks,
        "activity": activity_items,
        "worker": {
            "title": worker_title,
            "status": worker_status,
            "lines": worker_lines,
        },
        "approval_count": len(pending_approvals),
        "selected_repo_id": primary_repo_id,
        "selected_task_id": tasks[0]["id"] if tasks else "",
    }


@dataclass(frozen=True, slots=True)
class DesktopFeature:
    id: str
    label: str
    status: str
    source: str
    detail: str


@dataclass(frozen=True, slots=True)
class DesktopPackagingTarget:
    id: str
    label: str
    build_os: str
    artifact: str
    detail: str
    profile_id: str
    profile_label: str
    model_router_mode: str
    model_systems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DesktopChatEvent:
    event: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DesktopSnapshot:
    session_id: str | None
    current_project_path: str | None
    workspace_surface: dict[str, Any]
    config: dict[str, Any]
    status: dict[str, Any]
    health: dict[str, Any]
    sessions: tuple[dict[str, Any], ...]
    transcript: tuple[dict[str, Any], ...]
    workspace: dict[str, Any] | None
    mystic: dict[str, Any] | None
    activity: tuple[dict[str, Any], ...]
    discards: tuple[dict[str, Any], ...]
    fame: tuple[dict[str, Any], ...]
    shame: tuple[dict[str, Any], ...]
    features: tuple[DesktopFeature, ...]
    packaging_targets: tuple[DesktopPackagingTarget, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_project_path": self.current_project_path,
            "workspace_surface": self.workspace_surface,
            "config": self.config,
            "status": self.status,
            "health": self.health,
            "sessions": list(self.sessions),
            "transcript": list(self.transcript),
            "workspace": self.workspace,
            "mystic": self.mystic,
            "activity": list(self.activity),
            "discards": list(self.discards),
            "fame": list(self.fame),
            "shame": list(self.shame),
            "features": [asdict(item) for item in self.features],
            "packaging_targets": [asdict(item) for item in self.packaging_targets],
        }


def desktop_packaging_targets(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    model_router: dict[str, Any] | None = None,
) -> tuple[DesktopPackagingTarget, ...]:
    profile = resolve_profile(profile_id)
    router = _dict(model_router) or build_model_router_payload()
    systems = _model_router_summary(router)
    router_mode = str(router.get("mode", "auto")).strip().lower() or "auto"
    detail_suffix = (
        f" Includes the {router_mode} three-system switch: {'; '.join(systems)}."
        if systems
        else ""
    )
    return (
        DesktopPackagingTarget(
            id="windows",
            label="Windows",
            build_os="windows-latest",
            artifact=f"{profile.artifact_name}.exe",
            detail=(
                "Build natively on Windows to produce the desktop executable bundle for "
                f"{profile.artifact_name}.{detail_suffix}"
            ),
            profile_id=profile.id,
            profile_label=profile.label,
            model_router_mode=router_mode,
            model_systems=systems,
        ),
        DesktopPackagingTarget(
            id="macos",
            label="macOS",
            build_os="macos-latest",
            artifact=f"{profile.artifact_name}.app",
            detail=(
                "Build natively on macOS to produce the signed-ready application bundle for "
                f"{profile.artifact_name}.{detail_suffix}"
            ),
            profile_id=profile.id,
            profile_label=profile.label,
            model_router_mode=router_mode,
            model_systems=systems,
        ),
        DesktopPackagingTarget(
            id="linux",
            label="Linux",
            build_os="ubuntu-latest",
            artifact=f"dist/{profile.artifact_name}/",
            detail=(
                "Build natively on Linux to produce the desktop bundle for downstream AppImage or distro packaging "
                f"for {profile.artifact_name}.{detail_suffix}"
            ),
            profile_id=profile.id,
            profile_label=profile.label,
            model_router_mode=router_mode,
            model_systems=systems,
        ),
    )


def current_packaging_target(
    platform_name: str | None = None,
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    model_router: dict[str, Any] | None = None,
) -> DesktopPackagingTarget:
    key = _platform_key(platform_name)
    for target in desktop_packaging_targets(profile_id=profile_id, model_router=model_router):
        if target.id == key:
            return target
    return desktop_packaging_targets(profile_id=profile_id, model_router=model_router)[-1]


def parse_sse_events(chunk: str) -> tuple[DesktopChatEvent, ...]:
    blocks = [item.strip() for item in str(chunk or "").split("\n\n") if item.strip()]
    events: list[DesktopChatEvent] = []
    for block in blocks:
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("event:"):
                event_name = stripped.partition(":")[2].strip() or "message"
                continue
            if stripped.startswith("data:"):
                data_lines.append(stripped.partition(":")[2].strip())
        raw_payload = "\n".join(data_lines).strip()
        payload: dict[str, Any]
        if not raw_payload:
            payload = {}
        else:
            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                payload = {"raw": raw_payload}
            else:
                payload = parsed if isinstance(parsed, dict) else {"value": parsed}
        events.append(DesktopChatEvent(event=event_name, payload=payload))
    return tuple(events)


def build_feature_inventory(
    *,
    config_payload: dict[str, Any],
    status_payload: dict[str, Any],
    health_payload: dict[str, Any],
) -> tuple[DesktopFeature, ...]:
    capabilities = _dict(config_payload.get("capabilities"))
    demo_mode = _dict(status_payload.get("demo_mode"))
    ul_runtime = _dict(status_payload.get("ul_runtime"))
    primitive_inventory = _dict(ul_runtime.get("primitive_inventory"))
    substrate = _dict(ul_runtime.get("substrate"))
    shield = _dict(status_payload.get("shield_of_truth"))
    logbook = _dict(status_payload.get("repo_logbook"))
    mystic = _dict(status_payload.get("mystic"))
    mystic_reflection = _dict(status_payload.get("mystic_reflection"))
    shell_execution = _dict(status_payload.get("shell_execution"))
    kill_switch = _dict(status_payload.get("kill_switch"))
    hall_of_discard = _dict(status_payload.get("hall_of_discard"))
    hall_of_fame = _dict(status_payload.get("hall_of_fame"))
    hall_of_shame = _dict(status_payload.get("hall_of_shame"))
    forge = _dict(status_payload.get("forge"))
    evolving_engine = _dict(status_payload.get("evolving_engine"))
    model_router = _model_router_payload(config_payload=config_payload, status_payload=status_payload)
    model_systems = _model_router_summary(model_router)

    features = [
        DesktopFeature(
            id="operator_surface",
            label="Operator Surface",
            status="live" if capabilities.get("chat") else "offline",
            source="ARIS Demo host",
            detail="Governed conversation, tool routing, and workspace inspection remain available through the existing service layer.",
        ),
        DesktopFeature(
            id="ul_runtime",
            label="UL Runtime",
            status="extracted" if primitive_inventory else "missing",
            source="UL Runtime substrate",
            detail=(
                f"{primitive_inventory.get('binding_layer', 'Unknown binding layer')} with "
                f"{len(primitive_inventory.get('core_primitives', []))} canonical runtime primitives."
                if primitive_inventory
                else "The extracted UL runtime substrate is not present in status output."
            ),
        ),
        DesktopFeature(
            id="identity_source",
            label="UL Identity Source",
            status=str(primitive_inventory.get("identity_source", "unknown")),
            source="Runtime law",
            detail="Identity remains sourced from UL rather than being delegated to the desktop host.",
        ),
        DesktopFeature(
            id="cisiv_governance",
            label="CISIV Governance",
            status="staged" if primitive_inventory.get("governance_model") == "CISIV" else "unknown",
            source="Runtime law",
            detail=(
                "Stages: " + " -> ".join(substrate.get("cisiv_stage_sequence", []))
                if substrate.get("cisiv_stage_sequence")
                else "CISIV stage sequence was not exposed."
            ),
        ),
        DesktopFeature(
            id="speech_chain",
            label="Law Of Speech",
            status="enforced" if primitive_inventory.get("speech_chain") else "unknown",
            source="Runtime law",
            detail=" -> ".join(primitive_inventory.get("speech_chain", ["0001", "1000", "1001"])),
        ),
        DesktopFeature(
            id="shield_of_truth",
            label="Shield Of Truth",
            status="active" if shield.get("active") else "offline",
            source="Governance",
            detail=(
                f"Immutable laws: {len(shield.get('immutable_laws', []))}; failures tracked: {shield.get('failure_registry_count', 0)}."
            ),
        ),
        DesktopFeature(
            id="ledger_logbook",
            label="Ledger And Logbook",
            status="required" if logbook.get("required_for_meaningful_changes") else "optional",
            source="Truth surface",
            detail=(
                f"Repo logbook entries: {logbook.get('entry_count', 0)}; law ledger active: {bool(ul_runtime.get('ledger_path'))}."
            ),
        ),
        DesktopFeature(
            id="model_switchboard",
            label="Model Switchboard",
            status=str(model_router.get("mode", "unknown")),
            source="Three-system router",
            detail=(
                f"Systems: {'; '.join(model_systems)}."
                if model_systems
                else "The three-system model router did not expose any configured systems."
            ),
        ),
        DesktopFeature(
            id="workspace_intel",
            label="Workspace Intel",
            status="live" if capabilities.get("workspace_repo_map") else "offline",
            source="ARIS Demo host",
            detail="Project detection, repo map inspection, git state, verification, and approvals stay outside the runtime core.",
        ),
        DesktopFeature(
            id="shell_execution",
            label="Shell Execution",
            status="degraded" if shell_execution.get("degraded") else "ready",
            source="Host capability",
            detail=(
                f"Requested backend: {shell_execution.get('requested_backend', 'unknown')}; "
                f"active backend: {shell_execution.get('active_backend', 'unknown')}."
            ),
        ),
        DesktopFeature(
            id="mystic_sustainment",
            label="Mystic Sustainment",
            status="active" if mystic.get("active") else "offline",
            source="Human sustainment layer",
            detail=f"Latest reminders tracked: {len(mystic.get('latest_reminders', []))}.",
        ),
        DesktopFeature(
            id="mystic_reflection",
            label="Mystic Reflection",
            status="active" if mystic_reflection.get("active") else "offline",
            source="Reflection layer",
            detail=(
                "Merged with Jarvis under ARIS governance."
                if mystic_reflection.get("merged_with_jarvis")
                else "Reflection remains available as a separate governed surface."
            ),
        ),
        DesktopFeature(
            id="governance_halls",
            label="Governance Halls",
            status="active",
            source="Containment surfaces",
            detail=(
                f"Discard: {hall_of_discard.get('entry_count', 0)}, "
                f"Fame: {hall_of_fame.get('entry_count', 0)}, "
                f"Shame: {hall_of_shame.get('entry_count', 0)}."
            ),
        ),
        DesktopFeature(
            id="kill_switch",
            label="Kill Switch",
            status=str(kill_switch.get("mode", "unknown")),
            source="Containment",
            detail=str(kill_switch.get("summary", "Kill switch state is unavailable.")),
        ),
        DesktopFeature(
            id="forge_planning",
            label="Forge Planning",
            status=(
                "available"
                if forge.get("connected")
                else ("stripped" if demo_mode.get("active") else "offline")
            ),
            source="Runtime profile",
            detail=(
                "Forge and Forge Eval are available as governed worker surfaces while ARIS keeps the conversation on the operator side."
                if forge.get("connected")
                else (
                    "Forge and Forge Eval stay truthfully surfaced as stripped in the demo host."
                    if demo_mode.get("active")
                    else "Forge or Forge Eval is unavailable in this runtime profile."
                )
            ),
        ),
        DesktopFeature(
            id="evolving_engine",
            label="Evolving Engine",
            status="stripped" if not evolving_engine.get("active") else "active",
            source="Runtime profile",
            detail=(
                "The evolving engine is admitted through the extracted UL runtime and remains proposal-bound under law."
                if evolving_engine.get("active")
                else str(
                    evolving_engine.get(
                        "reason",
                        "The evolving engine remains outside this ARIS Demo profile.",
                    )
                )
            ),
        ),
        DesktopFeature(
            id="non_copy_clause",
            label="Non-Copy Clause",
            status="enforced" if primitive_inventory.get("binding_layer") == "Universal Adapter Protocol" else "unknown",
            source="Universal Adapter Protocol",
            detail="Protected identities still depend on lawful host capability declarations before claims are admitted.",
        ),
        DesktopFeature(
            id="startup_health",
            label="Startup Health",
            status="ready" if health_payload.get("ok") else "blocked",
            source="ARIS Demo runtime",
            detail=(
                "Startup blockers: none"
                if not health_payload.get("startup_blockers")
                else "Startup blockers: " + " | ".join(str(item) for item in health_payload.get("startup_blockers", []))
            ),
        ),
    ]
    return tuple(features)


class ArisDemoDesktopHost:
    """Desktop host wrapper over the existing ARIS Demo service."""

    @staticmethod
    def _ensure_data_root(requested_root: Path, *, fallback_name: str) -> Path:
        resolved = requested_root.resolve()
        fallback = (Path.cwd() / ".runtime" / fallback_name).resolve()
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            state_root = resolved / ".forge_chat"
            if state_root.exists() and state_root.is_file():
                raise PermissionError
            state_root.mkdir(parents=True, exist_ok=True)
            return resolved
        except OSError:
            fallback.mkdir(parents=True, exist_ok=True)
            (fallback / ".forge_chat").mkdir(parents=True, exist_ok=True)
            return fallback

    def __init__(
        self,
        *,
        data_root: Path | None = None,
        start_workers: bool = True,
        profile_id: str = DEFAULT_PROFILE_ID,
    ) -> None:
        self.profile = resolve_profile(profile_id)
        self.data_root = self._ensure_data_root(
            data_root or default_desktop_data_root(profile_id=self.profile.id),
            fallback_name=f"aris_demo_desktop_{self.profile.id}",
        )
        self.config = AppConfig.from_env(self.data_root)
        self.service = ArisDemoChatService(self.config, profile_id=self.profile.id)
        self.app_version = str(os.getenv("ARIS_DEMO_APP_VERSION", "0.1.0")).strip() or "0.1.0"
        self.current_project_path: str | None = None
        self._selected_workspace_file_path: str | None = None
        self._event_log_path = (self.data_root / "runtime-events.jsonl").resolve()
        self._feedback_dir = (self.data_root / "feedback").resolve()
        self.workspace_registry = WorkspaceRegistry(
            (self.data_root / "workspace_registry.json").resolve(),
            seed_root=Path(__file__).resolve().parents[2],
        )
        self._workers_started = False
        if start_workers:
            self.service.start_background_workers()
            self._workers_started = True
        self._record_event(
            "system",
            "ARIS ready",
            f"{self.profile.desktop_title} host is online with {self.workspace_registry.active().get('name', 'workspace')} active.",
        )

    def close(self) -> None:
        if self._workers_started:
            self.service.stop_background_workers()
            self._workers_started = False

    def create_session(self, title_seed: str | None = None) -> str:
        session = self.service.sessions.get_or_create(None, title_seed or self.profile.desktop_title)
        return session.id

    def ensure_session(self, session_id: str | None = None, *, title_seed: str | None = None) -> str:
        if session_id:
            existing = self.service.sessions.sessions.get(session_id)
            if existing is not None:
                return existing.id
        sessions = self.service.list_sessions()
        if sessions:
            return str(sessions[0].get("id", "")).strip() or self.create_session(title_seed)
        return self.create_session(title_seed)

    def list_sessions(self) -> list[dict[str, Any]]:
        return list(self.service.list_sessions())

    def session_messages(self, session_id: str) -> tuple[dict[str, Any], ...]:
        session = self.service.sessions.sessions.get(session_id)
        if session is None:
            return ()
        messages = [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in session.messages
        ]
        return tuple(messages)

    def set_current_project_path(self, folder_path: str | Path | None) -> str | None:
        if not folder_path:
            self.current_project_path = None
            return None
        resolved = Path(str(folder_path)).expanduser().resolve()
        self.current_project_path = str(resolved)
        workspace = self.workspace_registry.add_workspace(
            resolved,
            name=resolved.name or "Selected Project",
            workspace_type="project",
            activate=True,
        )
        self._record_event(
            "workspace",
            "Workspace selected",
            f"{workspace.get('name', 'Workspace')} is now the active workspace root.",
            workspace_id=str(workspace.get("id", "")),
            file_path=str(resolved),
        )
        return self.current_project_path

    def select_current_project(self) -> str | None:
        folder_path = select_project_folder()
        if not folder_path:
            return None
        return self.set_current_project_path(folder_path)

    def _record_event(
        self,
        kind: str,
        label: str,
        detail: str,
        *,
        status: str = "ok",
        workspace_id: str | None = None,
        file_path: str | None = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "kind": str(kind or "runtime").strip() or "runtime",
            "title": str(label or "Event").strip() or "Event",
            "detail": str(detail or "").strip(),
            "status": str(status or "ok").strip() or "ok",
            "workspace_id": str(workspace_id or "").strip(),
            "file_path": str(file_path or "").strip(),
        }
        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def recent_events(self, *, limit: int = 30) -> list[dict[str, Any]]:
        if not self._event_log_path.exists():
            return []
        try:
            lines = self._event_log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in reversed(lines[-limit:]):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def workspaces(self) -> list[dict[str, Any]]:
        return self.workspace_registry.entries()

    def active_workspace(self) -> dict[str, Any]:
        return self.workspace_registry.active()

    def activate_workspace(self, workspace_id: str) -> dict[str, Any]:
        workspace = self.workspace_registry.set_active(workspace_id)
        self.current_project_path = str(workspace.get("root_path", "")).strip() or self.current_project_path
        self._record_event(
            "workspace",
            "Workspace activated",
            f"{workspace.get('name', 'Workspace')} is now active in ARIS Studio.",
            workspace_id=str(workspace.get("id", "")),
            file_path=str(workspace.get("root_path", "")),
        )
        return workspace

    def add_workspace(
        self,
        folder_path: str | Path,
        *,
        name: str | None = None,
        workspace_type: str = "project",
    ) -> dict[str, Any]:
        workspace = self.workspace_registry.add_workspace(
            folder_path,
            name=name,
            workspace_type=workspace_type,
            activate=True,
        )
        self.current_project_path = str(workspace.get("root_path", "")).strip() or self.current_project_path
        self._record_event(
            "workspace",
            "Workspace added",
            f"{workspace.get('name', 'Workspace')} was registered for bounded browsing and actions.",
            workspace_id=str(workspace.get("id", "")),
            file_path=str(workspace.get("root_path", "")),
        )
        return workspace

    def select_and_add_workspace(self) -> dict[str, Any] | None:
        folder_path = select_project_folder()
        if not folder_path:
            return None
        return self.add_workspace(folder_path)

    def workspace_tree(self, workspace_id: str | None = None) -> dict[str, Any]:
        return self.workspace_registry.tree_payload(workspace_id=workspace_id)

    def preview_workspace_target(
        self,
        target_path: str | Path,
        *,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        preview = self.workspace_registry.preview_file(target_path, workspace_id=workspace_id)
        self._selected_workspace_file_path = str(preview.get("path", "")).strip() or self._selected_workspace_file_path
        workspace = _dict(preview.get("workspace"))
        self._record_event(
            "file",
            "File previewed",
            f"{preview.get('relative_path', 'file')} was opened in the ARIS explorer.",
            workspace_id=str(workspace.get("id", "")),
            file_path=str(preview.get("path", "")),
        )
        return preview

    def search_workspace(self, query: str, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        results = self.workspace_registry.search_files(query, workspace_id=workspace_id)
        if query.strip():
            workspace = self.workspace_registry.by_id(workspace_id)
            self._record_event(
                "file",
                "Workspace searched",
                f"Search for '{query.strip()}' returned {len(results)} match(es).",
                workspace_id=str(workspace.get("id", "")),
                file_path=str(workspace.get("root_path", "")),
            )
        return results

    def workspace_action(
        self,
        action_name: str,
        target_path: str | Path,
        *,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        result = self.workspace_registry.action(action_name, target_path, workspace_id=workspace_id)
        payload = result.as_payload()
        self._record_event(
            "file",
            f"Action: {result.action}",
            result.summary,
            workspace_id=str(result.workspace.get("id", "")),
            file_path=result.path,
        )
        return payload

    def submit_feedback(
        self,
        *,
        feedback_type: str,
        user_note: str,
        active_brain: str,
        active_tier: str,
        active_workspace: str,
        recent_logs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        packet = build_feedback_packet(
            app_version=f"{self.profile.desktop_title} {self.app_version}",
            feedback_type=feedback_type,
            user_note=user_note,
            active_brain=active_brain,
            active_tier=active_tier,
            active_workspace=active_workspace,
            recent_events=self.recent_events(limit=12),
            recent_logs=list(recent_logs or [])[:12],
            runtime_profile=self.profile.id,
        )
        packet_path = write_feedback_packet(self._feedback_dir, packet)
        self._record_event(
            "feedback",
            "Tester feedback captured",
            f"{feedback_type} feedback was exported to {packet_path.name}.",
            workspace_id=str(self.active_workspace().get("id", "")),
            file_path=str(packet_path),
        )
        return {
            "packet": packet,
            "path": str(packet_path),
            "external_form_url": feedback_form_url(),
        }

    def _shipping_python_executable(self) -> Path:
        override = str(os.getenv("ARIS_SHIPPING_PYTHON", "")).strip()
        if override:
            return Path(override).expanduser().resolve()
        repo_root = Path(__file__).resolve().parents[2]
        bundled_runtime = repo_root / ".runtime" / "ul_desktop_runtime" / "venv" / "Scripts" / "python.exe"
        if bundled_runtime.exists():
            return bundled_runtime.resolve()
        return Path(sys.executable).resolve()

    def ship_release(self) -> dict[str, Any]:
        from .shipping_lane import ship_release

        payload = ship_release(
            repo_root=Path(__file__).resolve().parents[2],
            python_executable=self._shipping_python_executable(),
        )
        self._record_event(
            "shipping",
            "Shipping lane completed" if payload.get("ok") else "Shipping lane failed",
            f"Shipping returned {'PASS' if payload.get('ok') else 'FAIL'} with {len(list(payload.get('generated_artifact_paths', [])))} artifact path(s).",
            status="ok" if payload.get("ok") else "fail",
            workspace_id=str(self.active_workspace().get("id", "")),
        )
        return payload

    def snapshot(self, session_id: str | None = None) -> DesktopSnapshot:
        sessions = tuple(self.list_sessions())
        active_session_id = None
        if session_id and any(str(item.get("id", "")).strip() == session_id for item in sessions):
            active_session_id = session_id
        elif sessions:
            active_session_id = str(sessions[0].get("id", "")).strip() or None

        config_payload = self.service.config_payload()
        status_payload = self.service.aris_status_payload()
        health_payload = self.service.aris_health_payload()
        activity = tuple(self.service.aris_activity_payload(limit=10).get("activity", []))
        discards = tuple(self.service.aris_discards_payload(limit=10).get("entries", []))
        fame = tuple(self.service.aris_fame_payload(limit=10).get("entries", []))
        shame = tuple(self.service.aris_shame_payload(limit=10).get("entries", []))
        workspace = self.service.workspace_payload(active_session_id) if active_session_id else None
        mystic = self.service.aris_mystic_status(session_id=active_session_id) if active_session_id else None
        transcript = self.session_messages(active_session_id) if active_session_id else ()
        features = build_feature_inventory(
            config_payload=config_payload,
            status_payload=status_payload,
            health_payload=health_payload,
        )
        workspace_surface = build_workspace_surface(
            session_id=active_session_id,
            current_project_path=self.current_project_path,
            workspace=workspace,
            activity=activity,
            status_payload=status_payload,
        )
        active_workspace = self.active_workspace()
        explorer_payload = self.workspace_tree(str(active_workspace.get("id", "")))
        preview_payload: dict[str, Any] | None = None
        if self._selected_workspace_file_path:
            try:
                preview_payload = self.workspace_registry.preview_file(
                    self._selected_workspace_file_path,
                    workspace_id=str(active_workspace.get("id", "")),
                )
            except Exception:
                self._selected_workspace_file_path = None
                preview_payload = None
        workspace_surface.update(
            {
                "workspaces": self.workspaces(),
                "active_workspace": active_workspace,
                "file_explorer": {
                    "tree": explorer_payload.get("tree"),
                    "selected_file": preview_payload,
                    "selected_file_path": self._selected_workspace_file_path,
                },
                "event_stream": self.recent_events(limit=20),
                "feedback": {
                    "categories": ["bug", "confusing", "impressive", "feature_request"],
                    "external_form_url": feedback_form_url(),
                    "storage_path": str(self._feedback_dir),
                },
                "upgrades": [
                    {
                        "id": "upgrade-workspace-registry",
                        "title": "Promote workspace registry to governed default",
                        "status": "Review",
                        "summary": "Bounded multi-workspace routing is ready for operator acceptance.",
                    },
                    {
                        "id": "upgrade-voice-lane",
                        "title": "Admit voice lane for short system events",
                        "status": "Review",
                        "summary": "Voice is proposal-bound and remains off for full chat reads.",
                    },
                ],
            }
        )
        return DesktopSnapshot(
            session_id=active_session_id,
            current_project_path=self.current_project_path,
            workspace_surface=workspace_surface,
            config=config_payload,
            status=status_payload,
            health=health_payload,
            sessions=sessions,
            transcript=transcript,
            workspace=workspace,
            mystic=mystic,
            activity=activity,
            discards=discards,
            fame=fame,
            shame=shame,
            features=features,
            packaging_targets=desktop_packaging_targets(
                profile_id=self.profile.id,
                model_router=_model_router_payload(
                    config_payload=config_payload,
                    status_payload=status_payload,
                ),
            ),
        )

    def stream_chat_events(
        self,
        *,
        session_id: str,
        user_message: str,
        mode: str = "chat",
        fast_mode: bool | None = None,
        retrieval_k: int | None = None,
        attachments: list[Attachment] | None = None,
    ) -> tuple[DesktopChatEvent, ...]:
        return tuple(
            self.iter_chat_events(
                session_id=session_id,
                user_message=user_message,
                mode=mode,
                fast_mode=fast_mode,
                retrieval_k=retrieval_k,
                attachments=attachments,
            )
        )

    def iter_chat_events(
        self,
        *,
        session_id: str,
        user_message: str,
        mode: str = "chat",
        fast_mode: bool | None = None,
        retrieval_k: int | None = None,
        attachments: list[Attachment] | None = None,
    ):
        normalized_mode = str(mode or "chat").strip().lower()
        if normalized_mode not in _ALLOWED_CHAT_MODES:
            normalized_mode = "chat"
        normalized_fast_mode = self.config.fast_mode_default if fast_mode is None else bool(fast_mode)
        normalized_retrieval_k = max(1, int(retrieval_k or self.config.retrieval_k))
        normalized_attachments = list(attachments or [])

        stream = self.service.stream_chat(
            session_id=session_id,
            user_message=user_message,
            fast_mode=normalized_fast_mode,
            retrieval_k=normalized_retrieval_k,
            mode=normalized_mode,
            attachments=normalized_attachments,
        )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            while True:
                try:
                    chunk = loop.run_until_complete(stream.__anext__())
                except StopAsyncIteration:
                    break
                for event in parse_sse_events(chunk):
                    yield event
        finally:
            try:
                loop.run_until_complete(stream.aclose())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    def mystic_read(self, *, session_id: str | None, input_text: str) -> dict[str, Any]:
        return self.service.aris_mystic_read(session_id=session_id, input_text=input_text)

    def mystic_tick(self, *, session_id: str | None) -> dict[str, Any]:
        return self.service.aris_mystic_tick(session_id=session_id)

    def mystic_break(self, *, session_id: str | None) -> dict[str, Any]:
        return self.service.aris_mystic_break(session_id=session_id)

    def mystic_acknowledge(self, *, session_id: str | None) -> dict[str, Any]:
        return self.service.aris_mystic_acknowledge(session_id=session_id)

    def mystic_mute(self, *, session_id: str | None, minutes: float) -> dict[str, Any]:
        return self.service.aris_mystic_mute(session_id=session_id, minutes=minutes)

    def activate_soft_kill(self, *, reason: str) -> dict[str, Any]:
        return self.service.aris_kill_soft(reason=reason)

    def activate_hard_kill(self, *, reason: str) -> dict[str, Any]:
        return self.service.aris_kill_hard(reason=reason)

    def reset_kill_switch(self, *, reason: str, reseal_integrity: bool = False) -> dict[str, Any]:
        return self.service.aris_kill_reset(reason=reason, reseal_integrity=reseal_integrity)