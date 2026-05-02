from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_ALLOWED_ACTIONS = (
    "open",
    "copy_path",
    "send_to_aris",
    "inspect",
    "use_in_task",
)
_ALLOWED_ACTION_SET = frozenset(DEFAULT_ALLOWED_ACTIONS)
_IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".runtime",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
_TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_PREVIEW_BYTES = 64 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed or "workspace"


def _workspace_status(root_path: Path) -> str:
    return "active" if root_path.exists() and root_path.is_dir() else "error"


def _normalize_actions(actions: list[str] | tuple[str, ...] | None) -> list[str]:
    if not actions:
        return list(DEFAULT_ALLOWED_ACTIONS)
    normalized = []
    for item in actions:
        action = str(item or "").strip().lower()
        if action in _ALLOWED_ACTION_SET and action not in normalized:
            normalized.append(action)
    return normalized or list(DEFAULT_ALLOWED_ACTIONS)


def _relative_label(root_path: Path, target_path: Path) -> str:
    if target_path == root_path:
        return "."
    return target_path.relative_to(root_path).as_posix()


def _path_belongs_to_root(target_path: Path, root_path: Path) -> bool:
    try:
        target_path.relative_to(root_path)
        return True
    except ValueError:
        return False


def _entry_from_payload(payload: dict[str, Any], *, fallback_name: str) -> dict[str, Any]:
    root_path = Path(str(payload.get("root_path", "")).strip() or ".").expanduser().resolve()
    name = str(payload.get("name", "")).strip() or fallback_name
    entry_id = str(payload.get("id", "")).strip() or f"workspace-{_slug(name)}"
    return {
        "id": entry_id,
        "name": name,
        "root_path": str(root_path),
        "type": str(payload.get("type", "project")).strip() or "project",
        "allowed_actions": _normalize_actions(list(payload.get("allowed_actions", []))),
        "active": bool(payload.get("active", False)),
        "status": str(payload.get("status", "")).strip() or _workspace_status(root_path),
        "created_at": str(payload.get("created_at", "")).strip() or _utc_now(),
        "updated_at": str(payload.get("updated_at", "")).strip() or _utc_now(),
    }


@dataclass(slots=True)
class WorkspaceActionResult:
    workspace: dict[str, Any]
    action: str
    path: str
    relative_path: str
    summary: str
    payload: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "workspace": dict(self.workspace),
            "action": self.action,
            "path": self.path,
            "relative_path": self.relative_path,
            "summary": self.summary,
            "payload": dict(self.payload),
        }


class WorkspaceRegistry:
    def __init__(self, registry_path: Path, *, seed_root: Path) -> None:
        self.registry_path = registry_path.resolve()
        self.seed_root = seed_root.resolve()
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = self._load_entries()

    def _seed_entry(self) -> dict[str, Any]:
        return {
            "id": "workspace-project-infi-code",
            "name": "Project Infi Code",
            "root_path": str(self.seed_root),
            "type": "repo",
            "allowed_actions": list(DEFAULT_ALLOWED_ACTIONS),
            "active": True,
            "status": _workspace_status(self.seed_root),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }

    def _load_entries(self) -> list[dict[str, Any]]:
        if self.registry_path.exists():
            try:
                payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
        else:
            payload = {}

        raw_entries = payload.get("workspaces", []) if isinstance(payload, dict) else []
        entries = [
            _entry_from_payload(item, fallback_name="Workspace")
            for item in raw_entries
            if isinstance(item, dict)
        ]
        if not entries:
            entries = [self._seed_entry()]
        self._normalize_active(entries)
        self._save_entries(entries)
        return entries

    def _normalize_active(self, entries: list[dict[str, Any]]) -> None:
        active_index = next((index for index, item in enumerate(entries) if item.get("active")), 0)
        for index, item in enumerate(entries):
            root_path = Path(str(item.get("root_path", ""))).expanduser().resolve()
            item["root_path"] = str(root_path)
            item["status"] = _workspace_status(root_path)
            item["active"] = index == active_index
            item["allowed_actions"] = _normalize_actions(list(item.get("allowed_actions", [])))
            item["updated_at"] = str(item.get("updated_at", "")).strip() or _utc_now()
            item["created_at"] = str(item.get("created_at", "")).strip() or item["updated_at"]

    def _save_entries(self, entries: list[dict[str, Any]] | None = None) -> None:
        payload = {
            "workspaces": entries if entries is not None else self._entries,
            "updated_at": _utc_now(),
        }
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def entries(self) -> list[dict[str, Any]]:
        refreshed = [dict(item) for item in self._entries]
        self._normalize_active(refreshed)
        self._entries = refreshed
        self._save_entries()
        return [dict(item) for item in self._entries]

    def active(self) -> dict[str, Any]:
        entries = self.entries()
        for item in entries:
            if item.get("active"):
                return dict(item)
        return dict(entries[0])

    def by_id(self, workspace_id: str | None) -> dict[str, Any]:
        entries = self.entries()
        if workspace_id:
            for item in entries:
                if str(item.get("id", "")).strip() == str(workspace_id).strip():
                    return dict(item)
        return dict(self.active())

    def add_workspace(
        self,
        root_path: str | Path,
        *,
        name: str | None = None,
        workspace_type: str = "project",
        allowed_actions: list[str] | tuple[str, ...] | None = None,
        activate: bool = True,
    ) -> dict[str, Any]:
        resolved_root = Path(str(root_path)).expanduser().resolve()
        if not resolved_root.exists() or not resolved_root.is_dir():
            raise ValueError(f"Workspace root is missing or not a directory: {resolved_root}")

        entries = self.entries()
        existing = next(
            (
                item
                for item in entries
                if Path(str(item.get("root_path", ""))).expanduser().resolve() == resolved_root
            ),
            None,
        )
        if existing is not None:
            existing["name"] = str(name or existing.get("name") or resolved_root.name).strip() or resolved_root.name
            existing["type"] = str(workspace_type or existing.get("type") or "project").strip() or "project"
            existing["allowed_actions"] = _normalize_actions(list(allowed_actions or existing.get("allowed_actions", [])))
            existing["updated_at"] = _utc_now()
            if activate:
                for item in entries:
                    item["active"] = item["id"] == existing["id"]
            self._entries = entries
            self._save_entries()
            return dict(existing)

        entry_name = str(name or resolved_root.name or "Workspace").strip() or "Workspace"
        entry = {
            "id": f"workspace-{_slug(entry_name)}",
            "name": entry_name,
            "root_path": str(resolved_root),
            "type": str(workspace_type or "project").strip() or "project",
            "allowed_actions": _normalize_actions(list(allowed_actions or DEFAULT_ALLOWED_ACTIONS)),
            "active": bool(activate),
            "status": _workspace_status(resolved_root),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        if activate:
            for item in entries:
                item["active"] = False
        entries.append(entry)
        self._entries = entries
        self._normalize_active(self._entries)
        self._save_entries()
        return dict(entry)

    def set_active(self, workspace_id: str) -> dict[str, Any]:
        entries = self.entries()
        matched = None
        for item in entries:
            is_match = str(item.get("id", "")).strip() == str(workspace_id).strip()
            item["active"] = is_match
            if is_match:
                matched = item
        if matched is None:
            raise ValueError(f"Unknown workspace id: {workspace_id}")
        self._entries = entries
        self._save_entries()
        return dict(matched)

    def validate_target(
        self,
        target_path: str | Path,
        *,
        workspace_id: str | None = None,
    ) -> tuple[dict[str, Any], Path]:
        workspace = self.by_id(workspace_id)
        root_path = Path(str(workspace.get("root_path", ""))).expanduser().resolve()
        candidate = Path(str(target_path))
        resolved = (root_path / candidate).resolve() if not candidate.is_absolute() else candidate.expanduser().resolve()
        if not _path_belongs_to_root(resolved, root_path):
            raise ValueError("Target path falls outside the registered workspace root.")
        return workspace, resolved

    def _walk_entries(self, root_path: Path):
        for current_root, dir_names, file_names in os.walk(root_path):
            dir_names[:] = sorted(
                [name for name in dir_names if name not in _IGNORED_DIRECTORIES],
                key=str.lower,
            )
            file_names[:] = sorted(file_names, key=str.lower)
            yield Path(current_root), dir_names, file_names

    def tree_payload(
        self,
        *,
        workspace_id: str | None = None,
        max_depth: int = 4,
        max_children: int = 60,
    ) -> dict[str, Any]:
        workspace = self.by_id(workspace_id)
        root_path = Path(str(workspace.get("root_path", ""))).expanduser().resolve()

        def build_node(target_path: Path, depth: int) -> dict[str, Any]:
            relative_path = _relative_label(root_path, target_path)
            if not target_path.is_dir():
                return {
                    "name": target_path.name,
                    "relative_path": relative_path,
                    "path": str(target_path),
                    "type": "file",
                    "children": [],
                    "truncated": False,
                }

            children: list[dict[str, Any]] = []
            truncated = False
            if depth < max_depth:
                try:
                    entries = sorted(
                        [
                            item
                            for item in target_path.iterdir()
                            if item.name not in _IGNORED_DIRECTORIES
                        ],
                        key=lambda item: (item.is_file(), item.name.lower()),
                    )
                except OSError:
                    entries = []
                if len(entries) > max_children:
                    entries = entries[:max_children]
                    truncated = True
                for child in entries:
                    children.append(build_node(child, depth + 1))

            return {
                "name": target_path.name or workspace.get("name", "Workspace"),
                "relative_path": relative_path,
                "path": str(target_path),
                "type": "directory",
                "children": children,
                "truncated": truncated,
            }

        return {
            "workspace": workspace,
            "tree": build_node(root_path, 0),
        }

    def preview_file(
        self,
        target_path: str | Path,
        *,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        workspace, resolved = self.validate_target(target_path, workspace_id=workspace_id)
        root_path = Path(str(workspace.get("root_path", ""))).expanduser().resolve()
        relative_path = _relative_label(root_path, resolved)
        if resolved.is_dir():
            try:
                children = sorted(
                    [item.name for item in resolved.iterdir() if item.name not in _IGNORED_DIRECTORIES],
                    key=str.lower,
                )[:80]
            except OSError:
                children = []
            return {
                "workspace": workspace,
                "path": str(resolved),
                "relative_path": relative_path,
                "type": "directory",
                "content": "\n".join(children) if children else "Directory is empty or unreadable.",
                "truncated": False,
                "binary": False,
            }

        raw_bytes = resolved.read_bytes()
        truncated = len(raw_bytes) > _PREVIEW_BYTES
        preview_bytes = raw_bytes[:_PREVIEW_BYTES]
        suffix = resolved.suffix.lower()
        is_binary = (b"\x00" in preview_bytes) or (suffix and suffix not in _TEXT_EXTENSIONS and suffix not in {".log", ".cfg"})
        if is_binary:
            content = f"Binary preview withheld for {resolved.name} ({len(raw_bytes)} bytes)."
        else:
            content = preview_bytes.decode("utf-8", errors="replace")

        return {
            "workspace": workspace,
            "path": str(resolved),
            "relative_path": relative_path,
            "type": "file",
            "content": content,
            "truncated": truncated,
            "binary": is_binary,
            "size_bytes": len(raw_bytes),
        }

    def search_files(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        search_text = str(query or "").strip().lower()
        if not search_text:
            return []
        workspace = self.by_id(workspace_id)
        root_path = Path(str(workspace.get("root_path", ""))).expanduser().resolve()
        matches: list[dict[str, Any]] = []

        for current_root, _dir_names, file_names in self._walk_entries(root_path):
            if len(matches) >= limit:
                break
            for file_name in file_names:
                candidate = current_root / file_name
                relative_path = _relative_label(root_path, candidate)
                lowered_path = relative_path.lower()
                snippet = ""
                matched = search_text in lowered_path
                if not matched and candidate.suffix.lower() in _TEXT_EXTENSIONS:
                    try:
                        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                            for line_number, line in enumerate(handle, start=1):
                                lowered_line = line.lower()
                                if search_text in lowered_line:
                                    snippet = f"L{line_number}: {line.strip()[:180]}"
                                    matched = True
                                    break
                    except OSError:
                        matched = False
                if not matched:
                    continue
                matches.append(
                    {
                        "workspace_id": workspace.get("id"),
                        "path": str(candidate),
                        "relative_path": relative_path,
                        "name": candidate.name,
                        "snippet": snippet,
                    }
                )
                if len(matches) >= limit:
                    break
        return matches

    def action(
        self,
        action_name: str,
        target_path: str | Path,
        *,
        workspace_id: str | None = None,
    ) -> WorkspaceActionResult:
        action = str(action_name or "").strip().lower()
        workspace, resolved = self.validate_target(target_path, workspace_id=workspace_id)
        allowed_actions = set(workspace.get("allowed_actions", []))
        if action not in allowed_actions:
            raise PermissionError(f"Action '{action}' is not allowed in workspace {workspace.get('name')}.")
        root_path = Path(str(workspace.get("root_path", ""))).expanduser().resolve()
        relative_path = _relative_label(root_path, resolved)

        if action == "open":
            payload = self.preview_file(resolved, workspace_id=str(workspace.get("id", "")))
            summary = f"Opened {relative_path} inside {workspace.get('name')}."
        elif action == "copy_path":
            payload = {
                "path": str(resolved),
                "relative_path": relative_path,
            }
            summary = f"Copied path for {relative_path}."
        elif action == "send_to_aris":
            payload = {
                "prompt": f"Use {relative_path} from {workspace.get('name')} as active workspace context.",
                "path": str(resolved),
                "relative_path": relative_path,
            }
            summary = f"Prepared {relative_path} for ARIS context."
        elif action == "inspect":
            payload = {
                "path": str(resolved),
                "relative_path": relative_path,
                "exists": resolved.exists(),
                "is_dir": resolved.is_dir(),
                "size_bytes": resolved.stat().st_size if resolved.exists() and resolved.is_file() else 0,
            }
            summary = f"Inspected {relative_path}."
        else:
            payload = {
                "task_note": f"Use {relative_path} from {workspace.get('name')} in the selected task.",
                "path": str(resolved),
                "relative_path": relative_path,
            }
            summary = f"Linked {relative_path} to the selected task."

        return WorkspaceActionResult(
            workspace=workspace,
            action=action,
            path=str(resolved),
            relative_path=relative_path,
            summary=summary,
            payload=payload,
        )