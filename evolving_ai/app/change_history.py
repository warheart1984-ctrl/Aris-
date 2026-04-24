from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import difflib
import hashlib
import json
from pathlib import Path
import uuid

from .execution import SandboxPolicy, WorkspaceManager


@dataclass(slots=True)
class AppliedWorkspaceChange:
    id: str
    path: str
    operation: str
    source: str
    created_at: str
    summary: str
    before_exists: bool
    before_content: str
    after_exists: bool
    after_content: str
    diff: str
    verification: dict[str, object] | None = None

    def payload(
        self,
        *,
        current_exists: bool,
        current_content: str,
        max_diff_chars: int | None = None,
        max_verification_chars: int | None = None,
    ) -> dict[str, object]:
        diff = self.diff
        truncated = False
        if max_diff_chars is not None and len(diff) > max_diff_chars:
            diff = f"{diff[:max_diff_chars]}\n...[diff truncated]..."
            truncated = True
        return {
            "id": self.id,
            "path": self.path,
            "operation": self.operation,
            "source": self.source,
            "created_at": self.created_at,
            "summary": self.summary,
            "before_exists": self.before_exists,
            "after_exists": self.after_exists,
            "before_hash": _text_hash(self.before_content) if self.before_exists else "",
            "after_hash": _text_hash(self.after_content) if self.after_exists else "",
            "current_hash": _text_hash(current_content) if current_exists else "",
            "rollback_ready": (
                current_exists == self.after_exists
                and current_content == self.after_content
            ),
            "diff": diff,
            "diff_truncated": truncated,
            "verification": _verification_payload(
                self.verification,
                max_output_chars=max_verification_chars,
            ),
        }


class WorkspaceChangeHistoryManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        policy: SandboxPolicy,
        max_diff_chars: int = 12_000,
        max_verification_chars: int = 4_000,
        max_entries: int = 40,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.policy = policy
        self.max_diff_chars = max_diff_chars
        self.max_verification_chars = max_verification_chars
        self.max_entries = max_entries

    def list_changes(self, session_id: str) -> list[dict[str, object]]:
        changes = self._load(session_id)
        payloads: list[dict[str, object]] = []
        for change in changes:
            current_exists, current_content = self._read_current_text(
                session_id=session_id,
                path=change.path,
            )
            payloads.append(
                change.payload(
                    current_exists=current_exists,
                    current_content=current_content,
                    max_diff_chars=self.max_diff_chars,
                    max_verification_chars=self.max_verification_chars,
                )
            )
        return payloads

    def get_change(self, session_id: str, change_id: str) -> AppliedWorkspaceChange | None:
        return next(
            (item for item in self._load(session_id) if item.id == change_id),
            None,
        )

    def record_change(
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
        if before_exists == after_exists and before_content == after_content:
            return None
        change = AppliedWorkspaceChange(
            id=uuid.uuid4().hex,
            path=path,
            operation=operation,
            source=source,
            created_at=_utc_now(),
            summary=summary or f"{operation.title()} {path}",
            before_exists=before_exists,
            before_content=before_content,
            after_exists=after_exists,
            after_content=after_content,
            diff=_build_unified_diff(path, before_content, after_content),
        )
        self._append(session_id, change)
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            path=path,
        )
        return change.payload(
            current_exists=current_exists,
            current_content=current_content,
            max_diff_chars=self.max_diff_chars,
            max_verification_chars=self.max_verification_chars,
        )

    def record_verification(
        self,
        *,
        session_id: str,
        change_id: str,
        verification: dict[str, object],
    ) -> dict[str, object] | None:
        changes = self._load(session_id)
        change = next((item for item in changes if item.id == change_id), None)
        if change is None:
            return None
        change.verification = verification
        self._save(session_id, changes)
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            path=change.path,
        )
        return change.payload(
            current_exists=current_exists,
            current_content=current_content,
            max_diff_chars=self.max_diff_chars,
            max_verification_chars=self.max_verification_chars,
        )

    def rollback_change(
        self,
        *,
        session_id: str,
        change_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        changes = self._load(session_id)
        change = next((item for item in changes if item.id == change_id), None)
        if change is None:
            return {
                "ok": False,
                "session_id": session_id,
                "change_id": change_id,
                "error": f"Applied change `{change_id}` was not found.",
                "applied_changes": self.list_changes(session_id),
            }

        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            path=change.path,
        )
        if current_exists != change.after_exists or current_content != change.after_content:
            return {
                "ok": False,
                "session_id": session_id,
                "change_id": change_id,
                "error": (
                    f"`{change.path}` changed again after `{change.summary}`. "
                    "Review the latest diff before rolling back."
                ),
                "change": change.payload(
                    current_exists=current_exists,
                    current_content=current_content,
                    max_diff_chars=self.max_diff_chars,
                    max_verification_chars=self.max_verification_chars,
                ),
                "applied_changes": self.list_changes(session_id),
            }

        workspace, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id,
            change.path,
        )
        if change.before_exists:
            self.workspace_manager.write_text_file(
                session_id,
                relative,
                change.before_content,
                max_file_bytes=self.policy.max_file_bytes,
                max_files=self.policy.max_files,
            )
        elif target.exists():
            if not target.is_file():
                return {
                    "ok": False,
                    "session_id": session_id,
                    "change_id": change_id,
                    "error": f"Workspace path `{relative}` is not a file.",
                    "applied_changes": self.list_changes(session_id),
                }
            target.unlink()

        rollback_payload = self.record_change(
            session_id=session_id,
            path=relative,
            operation="rollback",
            source=source,
            before_exists=change.after_exists,
            before_content=change.after_content,
            after_exists=change.before_exists,
            after_content=change.before_content,
            summary=f"Rollback {change.operation} on {relative}",
        )
        return {
            "ok": True,
            "session_id": session_id,
            "change_id": change_id,
            "rolled_back": True,
            "path": relative,
            "files": self.workspace_manager.list_files(session_id),
            "change": rollback_payload,
            "applied_changes": self.list_changes(session_id),
        }

    def _append(self, session_id: str, change: AppliedWorkspaceChange) -> None:
        changes = self._load(session_id)
        changes.insert(0, change)
        if self.max_entries > 0:
            changes = changes[: self.max_entries]
        self._save(session_id, changes)

    def _load(self, session_id: str) -> list[AppliedWorkspaceChange]:
        store_path = self._store_path(session_id)
        if not store_path.exists():
            return []
        try:
            payload = json.loads(store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        changes: list[AppliedWorkspaceChange] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                changes.append(AppliedWorkspaceChange(**item))
            except TypeError:
                continue
        return changes

    def _save(self, session_id: str, changes: list[AppliedWorkspaceChange]) -> None:
        store_path = self._store_path(session_id)
        if not changes:
            if store_path.exists():
                store_path.unlink()
            return
        payload = [asdict(item) for item in changes]
        store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _store_path(self, session_id: str) -> Path:
        workspace = self.workspace_manager.workspace_for(session_id)
        return workspace / ".forge_exec_applied_changes.json"

    def _read_current_text(self, *, session_id: str, path: str) -> tuple[bool, str]:
        workspace, target, _ = self.workspace_manager.resolve_workspace_path(
            session_id,
            path,
        )
        del workspace
        if not target.exists():
            return False, ""
        if not target.is_file():
            raise IsADirectoryError(f"Workspace path `{path}` is not a file.")
        return True, target.read_text(encoding="utf-8")


def _build_unified_diff(path: str, before: str, after: str) -> str:
    diff_lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff_lines) or f"No textual diff for `{path}`."


def _verification_payload(
    verification: dict[str, object] | None,
    *,
    max_output_chars: int | None = None,
) -> dict[str, object] | None:
    if not isinstance(verification, dict):
        return None
    results_payload: list[dict[str, object]] = []
    raw_results = verification.get("results", [])
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            stdout, stdout_truncated = _truncate_text(
                str(item.get("stdout", "")),
                max_chars=max_output_chars,
            )
            stderr, stderr_truncated = _truncate_text(
                str(item.get("stderr", "")),
                max_chars=max_output_chars,
            )
            results_payload.append(
                {
                    "command": str(item.get("command", "")).strip(),
                    "cwd": str(item.get("cwd", ".")).strip() or ".",
                    "returncode": int(item.get("returncode", 0)),
                    "timed_out": bool(item.get("timed_out", False)),
                    "ok": bool(item.get("ok", False)),
                    "backend": str(item.get("backend", "")).strip(),
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                }
            )
    passed_count = sum(1 for item in results_payload if item.get("ok"))
    status = str(verification.get("status", "")).strip().lower()
    if not status:
        status = "passed" if bool(verification.get("ok", False)) else "failed"
    return {
        "created_at": str(verification.get("created_at", "")).strip(),
        "preset_id": str(verification.get("preset_id", "")).strip(),
        "label": str(verification.get("label", "")).strip(),
        "summary": str(verification.get("summary", "")).strip(),
        "status": status,
        "ok": bool(verification.get("ok", False)),
        "command_count": len(results_payload),
        "passed_count": passed_count,
        "failed_count": max(0, len(results_payload) - passed_count),
        "results": results_payload,
    }


def _text_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _truncate_text(value: str, *, max_chars: int | None) -> tuple[str, bool]:
    if max_chars is None or len(value) <= max_chars:
        return value, False
    if max_chars <= 0:
        return "", bool(value)
    return f"{value[:max_chars]}\n...[output truncated]...", True


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
