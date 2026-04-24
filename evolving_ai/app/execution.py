from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import uuid

_DEFAULT_ALLOWED_MODULES = (
    "base64",
    "collections",
    "csv",
    "datetime",
    "decimal",
    "fractions",
    "functools",
    "hashlib",
    "heapq",
    "io",
    "itertools",
    "json",
    "math",
    "operator",
    "pathlib",
    "random",
    "re",
    "statistics",
    "string",
    "textwrap",
    "typing",
)
_BLOCKED_CALL_NAMES = frozenset(
    {"__import__", "breakpoint", "compile", "eval", "exec", "input"}
)
_INTERNAL_WORKSPACE_PREFIX = ".forge_exec_"
_BLOCKED_WORKSPACE_PARTS = frozenset({".git"})
_PATCH_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    timeout_seconds: float
    max_code_chars: int = 12_000
    max_output_chars: int = 16_000
    max_files: int = 32
    max_file_bytes: int = 256_000
    allow_network: bool = False
    allow_subprocess: bool = False
    allow_outside_workspace: bool = False
    allowed_modules: tuple[str, ...] = _DEFAULT_ALLOWED_MODULES

    def payload(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_code_chars": self.max_code_chars,
            "max_output_chars": self.max_output_chars,
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "allow_network": self.allow_network,
            "allow_subprocess": self.allow_subprocess,
            "allow_outside_workspace": self.allow_outside_workspace,
            "allowed_modules": list(self.allowed_modules),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceInspection:
    files: list[str]
    violations: list[str]


@dataclass(frozen=True, slots=True)
class WorkspaceFileRead:
    path: str
    content: str
    total_lines: int
    start_line: int
    end_line: int
    truncated: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class WorkspaceFileWrite:
    path: str
    created: bool
    size_bytes: int


@dataclass(frozen=True, slots=True)
class WorkspaceFileReplace:
    path: str
    replacements: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class WorkspacePatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    additions: int
    deletions: int


@dataclass(frozen=True, slots=True)
class WorkspacePatchPreview:
    path: str
    can_apply: bool
    creates_file: bool
    current_hash: str
    patched_hash: str
    hunk_count: int
    additions: int
    deletions: int
    size_bytes: int
    issues: list[str]
    preview: str
    hunks: list[WorkspacePatchHunk]


@dataclass(frozen=True, slots=True)
class WorkspacePatchApply:
    path: str
    created: bool
    current_hash: str
    patched_hash: str
    hunk_count: int
    additions: int
    deletions: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _ParsedPatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    additions: int
    deletions: int
    lines: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _WorkspacePatchComputation:
    preview: WorkspacePatchPreview
    patched_text: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    session_id: str
    returncode: int
    stdout: str
    stderr: str
    files: list[str]
    timed_out: bool
    sandbox: dict[str, object]


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace_for(self, session_id: str) -> Path:
        safe_session = "".join(
            char for char in session_id if char.isalnum() or char in {"-", "_"}
        ) or "default"
        path = self.root / safe_session
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_files(self, session_id: str) -> list[str]:
        workspace = self.workspace_for(session_id)
        files = []
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(workspace)
            if self._is_hidden_workspace_path(relative):
                continue
            files.append(str(relative).replace("\\", "/"))
        return sorted(files)

    def inspect(self, session_id: str, *, policy: SandboxPolicy) -> WorkspaceInspection:
        workspace = self.workspace_for(session_id)
        files: list[str] = []
        violations: list[str] = []
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(workspace)
            if self._is_hidden_workspace_path(relative_path):
                continue
            relative = str(relative_path).replace("\\", "/")
            files.append(relative)
            size = path.stat().st_size
            if size > policy.max_file_bytes:
                violations.append(
                    f"Workspace file `{relative}` exceeded the {policy.max_file_bytes} byte limit."
                )
        files.sort()
        if len(files) > policy.max_files:
            violations.append(
                f"Workspace created {len(files)} files, above the {policy.max_files} file limit."
            )
        return WorkspaceInspection(files=files, violations=violations)

    def read_text_file(
        self,
        session_id: str,
        relative_path: str,
        *,
        max_chars: int,
        max_file_bytes: int,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> WorkspaceFileRead:
        _, target, relative = self._resolve_file_path(session_id, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Workspace file `{relative}` does not exist.")
        if not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")
        size_bytes = target.stat().st_size
        if size_bytes > max_file_bytes:
            raise ValueError(
                f"Workspace file `{relative}` exceeds the {max_file_bytes} byte limit."
            )
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Workspace file `{relative}` is not a UTF-8 text file."
            ) from exc

        lines = content.splitlines()
        total_lines = len(lines)
        normalized_start = start_line or 1
        if normalized_start < 1:
            raise ValueError("`start_line` must be at least 1.")
        normalized_end = end_line if end_line is not None else total_lines or normalized_start
        if normalized_end < normalized_start:
            raise ValueError("`end_line` must be greater than or equal to `start_line`.")
        if total_lines and normalized_start > total_lines:
            raise ValueError(
                f"`start_line` {normalized_start} is beyond the end of `{relative}` ({total_lines} lines)."
            )

        if total_lines == 0:
            selected = ""
            bounded_start = 0
            bounded_end = 0
        else:
            bounded_start = normalized_start
            bounded_end = min(normalized_end, total_lines)
            selected = "\n".join(lines[bounded_start - 1 : bounded_end])

        truncated = False
        if len(selected) > max_chars:
            selected = selected[:max_chars]
            truncated = True

        return WorkspaceFileRead(
            path=relative,
            content=selected,
            total_lines=total_lines,
            start_line=bounded_start,
            end_line=bounded_end,
            truncated=truncated,
            size_bytes=size_bytes,
        )

    def write_text_file(
        self,
        session_id: str,
        relative_path: str,
        content: str,
        *,
        max_file_bytes: int,
        max_files: int,
    ) -> WorkspaceFileWrite:
        workspace, target, relative = self._resolve_file_path(session_id, relative_path)
        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")

        data = content.encode("utf-8")
        if len(data) > max_file_bytes:
            raise ValueError(
                f"Workspace file `{relative}` would exceed the {max_file_bytes} byte limit."
            )

        created = not target.exists()
        if created and len(self.list_files(session_id)) >= max_files:
            raise ValueError(
                f"Workspace already has {max_files} files, so `{relative}` cannot be created."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return WorkspaceFileWrite(
            path=relative,
            created=created,
            size_bytes=len(data),
        )

    def replace_text_in_file(
        self,
        session_id: str,
        relative_path: str,
        old_text: str,
        new_text: str,
        *,
        max_file_bytes: int,
        replace_all: bool = False,
        expected_occurrences: int | None = None,
    ) -> WorkspaceFileReplace:
        _, target, relative = self._resolve_file_path(session_id, relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Workspace file `{relative}` does not exist.")
        if not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")
        if not old_text:
            raise ValueError("`old_text` cannot be empty.")
        if expected_occurrences is not None and expected_occurrences < 1:
            raise ValueError("`expected_occurrences` must be at least 1.")
        if expected_occurrences not in {None, 1} and not replace_all:
            raise ValueError(
                "Set `replace_all` when `expected_occurrences` is greater than 1."
            )
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Workspace file `{relative}` is not a UTF-8 text file."
            ) from exc

        occurrences = content.count(old_text)
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
        updated = content.replace(old_text, new_text, replacements)
        size_bytes = len(updated.encode("utf-8"))
        if size_bytes > max_file_bytes:
            raise ValueError(
                f"Workspace file `{relative}` would exceed the {max_file_bytes} byte limit."
            )
        target.write_text(updated, encoding="utf-8")
        return WorkspaceFileReplace(
            path=relative,
            replacements=replacements,
            size_bytes=size_bytes,
        )

    def preview_text_patch(
        self,
        session_id: str,
        relative_path: str,
        patch: str,
        *,
        max_file_bytes: int,
        max_files: int,
    ) -> WorkspacePatchPreview:
        return self._compute_text_patch(
            session_id=session_id,
            relative_path=relative_path,
            patch=patch,
            max_file_bytes=max_file_bytes,
            max_files=max_files,
        ).preview

    def apply_text_patch(
        self,
        session_id: str,
        relative_path: str,
        patch: str,
        *,
        max_file_bytes: int,
        max_files: int,
        expected_hash: str | None = None,
    ) -> WorkspacePatchApply:
        workspace, target, relative = self._resolve_file_path(session_id, relative_path)
        computation = self._compute_text_patch(
            session_id=session_id,
            relative_path=relative_path,
            patch=patch,
            max_file_bytes=max_file_bytes,
            max_files=max_files,
        )
        preview = computation.preview
        if expected_hash and expected_hash.strip() != preview.current_hash:
            raise ValueError(
                f"Workspace file `{relative}` changed since the preview was generated."
            )
        if not preview.can_apply:
            raise ValueError(
                "; ".join(preview.issues)
                or f"Patch for `{relative}` could not be applied."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(computation.patched_text, encoding="utf-8")
        return WorkspacePatchApply(
            path=str(target.relative_to(workspace)).replace("\\", "/"),
            created=preview.creates_file,
            current_hash=preview.current_hash,
            patched_hash=preview.patched_hash,
            hunk_count=preview.hunk_count,
            additions=preview.additions,
            deletions=preview.deletions,
            size_bytes=preview.size_bytes,
        )

    def _compute_text_patch(
        self,
        *,
        session_id: str,
        relative_path: str,
        patch: str,
        max_file_bytes: int,
        max_files: int,
    ) -> _WorkspacePatchComputation:
        _, target, relative = self._resolve_file_path(session_id, relative_path)
        if not patch.strip():
            raise ValueError("Patch cannot be empty.")
        if target.exists() and not target.is_file():
            raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")

        current_exists = target.exists()
        if current_exists:
            size_bytes = target.stat().st_size
            if size_bytes > max_file_bytes:
                raise ValueError(
                    f"Workspace file `{relative}` exceeds the {max_file_bytes} byte limit."
                )
            try:
                current_text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"Workspace file `{relative}` is not a UTF-8 text file."
                ) from exc
        else:
            current_text = ""

        parsed_hunks = self._parse_unified_patch(patch)
        preview_text = self._render_patch_preview(relative, parsed_hunks)
        issues: list[str] = []
        if not current_exists and len(self.list_files(session_id)) >= max_files:
            issues.append(
                f"Workspace already has {max_files} files, so `{relative}` cannot be created."
            )

        patched_text = current_text
        if not issues:
            try:
                patched_text = self._apply_parsed_hunks(
                    current_text=current_text,
                    relative=relative,
                    hunks=parsed_hunks,
                )
            except ValueError as exc:
                issues.append(str(exc))

        patched_size = len(patched_text.encode("utf-8"))
        if patched_size > max_file_bytes:
            issues.append(
                f"Workspace file `{relative}` would exceed the {max_file_bytes} byte limit."
            )

        additions = sum(item.additions for item in parsed_hunks)
        deletions = sum(item.deletions for item in parsed_hunks)
        preview = WorkspacePatchPreview(
            path=relative,
            can_apply=not issues,
            creates_file=not current_exists,
            current_hash=self._text_hash(current_text),
            patched_hash=self._text_hash(patched_text),
            hunk_count=len(parsed_hunks),
            additions=additions,
            deletions=deletions,
            size_bytes=patched_size,
            issues=issues,
            preview=preview_text,
            hunks=[
                WorkspacePatchHunk(
                    old_start=item.old_start,
                    old_count=item.old_count,
                    new_start=item.new_start,
                    new_count=item.new_count,
                    additions=item.additions,
                    deletions=item.deletions,
                )
                for item in parsed_hunks
            ],
        )
        return _WorkspacePatchComputation(preview=preview, patched_text=patched_text)

    def _parse_unified_patch(self, patch: str) -> list[_ParsedPatchHunk]:
        lines = patch.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        index = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line.startswith(("--- ", "+++ ", "diff --git ", "index ")) or not line:
                index += 1
                continue
            raise ValueError(
                "Patch must use unified diff hunks that start with `@@`."
            )

        hunks: list[_ParsedPatchHunk] = []
        while index < len(lines):
            match = _PATCH_HUNK_RE.match(lines[index])
            if match is None:
                raise ValueError(f"Invalid patch hunk header: `{lines[index]}`.")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            if old_start == 0 and old_count != 0:
                raise ValueError("Patch hunks with `-0` must also use `,0`.")
            index += 1
            hunk_lines: list[tuple[str, str]] = []
            additions = 0
            deletions = 0
            while index < len(lines) and not lines[index].startswith("@@ "):
                line = lines[index]
                if line == r"\ No newline at end of file":
                    index += 1
                    continue
                if not line:
                    raise ValueError("Patch lines must begin with ` `, `-`, or `+`.")
                prefix = line[0]
                if prefix not in {" ", "-", "+"}:
                    raise ValueError(
                        f"Patch lines must begin with ` `, `-`, or `+`: `{line}`."
                    )
                hunk_lines.append((prefix, line[1:]))
                if prefix == "+":
                    additions += 1
                elif prefix == "-":
                    deletions += 1
                index += 1

            actual_old_count = sum(
                1 for prefix, _ in hunk_lines if prefix in {" ", "-"}
            )
            actual_new_count = sum(
                1 for prefix, _ in hunk_lines if prefix in {" ", "+"}
            )
            if actual_old_count != old_count or actual_new_count != new_count:
                raise ValueError(
                    "Patch hunk line counts do not match the `@@` header metadata."
                )
            hunks.append(
                _ParsedPatchHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    additions=additions,
                    deletions=deletions,
                    lines=tuple(hunk_lines),
                )
            )

        if not hunks:
            raise ValueError("Patch must contain at least one hunk.")
        return hunks

    def _apply_parsed_hunks(
        self,
        *,
        current_text: str,
        relative: str,
        hunks: list[_ParsedPatchHunk],
    ) -> str:
        current_lines = current_text.splitlines()
        patched_lines = list(current_lines)
        offset = 0
        last_original_end = 0
        had_trailing_newline = current_text.endswith("\n")

        for number, hunk in enumerate(hunks, start=1):
            original_start = 0 if hunk.old_start == 0 else hunk.old_start - 1
            if original_start < last_original_end:
                raise ValueError(
                    f"Patch hunk {number} overlaps a previous hunk in `{relative}`."
                )
            last_original_end = original_start + hunk.old_count
            start = original_start + offset
            if start < 0 or start > len(patched_lines):
                raise ValueError(
                    f"Patch hunk {number} starts outside the current contents of `{relative}`."
                )
            expected_lines = [
                line for prefix, line in hunk.lines if prefix in {" ", "-"}
            ]
            replacement_lines = [
                line for prefix, line in hunk.lines if prefix in {" ", "+"}
            ]
            actual_lines = patched_lines[start : start + len(expected_lines)]
            if actual_lines != expected_lines:
                location = hunk.old_start or 1
                raise ValueError(
                    f"Patch hunk {number} does not match `{relative}` at line {location}."
                )
            patched_lines[start : start + len(expected_lines)] = replacement_lines
            offset += len(replacement_lines) - len(expected_lines)

        patched_text = "\n".join(patched_lines)
        if patched_lines and (had_trailing_newline or not current_text):
            patched_text += "\n"
        return patched_text

    def _render_patch_preview(
        self,
        relative: str,
        hunks: list[_ParsedPatchHunk],
    ) -> str:
        lines = [f"--- a/{relative}", f"+++ b/{relative}"]
        for hunk in hunks:
            lines.append(
                f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
            )
            for prefix, line in hunk.lines:
                lines.append(f"{prefix}{line}")
        return "\n".join(lines)

    def _text_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def resolve_workspace_path(
        self, session_id: str, relative_path: str
    ) -> tuple[Path, Path, str]:
        return self._resolve_file_path(session_id, relative_path)

    def _resolve_file_path(self, session_id: str, relative_path: str) -> tuple[Path, Path, str]:
        workspace = self.workspace_for(session_id).resolve()
        raw = str(relative_path or "").strip()
        if not raw or raw in {".", "/"}:
            raise ValueError("Workspace file path cannot be empty.")

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        candidate = candidate.resolve(strict=False)
        try:
            relative = candidate.relative_to(workspace)
        except ValueError as exc:
            raise ValueError("Workspace file path must stay inside the session workspace.") from exc
        if self._is_hidden_workspace_path(relative):
            raise ValueError("Internal sandbox files cannot be accessed through workspace tools.")
        return workspace, candidate, str(relative).replace("\\", "/")

    def _is_hidden_workspace_path(self, relative: Path) -> bool:
        return any(
            part.startswith(_INTERNAL_WORKSPACE_PREFIX) or part in _BLOCKED_WORKSPACE_PARTS
            for part in relative.parts
        )


class PythonExecutor:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        timeout_seconds: float,
        *,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.policy = policy or SandboxPolicy(timeout_seconds=timeout_seconds)

    def execute(self, *, session_id: str, code: str) -> ExecutionResult:
        workspace = self.workspace_manager.workspace_for(session_id)
        violations = self._validate_code(workspace=workspace, code=code)
        if violations:
            inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
            return ExecutionResult(
                session_id=session_id,
                returncode=126,
                stdout="",
                stderr="\n".join(violations),
                files=inspection.files,
                timed_out=False,
                sandbox=self._sandbox_payload(blocked=True, violations=violations),
            )

        payload_path, bootstrap_path, stdout_path, stderr_path = self.prepare_runtime_files(
            workspace=workspace,
            code=code,
        )
        timed_out = False
        returncode = -1
        stdout = ""
        stderr = ""
        runtime_violations: list[str] = []
        try:
            with stdout_path.open("wb") as stdout_handle, stderr_path.open(
                "wb"
            ) as stderr_handle:
                completed = subprocess.run(
                    [sys.executable, "-I", "-S", "-B", bootstrap_path.name],
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    timeout=self.policy.timeout_seconds,
                    env=self._sandbox_env(workspace),
                    creationflags=self._creation_flags(),
                )
            returncode = completed.returncode
            stdout = self._read_output(stdout_path)
            stderr = self._read_output(stderr_path)
        except subprocess.TimeoutExpired:
            timed_out = True
            stdout = self._read_output(stdout_path)
            stderr = self._read_output(stderr_path)
            returncode = -1
            timeout_message = "Execution timed out and the sandbox process was stopped."
            stderr = f"{stderr.rstrip()}\n{timeout_message}".strip()
            runtime_violations.append(timeout_message)
        finally:
            self.cleanup_runtime_files(
                payload_path, bootstrap_path, stdout_path, stderr_path
            )

        inspection = self.workspace_manager.inspect(session_id, policy=self.policy)
        if inspection.violations:
            runtime_violations.extend(inspection.violations)
            detail = "\n".join(inspection.violations)
            stderr = f"{stderr.rstrip()}\n{detail}".strip()
            if returncode == 0:
                returncode = 125
        return ExecutionResult(
            session_id=session_id,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            files=inspection.files,
            timed_out=timed_out,
            sandbox=self._sandbox_payload(
                blocked=bool(runtime_violations), violations=runtime_violations
            ),
        )

    def prepare_runtime_files(
        self,
        *,
        workspace: Path,
        code: str,
        runtime_workspace: str | None = None,
        runtime_payload: str | None = None,
    ) -> tuple[Path, Path, Path, Path]:
        token = uuid.uuid4().hex
        payload_path = workspace / f".forge_exec_{token}.py"
        bootstrap_path = workspace / f".forge_exec_{token}_bootstrap.py"
        stdout_path = workspace / f".forge_exec_{token}.stdout"
        stderr_path = workspace / f".forge_exec_{token}.stderr"
        if runtime_workspace and runtime_payload is None:
            normalized_workspace = runtime_workspace.rstrip("/") or "/workspace"
            runtime_payload = f"{normalized_workspace}/{payload_path.name}"
        payload_path.write_text(code, encoding="utf-8")
        bootstrap_path.write_text(
            self._bootstrap_script(
                workspace=workspace,
                payload_path=payload_path,
                runtime_workspace=runtime_workspace,
                runtime_payload=runtime_payload,
                timeout_seconds=self.policy.timeout_seconds,
            ),
            encoding="utf-8",
        )
        return payload_path, bootstrap_path, stdout_path, stderr_path

    def cleanup_runtime_files(self, *paths: Path) -> None:
        for internal_path in paths:
            if internal_path.exists():
                internal_path.unlink()

    def _validate_code(self, *, workspace: Path, code: str) -> list[str]:
        violations: set[str] = set()
        if len(code) > self.policy.max_code_chars:
            violations.add(
                f"Code exceeds the {self.policy.max_code_chars} character sandbox limit."
            )
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return sorted(violations)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if not self._module_allowed(workspace, root):
                        violations.add(
                            f"Import `{root}` is not allowed in the sandbox."
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if not self._module_allowed(workspace, root):
                        violations.add(
                            f"Import `{root}` is not allowed in the sandbox."
                        )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in _BLOCKED_CALL_NAMES:
                    violations.add(
                        f"Call to `{node.func.id}` is disabled in the sandbox."
                    )
        return sorted(violations)

    def _module_allowed(self, workspace: Path, module_name: str) -> bool:
        if module_name in self.policy.allowed_modules or module_name == "__future__":
            return True
        if (workspace / f"{module_name}.py").exists():
            return True
        package_dir = workspace / module_name
        return package_dir.is_dir() and (package_dir / "__init__.py").exists()

    def _bootstrap_script(
        self,
        *,
        workspace: Path,
        payload_path: Path,
        runtime_workspace: str | None = None,
        runtime_payload: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        template = """
        from __future__ import annotations

        import builtins
        import importlib
        import io
        import os
        from pathlib import Path
        import signal
        import socket
        import subprocess
        import sys

        WORKSPACE = Path(__WORKSPACE__).resolve()
        PAYLOAD = Path(__PAYLOAD__).resolve()
        ALLOWED_MODULES = set(__ALLOWED_MODULES__)
        MAX_FILE_BYTES = __MAX_FILE_BYTES__
        MAX_FILES = __MAX_FILES__
        TIMEOUT_SECONDS = __TIMEOUT_SECONDS__

        _ORIGINAL_IMPORT = builtins.__import__
        _ORIGINAL_OPEN = builtins.open
        _ORIGINAL_EXEC = builtins.exec
        _ORIGINAL_COMPILE = builtins.compile
        _ORIGINAL_IMPORT_MODULE = importlib.import_module
        _ORIGINAL_PATH_MKDIR = Path.mkdir
        _ORIGINAL_PATH_OPEN = Path.open
        _ORIGINAL_PATH_REPLACE = Path.replace
        _ORIGINAL_PATH_RENAME = Path.rename
        _ORIGINAL_PATH_UNLINK = Path.unlink

        class SandboxError(PermissionError):
            pass

        def _normalize_path(target: object) -> Path:
            candidate = Path(target)
            if not candidate.is_absolute():
                candidate = WORKSPACE / candidate
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(WORKSPACE)
            except ValueError as exc:
                raise SandboxError("File access outside the workspace is blocked.") from exc
            return resolved

        def _count_workspace_files() -> int:
            total = 0
            for item in WORKSPACE.rglob("*"):
                if item.is_file() and not item.name.startswith(".forge_exec_"):
                    total += 1
            return total

        def _check_file_budget(target: Path, mode: str) -> None:
            writes = any(flag in mode for flag in ("a", "w", "x", "+"))
            if writes and not target.exists() and _count_workspace_files() >= MAX_FILES:
                raise SandboxError(
                    f"Workspace file limit of {MAX_FILES} files has been reached."
                )

        class _TrackedFile:
            def __init__(self, handle, path: Path):
                self._handle = handle
                self._path = path
                self._estimated_size = path.stat().st_size if path.exists() else 0

            def write(self, data):
                size = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
                if self._estimated_size + size > MAX_FILE_BYTES:
                    raise SandboxError(
                        f"File `{self._path.name}` would exceed the {MAX_FILE_BYTES} byte limit."
                    )
                written = self._handle.write(data)
                self._estimated_size += size
                return written

            def writelines(self, lines):
                total = 0
                for line in lines:
                    total += self.write(line)
                return total

            def __enter__(self):
                self._handle.__enter__()
                return self

            def __exit__(self, exc_type, exc, tb):
                return self._handle.__exit__(exc_type, exc, tb)

            def __iter__(self):
                return iter(self._handle)

            def __getattr__(self, name: str):
                return getattr(self._handle, name)

        def _safe_open(file, mode="r", *args, **kwargs):
            target = _normalize_path(file)
            _check_file_budget(target, mode)
            if any(flag in mode for flag in ("a", "w", "x", "+")):
                target.parent.mkdir(parents=True, exist_ok=True)
            handle = _ORIGINAL_OPEN(target, mode, *args, **kwargs)
            if any(flag in mode for flag in ("a", "w", "x", "+")):
                return _TrackedFile(handle, target)
            return handle

        def _path_open(self, mode="r", *args, **kwargs):
            return _safe_open(self, mode, *args, **kwargs)

        def _path_mkdir(self, mode=0o777, parents=False, exist_ok=False):
            target = _normalize_path(self)
            return _ORIGINAL_PATH_MKDIR(target, mode=mode, parents=parents, exist_ok=exist_ok)

        def _path_write_text(self, data, encoding="utf-8", errors=None, newline=None):
            with _safe_open(self, "w", encoding=encoding, errors=errors, newline=newline) as handle:
                return handle.write(data)

        def _path_write_bytes(self, data):
            with _safe_open(self, "wb") as handle:
                return handle.write(data)

        def _path_read_text(self, encoding="utf-8", errors=None):
            with _safe_open(self, "r", encoding=encoding, errors=errors) as handle:
                return handle.read()

        def _path_read_bytes(self):
            with _safe_open(self, "rb") as handle:
                return handle.read()

        def _path_unlink(self, missing_ok=False):
            target = _normalize_path(self)
            try:
                return _ORIGINAL_PATH_UNLINK(target)
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise

        def _path_rename(self, target):
            source = _normalize_path(self)
            destination = _normalize_path(target)
            return _ORIGINAL_PATH_RENAME(source, destination)

        def _path_replace(self, target):
            source = _normalize_path(self)
            destination = _normalize_path(target)
            return _ORIGINAL_PATH_REPLACE(source, destination)

        def _module_allowed(name: str) -> bool:
            root = name.split(".")[0]
            if root in ALLOWED_MODULES or root == "__future__":
                return True
            return (WORKSPACE / f"{root}.py").exists() or (
                (WORKSPACE / root).is_dir() and (WORKSPACE / root / "__init__.py").exists()
            )

        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if not _module_allowed(name):
                raise SandboxError(f"Import `{name.split('.')[0]}` is not allowed in the sandbox.")
            return _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)

        def _safe_import_module(name, package=None):
            if not _module_allowed(name):
                raise SandboxError(f"Import `{name.split('.')[0]}` is not allowed in the sandbox.")
            return _ORIGINAL_IMPORT_MODULE(name, package)

        def _blocked(reason: str):
            def _raiser(*args, **kwargs):
                raise SandboxError(reason)
            return _raiser

        builtins.__import__ = _safe_import
        builtins.open = _safe_open
        builtins.eval = _blocked("`eval` is disabled in the sandbox.")
        builtins.exec = _blocked("`exec` is disabled in the sandbox.")
        builtins.compile = _blocked("`compile` is disabled in the sandbox.")
        builtins.input = _blocked("`input` is disabled in the sandbox.")
        builtins.breakpoint = _blocked("`breakpoint` is disabled in the sandbox.")
        io.open = _safe_open
        importlib.import_module = _safe_import_module

        socket.socket = _blocked("Network access is disabled in the sandbox.")
        socket.create_connection = _blocked("Network access is disabled in the sandbox.")
        socket.getaddrinfo = _blocked("Network access is disabled in the sandbox.")
        socket.gethostbyname = _blocked("Network access is disabled in the sandbox.")
        socket.gethostbyname_ex = _blocked("Network access is disabled in the sandbox.")
        socket.getnameinfo = _blocked("Network access is disabled in the sandbox.")

        subprocess.Popen = _blocked("Process creation is disabled in the sandbox.")
        subprocess.run = _blocked("Process creation is disabled in the sandbox.")
        subprocess.call = _blocked("Process creation is disabled in the sandbox.")
        subprocess.check_call = _blocked("Process creation is disabled in the sandbox.")
        subprocess.check_output = _blocked("Process creation is disabled in the sandbox.")

        os.system = _blocked("Shell execution is disabled in the sandbox.")
        os.popen = _blocked("Shell execution is disabled in the sandbox.")
        if hasattr(os, "startfile"):
            os.startfile = _blocked("Shell execution is disabled in the sandbox.")

        Path.open = _path_open
        Path.mkdir = _path_mkdir
        Path.read_text = _path_read_text
        Path.read_bytes = _path_read_bytes
        Path.write_text = _path_write_text
        Path.write_bytes = _path_write_bytes
        Path.unlink = _path_unlink
        Path.rename = _path_rename
        Path.replace = _path_replace

        os.chdir(WORKSPACE)

        def _handle_timeout(signum, frame):
            raise TimeoutError("Execution timed out inside the sandbox.")

        if TIMEOUT_SECONDS > 0 and hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(TIMEOUT_SECONDS)

        try:
            source = _ORIGINAL_OPEN(PAYLOAD, "r", encoding="utf-8").read()
            code = _ORIGINAL_COMPILE(source, PAYLOAD.name, "exec")
            namespace = {"__name__": "__main__", "__file__": str(PAYLOAD), "__builtins__": builtins}
            _ORIGINAL_EXEC(code, namespace, namespace)
        except TimeoutError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(124)
        finally:
            if TIMEOUT_SECONDS > 0 and hasattr(signal, "SIGALRM"):
                signal.alarm(0)
        """
        return (
            textwrap.dedent(template)
            .replace("__WORKSPACE__", repr(runtime_workspace or str(workspace)))
            .replace("__PAYLOAD__", repr(runtime_payload or str(payload_path)))
            .replace("__ALLOWED_MODULES__", repr(self.policy.allowed_modules))
            .replace("__MAX_FILE_BYTES__", str(self.policy.max_file_bytes))
            .replace("__MAX_FILES__", str(self.policy.max_files))
            .replace("__TIMEOUT_SECONDS__", str(max(0, int(timeout_seconds or 0))))
        )

    def _sandbox_env(self, workspace: Path) -> dict[str, str]:
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "HOME": str(workspace),
            "USERPROFILE": str(workspace),
            "TMP": str(workspace),
            "TEMP": str(workspace),
            "PATH": "",
        }
        for key in (
            "SYSTEMROOT",
            "WINDIR",
            "SYSTEMDRIVE",
            "PROGRAMDATA",
            "APPDATA",
            "LOCALAPPDATA",
            "PUBLIC",
        ):
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def _read_output(self, path: Path) -> str:
        if not path.exists():
            return ""
        data = path.read_bytes()
        if len(data) <= self.policy.max_output_chars:
            return data.decode("utf-8", errors="replace")
        clipped = data[: self.policy.max_output_chars].decode(
            "utf-8", errors="replace"
        )
        return (
            f"{clipped}\n...[output truncated to {self.policy.max_output_chars} bytes]..."
        )

    def _sandbox_payload(
        self,
        *,
        blocked: bool,
        violations: list[str],
        requested_backend: str = "local",
        fallback_reason: str = "",
    ) -> dict[str, object]:
        return {
            "backend": "local",
            "requested_backend": requested_backend,
            "fallback": {
                "used": bool(fallback_reason),
                "reason": fallback_reason,
            },
            "blocked": blocked,
            "violations": violations,
            "policy": self.policy.payload(),
        }

    def _creation_flags(self) -> int:
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        return flags
