from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
from urllib.parse import urlparse
import uuid
import zipfile

from .execution import WorkspaceManager

_IMPORT_STORE_NAME = ".forge_exec_imports.json"
_TASK_STORE_NAME = ".forge_exec_tasks.json"
_ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
)


@dataclass(frozen=True, slots=True)
class WorkspaceImportConfig:
    max_upload_bytes: int = 12_000_000
    max_archive_entries: int = 2_048
    max_total_bytes: int = 48_000_000
    clone_timeout_seconds: float = 180.0
    allowed_clone_hosts: tuple[str, ...] = (
        "github.com",
        "gitlab.com",
        "bitbucket.org",
    )

    def payload(self) -> dict[str, object]:
        return {
            "max_upload_bytes": self.max_upload_bytes,
            "max_archive_entries": self.max_archive_entries,
            "max_total_bytes": self.max_total_bytes,
            "clone_timeout_seconds": self.clone_timeout_seconds,
            "allowed_clone_hosts": list(self.allowed_clone_hosts),
        }


@dataclass(slots=True)
class WorkspaceImportEntry:
    id: str
    kind: str
    source: str
    created_at: str
    summary: str
    target_path: str
    entry_count: int
    total_bytes: int
    files_sample: list[str] = field(default_factory=list)
    filename: str = ""
    repo_url: str = ""
    branch: str = ""
    host: str = ""

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class WorkspaceTaskRecord:
    id: str
    title: str
    goal: str
    cwd: str
    test_commands: list[str]
    status: str
    phase: str
    created_at: str
    updated_at: str
    source: str
    summary: str = ""
    final_message: str = ""
    review_summary: str = ""
    changed_files: list[str] = field(default_factory=list)
    approval_note: str = ""
    plan: dict[str, object] = field(default_factory=dict)
    git_handoff: dict[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return asdict(self)


class WorkspaceProjectManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        max_files: int,
        max_file_bytes: int,
        config: WorkspaceImportConfig,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.config = config

    def list_imports(self, session_id: str) -> list[dict[str, object]]:
        return [item.payload() for item in self._load_imports(session_id)]

    def import_upload(
        self,
        *,
        session_id: str,
        filename: str,
        payload: bytes,
        target_path: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        if len(payload) > self.config.max_upload_bytes:
            return {
                "ok": False,
                "session_id": session_id,
                "error": (
                    f"Upload exceeded the {self.config.max_upload_bytes} byte limit."
                ),
                "imports": self.list_imports(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }

        clean_name = Path(filename or "upload.bin").name or "upload.bin"
        try:
            if self._is_archive_name(clean_name):
                extracted = self._extract_archive(
                    session_id=session_id,
                    filename=clean_name,
                    payload=payload,
                    target_dir=target_path,
                )
                entry = WorkspaceImportEntry(
                    id=uuid.uuid4().hex,
                    kind="archive",
                    source=source,
                    created_at=_utc_now(),
                    summary=(
                        f"Imported archive `{clean_name}` "
                        f"with {len(extracted)} file(s)."
                    ),
                    target_path=str(target_path or ".").strip() or ".",
                    entry_count=len(extracted),
                    total_bytes=sum(size for _, size in extracted),
                    files_sample=[path for path, _ in extracted[:12]],
                    filename=clean_name,
                )
            else:
                target = str(target_path or clean_name).strip() or clean_name
                _, resolved, relative = self.workspace_manager.resolve_workspace_path(
                    session_id,
                    target,
                )
                if resolved.exists() and not resolved.is_file():
                    raise IsADirectoryError(
                        f"Workspace path `{relative}` is not a file."
                    )
                if len(payload) > self.max_file_bytes:
                    raise ValueError(
                        f"Workspace file `{relative}` would exceed the {self.max_file_bytes} byte limit."
                    )
                created = not resolved.exists()
                if created and len(self.workspace_manager.list_files(session_id)) >= self.max_files:
                    raise ValueError(
                        f"Workspace already has {self.max_files} files, so `{relative}` cannot be created."
                    )
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(payload)
                entry = WorkspaceImportEntry(
                    id=uuid.uuid4().hex,
                    kind="file",
                    source=source,
                    created_at=_utc_now(),
                    summary=f"Imported file `{relative}`.",
                    target_path=relative,
                    entry_count=1,
                    total_bytes=len(payload),
                    files_sample=[relative],
                    filename=clean_name,
                )
        except (
            FileNotFoundError,
            IsADirectoryError,
            ValueError,
            zipfile.BadZipFile,
            tarfile.TarError,
        ) as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "error": str(exc),
                "imports": self.list_imports(session_id),
                "files": self.workspace_manager.list_files(session_id),
            }

        self._append_import(session_id, entry)
        return {
            "ok": True,
            "session_id": session_id,
            "import": entry.payload(),
            "imports": self.list_imports(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def clone_repository(
        self,
        *,
        session_id: str,
        repo_url: str,
        branch: str | None = None,
        target_dir: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        parsed = urlparse(repo_url.strip())
        host = parsed.hostname.lower() if parsed.hostname else ""
        if parsed.scheme != "https":
            return self._clone_error(
                session_id,
                "Only HTTPS git clone URLs are allowed.",
            )
        if parsed.username or parsed.password:
            return self._clone_error(
                session_id,
                "Clone URLs with embedded credentials are not allowed.",
            )
        if parsed.query or parsed.fragment:
            return self._clone_error(
                session_id,
                "Clone URLs cannot include query strings or fragments.",
            )
        if host not in {item.lower() for item in self.config.allowed_clone_hosts}:
            return self._clone_error(
                session_id,
                f"Clone host `{host or '(missing)'}` is not in the allowed host list.",
            )

        workspace = self.workspace_manager.workspace_for(session_id)
        default_target = self._default_clone_target(
            session_id=session_id,
            repo_url=repo_url,
        )
        requested_target = str(target_dir or default_target).strip() or default_target
        if requested_target in {"", ".", "/"}:
            resolved = workspace
            relative = "."
            if any(workspace.iterdir()):
                return self._clone_error(
                    session_id,
                    "Workspace root is not empty, so the repository must be cloned into a subdirectory.",
                )
        else:
            try:
                _, resolved, relative = self.workspace_manager.resolve_workspace_path(
                    session_id,
                    requested_target,
                )
            except ValueError as exc:
                return self._clone_error(session_id, str(exc))
            if resolved.exists():
                if resolved.is_file():
                    return self._clone_error(
                        session_id,
                        f"Workspace path `{relative}` is already a file.",
                    )
                if any(resolved.iterdir()):
                    return self._clone_error(
                        session_id,
                        f"Workspace directory `{relative}` is not empty.",
                    )
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)

        command = ["git", "-c", "core.hooksPath=/dev/null", "clone", "--depth", "1", "--single-branch"]
        if branch:
            command.extend(["--branch", branch])
        command.extend([repo_url, str(resolved)])
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.config.clone_timeout_seconds,
                creationflags=_creation_flags(),
                cwd=workspace,
            )
        except FileNotFoundError:
            return self._clone_error(session_id, "Git is not installed on the host machine.")
        except subprocess.TimeoutExpired:
            if resolved.exists():
                shutil.rmtree(resolved, ignore_errors=True)
            return self._clone_error(
                session_id,
                f"Git clone timed out after {self.config.clone_timeout_seconds} seconds.",
            )

        if completed.returncode != 0:
            if resolved.exists():
                shutil.rmtree(resolved, ignore_errors=True)
            detail = (completed.stderr or completed.stdout).strip()
            return self._clone_error(session_id, detail or "Git clone failed.")

        imported_files, total_bytes = self._visible_stats(resolved)
        if imported_files > self.max_files:
            shutil.rmtree(resolved, ignore_errors=True)
            return self._clone_error(
                session_id,
                f"Cloned repository created {imported_files} files, above the {self.max_files} file limit.",
            )
        if total_bytes > self.config.max_total_bytes:
            shutil.rmtree(resolved, ignore_errors=True)
            return self._clone_error(
                session_id,
                f"Cloned repository exceeded the {self.config.max_total_bytes} byte limit.",
            )

        files = self.workspace_manager.list_files(session_id)
        entry = WorkspaceImportEntry(
            id=uuid.uuid4().hex,
            kind="clone",
            source=source,
            created_at=_utc_now(),
            summary=(
                f"Cloned `{repo_url}` into `{relative}`"
                + (f" on branch `{branch}`." if branch else ".")
            ),
            target_path=relative,
            entry_count=imported_files,
            total_bytes=total_bytes,
            files_sample=self._sample_visible_files(resolved, relative),
            repo_url=repo_url,
            branch=branch or "",
            host=host,
        )
        self._append_import(session_id, entry)
        return {
            "ok": True,
            "session_id": session_id,
            "import": entry.payload(),
            "imports": self.list_imports(session_id),
            "files": files,
        }

    def collect_git_review(
        self,
        session_id: str,
        *,
        cwd: str | None = None,
    ) -> dict[str, object]:
        selected_repo = self._resolve_repo_root(session_id, cwd=cwd)
        repo_root = selected_repo[0] if selected_repo is not None else None
        review = {
            "status": "",
            "diff_stat": "",
            "diff": "",
            "changed_files": [],
            "status_entries": [],
            "repo_path": selected_repo[1] if selected_repo is not None else "",
        }
        if repo_root is None:
            return review

        commands = (
            ("status", ["status", "--short"]),
            ("diff_stat", ["diff", "--stat"]),
            ("diff", ["diff", "--no-ext-diff", "--unified=3"]),
        )
        for field, arguments in commands:
            completed = self._run_git(repo_root, arguments)
            if completed is None or completed.returncode != 0:
                continue
            review[field] = (completed.stdout or "").strip()

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
                normalized = path.replace("\\", "/")
                changed_files.append(normalized)
                status_entries.append(
                    {
                        "status": status_code,
                        "path": normalized,
                        "summary": f"{status_code} {normalized}".strip(),
                    }
                )
            review["changed_files"] = changed_files
            review["status_entries"] = status_entries
        return review

    def inspect_git(
        self,
        session_id: str,
        *,
        cwd: str | None = None,
    ) -> dict[str, object]:
        selected_repo = self._resolve_repo_root(session_id, cwd=cwd)
        if selected_repo is None:
            return {
                "ok": True,
                "session_id": session_id,
                "git": {
                    "is_repo": False,
                    "repo_path": "",
                    "branch": "",
                    "head": "",
                    "status": "",
                    "diff_stat": "",
                    "diff": "",
                    "changed_files": [],
                    "status_entries": [],
                    "recent_commits": [],
                    "available_actions": ["handoff"],
                },
            }

        repo_root, repo_path = selected_repo
        review = self.collect_git_review(session_id, cwd=cwd)
        branch = self._git_stdout(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        head = self._git_stdout(repo_root, ["rev-parse", "--short", "HEAD"])
        recent_commits_raw = self._git_stdout(repo_root, ["log", "--oneline", "-5"])
        recent_commits = [
            line.strip() for line in recent_commits_raw.splitlines() if line.strip()
        ]
        repo_candidates = [
            path for _, path in self._discover_repo_roots(session_id) if path.strip()
        ]
        return {
            "ok": True,
            "session_id": session_id,
            "git": {
                "is_repo": True,
                "repo_path": repo_path,
                "branch": branch,
                "head": head,
                "status": str(review.get("status", "")).strip(),
                "diff_stat": str(review.get("diff_stat", "")).strip(),
                "diff": str(review.get("diff", "")).strip(),
                "changed_files": list(review.get("changed_files", []))
                if isinstance(review.get("changed_files", []), list)
                else [],
                "status_entries": list(review.get("status_entries", []))
                if isinstance(review.get("status_entries", []), list)
                else [],
                "recent_commits": recent_commits,
                "available_actions": ["branch", "handoff"],
                "repo_candidates": repo_candidates,
            },
        }

    def create_branch(
        self,
        session_id: str,
        *,
        name: str,
        cwd: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        branch_name = " ".join(name.split()).strip()
        if not branch_name:
            return self._git_error(
                session_id=session_id,
                cwd=cwd,
                message="Git branch name cannot be empty.",
            )
        selected_repo = self._resolve_repo_root(session_id, cwd=cwd)
        if selected_repo is None:
            return self._git_error(
                session_id=session_id,
                cwd=cwd,
                message="No Git repository was found in this workspace.",
            )
        repo_root, repo_path = selected_repo
        branch_check = self._run_git(
            repo_root,
            ["check-ref-format", "--branch", branch_name],
        )
        if branch_check is None or branch_check.returncode != 0:
            return self._git_error(
                session_id=session_id,
                cwd=cwd,
                message=f"`{branch_name}` is not a valid Git branch name.",
            )
        existing = self._run_git(
            repo_root,
            ["rev-parse", "--verify", f"refs/heads/{branch_name}"],
        )
        if existing is not None and existing.returncode == 0:
            return self._git_error(
                session_id=session_id,
                cwd=cwd,
                message=f"Git branch `{branch_name}` already exists.",
            )
        switch = self._run_git(repo_root, ["switch", "-c", branch_name])
        if switch is None or switch.returncode != 0:
            switch = self._run_git(repo_root, ["checkout", "-b", branch_name])
        if switch is None or switch.returncode != 0:
            detail = ""
            if switch is not None:
                detail = (switch.stderr or switch.stdout).strip()
            return self._git_error(
                session_id=session_id,
                cwd=cwd,
                message=detail or f"Unable to create branch `{branch_name}`.",
            )
        git_state = self.inspect_git(session_id, cwd=cwd)
        git_payload = git_state.get("git", {})
        if isinstance(git_payload, dict):
            git_payload["branch"] = branch_name
            git_payload["repo_path"] = repo_path
            git_payload["source"] = source
        return {
            "ok": True,
            "session_id": session_id,
            "branch": branch_name,
            "files": self.workspace_manager.list_files(session_id),
            "git": git_payload if isinstance(git_payload, dict) else {},
        }

    def _extract_archive(
        self,
        *,
        session_id: str,
        filename: str,
        payload: bytes,
        target_dir: str | None,
    ) -> list[tuple[str, int]]:
        entries = self._read_archive_entries(filename=filename, payload=payload)
        if not entries:
            raise ValueError("Archive did not contain any regular files.")
        if len(entries) > self.config.max_archive_entries:
            raise ValueError(
                f"Archive contains {len(entries)} files, above the {self.config.max_archive_entries} entry limit."
            )
        total_bytes = sum(len(content) for _, content in entries)
        if total_bytes > self.config.max_total_bytes:
            raise ValueError(
                f"Archive exceeded the {self.config.max_total_bytes} byte limit."
            )

        existing_files = set(self.workspace_manager.list_files(session_id))
        created_files = 0
        written: list[tuple[str, int]] = []
        normalized_target_dir = str(target_dir or "").strip().strip("/")
        for entry_name, content in entries:
            relative_name = entry_name
            if normalized_target_dir:
                relative_name = f"{normalized_target_dir}/{entry_name}"
            _, resolved, relative = self.workspace_manager.resolve_workspace_path(
                session_id,
                relative_name,
            )
            if resolved.exists() and not resolved.is_file():
                raise IsADirectoryError(f"Workspace path `{relative}` is not a file.")
            if len(content) > self.max_file_bytes:
                raise ValueError(
                    f"Workspace file `{relative}` would exceed the {self.max_file_bytes} byte limit."
                )
            if relative not in existing_files:
                created_files += 1
                if len(existing_files) + created_files > self.max_files:
                    raise ValueError(
                        f"Workspace already has {self.max_files} files, so `{relative}` cannot be created."
                    )
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(content)
            written.append((relative, len(content)))
        return sorted(written, key=lambda item: item[0])

    def _read_archive_entries(
        self, *, filename: str, payload: bytes
    ) -> list[tuple[str, bytes]]:
        lower_name = filename.lower()
        if lower_name.endswith(".zip"):
            return self._read_zip_entries(payload)
        return self._read_tar_entries(payload)

    def _read_zip_entries(self, payload: bytes) -> list[tuple[str, bytes]]:
        entries: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                mode = (item.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError(
                        f"Archive entry `{item.filename}` is a symlink and cannot be imported."
                    )
                relative = _normalize_archive_path(item.filename)
                with archive.open(item, "r") as handle:
                    entries.append((relative, handle.read()))
        return entries

    def _read_tar_entries(self, payload: bytes) -> list[tuple[str, bytes]]:
        entries: list[tuple[str, bytes]] = []
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
            for item in archive.getmembers():
                if item.isdir():
                    continue
                if not item.isreg():
                    raise ValueError(
                        f"Archive entry `{item.name}` is not a regular file."
                    )
                relative = _normalize_archive_path(item.name)
                extracted = archive.extractfile(item)
                if extracted is None:
                    raise ValueError(f"Archive entry `{item.name}` could not be read.")
                entries.append((relative, extracted.read()))
        return entries

    def _visible_stats(self, root: Path) -> tuple[int, int]:
        count = 0
        total_bytes = 0
        for path in self._iter_visible_files(root):
            count += 1
            total_bytes += path.stat().st_size
        return count, total_bytes

    def _sample_visible_files(self, root: Path, root_label: str) -> list[str]:
        prefix = "" if root_label in {"", "."} else f"{root_label.strip('/')}/"
        items: list[str] = []
        for path in self._iter_visible_files(root):
            relative = str(path.relative_to(root)).replace("\\", "/")
            items.append(f"{prefix}{relative}")
            if len(items) >= 12:
                break
        return items

    def _iter_visible_files(self, root: Path):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue
            yield path

    def _run_git(
        self, repo_root: Path, arguments: list[str]
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                creationflags=_creation_flags(),
                cwd=repo_root,
            )
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None

    def _git_stdout(self, repo_root: Path, arguments: list[str]) -> str:
        completed = self._run_git(repo_root, arguments)
        if completed is None or completed.returncode != 0:
            return ""
        return (completed.stdout or "").strip()

    def _resolve_repo_root(
        self,
        session_id: str,
        *,
        cwd: str | None = None,
    ) -> tuple[Path, str] | None:
        workspace = self.workspace_manager.workspace_for(session_id).resolve()
        normalized_cwd = str(cwd or ".").strip() or "."
        candidate = workspace
        if normalized_cwd not in {"", "."}:
            raw = Path(normalized_cwd)
            if raw.is_absolute():
                candidate = raw.resolve(strict=False)
            else:
                candidate = (workspace / raw).resolve(strict=False)
            try:
                candidate.relative_to(workspace)
            except ValueError:
                return None
            if candidate.exists() and candidate.is_file():
                candidate = candidate.parent
        for path in [candidate, *candidate.parents]:
            if path == workspace.parent:
                break
            if path == workspace or workspace in path.parents:
                if (path / ".git").exists():
                    return path, self._repo_relative(workspace, path)
        discovered = self._discover_repo_roots(session_id)
        if not discovered:
            return None
        workspace_repo = next((item for item in discovered if item[1] == "."), None)
        if workspace_repo is not None:
            return workspace_repo
        return discovered[0]

    def _discover_repo_roots(self, session_id: str) -> list[tuple[Path, str]]:
        workspace = self.workspace_manager.workspace_for(session_id).resolve()
        roots: list[tuple[Path, str]] = []
        if (workspace / ".git").exists():
            roots.append((workspace, "."))
        for git_dir in workspace.rglob(".git"):
            if not git_dir.is_dir():
                continue
            repo_root = git_dir.parent.resolve()
            if repo_root == workspace:
                continue
            roots.append((repo_root, self._repo_relative(workspace, repo_root)))
        deduped: dict[str, Path] = {}
        for repo_root, relative in roots:
            deduped.setdefault(relative, repo_root)
        return sorted(
            [(root, relative) for relative, root in deduped.items()],
            key=lambda item: (item[1] != ".", item[1]),
        )

    def _repo_relative(self, workspace: Path, repo_root: Path) -> str:
        relative = repo_root.relative_to(workspace)
        parts = [part for part in relative.parts if part]
        if not parts:
            return "."
        return "/".join(parts)

    def _git_error(
        self,
        *,
        session_id: str,
        cwd: str | None,
        message: str,
    ) -> dict[str, object]:
        return {
            "ok": False,
            "session_id": session_id,
            "error": message,
            "files": self.workspace_manager.list_files(session_id),
            "git": self.inspect_git(session_id, cwd=cwd).get("git", {}),
        }

    def _default_clone_target(self, *, session_id: str, repo_url: str) -> str:
        workspace = self.workspace_manager.workspace_for(session_id)
        repo_name = Path(urlparse(repo_url).path).name
        repo_name = repo_name[:-4] if repo_name.lower().endswith(".git") else repo_name
        repo_name = repo_name or "repo"
        if not any(workspace.iterdir()):
            return "."
        return repo_name

    def _clone_error(self, session_id: str, message: str) -> dict[str, object]:
        return {
            "ok": False,
            "session_id": session_id,
            "error": message,
            "imports": self.list_imports(session_id),
            "files": self.workspace_manager.list_files(session_id),
        }

    def _append_import(self, session_id: str, entry: WorkspaceImportEntry) -> None:
        imports = self._load_imports(session_id)
        imports.insert(0, entry)
        self._save_imports(session_id, imports[:20])

    def _load_imports(self, session_id: str) -> list[WorkspaceImportEntry]:
        store_path = self._imports_path(session_id)
        if not store_path.exists():
            return []
        try:
            payload = json.loads(store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries: list[WorkspaceImportEntry] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                entries.append(WorkspaceImportEntry(**item))
            except TypeError:
                continue
        return entries

    def _save_imports(self, session_id: str, entries: list[WorkspaceImportEntry]) -> None:
        store_path = self._imports_path(session_id)
        if not entries:
            if store_path.exists():
                store_path.unlink()
            return
        payload = [item.payload() for item in entries]
        store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _imports_path(self, session_id: str) -> Path:
        return self.workspace_manager.workspace_for(session_id) / _IMPORT_STORE_NAME

    def _is_archive_name(self, filename: str) -> bool:
        lowered = filename.lower()
        return any(lowered.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


class WorkspaceTaskManager:
    def __init__(self, *, workspace_manager: WorkspaceManager, max_entries: int = 20) -> None:
        self.workspace_manager = workspace_manager
        self.max_entries = max_entries

    def list_tasks(self, session_id: str) -> list[dict[str, object]]:
        return [item.payload() for item in self._load(session_id)]

    def start_task(
        self,
        *,
        session_id: str,
        goal: str,
        cwd: str,
        test_commands: list[str],
        source: str = "ui",
        title: str | None = None,
        plan: dict[str, object] | None = None,
    ) -> dict[str, object]:
        record = WorkspaceTaskRecord(
            id=uuid.uuid4().hex,
            title=title or _task_title(goal),
            goal=goal,
            cwd=cwd,
            test_commands=list(test_commands),
            status="running",
            phase="plan",
            created_at=_utc_now(),
            updated_at=_utc_now(),
            source=source,
            summary="Task plan prepared. Starting workspace inspection.",
            plan=dict(plan or {}),
        )
        self._upsert(session_id, record)
        return record.payload()

    def update_task(
        self,
        *,
        session_id: str,
        task_id: str,
        phase: str | None = None,
        status: str | None = None,
        summary: str | None = None,
        final_message: str | None = None,
        review_summary: str | None = None,
        changed_files: list[str] | None = None,
        approval_note: str | None = None,
        plan: dict[str, object] | None = None,
        git_handoff: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        tasks = self._load(session_id)
        for index, task in enumerate(tasks):
            if task.id != task_id:
                continue
            if phase is not None:
                task.phase = phase
            if status is not None:
                task.status = status
            if summary is not None:
                task.summary = summary
            if final_message is not None:
                task.final_message = final_message
            if review_summary is not None:
                task.review_summary = review_summary
            if changed_files is not None:
                task.changed_files = list(changed_files)
            if approval_note is not None:
                task.approval_note = approval_note
            if plan is not None:
                task.plan = dict(plan)
            if git_handoff is not None:
                task.git_handoff = dict(git_handoff)
            task.updated_at = _utc_now()
            tasks[index] = task
            self._save(session_id, tasks)
            return task.payload()
        return None

    def get_task(self, session_id: str, task_id: str) -> dict[str, object] | None:
        for task in self._load(session_id):
            if task.id == task_id:
                return task.payload()
        return None

    def resolve_task(
        self,
        *,
        session_id: str,
        task_id: str,
        approved: bool,
        note: str = "",
    ) -> dict[str, object]:
        status = "approved" if approved else "needs_changes"
        summary = "Task approved and ready to keep." if approved else "Task marked for follow-up changes."
        task = self.update_task(
            session_id=session_id,
            task_id=task_id,
            phase="done" if approved else "edit",
            status=status,
            summary=summary,
            approval_note=note.strip(),
        )
        if task is None:
            return {
                "ok": False,
                "session_id": session_id,
                "task_id": task_id,
                "error": f"Task `{task_id}` was not found.",
                "tasks": self.list_tasks(session_id),
            }
        return {
            "ok": True,
            "session_id": session_id,
            "task": task,
            "tasks": self.list_tasks(session_id),
        }

    def _upsert(self, session_id: str, record: WorkspaceTaskRecord) -> None:
        tasks = [item for item in self._load(session_id) if item.id != record.id]
        tasks.insert(0, record)
        self._save(session_id, tasks[: self.max_entries])

    def _load(self, session_id: str) -> list[WorkspaceTaskRecord]:
        store_path = self._store_path(session_id)
        if not store_path.exists():
            return []
        try:
            payload = json.loads(store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items: list[WorkspaceTaskRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                items.append(WorkspaceTaskRecord(**item))
            except TypeError:
                continue
        return items

    def _save(self, session_id: str, tasks: list[WorkspaceTaskRecord]) -> None:
        store_path = self._store_path(session_id)
        if not tasks:
            if store_path.exists():
                store_path.unlink()
            return
        payload = [item.payload() for item in tasks]
        store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _store_path(self, session_id: str) -> Path:
        return self.workspace_manager.workspace_for(session_id) / _TASK_STORE_NAME


def _normalize_archive_path(raw_name: str) -> str:
    normalized = raw_name.replace("\\", "/").strip()
    if not normalized:
        raise ValueError("Archive contains an empty path entry.")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute():
        raise ValueError(f"Archive entry `{raw_name}` must stay inside the workspace.")
    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts:
        raise ValueError("Archive contains an invalid path entry.")
    if any(part == ".." for part in parts):
        raise ValueError(f"Archive entry `{raw_name}` must stay inside the workspace.")
    if any(part.startswith(".forge_exec_") or part == ".git" for part in parts):
        raise ValueError(f"Archive entry `{raw_name}` targets a protected workspace path.")
    return "/".join(parts)


def _task_title(goal: str) -> str:
    words = [word for word in goal.split() if word]
    return " ".join(words[:6]) or "Workspace task"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _creation_flags() -> int:
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    return flags
