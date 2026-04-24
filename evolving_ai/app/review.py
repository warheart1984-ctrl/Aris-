from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import difflib
import json
from pathlib import Path
import uuid

from .execution import SandboxPolicy, WorkspaceManager


Opcode = tuple[str, int, int, int, int]


@dataclass(slots=True)
class WorkspacePatchLineAction:
    index: int
    kind: str
    before_line_number: int | None
    after_line_number: int | None
    before_text: str | None
    after_text: str | None
    diff: str
    opcode: Opcode
    opcode_unit_index: int

    def payload(self) -> dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind,
            "before_line_number": self.before_line_number,
            "after_line_number": self.after_line_number,
            "before_text": self.before_text,
            "after_text": self.after_text,
            "diff": self.diff,
        }


@dataclass(slots=True)
class WorkspacePatchHunk:
    index: int
    header: str
    diff: str
    additions: int
    deletions: int
    before_start: int
    before_count: int
    after_start: int
    after_count: int
    opcodes: tuple[Opcode, ...]
    lines: tuple[WorkspacePatchLineAction, ...]

    def payload(self) -> dict[str, object]:
        return {
            "index": self.index,
            "header": self.header,
            "diff": self.diff,
            "additions": self.additions,
            "deletions": self.deletions,
            "before_start": self.before_start,
            "before_count": self.before_count,
            "after_start": self.after_start,
            "after_count": self.after_count,
            "lines": [line.payload() for line in self.lines],
            "line_count": len(self.lines),
        }


@dataclass(slots=True)
class PendingWorkspacePatch:
    id: str
    path: str
    operation: str
    source: str
    created_at: str
    summary: str
    base_exists: bool
    base_content: str
    target_content: str
    diff: str

    def payload(self, *, max_diff_chars: int | None = None) -> dict[str, object]:
        hunks = _build_patch_hunks(self.path, self.base_content, self.target_content)
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
            "created": not self.base_exists,
            "diff": diff,
            "diff_truncated": truncated,
            "hunks": [hunk.payload() for hunk in hunks],
            "hunk_count": len(hunks),
            "review_complete": not hunks,
        }


class WorkspacePatchManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        policy: SandboxPolicy,
        max_diff_chars: int = 12_000,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.policy = policy
        self.max_diff_chars = max_diff_chars

    def list_pending(self, session_id: str) -> list[dict[str, object]]:
        patches = self._load(session_id)
        return [
            patch.payload(max_diff_chars=self.max_diff_chars)
            for patch in patches
        ]

    def propose_write(
        self,
        *,
        session_id: str,
        path: str,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, path
        )
        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")

        base_exists, base_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
        )
        self._validate_target(
            session_id=session_id,
            relative=relative,
            target_content=content,
            base_exists=base_exists,
        )
        if content == base_content:
            raise ValueError(f"No file changes were proposed for `{relative}`.")

        summary = "Create file" if not base_exists else "Replace full file contents"
        patch = PendingWorkspacePatch(
            id=uuid.uuid4().hex,
            path=relative,
            operation="write",
            source=source,
            created_at=_utc_now(),
            summary=f"{summary}: {relative}",
            base_exists=base_exists,
            base_content=base_content,
            target_content=content,
            diff=_build_unified_diff(relative, base_content, content),
        )
        return self._store_patch(session_id=session_id, patch=patch)

    def propose_replace(
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
        if not old_text:
            raise ValueError("`old_text` cannot be empty.")
        if expected_occurrences is not None and expected_occurrences < 1:
            raise ValueError("`expected_occurrences` must be at least 1.")
        if expected_occurrences not in {None, 1} and not replace_all:
            raise ValueError(
                "Set `replace_all` when `expected_occurrences` is greater than 1."
            )

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, path
        )
        if not target.exists():
            raise FileNotFoundError(f"Workspace file `{relative}` does not exist.")
        if not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")

        _, base_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
        )
        occurrences = base_content.count(old_text)
        if occurrences == 0:
            raise ValueError(f"`old_text` was not found in `{relative}`.")
        if expected_occurrences is not None and occurrences != expected_occurrences:
            raise ValueError(
                f"Expected {expected_occurrences} occurrence(s) in `{relative}`, found {occurrences}."
            )
        if occurrences > 1 and not replace_all and expected_occurrences is None:
            raise ValueError(
                f"`old_text` matched {occurrences} times in `{relative}`. Narrow the match or set `replace_all`."
            )

        replacements = occurrences if replace_all else 1
        target_content = base_content.replace(old_text, new_text, replacements)
        if target_content == base_content:
            raise ValueError(f"No file changes were proposed for `{relative}`.")

        self._validate_target(
            session_id=session_id,
            relative=relative,
            target_content=target_content,
            base_exists=True,
        )
        patch = PendingWorkspacePatch(
            id=uuid.uuid4().hex,
            path=relative,
            operation="replace",
            source=source,
            created_at=_utc_now(),
            summary=f"Replace {replacements} occurrence(s) in {relative}",
            base_exists=True,
            base_content=base_content,
            target_content=target_content,
            diff=_build_unified_diff(relative, base_content, target_content),
        )
        return self._store_patch(session_id=session_id, patch=patch)

    def apply_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        if current_exists == patch.base_exists and patch.base_content == patch.target_content:
            remaining = [item for item in patches if item.id != patch_id]
            self._save(session_id, remaining)
            return {
                "ok": True,
                "session_id": session_id,
                "patch_id": patch_id,
                "path": patch.path,
                "operation": patch.operation,
                "applied": False,
                "noop": True,
                "summary": patch.summary,
                "files": self.workspace_manager.list_files(session_id),
                "pending_patches": self.list_pending(session_id),
            }

        write_result = self.workspace_manager.write_text_file(
            session_id,
            patch.path,
            patch.target_content,
            max_file_bytes=self.policy.max_file_bytes,
            max_files=self.policy.max_files,
        )
        remaining = [item for item in patches if item.id != patch_id]
        self._save(session_id, remaining)
        return {
            "ok": True,
            "session_id": session_id,
            "patch_id": patch_id,
            "path": patch.path,
            "operation": patch.operation,
            "applied": True,
            "summary": patch.summary,
            "write_result": {
                "path": write_result.path,
                "created": write_result.created,
                "size_bytes": write_result.size_bytes,
            },
            "files": self.workspace_manager.list_files(session_id),
            "pending_patches": self.list_pending(session_id),
        }

    def accept_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        keep_when_empty: bool = False,
    ) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        hunks = _build_patch_hunks(patch.path, patch.base_content, patch.target_content)
        if not hunks:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": f"Pending patch `{patch.path}` has no hunks left to accept.",
                "pending_patches": self.list_pending(session_id),
            }
        if hunk_index < 0 or hunk_index >= len(hunks):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": (
                    f"Hunk `{hunk_index}` is out of range for `{patch.path}`. "
                    f"Expected 0 through {len(hunks) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        selected_hunk = hunks[hunk_index]
        next_base_content = _resolve_hunk_content(
            patch.base_content,
            patch.target_content,
            selected_hunk,
            accept_selected=True,
        )
        write_result = self.workspace_manager.write_text_file(
            session_id,
            patch.path,
            next_base_content,
            max_file_bytes=self.policy.max_file_bytes,
            max_files=self.policy.max_files,
        )
        return self._finalize_hunk_resolution(
            session_id=session_id,
            patches=patches,
            patch=patch,
            next_base_exists=True,
            next_base_content=next_base_content,
            next_target_content=patch.target_content,
            keep_when_empty=keep_when_empty,
            hunk_index=hunk_index,
            hunk_total=len(hunks),
            resolution="accepted",
            write_result={
                "path": write_result.path,
                "created": write_result.created,
                "size_bytes": write_result.size_bytes,
            },
        )

    def reject_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        keep_when_empty: bool = False,
    ) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        hunks = _build_patch_hunks(patch.path, patch.base_content, patch.target_content)
        if not hunks:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": f"Pending patch `{patch.path}` has no hunks left to reject.",
                "pending_patches": self.list_pending(session_id),
            }
        if hunk_index < 0 or hunk_index >= len(hunks):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "path": patch.path,
                "error": (
                    f"Hunk `{hunk_index}` is out of range for `{patch.path}`. "
                    f"Expected 0 through {len(hunks) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        selected_hunk = hunks[hunk_index]
        next_target_content = _resolve_hunk_content(
            patch.base_content,
            patch.target_content,
            selected_hunk,
            accept_selected=False,
        )
        return self._finalize_hunk_resolution(
            session_id=session_id,
            patches=patches,
            patch=patch,
            next_base_exists=patch.base_exists,
            next_base_content=patch.base_content,
            next_target_content=next_target_content,
            keep_when_empty=keep_when_empty,
            hunk_index=hunk_index,
            hunk_total=len(hunks),
            resolution="rejected",
        )

    def accept_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        keep_when_empty: bool = False,
    ) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        hunks = _build_patch_hunks(patch.path, patch.base_content, patch.target_content)
        if not hunks:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": f"Pending patch `{patch.path}` has no line edits left to accept.",
                "pending_patches": self.list_pending(session_id),
            }
        if hunk_index < 0 or hunk_index >= len(hunks):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Hunk `{hunk_index}` is out of range for `{patch.path}`. "
                    f"Expected 0 through {len(hunks) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }
        selected_hunk = hunks[hunk_index]
        if line_index < 0 or line_index >= len(selected_hunk.lines):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Line `{line_index}` is out of range for hunk `{hunk_index}` in `{patch.path}`. "
                    f"Expected 0 through {len(selected_hunk.lines) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        selected_line = selected_hunk.lines[line_index]
        next_base_content = _resolve_line_content(
            patch.base_content,
            patch.target_content,
            selected_line,
            accept_selected=True,
        )
        write_result = self.workspace_manager.write_text_file(
            session_id,
            patch.path,
            next_base_content,
            max_file_bytes=self.policy.max_file_bytes,
            max_files=self.policy.max_files,
        )
        return self._finalize_line_resolution(
            session_id=session_id,
            patches=patches,
            patch=patch,
            next_base_exists=True,
            next_base_content=next_base_content,
            next_target_content=patch.target_content,
            keep_when_empty=keep_when_empty,
            hunk_index=hunk_index,
            hunk_total=len(hunks),
            line_index=line_index,
            line_total=len(selected_hunk.lines),
            resolution="accepted",
            write_result={
                "path": write_result.path,
                "created": write_result.created,
                "size_bytes": write_result.size_bytes,
            },
        )

    def reject_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        keep_when_empty: bool = False,
    ) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        hunks = _build_patch_hunks(patch.path, patch.base_content, patch.target_content)
        if not hunks:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": f"Pending patch `{patch.path}` has no line edits left to reject.",
                "pending_patches": self.list_pending(session_id),
            }
        if hunk_index < 0 or hunk_index >= len(hunks):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Hunk `{hunk_index}` is out of range for `{patch.path}`. "
                    f"Expected 0 through {len(hunks) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }
        selected_hunk = hunks[hunk_index]
        if line_index < 0 or line_index >= len(selected_hunk.lines):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Line `{line_index}` is out of range for hunk `{hunk_index}` in `{patch.path}`. "
                    f"Expected 0 through {len(selected_hunk.lines) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        selected_line = selected_hunk.lines[line_index]
        next_target_content = _resolve_line_content(
            patch.base_content,
            patch.target_content,
            selected_line,
            accept_selected=False,
        )
        return self._finalize_line_resolution(
            session_id=session_id,
            patches=patches,
            patch=patch,
            next_base_exists=patch.base_exists,
            next_base_content=patch.base_content,
            next_target_content=next_target_content,
            keep_when_empty=keep_when_empty,
            hunk_index=hunk_index,
            hunk_total=len(hunks),
            line_index=line_index,
            line_total=len(selected_hunk.lines),
            resolution="rejected",
        )

    def edit_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        after_text: str,
        keep_when_empty: bool = False,
    ) -> dict[str, object]:
        if "\n" in after_text or "\r" in after_text:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "error": "Line edits must stay on a single line.",
                "pending_patches": self.list_pending(session_id),
            }

        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }

        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id, patch.path
        )
        current_exists, current_content = self._read_current_text(
            session_id=session_id,
            target=target,
            relative=relative,
            allow_missing=True,
        )
        if current_exists != patch.base_exists or current_content != patch.base_content:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Workspace file `{patch.path}` changed after the patch was proposed. "
                    "Re-read the file and create a fresh patch."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        hunks = _build_patch_hunks(patch.path, patch.base_content, patch.target_content)
        if not hunks:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": f"Pending patch `{patch.path}` has no editable lines left.",
                "pending_patches": self.list_pending(session_id),
            }
        if hunk_index < 0 or hunk_index >= len(hunks):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Hunk `{hunk_index}` is out of range for `{patch.path}`. "
                    f"Expected 0 through {len(hunks) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }
        selected_hunk = hunks[hunk_index]
        if line_index < 0 or line_index >= len(selected_hunk.lines):
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "hunk_index": hunk_index,
                "line_index": line_index,
                "path": patch.path,
                "error": (
                    f"Line `{line_index}` is out of range for hunk `{hunk_index}` in `{patch.path}`. "
                    f"Expected 0 through {len(selected_hunk.lines) - 1}."
                ),
                "pending_patches": self.list_pending(session_id),
            }

        selected_line = selected_hunk.lines[line_index]
        next_target_content = _edit_line_target_content(
            patch.base_content,
            patch.target_content,
            selected_line,
            after_text,
        )
        self._validate_target(
            session_id=session_id,
            relative=patch.path,
            target_content=next_target_content,
            base_exists=patch.base_exists,
        )

        updated_patch = PendingWorkspacePatch(
            id=patch.id,
            path=patch.path,
            operation=patch.operation,
            source=patch.source,
            created_at=patch.created_at,
            summary=patch.summary,
            base_exists=patch.base_exists,
            base_content=patch.base_content,
            target_content=next_target_content,
            diff=_build_unified_diff(patch.path, patch.base_content, next_target_content),
        )
        remaining_hunks = _build_patch_hunks(
            patch.path,
            updated_patch.base_content,
            updated_patch.target_content,
        )
        completed = not remaining_hunks
        if completed and not keep_when_empty:
            next_patches = [item for item in patches if item.id != patch.id]
            stored_patch = None
        else:
            next_patches = [
                updated_patch if item.id == patch.id else item for item in patches
            ]
            stored_patch = updated_patch

        self._save(session_id, next_patches)
        result = {
            "ok": True,
            "session_id": session_id,
            "patch_id": patch.id,
            "path": patch.path,
            "operation": "patch_line_edit",
            "hunk_index": hunk_index,
            "line_index": line_index,
            "edited": True,
            "completed": completed,
            "review_complete": completed,
            "summary": (
                f"Updated line {line_index + 1} in hunk {hunk_index + 1} of {patch.path}"
            ),
            "pending_patches": self.list_pending(session_id),
        }
        if stored_patch is not None:
            result["patch"] = stored_patch.payload(max_diff_chars=self.max_diff_chars)
        return result

    def reject_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        patches = self._load(session_id)
        patch = next((item for item in patches if item.id == patch_id), None)
        if patch is None:
            return {
                "ok": False,
                "session_id": session_id,
                "patch_id": patch_id,
                "error": f"Pending patch `{patch_id}` was not found.",
                "pending_patches": self.list_pending(session_id),
            }
        remaining = [item for item in patches if item.id != patch_id]
        self._save(session_id, remaining)
        return {
            "ok": True,
            "session_id": session_id,
            "patch_id": patch_id,
            "rejected": True,
            "summary": patch.summary,
            "pending_patches": self.list_pending(session_id),
        }

    def _store_patch(
        self, *, session_id: str, patch: PendingWorkspacePatch
    ) -> dict[str, object]:
        patches = self._load(session_id)
        patches.append(patch)
        self._save(session_id, patches)
        return {
            "ok": True,
            "session_id": session_id,
            "patch": patch.payload(max_diff_chars=self.max_diff_chars),
            "pending_patches": self.list_pending(session_id),
        }

    def _validate_target(
        self,
        *,
        session_id: str,
        relative: str,
        target_content: str,
        base_exists: bool,
    ) -> None:
        size_bytes = len(target_content.encode("utf-8"))
        if size_bytes > self.policy.max_file_bytes:
            raise ValueError(
                f"Workspace file `{relative}` would exceed the {self.policy.max_file_bytes} byte limit."
            )
        if not base_exists:
            files = self.workspace_manager.list_files(session_id)
            if relative not in files and len(files) + 1 > self.policy.max_files:
                raise ValueError(
                    f"Workspace would exceed the {self.policy.max_files} file limit."
                )

    def _read_current_text(
        self,
        *,
        session_id: str,
        target: Path,
        relative: str,
        allow_missing: bool = False,
    ) -> tuple[bool, str]:
        if not target.exists():
            if allow_missing:
                return False, ""
            return False, ""
        try:
            return True, target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Workspace file `{relative}` is not a UTF-8 text file."
            ) from exc

    def _load(self, session_id: str) -> list[PendingWorkspacePatch]:
        store_path = self._store_path(session_id)
        if not store_path.exists():
            return []
        try:
            payload = json.loads(store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        patches: list[PendingWorkspacePatch] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                patches.append(PendingWorkspacePatch(**item))
            except TypeError:
                continue
        return patches

    def _save(self, session_id: str, patches: list[PendingWorkspacePatch]) -> None:
        store_path = self._store_path(session_id)
        if not patches:
            if store_path.exists():
                store_path.unlink()
            return
        payload = [asdict(item) for item in patches]
        store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _store_path(self, session_id: str) -> Path:
        workspace = self.workspace_manager.workspace_for(session_id)
        return workspace / ".forge_pending_patches.json"

    def _finalize_hunk_resolution(
        self,
        *,
        session_id: str,
        patches: list[PendingWorkspacePatch],
        patch: PendingWorkspacePatch,
        next_base_exists: bool,
        next_base_content: str,
        next_target_content: str,
        keep_when_empty: bool,
        hunk_index: int,
        hunk_total: int,
        resolution: str,
        write_result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        updated_patch = PendingWorkspacePatch(
            id=patch.id,
            path=patch.path,
            operation=patch.operation,
            source=patch.source,
            created_at=patch.created_at,
            summary=patch.summary,
            base_exists=next_base_exists,
            base_content=next_base_content,
            target_content=next_target_content,
            diff=_build_unified_diff(patch.path, next_base_content, next_target_content),
        )
        remaining_hunks = _build_patch_hunks(
            patch.path,
            updated_patch.base_content,
            updated_patch.target_content,
        )
        completed = not remaining_hunks

        if completed and not keep_when_empty:
            next_patches = [item for item in patches if item.id != patch.id]
            stored_patch = None
        else:
            next_patches = [
                updated_patch if item.id == patch.id else item for item in patches
            ]
            stored_patch = updated_patch

        self._save(session_id, next_patches)
        summary = (
            f"{resolution.title()} hunk {hunk_index + 1} of {hunk_total} in {patch.path}"
        )
        result = {
            "ok": True,
            "session_id": session_id,
            "patch_id": patch.id,
            "path": patch.path,
            "operation": "patch_hunk",
            "hunk_index": hunk_index,
            "hunk_total": hunk_total,
            resolution: True,
            "completed": completed,
            "review_complete": completed,
            "summary": summary,
            "pending_patches": self.list_pending(session_id),
        }
        if stored_patch is not None:
            result["patch"] = stored_patch.payload(max_diff_chars=self.max_diff_chars)
        if write_result is not None:
            result["write_result"] = write_result
        return result

    def _finalize_line_resolution(
        self,
        *,
        session_id: str,
        patches: list[PendingWorkspacePatch],
        patch: PendingWorkspacePatch,
        next_base_exists: bool,
        next_base_content: str,
        next_target_content: str,
        keep_when_empty: bool,
        hunk_index: int,
        hunk_total: int,
        line_index: int,
        line_total: int,
        resolution: str,
        write_result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        updated_patch = PendingWorkspacePatch(
            id=patch.id,
            path=patch.path,
            operation=patch.operation,
            source=patch.source,
            created_at=patch.created_at,
            summary=patch.summary,
            base_exists=next_base_exists,
            base_content=next_base_content,
            target_content=next_target_content,
            diff=_build_unified_diff(patch.path, next_base_content, next_target_content),
        )
        remaining_hunks = _build_patch_hunks(
            patch.path,
            updated_patch.base_content,
            updated_patch.target_content,
        )
        completed = not remaining_hunks

        if completed and not keep_when_empty:
            next_patches = [item for item in patches if item.id != patch.id]
            stored_patch = None
        else:
            next_patches = [
                updated_patch if item.id == patch.id else item for item in patches
            ]
            stored_patch = updated_patch

        self._save(session_id, next_patches)
        summary = (
            f"{resolution.title()} line {line_index + 1} of {line_total} "
            f"in hunk {hunk_index + 1} of {hunk_total} in {patch.path}"
        )
        result = {
            "ok": True,
            "session_id": session_id,
            "patch_id": patch.id,
            "path": patch.path,
            "operation": "patch_line",
            "hunk_index": hunk_index,
            "hunk_total": hunk_total,
            "line_index": line_index,
            "line_total": line_total,
            resolution: True,
            "completed": completed,
            "review_complete": completed,
            "summary": summary,
            "pending_patches": self.list_pending(session_id),
        }
        if stored_patch is not None:
            result["patch"] = stored_patch.payload(max_diff_chars=self.max_diff_chars)
        if write_result is not None:
            result["write_result"] = write_result
        return result


def _build_unified_diff(path: str, before: str, after: str) -> str:
    diff_lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff_lines) or f"No textual diff for `{path}`."


def _build_patch_hunks(path: str, before: str, after: str) -> list[WorkspacePatchHunk]:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    hunks: list[WorkspacePatchHunk] = []
    for index, group in enumerate(matcher.get_grouped_opcodes(3)):
        changed = [tuple(opcode) for opcode in group if opcode[0] != "equal"]
        if not changed:
            continue
        before_start = group[0][1]
        before_end = group[-1][2]
        after_start = group[0][3]
        after_end = group[-1][4]
        line_actions: list[WorkspacePatchLineAction] = []
        additions = sum(
            j2 - j1 for tag, _, _, j1, j2 in changed if tag in {"replace", "insert"}
        )
        deletions = sum(
            i2 - i1 for tag, i1, i2, _, _ in changed if tag in {"replace", "delete"}
        )
        header = (
            f"@@ -{_format_unified_range(before_start, before_end - before_start)} "
            f"+{_format_unified_range(after_start, after_end - after_start)} @@"
        )
        diff_lines = [header]
        for tag, i1, i2, j1, j2 in group:
            if tag in {"equal", "replace", "delete"}:
                diff_lines.extend(
                    f"{' ' if tag == 'equal' else '-'}{_display_diff_line(line)}"
                    for line in before_lines[i1:i2]
                )
            if tag in {"replace", "insert"}:
                diff_lines.extend(
                    f"+{_display_diff_line(line)}" for line in after_lines[j1:j2]
                )
            if tag != "equal":
                line_actions.extend(
                    _build_line_actions_for_opcode(
                        before_lines=before_lines,
                        after_lines=after_lines,
                        opcode=(tag, i1, i2, j1, j2),
                        start_index=len(line_actions),
                    )
                )
        hunks.append(
            WorkspacePatchHunk(
                index=len(hunks),
                header=header,
                diff="\n".join(diff_lines),
                additions=additions,
                deletions=deletions,
                before_start=before_start + 1,
                before_count=before_end - before_start,
                after_start=after_start + 1,
                after_count=after_end - after_start,
                opcodes=tuple(changed),
                lines=tuple(line_actions),
            )
        )
    return hunks


def _resolve_hunk_content(
    before: str,
    after: str,
    hunk: WorkspacePatchHunk,
    *,
    accept_selected: bool,
) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    selected = set(hunk.opcodes)
    resolved: list[str] = []
    for opcode in matcher.get_opcodes():
        tag, i1, i2, j1, j2 = opcode
        key = tuple(opcode)
        if tag == "equal":
            resolved.extend(before_lines[i1:i2])
            continue
        if key in selected:
            if accept_selected:
                resolved.extend(after_lines[j1:j2])
            else:
                resolved.extend(before_lines[i1:i2])
            continue
        if accept_selected:
            resolved.extend(before_lines[i1:i2])
        else:
            resolved.extend(after_lines[j1:j2])
    return "".join(resolved)


def _resolve_line_content(
    before: str,
    after: str,
    line_action: WorkspacePatchLineAction,
    *,
    accept_selected: bool,
) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    selected_opcode = line_action.opcode
    selected_unit_index = line_action.opcode_unit_index
    resolved: list[str] = []
    for opcode in matcher.get_opcodes():
        tag, i1, i2, j1, j2 = opcode
        key = tuple(opcode)
        if tag == "equal":
            resolved.extend(before_lines[i1:i2])
            continue
        if key == selected_opcode:
            resolved.extend(
                _resolve_opcode_line_unit(
                    before_lines=before_lines,
                    after_lines=after_lines,
                    opcode=key,
                    selected_unit_index=selected_unit_index,
                    accept_selected=accept_selected,
                )
            )
            continue
        if accept_selected:
            resolved.extend(before_lines[i1:i2])
        else:
            resolved.extend(after_lines[j1:j2])
    return "".join(resolved)


def _edit_line_target_content(
    before: str,
    after: str,
    line_action: WorkspacePatchLineAction,
    edited_after_text: str,
) -> str:
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    selected_opcode = line_action.opcode
    selected_unit_index = line_action.opcode_unit_index
    resolved: list[str] = []
    for opcode in matcher.get_opcodes():
        tag, i1, i2, j1, j2 = opcode
        key = tuple(opcode)
        if tag == "equal":
            resolved.extend(before_lines[i1:i2])
            continue
        if key == selected_opcode:
            resolved.extend(
                _edit_opcode_line_unit(
                    before_lines=before_lines,
                    after_lines=after_lines,
                    opcode=key,
                    selected_unit_index=selected_unit_index,
                    edited_after_text=edited_after_text,
                    fallback_content=after or before,
                )
            )
            continue
        resolved.extend(after_lines[j1:j2])
    return "".join(resolved)


def _build_line_actions_for_opcode(
    *,
    before_lines: list[str],
    after_lines: list[str],
    opcode: Opcode,
    start_index: int,
) -> list[WorkspacePatchLineAction]:
    tag, i1, i2, j1, j2 = opcode
    previous_lines = before_lines[i1:i2]
    next_lines = after_lines[j1:j2]
    unit_count = max(len(previous_lines), len(next_lines))
    actions: list[WorkspacePatchLineAction] = []
    for offset in range(unit_count):
        before_text = (
            _display_diff_line(previous_lines[offset])
            if offset < len(previous_lines)
            else None
        )
        after_text = (
            _display_diff_line(next_lines[offset]) if offset < len(next_lines) else None
        )
        diff_parts: list[str] = []
        if before_text is not None:
            diff_parts.append(f"-{before_text}")
        if after_text is not None:
            diff_parts.append(f"+{after_text}")
        actions.append(
            WorkspacePatchLineAction(
                index=start_index + offset,
                kind=tag,
                before_line_number=(i1 + offset + 1) if offset < len(previous_lines) else None,
                after_line_number=(j1 + offset + 1) if offset < len(next_lines) else None,
                before_text=before_text,
                after_text=after_text,
                diff="\n".join(diff_parts),
                opcode=opcode,
                opcode_unit_index=offset,
            )
        )
    return actions


def _resolve_opcode_line_unit(
    *,
    before_lines: list[str],
    after_lines: list[str],
    opcode: Opcode,
    selected_unit_index: int,
    accept_selected: bool,
) -> list[str]:
    _, i1, i2, j1, j2 = opcode
    previous_lines = before_lines[i1:i2]
    next_lines = after_lines[j1:j2]
    unit_count = max(len(previous_lines), len(next_lines))
    resolved: list[str] = []
    for offset in range(unit_count):
        before_line = previous_lines[offset] if offset < len(previous_lines) else None
        after_line = next_lines[offset] if offset < len(next_lines) else None
        use_after = accept_selected if offset == selected_unit_index else not accept_selected
        if use_after:
            if after_line is not None:
                resolved.append(after_line)
        elif before_line is not None:
            resolved.append(before_line)
    return resolved


def _edit_opcode_line_unit(
    *,
    before_lines: list[str],
    after_lines: list[str],
    opcode: Opcode,
    selected_unit_index: int,
    edited_after_text: str,
    fallback_content: str,
) -> list[str]:
    _, i1, i2, j1, j2 = opcode
    previous_lines = before_lines[i1:i2]
    next_lines = after_lines[j1:j2]
    unit_count = max(len(previous_lines), len(next_lines))
    resolved: list[str] = []
    for offset in range(unit_count):
        before_line = previous_lines[offset] if offset < len(previous_lines) else None
        after_line = next_lines[offset] if offset < len(next_lines) else None
        if offset == selected_unit_index:
            resolved.append(
                _compose_edited_line(
                    edited_after_text,
                    template_line=after_line or before_line,
                    fallback_content=fallback_content,
                )
            )
            continue
        if after_line is not None:
            resolved.append(after_line)
    return resolved


def _compose_edited_line(
    text: str,
    *,
    template_line: str | None,
    fallback_content: str,
) -> str:
    newline = _detect_line_ending(template_line, fallback_content)
    return f"{text}{newline}" if newline else text


def _detect_line_ending(template_line: str | None, fallback_content: str) -> str:
    if template_line:
        if template_line.endswith("\r\n"):
            return "\r\n"
        if template_line.endswith("\n"):
            return "\n"
    if "\r\n" in fallback_content:
        return "\r\n"
    if "\n" in fallback_content:
        return "\n"
    return ""


def _display_diff_line(line: str) -> str:
    return line[:-1] if line.endswith("\n") else line


def _format_unified_range(start_index: int, length: int) -> str:
    start = start_index + 1
    if length == 0:
        return f"{max(start - 1, 0)},0"
    if length == 1:
        return str(start)
    return f"{start},{length}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
