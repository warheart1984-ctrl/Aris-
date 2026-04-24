from __future__ import annotations

import ast
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tomllib
import zipfile
import uuid

from .execution import WorkspaceManager

_SNAPSHOT_INDEX_NAME = "snapshots.json"
_SNAPSHOT_ROOT_NAME = ".forge_exec_workspace_snapshots"
_TRANSIENT_RUNTIME_FILE_RE = re.compile(
    r"^\.forge_exec_[0-9a-f]{32}(?:_bootstrap)?\.(?:py|stdout|stderr)$"
)
_SCRIPT_IMPORT_FROM_RE = re.compile(
    r"(?:import|export)\s+(?:type\s+)?(?:[^;]*?\s+from\s+)?['\"](?P<module>[^'\"]+)['\"]"
)
_SCRIPT_REQUIRE_RE = re.compile(r"require\(\s*['\"](?P<module>[^'\"]+)['\"]\s*\)")
_PYTHON_SYMBOL_PATTERNS = (
    (re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b.*:"), "class"),
    (
        re.compile(r"^\s*async\s+def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        "async_function",
    ),
    (re.compile(r"^\s*def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("), "function"),
)
_SCRIPT_SYMBOL_PATTERNS = (
    (
        re.compile(
            r"^\s*(?:export\s+default\s+)?class\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\b"
        ),
        "class",
    ),
    (
        re.compile(
            r"^\s*(?:export\s+)?interface\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\b"
        ),
        "interface",
    ),
    (
        re.compile(r"^\s*(?:export\s+)?type\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\b"),
        "type",
    ),
    (
        re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\("
        ),
        "function",
    ),
    (
        re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^=]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>"
        ),
        "arrow_function",
    ),
)
_SCRIPT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_CODE_FILE_SUFFIXES = {".py", *_SCRIPT_SUFFIXES}
_GOAL_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "app",
    "behavior",
    "bug",
    "class",
    "code",
    "component",
    "create",
    "edit",
    "feature",
    "file",
    "files",
    "fix",
    "for",
    "function",
    "in",
    "is",
    "issue",
    "make",
    "module",
    "of",
    "on",
    "or",
    "repo",
    "repository",
    "service",
    "symbol",
    "task",
    "test",
    "tests",
    "the",
    "this",
    "to",
    "update",
    "validate",
    "with",
}


@dataclass(frozen=True, slots=True)
class WorkspaceSearchConfig:
    max_results: int = 25
    max_excerpt_chars: int = 220

    def payload(self) -> dict[str, int]:
        return {
            "max_results": self.max_results,
            "max_excerpt_chars": self.max_excerpt_chars,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotConfig:
    max_entries: int = 4_096
    max_total_bytes: int = 64_000_000
    max_snapshots: int = 20

    def payload(self) -> dict[str, int]:
        return {
            "max_entries": self.max_entries,
            "max_total_bytes": self.max_total_bytes,
            "max_snapshots": self.max_snapshots,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRepoMapConfig:
    max_focus_paths: int = 6
    max_related_paths: int = 12
    max_nodes: int = 32
    max_edges: int = 64
    max_goal_tokens: int = 8

    def payload(self) -> dict[str, int]:
        return {
            "max_focus_paths": self.max_focus_paths,
            "max_related_paths": self.max_related_paths,
            "max_nodes": self.max_nodes,
            "max_edges": self.max_edges,
            "max_goal_tokens": self.max_goal_tokens,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceSearchResult:
    type: str
    path: str
    line: int | None = None
    column: int | None = None
    snippet: str = ""
    match: str = ""
    symbol: str = ""
    symbol_kind: str = ""
    signature: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "type": self.type,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "snippet": self.snippet,
            "match": self.match,
            "symbol": self.symbol,
            "symbol_kind": self.symbol_kind,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceSymbolRecord:
    path: str
    language: str
    name: str
    qualname: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    content: str
    start_index: int = field(repr=False)
    end_index: int = field(repr=False)

    def payload(self, *, include_content: bool = False) -> dict[str, object]:
        payload = {
            "path": self.path,
            "language": self.language,
            "name": self.name,
            "qualname": self.qualname,
            "kind": self.kind,
            "signature": self.signature,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
        }
        if include_content:
            payload["content"] = self.content
        return payload


@dataclass(frozen=True, slots=True)
class WorkspaceProjectProfile:
    languages: list[str]
    frameworks: list[str]
    package_managers: list[str]
    install_commands: list[str]
    test_commands: list[str]
    lint_commands: list[str]
    run_commands: list[str]
    entrypoints: list[str]
    scripts: dict[str, str]
    signals: list[str]

    def payload(self) -> dict[str, object]:
        return {
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
            "package_managers": list(self.package_managers),
            "install_commands": list(self.install_commands),
            "test_commands": list(self.test_commands),
            "lint_commands": list(self.lint_commands),
            "run_commands": list(self.run_commands),
            "entrypoints": list(self.entrypoints),
            "scripts": dict(self.scripts),
            "signals": list(self.signals),
        }


@dataclass(slots=True)
class WorkspaceSnapshotRecord:
    id: str
    created_at: str
    label: str
    source: str
    file_count: int
    total_bytes: int
    archive_name: str
    sample_files: list[str] = field(default_factory=list)

    def payload(self, *, available: bool) -> dict[str, object]:
        payload = asdict(self)
        payload["available"] = available
        return payload


@dataclass(frozen=True, slots=True)
class WorkspaceRepoMapNode:
    path: str
    language: str
    symbol_count: int
    import_count: int
    imported_by_count: int
    is_test: bool

    def payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "language": self.language,
            "symbol_count": self.symbol_count,
            "import_count": self.import_count,
            "imported_by_count": self.imported_by_count,
            "is_test": self.is_test,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRepoMapEdge:
    source: str
    target: str
    kind: str = "import"

    def payload(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
        }


class WorkspaceSearchManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        max_file_bytes: int,
        config: WorkspaceSearchConfig | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.max_file_bytes = max_file_bytes
        self.config = config or WorkspaceSearchConfig()

    def search(
        self,
        *,
        session_id: str,
        query: str,
        mode: str = "text",
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        normalized_query = " ".join(str(query).split())
        if not normalized_query:
            raise ValueError("Search query cannot be empty.")
        normalized_mode = str(mode or "text").strip().lower()
        result_limit = min(
            max(1, int(limit or self.config.max_results)),
            self.config.max_results,
        )
        normalized_prefix = self._normalize_path_prefix(session_id, path_prefix)
        if normalized_mode in {"file", "files", "filename", "path"}:
            results = self._search_files(
                session_id=session_id,
                query=normalized_query,
                limit=result_limit,
                path_prefix=normalized_prefix,
            )
            active_mode = "files"
        elif normalized_mode in {"text", "grep", "content"}:
            results = self._search_text(
                session_id=session_id,
                query=normalized_query,
                limit=result_limit,
                path_prefix=normalized_prefix,
            )
            active_mode = "text"
        elif normalized_mode in {"symbol", "symbols"}:
            results = self._search_symbols(
                session_id=session_id,
                query=normalized_query,
                limit=result_limit,
                path_prefix=normalized_prefix,
            )
            active_mode = "symbols"
        else:
            raise ValueError("Search mode must be one of `files`, `text`, or `symbols`.")
        return {
            "ok": True,
            "session_id": session_id,
            "query": normalized_query,
            "mode": active_mode,
            "path_prefix": normalized_prefix or "",
            "limit": result_limit,
            "result_count": len(results),
            "results": [item.payload() for item in results],
        }

    def list_symbols(
        self,
        *,
        session_id: str,
        query: str | None = None,
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        result_limit = min(
            max(1, int(limit or self.config.max_results)),
            self.config.max_results,
        )
        normalized_query = " ".join(str(query or "").split()).lower()
        normalized_prefix = self._normalize_path_prefix(session_id, path_prefix)
        symbols = self._symbol_records(session_id, normalized_prefix)
        if normalized_query:
            symbols = [
                item
                for item in symbols
                if normalized_query in item.name.lower()
                or normalized_query in item.qualname.lower()
                or normalized_query in item.signature.lower()
                or normalized_query in item.path.lower()
            ]
        symbols = symbols[:result_limit]
        return {
            "ok": True,
            "session_id": session_id,
            "query": normalized_query,
            "path_prefix": normalized_prefix or "",
            "limit": result_limit,
            "symbol_count": len(symbols),
            "symbols": [item.payload() for item in symbols],
        }

    def read_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None = None,
    ) -> dict[str, object]:
        record = self._resolve_symbol(
            session_id=session_id,
            symbol=symbol,
            path=path,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "symbol": record.payload(include_content=True),
        }

    def find_references(
        self,
        *,
        session_id: str,
        symbol: str,
        limit: int | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, object]:
        normalized_symbol = " ".join(str(symbol).split())
        if not normalized_symbol:
            raise ValueError("Symbol query cannot be empty.")
        normalized_prefix = self._normalize_path_prefix(session_id, path_prefix)
        result_limit = min(
            max(1, int(limit or self.config.max_results)),
            self.config.max_results,
        )
        pattern = _symbol_reference_pattern(normalized_symbol)
        results: list[WorkspaceSearchResult] = []
        for path_value in self._visible_files(session_id, normalized_prefix):
            content = self._read_search_text(session_id, path_value)
            if content is None:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                for match in pattern.finditer(line):
                    results.append(
                        WorkspaceSearchResult(
                            type="reference",
                            path=path_value,
                            line=line_number,
                            column=match.start() + 1,
                            match=normalized_symbol,
                            snippet=self._build_excerpt(
                                line,
                                match.start(),
                                max(1, match.end() - match.start()),
                            ),
                        )
                    )
                    if len(results) >= result_limit:
                        return {
                            "ok": True,
                            "session_id": session_id,
                            "symbol": normalized_symbol,
                            "path_prefix": normalized_prefix or "",
                            "limit": result_limit,
                            "result_count": len(results),
                            "results": [item.payload() for item in results],
                        }
        return {
            "ok": True,
            "session_id": session_id,
            "symbol": normalized_symbol,
            "path_prefix": normalized_prefix or "",
            "limit": result_limit,
            "result_count": len(results),
            "results": [item.payload() for item in results],
        }

    def edit_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None,
        content: str,
        max_file_bytes: int,
        max_files: int,
    ) -> dict[str, object]:
        replacement = str(content)
        if not replacement.strip():
            raise ValueError("Replacement symbol content cannot be empty.")
        record = self._resolve_symbol(
            session_id=session_id,
            symbol=symbol,
            path=path,
        )
        _, target, relative = self.workspace_manager.resolve_workspace_path(
            session_id,
            record.path,
        )
        current_text = target.read_text(encoding="utf-8")
        updated_text = (
            current_text[: record.start_index]
            + replacement.replace("\r\n", "\n")
            + current_text[record.end_index :]
        )
        write_result = self.workspace_manager.write_text_file(
            session_id,
            relative,
            updated_text,
            max_file_bytes=max_file_bytes,
            max_files=max_files,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "path": relative,
            "symbol": record.payload(),
            "size_bytes": write_result.size_bytes,
        }

    def _search_files(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
        path_prefix: str | None,
    ) -> list[WorkspaceSearchResult]:
        query_lower = query.lower()
        ranked: list[tuple[int, str, WorkspaceSearchResult]] = []
        for path in self._visible_files(session_id, path_prefix):
            path_lower = path.lower()
            filename = Path(path).name
            filename_lower = filename.lower()
            if query_lower == filename_lower:
                score = 0
            elif filename_lower.startswith(query_lower):
                score = 1
            elif query_lower in filename_lower:
                score = 2
            elif query_lower in path_lower:
                score = 3
            else:
                continue
            ranked.append(
                (
                    score,
                    path,
                    WorkspaceSearchResult(
                        type="file",
                        path=path,
                        match=filename,
                        snippet=path,
                    ),
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:limit]]

    def _search_text(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
        path_prefix: str | None,
    ) -> list[WorkspaceSearchResult]:
        query_lower = query.lower()
        results: list[WorkspaceSearchResult] = []
        for path in self._visible_files(session_id, path_prefix):
            content = self._read_search_text(session_id, path)
            if content is None:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                column = line.lower().find(query_lower)
                if column < 0:
                    continue
                results.append(
                    WorkspaceSearchResult(
                        type="text",
                        path=path,
                        line=line_number,
                        column=column + 1,
                        match=query,
                        snippet=self._build_excerpt(line, column, len(query)),
                    )
                )
                if len(results) >= limit:
                    return results
        return results

    def _search_symbols(
        self,
        *,
        session_id: str,
        query: str,
        limit: int,
        path_prefix: str | None,
    ) -> list[WorkspaceSearchResult]:
        query_lower = query.lower()
        ranked: list[tuple[int, str, int, WorkspaceSearchResult]] = []
        for result in self._symbol_records(session_id, path_prefix):
            search_result = WorkspaceSearchResult(
                type="symbol",
                path=result.path,
                line=result.start_line,
                column=result.start_column,
                snippet=result.signature,
                match=result.name,
                symbol=result.qualname,
                symbol_kind=result.kind,
                signature=result.signature,
            )
            name_lower = result.qualname.lower()
            signature_lower = result.signature.lower()
            path_lower = result.path.lower()
            if query_lower == name_lower or query_lower == result.name.lower():
                score = 0
            elif name_lower.startswith(query_lower) or result.name.lower().startswith(query_lower):
                score = 1
            elif query_lower in name_lower:
                score = 2
            elif query_lower in signature_lower:
                score = 3
            elif query_lower in path_lower:
                score = 4
            else:
                continue
            ranked.append((score, search_result.path, search_result.line or 0, search_result))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in ranked[:limit]]

    def _visible_files(
        self, session_id: str, path_prefix: str | None
    ) -> list[str]:
        files = self.workspace_manager.list_files(session_id)
        if not path_prefix:
            return files
        prefix = path_prefix.rstrip("/")
        return [
            path
            for path in files
            if path == prefix or path.startswith(f"{prefix}/")
        ]

    def _normalize_path_prefix(
        self, session_id: str, path_prefix: str | None
    ) -> str | None:
        raw = str(path_prefix or "").strip()
        if raw in {"", ".", "/"}:
            return None
        _, _, relative = self.workspace_manager.resolve_workspace_path(session_id, raw)
        return relative

    def _read_search_text(self, session_id: str, path: str) -> str | None:
        _, target, _ = self.workspace_manager.resolve_workspace_path(session_id, path)
        if not target.is_file() or target.stat().st_size > self.max_file_bytes:
            return None
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    def _symbol_records(
        self, session_id: str, path_prefix: str | None
    ) -> list[WorkspaceSymbolRecord]:
        records: list[WorkspaceSymbolRecord] = []
        for path in self._visible_files(session_id, path_prefix):
            content = self._read_search_text(session_id, path)
            if content is None:
                continue
            records.extend(self._iter_symbol_records(path=path, content=content))
        records.sort(key=lambda item: (item.path, item.start_line, item.name))
        return records

    def _iter_symbol_records(
        self,
        *,
        path: str,
        content: str,
    ) -> list[WorkspaceSymbolRecord]:
        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            return _extract_python_symbols(path=path, content=content)
        if suffix in _SCRIPT_SUFFIXES:
            return _extract_script_symbols(path=path, content=content)
        return []

    def _resolve_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None,
    ) -> WorkspaceSymbolRecord:
        normalized_symbol = " ".join(str(symbol).split())
        if not normalized_symbol:
            raise ValueError("Symbol name cannot be empty.")
        path_prefix = self._normalize_path_prefix(session_id, path)
        records = self._symbol_records(session_id, path_prefix)
        exact = [
            item
            for item in records
            if item.name == normalized_symbol or item.qualname == normalized_symbol
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise ValueError(
                "Symbol is ambiguous. Narrow it with `path`. Candidates: "
                + ", ".join(
                    f"{item.qualname} ({item.path}:{item.start_line})" for item in exact[:8]
                )
            )
        lowered = normalized_symbol.lower()
        partial = [
            item
            for item in records
            if lowered in item.name.lower() or lowered in item.qualname.lower()
        ]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise ValueError(
                "Symbol matched multiple results. Narrow it with `path`. Candidates: "
                + ", ".join(
                    f"{item.qualname} ({item.path}:{item.start_line})" for item in partial[:8]
                )
            )
        raise FileNotFoundError(f"Workspace symbol `{normalized_symbol}` was not found.")

    def _build_excerpt(self, line: str, column: int, query_length: int) -> str:
        if len(line) <= self.config.max_excerpt_chars:
            return line
        half_window = max(self.config.max_excerpt_chars // 2, query_length + 16)
        start = max(0, column - half_window)
        end = min(len(line), column + query_length + half_window)
        excerpt = line[start:end]
        if start > 0:
            excerpt = f"...{excerpt}"
        if end < len(line):
            excerpt = f"{excerpt}..."
        return excerpt


class WorkspaceRepoMapManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        max_file_bytes: int,
        config: WorkspaceRepoMapConfig | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.max_file_bytes = max_file_bytes
        self.config = config or WorkspaceRepoMapConfig()

    def inspect(
        self,
        *,
        session_id: str,
        goal: str | None = None,
        cwd: str | None = None,
        focus_path: str | None = None,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        normalized_goal = " ".join(str(goal or "").split())
        normalized_symbol = " ".join(str(symbol or "").split())
        normalized_cwd = self._normalize_scope_prefix(session_id, cwd)
        related_limit = min(
            max(1, int(limit or self.config.max_related_paths)),
            self.config.max_related_paths,
        )
        files = self._visible_files(session_id, normalized_cwd)
        code_files = [
            path for path in files if Path(path).suffix.lower() in _CODE_FILE_SUFFIXES
        ]
        file_index: dict[str, str] = {}
        symbol_index: dict[str, list[WorkspaceSymbolRecord]] = {}
        outgoing: dict[str, set[str]] = {}
        incoming: dict[str, set[str]] = {}
        edges: list[WorkspaceRepoMapEdge] = []
        available_paths = set(code_files)
        for path in code_files:
            content = self._read_text(session_id, path)
            if content is None:
                continue
            file_index[path] = content
            symbols = _repo_map_symbol_records(path=path, content=content)
            symbol_index[path] = symbols
            imports = self._extract_import_targets(
                source_path=path,
                content=content,
                available_paths=available_paths,
            )
            if not imports:
                continue
            for target in sorted(imports):
                outgoing.setdefault(path, set()).add(target)
                incoming.setdefault(target, set()).add(path)
                edges.append(WorkspaceRepoMapEdge(source=path, target=target))

        nodes = {
            path: WorkspaceRepoMapNode(
                path=path,
                language=_repo_map_language(path),
                symbol_count=len(symbol_index.get(path, [])),
                import_count=len(outgoing.get(path, set())),
                imported_by_count=len(incoming.get(path, set())),
                is_test=_repo_map_is_test_path(path),
            )
            for path in sorted(file_index)
        }
        focus_paths = self._resolve_focus_paths(
            session_id=session_id,
            goal=normalized_goal,
            focus_path=focus_path,
            symbol=normalized_symbol,
            files=file_index,
            symbol_index=symbol_index,
        )
        related_paths = self._related_paths(
            focus_paths=focus_paths,
            files=file_index,
            outgoing=outgoing,
            incoming=incoming,
            limit=related_limit,
        )
        likely_test_files = _ordered_unique(
            test_path
            for path in [*focus_paths, *related_paths]
            for test_path in _repo_map_guess_test_files(path, files)
        )[: self.config.max_related_paths]

        included_paths = _ordered_unique(
            [
                *focus_paths,
                *related_paths,
                *likely_test_files,
                *sorted(
                    nodes,
                    key=lambda item: (
                        -(
                            len(outgoing.get(item, set()))
                            + len(incoming.get(item, set()))
                            + len(symbol_index.get(item, []))
                        ),
                        item,
                    ),
                ),
            ]
        )[: self.config.max_nodes]
        included_set = set(included_paths)
        node_payload = [
            nodes[path].payload() for path in included_paths if path in nodes
        ]
        edge_payload = [
            edge.payload()
            for edge in edges
            if edge.source in included_set and edge.target in included_set
        ][: self.config.max_edges]
        summary = self._summary(
            focus_paths=focus_paths,
            related_paths=related_paths,
            likely_test_files=likely_test_files,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "goal": normalized_goal,
            "cwd": normalized_cwd or ".",
            "path": str(focus_path or "").strip(),
            "symbol": normalized_symbol,
            "repo_map": {
                "summary": summary,
                "scope_path": normalized_cwd or ".",
                "focus_paths": focus_paths,
                "owner_paths": focus_paths,
                "related_paths": related_paths,
                "likely_test_files": likely_test_files,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": node_payload,
                "edges": edge_payload,
            },
        }

    def _resolve_focus_paths(
        self,
        *,
        session_id: str,
        goal: str,
        focus_path: str | None,
        symbol: str,
        files: dict[str, str],
        symbol_index: dict[str, list[WorkspaceSymbolRecord]],
    ) -> list[str]:
        ranked: list[str] = []
        raw_focus = str(focus_path or "").strip()
        if raw_focus:
            try:
                _, _, relative = self.workspace_manager.resolve_workspace_path(
                    session_id,
                    raw_focus,
                )
            except ValueError:
                relative = ""
            if relative in files:
                ranked.append(relative)
        if symbol:
            exact_matches: list[str] = []
            partial_matches: list[str] = []
            lowered = symbol.lower()
            for path, records in symbol_index.items():
                for record in records:
                    if record.name == symbol or record.qualname == symbol:
                        exact_matches.append(path)
                        break
                else:
                    if any(
                        lowered in record.name.lower() or lowered in record.qualname.lower()
                        for record in records
                    ):
                        partial_matches.append(path)
            ranked.extend(sorted(exact_matches))
            ranked.extend(sorted(partial_matches))
        goal_tokens = _repo_map_goal_tokens(goal, max_tokens=self.config.max_goal_tokens)
        if goal_tokens and len(ranked) < self.config.max_focus_paths:
            scored: list[tuple[int, str]] = []
            for path, content in files.items():
                score = _repo_map_goal_score(
                    path=path,
                    content=content,
                    tokens=goal_tokens,
                    symbols=symbol_index.get(path, []),
                )
                if score > 0:
                    scored.append((score, path))
            scored.sort(key=lambda item: (-item[0], item[1]))
            remaining = max(0, min(2, self.config.max_focus_paths - len(ranked)))
            if remaining:
                ranked.extend(path for _, path in scored[:remaining])
        if not ranked:
            ranked.extend(sorted(files))
        return _ordered_unique(ranked)[: self.config.max_focus_paths]

    def _related_paths(
        self,
        *,
        focus_paths: list[str],
        files: dict[str, str],
        outgoing: dict[str, set[str]],
        incoming: dict[str, set[str]],
        limit: int,
    ) -> list[str]:
        related: list[str] = []
        seen = set(focus_paths)
        queue = list(focus_paths)
        while queue and len(related) < limit:
            current = queue.pop(0)
            neighbors = sorted(outgoing.get(current, set()) | incoming.get(current, set()))
            for path in neighbors:
                if path in seen or path not in files:
                    continue
                seen.add(path)
                related.append(path)
                queue.append(path)
                if len(related) >= limit:
                    break
        if len(related) < limit:
            focus_dirs = {str(Path(path).parent).replace("\\", "/") for path in focus_paths}
            for path in sorted(files):
                if path in seen:
                    continue
                parent = str(Path(path).parent).replace("\\", "/")
                if parent not in focus_dirs:
                    continue
                seen.add(path)
                related.append(path)
                if len(related) >= limit:
                    break
        return related

    def _extract_import_targets(
        self,
        *,
        source_path: str,
        content: str,
        available_paths: set[str],
    ) -> set[str]:
        suffix = Path(source_path).suffix.lower()
        if suffix == ".py":
            return _extract_python_import_paths(
                source_path=source_path,
                content=content,
                available_paths=available_paths,
            )
        if suffix in _SCRIPT_SUFFIXES:
            return _extract_script_import_paths(
                source_path=source_path,
                content=content,
                available_paths=available_paths,
            )
        return set()

    def _visible_files(self, session_id: str, path_prefix: str | None) -> list[str]:
        files = self.workspace_manager.list_files(session_id)
        if not path_prefix:
            return files
        prefix = path_prefix.rstrip("/")
        return [
            path
            for path in files
            if path == prefix or path.startswith(f"{prefix}/")
        ]

    def _normalize_scope_prefix(
        self, session_id: str, path_prefix: str | None
    ) -> str | None:
        raw = str(path_prefix or "").strip()
        if raw in {"", ".", "/"}:
            return None
        _, _, relative = self.workspace_manager.resolve_workspace_path(session_id, raw)
        return relative

    def _read_text(self, session_id: str, path: str) -> str | None:
        _, target, _ = self.workspace_manager.resolve_workspace_path(session_id, path)
        if not target.is_file() or target.stat().st_size > self.max_file_bytes:
            return None
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    def _summary(
        self,
        *,
        focus_paths: list[str],
        related_paths: list[str],
        likely_test_files: list[str],
    ) -> str:
        segments: list[str] = []
        if focus_paths:
            segments.append(
                "Focus files: " + ", ".join(focus_paths[: self.config.max_focus_paths])
            )
        if related_paths:
            segments.append(
                "Related files: "
                + ", ".join(related_paths[: self.config.max_related_paths])
            )
        if likely_test_files:
            segments.append(
                "Likely tests: "
                + ", ".join(likely_test_files[: self.config.max_related_paths])
            )
        return ". ".join(segment for segment in segments if segment).strip() or (
            "No repo-map focus files were detected in the current workspace scope."
        )


class WorkspaceSnapshotManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        config: WorkspaceSnapshotConfig | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.config = config or WorkspaceSnapshotConfig()
        self.snapshot_root = self.workspace_manager.root / _SNAPSHOT_ROOT_NAME
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

    def list_snapshots(self, session_id: str) -> list[dict[str, object]]:
        return [
            item.payload(available=self._archive_path(session_id, item.archive_name).exists())
            for item in self._load(session_id)
        ]

    def create_snapshot(
        self,
        *,
        session_id: str,
        label: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        files = self._snapshot_files(session_id)
        file_count = len(files)
        total_bytes = sum(size for _, _, size in files)
        if file_count > self.config.max_entries:
            raise ValueError(
                f"Workspace snapshot would include {file_count} files, above the {self.config.max_entries} file limit."
            )
        if total_bytes > self.config.max_total_bytes:
            raise ValueError(
                f"Workspace snapshot would include {total_bytes} bytes, above the {self.config.max_total_bytes} byte limit."
            )

        snapshot_id = uuid.uuid4().hex
        archive_name = f"{snapshot_id}.zip"
        archive_path = self._archive_path(session_id, archive_name)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for relative, target, _ in files:
                archive.write(target, arcname=relative)

        visible_sample = self.workspace_manager.list_files(session_id)[:12]
        record = WorkspaceSnapshotRecord(
            id=snapshot_id,
            created_at=_utc_now(),
            label=str(label or "").strip(),
            source=source,
            file_count=file_count,
            total_bytes=total_bytes,
            archive_name=archive_name,
            sample_files=visible_sample,
        )
        snapshots = self._load(session_id)
        snapshots.insert(0, record)
        if self.config.max_snapshots > 0:
            stale = snapshots[self.config.max_snapshots :]
            snapshots = snapshots[: self.config.max_snapshots]
            for item in stale:
                self._archive_path(session_id, item.archive_name).unlink(missing_ok=True)
        self._save(session_id, snapshots)
        return record.payload(available=True)

    def restore_snapshot(
        self,
        *,
        session_id: str,
        snapshot_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        del source
        snapshots = self._load(session_id)
        record = next((item for item in snapshots if item.id == snapshot_id), None)
        if record is None:
            raise FileNotFoundError(f"Workspace snapshot `{snapshot_id}` was not found.")
        archive_path = self._archive_path(session_id, record.archive_name)
        if not archive_path.exists():
            raise FileNotFoundError(
                f"Workspace snapshot archive `{record.archive_name}` is missing."
            )

        workspace = self.workspace_manager.workspace_for(session_id).resolve()
        self._assert_within_workspace_root(workspace)
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > self.config.max_entries:
                raise ValueError(
                    f"Workspace snapshot contains {len(members)} files, above the {self.config.max_entries} file limit."
                )
            total_bytes = sum(item.file_size for item in members)
            if total_bytes > self.config.max_total_bytes:
                raise ValueError(
                    f"Workspace snapshot contains {total_bytes} bytes, above the {self.config.max_total_bytes} byte limit."
                )

            self._clear_workspace(workspace)
            for member in members:
                relative = self._validated_archive_path(member.filename)
                target = (workspace / Path(*relative.parts)).resolve(strict=False)
                try:
                    target.relative_to(workspace)
                except ValueError as exc:
                    raise ValueError(
                        f"Snapshot file `{member.filename}` would restore outside the workspace."
                    ) from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, mode="r") as source_handle:
                    target.write_bytes(source_handle.read())
        return record.payload(available=True)

    def _snapshot_files(
        self, session_id: str
    ) -> list[tuple[str, Path, int]]:
        workspace = self.workspace_manager.workspace_for(session_id)
        files: list[tuple[str, Path, int]] = []
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(workspace)
            if not self._should_include_snapshot_path(relative_path):
                continue
            files.append(
                (
                    str(relative_path).replace("\\", "/"),
                    path,
                    path.stat().st_size,
                )
            )
        files.sort(key=lambda item: item[0])
        return files

    def _should_include_snapshot_path(self, relative_path: Path) -> bool:
        return not _TRANSIENT_RUNTIME_FILE_RE.match(relative_path.name)

    def _assert_within_workspace_root(self, workspace: Path) -> None:
        root = self.workspace_manager.root.resolve()
        try:
            workspace.relative_to(root)
        except ValueError as exc:
            raise ValueError("Workspace restore target is outside the configured workspaces root.") from exc

    def _clear_workspace(self, workspace: Path) -> None:
        for child in workspace.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _validated_archive_path(self, member_name: str) -> PurePosixPath:
        relative = PurePosixPath(member_name)
        if relative.is_absolute() or not relative.parts:
            raise ValueError("Snapshot archive contains an invalid absolute path.")
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError(
                f"Snapshot archive contains an unsafe path `{member_name}`."
            )
        return relative

    def _session_dir(self, session_id: str) -> Path:
        workspace = self.workspace_manager.workspace_for(session_id)
        return self.snapshot_root / workspace.name

    def _index_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / _SNAPSHOT_INDEX_NAME

    def _archive_path(self, session_id: str, archive_name: str) -> Path:
        return self._session_dir(session_id) / archive_name

    def _load(self, session_id: str) -> list[WorkspaceSnapshotRecord]:
        path = self._index_path(session_id)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        items: list[WorkspaceSnapshotRecord] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            items.append(
                WorkspaceSnapshotRecord(
                    id=str(entry.get("id", "")).strip(),
                    created_at=str(entry.get("created_at", "")).strip(),
                    label=str(entry.get("label", "")).strip(),
                    source=str(entry.get("source", "")).strip() or "ui",
                    file_count=int(entry.get("file_count", 0) or 0),
                    total_bytes=int(entry.get("total_bytes", 0) or 0),
                    archive_name=str(entry.get("archive_name", "")).strip(),
                    sample_files=[
                        str(item)
                        for item in entry.get("sample_files", [])
                        if str(item).strip()
                    ],
                )
            )
        return items

    def _save(self, session_id: str, snapshots: list[WorkspaceSnapshotRecord]) -> None:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._index_path(session_id).write_text(
            json.dumps([asdict(item) for item in snapshots], indent=2),
            encoding="utf-8",
        )


class WorkspaceProjectProfileManager:
    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManager,
        max_file_bytes: int,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.max_file_bytes = max_file_bytes

    def detect(self, session_id: str) -> dict[str, object]:
        files = self.workspace_manager.list_files(session_id)
        lower_files = {item.lower(): item for item in files}
        languages: list[str] = []
        frameworks: list[str] = []
        package_managers: list[str] = []
        install_commands: list[str] = []
        test_commands: list[str] = []
        lint_commands: list[str] = []
        run_commands: list[str] = []
        entrypoints: list[str] = []
        signals: list[str] = []
        scripts: dict[str, str] = {}

        pyproject = self._read_if_present(session_id, lower_files.get("pyproject.toml"))
        package_json = self._read_if_present(session_id, lower_files.get("package.json"))
        python_files = [item for item in files if item.lower().endswith(".py")]
        script_files = [
            item
            for item in files
            if Path(item).suffix.lower() in _SCRIPT_SUFFIXES
        ]
        has_python = bool(pyproject or python_files or self._any_file(lower_files, {"requirements.txt", "setup.py"}))
        has_node = bool(package_json or script_files or self._any_file(lower_files, {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}))

        if has_python:
            languages.append("python")
            signals.append("Detected Python sources or packaging files.")
            python_pm = self._detect_python_package_manager(lower_files, pyproject)
            if python_pm:
                package_managers.append(python_pm)
            if python_pm == "uv":
                install_commands.append("uv sync")
            elif self._any_file(lower_files, {"requirements.txt"}):
                install_commands.append("python -m pip install -r requirements.txt")
            elif pyproject:
                install_commands.append("python -m pip install -e .")

            python_deps = self._python_dependencies(pyproject)
            frameworks.extend(
                item
                for item in self._python_frameworks(python_deps)
                if item not in frameworks
            )
            if self._looks_like_pytest(lower_files, python_deps, files):
                test_commands.append("pytest -q")
            elif any(item.startswith("tests/") for item in files):
                test_commands.append("python -m unittest discover -s tests -v")
            if self._looks_like_ruff(lower_files, python_deps):
                lint_commands.append("ruff check .")
            elif "flake8" in python_deps:
                lint_commands.append("flake8 .")
            if "manage.py" in lower_files:
                entrypoints.append(lower_files["manage.py"])
                run_commands.append("python manage.py runserver")
            for candidate in [
                "main.py",
                "app.py",
                "server.py",
                "src/main.py",
                "src/app.py",
                "src/server.py",
            ]:
                if candidate in lower_files and lower_files[candidate] not in entrypoints:
                    entrypoints.append(lower_files[candidate])
            if "fastapi" in python_deps or "uvicorn" in python_deps:
                if "main.py" in lower_files:
                    run_commands.append("uvicorn main:app --reload")
                elif "app.py" in lower_files:
                    run_commands.append("uvicorn app:app --reload")
            for entrypoint in entrypoints:
                if entrypoint.endswith(".py"):
                    command = f"python {entrypoint}"
                    if command not in run_commands:
                        run_commands.append(command)

        if has_node:
            languages.append("typescript" if any(item.lower().endswith((".ts", ".tsx")) for item in files) else "javascript")
            signals.append("Detected Node or frontend project files.")
            node_pm = self._detect_node_package_manager(lower_files)
            if node_pm:
                package_managers.append(node_pm)
                install_commands.append(f"{node_pm} install")
            package_payload = self._parse_package_json(package_json)
            scripts = package_payload.get("scripts", {})
            node_deps = package_payload.get("dependencies", set())
            frameworks.extend(
                item for item in self._node_frameworks(node_deps) if item not in frameworks
            )
            if scripts:
                signals.append(
                    "Detected package.json scripts: "
                    + ", ".join(sorted(scripts.keys())[:8])
                )
            for script_name in ["test", "lint", "dev", "build"]:
                if script_name in scripts and node_pm:
                    command = _node_script_command(node_pm, script_name)
                    if script_name == "test":
                        test_commands.append(command)
                    elif script_name == "lint":
                        lint_commands.append(command)
                    else:
                        run_commands.append(command)
            if "test" not in scripts:
                if "vitest" in node_deps:
                    test_commands.append("vitest run")
                elif "jest" in node_deps:
                    test_commands.append("jest")
            if "lint" not in scripts:
                if "eslint" in node_deps:
                    lint_commands.append("eslint .")
                elif "@biomejs/biome" in node_deps or "biome" in node_deps:
                    lint_commands.append("biome check .")
            for candidate in self._node_entrypoints(lower_files, package_payload):
                if candidate not in entrypoints:
                    entrypoints.append(candidate)
            for candidate in entrypoints:
                if candidate.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx")):
                    command = f"node {candidate}"
                    if command not in run_commands:
                        run_commands.append(command)

        profile = WorkspaceProjectProfile(
            languages=_ordered_unique(languages),
            frameworks=_ordered_unique(frameworks),
            package_managers=_ordered_unique(package_managers),
            install_commands=_ordered_unique(install_commands),
            test_commands=_ordered_unique(test_commands),
            lint_commands=_ordered_unique(lint_commands),
            run_commands=_ordered_unique(run_commands),
            entrypoints=_ordered_unique(entrypoints),
            scripts=scripts,
            signals=_ordered_unique(signals),
        )
        return {
            "ok": True,
            "session_id": session_id,
            "project": profile.payload(),
            "files": files,
        }

    def _read_if_present(self, session_id: str, path: str | None) -> str:
        if not path:
            return ""
        _, target, _ = self.workspace_manager.resolve_workspace_path(session_id, path)
        if not target.is_file() or target.stat().st_size > self.max_file_bytes:
            return ""
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ""

    def _detect_python_package_manager(
        self,
        lower_files: dict[str, str],
        pyproject: str,
    ) -> str:
        if "uv.lock" in lower_files or "[tool.uv" in pyproject:
            return "uv"
        if "poetry.lock" in lower_files or "[tool.poetry" in pyproject:
            return "poetry"
        return "pip"

    def _detect_node_package_manager(self, lower_files: dict[str, str]) -> str:
        if "pnpm-lock.yaml" in lower_files:
            return "pnpm"
        if "yarn.lock" in lower_files:
            return "yarn"
        if "bun.lockb" in lower_files or "bun.lock" in lower_files:
            return "bun"
        return "npm"

    def _python_dependencies(self, pyproject: str) -> set[str]:
        if not pyproject:
            return set()
        try:
            data = tomllib.loads(pyproject)
        except tomllib.TOMLDecodeError:
            return set()
        names: set[str] = set()
        project = data.get("project", {})
        for item in project.get("dependencies", []):
            if isinstance(item, str):
                names.add(_dependency_name(item))
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group in optional.values():
                if isinstance(group, list):
                    for item in group:
                        if isinstance(item, str):
                            names.add(_dependency_name(item))
        tool = data.get("tool", {})
        poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
        dependencies = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
        if isinstance(dependencies, dict):
            for item in dependencies:
                if str(item).lower() != "python":
                    names.add(str(item).lower())
        return {item for item in names if item}

    def _python_frameworks(self, dependencies: set[str]) -> list[str]:
        mapping = {
            "fastapi": "fastapi",
            "flask": "flask",
            "django": "django",
            "streamlit": "streamlit",
            "gradio": "gradio",
        }
        return [label for key, label in mapping.items() if key in dependencies]

    def _looks_like_pytest(
        self,
        lower_files: dict[str, str],
        dependencies: set[str],
        files: list[str],
    ) -> bool:
        return (
            "pytest" in dependencies
            or "pytest.ini" in lower_files
            or any(item.startswith("tests/") and item.endswith(".py") for item in files)
        )

    def _looks_like_ruff(self, lower_files: dict[str, str], dependencies: set[str]) -> bool:
        return "ruff" in dependencies or self._any_file(
            lower_files,
            {".ruff.toml", "ruff.toml"},
        )

    def _parse_package_json(self, package_json: str) -> dict[str, object]:
        if not package_json:
            return {"scripts": {}, "dependencies": set(), "entrypoints": []}
        try:
            data = json.loads(package_json)
        except json.JSONDecodeError:
            return {"scripts": {}, "dependencies": set(), "entrypoints": []}
        scripts = data.get("scripts", {})
        merged_dependencies: set[str] = set()
        for bucket in ["dependencies", "devDependencies", "peerDependencies"]:
            entries = data.get(bucket, {})
            if isinstance(entries, dict):
                merged_dependencies.update(str(item).lower() for item in entries.keys())
        entrypoints: list[str] = []
        for key in ["main", "module"]:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                entrypoints.append(value.strip().replace("\\", "/"))
        bin_value = data.get("bin")
        if isinstance(bin_value, str) and bin_value.strip():
            entrypoints.append(bin_value.strip().replace("\\", "/"))
        elif isinstance(bin_value, dict):
            for value in bin_value.values():
                if isinstance(value, str) and value.strip():
                    entrypoints.append(value.strip().replace("\\", "/"))
        return {
            "scripts": {
                str(key): str(value)
                for key, value in scripts.items()
                if str(key).strip() and isinstance(value, str)
            }
            if isinstance(scripts, dict)
            else {},
            "dependencies": merged_dependencies,
            "entrypoints": _ordered_unique(entrypoints),
        }

    def _node_frameworks(self, dependencies: set[str]) -> list[str]:
        mapping = {
            "next": "nextjs",
            "react": "react",
            "vite": "vite",
            "express": "express",
            "astro": "astro",
            "nuxt": "nuxt",
            "@nestjs/core": "nestjs",
        }
        return [label for key, label in mapping.items() if key in dependencies]

    def _node_entrypoints(
        self,
        lower_files: dict[str, str],
        package_payload: dict[str, object],
    ) -> list[str]:
        entrypoints = [
            str(item)
            for item in package_payload.get("entrypoints", [])
            if str(item).strip()
        ]
        for candidate in [
            "src/index.ts",
            "src/index.js",
            "src/main.ts",
            "src/main.js",
            "src/app.ts",
            "src/app.js",
            "server.ts",
            "server.js",
            "index.ts",
            "index.js",
        ]:
            if candidate in lower_files:
                entrypoints.append(lower_files[candidate])
        return _ordered_unique(entrypoints)

    def _any_file(
        self,
        lower_files: dict[str, str],
        candidates: set[str],
    ) -> bool:
        return any(candidate in lower_files for candidate in candidates)


def _repo_map_symbol_records(
    *, path: str, content: str
) -> list[WorkspaceSymbolRecord]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return _extract_python_symbols(path=path, content=content)
    if suffix in _SCRIPT_SUFFIXES:
        return _extract_script_symbols(path=path, content=content)
    return []


def _repo_map_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix in _SCRIPT_SUFFIXES:
        return "javascript"
    return ""


def _repo_map_is_test_path(path: str) -> bool:
    lowered = path.lower()
    stem = Path(lowered).stem
    return (
        "/tests/" in f"/{lowered}/"
        or lowered.startswith("tests/")
        or stem.startswith("test_")
        or stem.endswith("_test")
        or ".test." in lowered
        or ".spec." in lowered
    )


def _repo_map_goal_tokens(goal: str | None, *, max_tokens: int) -> list[str]:
    lowered = str(goal or "").lower()
    tokens = re.findall(r"[a-z0-9_]{3,}", lowered)
    filtered = [
        token
        for token in tokens
        if token not in _GOAL_TOKEN_STOPWORDS and not token.isdigit()
    ]
    return _ordered_unique(filtered)[:max_tokens]


def _repo_map_goal_score(
    *,
    path: str,
    content: str,
    tokens: list[str],
    symbols: list[WorkspaceSymbolRecord],
) -> int:
    lowered_path = path.lower()
    basename = Path(path).stem.lower()
    symbol_names = " ".join(
        f"{record.name} {record.qualname}" for record in symbols[:32]
    ).lower()
    content_lower = content.lower()
    score = 0
    for token in tokens:
        if token in basename:
            score += 8
        elif token in lowered_path:
            score += 4
        if token in symbol_names:
            score += 10
        if token in content_lower:
            score += 2
    if _repo_map_is_test_path(path):
        score -= 8
    return score


def _repo_map_guess_test_files(path: str, files: list[str]) -> list[str]:
    if _repo_map_is_test_path(path):
        return [path]
    target_parts = _repo_map_name_tokens(Path(path).stem)
    parent_name = Path(path).parent.name.lower()
    ranked: list[tuple[int, str]] = []
    for candidate in files:
        if not _repo_map_is_test_path(candidate):
            continue
        candidate_stem = Path(candidate).stem.lower()
        normalized_stem = re.sub(r"^(test_)", "", candidate_stem)
        normalized_stem = re.sub(r"(_test|\\.test|\\.spec)$", "", normalized_stem)
        candidate_tokens = _repo_map_name_tokens(normalized_stem)
        score = 0
        if normalized_stem == Path(path).stem.lower():
            score += 8
        overlap = len(set(target_parts) & set(candidate_tokens))
        score += overlap * 4
        if parent_name and parent_name in candidate.lower():
            score += 1
        if score > 0:
            ranked.append((score, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in ranked[:6]]


def _repo_map_name_tokens(value: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [token for token in re.split(r"[^A-Za-z0-9]+", normalized.lower()) if token]


def _extract_python_import_paths(
    *,
    source_path: str,
    content: str,
    available_paths: set[str],
) -> set[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()
    resolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = str(alias.name or "").strip()
                if not module:
                    continue
                resolved.update(
                    _resolve_python_module_candidates(
                        source_path=source_path,
                        module=module,
                        level=0,
                        available_paths=available_paths,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "").strip()
            resolved.update(
                _resolve_python_module_candidates(
                    source_path=source_path,
                    module=module,
                    level=int(getattr(node, "level", 0) or 0),
                    available_paths=available_paths,
                )
            )
            for alias in node.names:
                name = str(alias.name or "").strip()
                if not name or name == "*":
                    continue
                candidate_module = ".".join(
                    part for part in [module, name] if part
                )
                resolved.update(
                    _resolve_python_module_candidates(
                        source_path=source_path,
                        module=candidate_module,
                        level=int(getattr(node, "level", 0) or 0),
                        available_paths=available_paths,
                    )
                )
    resolved.discard(source_path)
    return resolved


def _resolve_python_module_candidates(
    *,
    source_path: str,
    module: str,
    level: int,
    available_paths: set[str],
) -> set[str]:
    source = PurePosixPath(source_path)
    source_parts = list(source.parts[:-1])
    if source.name != "__init__.py" and source_parts:
        package_parts = source_parts
    else:
        package_parts = list(source.parts[:-1])
    if level > 0:
        trim = max(level - 1, 0)
        if trim:
            package_parts = package_parts[:-trim] if trim <= len(package_parts) else []
    module_parts = [part for part in module.split(".") if part]
    combined = [*package_parts, *module_parts] if level > 0 else module_parts
    candidates: set[str] = set()
    for parts in [combined]:
        if not parts:
            continue
        module_path = "/".join(parts)
        for candidate in (f"{module_path}.py", f"{module_path}/__init__.py"):
            if candidate in available_paths:
                candidates.add(candidate)
    return candidates


def _extract_script_import_paths(
    *,
    source_path: str,
    content: str,
    available_paths: set[str],
) -> set[str]:
    modules: set[str] = set()
    modules.update(
        match.group("module")
        for match in _SCRIPT_IMPORT_FROM_RE.finditer(content)
        if match.group("module")
    )
    modules.update(
        match.group("module")
        for match in _SCRIPT_REQUIRE_RE.finditer(content)
        if match.group("module")
    )
    resolved: set[str] = set()
    for module in modules:
        resolved.update(
            _resolve_script_import_candidates(
                source_path=source_path,
                module=module,
                available_paths=available_paths,
            )
        )
    resolved.discard(source_path)
    return resolved


def _resolve_script_import_candidates(
    *,
    source_path: str,
    module: str,
    available_paths: set[str],
) -> set[str]:
    token = str(module or "").strip()
    if not token:
        return set()
    source_dir = PurePosixPath(source_path).parent
    roots: list[str] = []
    if token.startswith("."):
        roots.append(_normalize_posix_path(f"{source_dir}/{token}"))
    else:
        roots.append(_normalize_posix_path(token.lstrip("/")))
    resolved: set[str] = set()
    for root in roots:
        if not root:
            continue
        variants = [root]
        if Path(root).suffix.lower() not in _SCRIPT_SUFFIXES:
            variants.extend(f"{root}{suffix}" for suffix in sorted(_SCRIPT_SUFFIXES))
            variants.extend(
                f"{root}/index{suffix}" for suffix in sorted(_SCRIPT_SUFFIXES)
            )
        for candidate in variants:
            normalized = candidate.replace("\\", "/").strip("/")
            if normalized in available_paths:
                resolved.add(normalized)
    return resolved


def _normalize_posix_path(raw: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ordered_unique(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _dependency_name(spec: str) -> str:
    token = re.split(r"[<>=!~\[\];\s]", spec.strip(), maxsplit=1)[0]
    return token.strip().lower()


def _node_script_command(package_manager: str, script_name: str) -> str:
    if package_manager in {"npm", "pnpm", "yarn", "bun"} and script_name == "test":
        return f"{package_manager} test"
    return f"{package_manager} run {script_name}"


def _symbol_reference_pattern(symbol: str) -> re.Pattern[str]:
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", symbol):
        return re.compile(rf"\b{re.escape(symbol)}\b")
    return re.compile(re.escape(symbol))


def _extract_python_symbols(path: str, content: str) -> list[WorkspaceSymbolRecord]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    line_starts = _line_start_offsets(content)
    records: list[WorkspaceSymbolRecord] = []

    def walk(
        body: list[ast.stmt],
        qualifiers: list[str],
        parent_is_class: bool,
    ) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                records.append(
                    _python_symbol_record(
                        path=path,
                        content=content,
                        line_starts=line_starts,
                        node=node,
                        name=node.name,
                        qualname=".".join([*qualifiers, node.name]),
                        kind="class",
                    )
                )
                walk(node.body, [*qualifiers, node.name], True)
                continue
            if isinstance(node, ast.FunctionDef):
                kind = "method" if parent_is_class else "function"
                records.append(
                    _python_symbol_record(
                        path=path,
                        content=content,
                        line_starts=line_starts,
                        node=node,
                        name=node.name,
                        qualname=".".join([*qualifiers, node.name]),
                        kind=kind,
                    )
                )
                walk(node.body, [*qualifiers, node.name], False)
                continue
            if isinstance(node, ast.AsyncFunctionDef):
                kind = "async_method" if parent_is_class else "async_function"
                records.append(
                    _python_symbol_record(
                        path=path,
                        content=content,
                        line_starts=line_starts,
                        node=node,
                        name=node.name,
                        qualname=".".join([*qualifiers, node.name]),
                        kind=kind,
                    )
                )
                walk(node.body, [*qualifiers, node.name], False)

    walk(tree.body, [], False)
    return records


def _python_symbol_record(
    *,
    path: str,
    content: str,
    line_starts: list[int],
    node: ast.AST,
    name: str,
    qualname: str,
    kind: str,
) -> WorkspaceSymbolRecord:
    start_line = int(getattr(node, "lineno", 1) or 1)
    end_line = int(getattr(node, "end_lineno", start_line) or start_line)
    start_col = int(getattr(node, "col_offset", 0) or 0)
    end_col = int(getattr(node, "end_col_offset", 0) or 0)
    start_index = line_starts[start_line - 1] + start_col
    end_index = (
        line_starts[end_line - 1] + end_col
        if end_col
        else _line_end_index(content, line_starts, end_line)
    )
    signature = _line_text(content, line_starts, start_line).strip()
    return WorkspaceSymbolRecord(
        path=path,
        language="python",
        name=name,
        qualname=qualname,
        kind=kind,
        signature=signature,
        start_line=start_line,
        end_line=end_line,
        start_column=start_col + 1,
        end_column=max(start_col + 1, end_col + 1),
        content=content[start_index:end_index],
        start_index=start_index,
        end_index=end_index,
    )


def _extract_script_symbols(path: str, content: str) -> list[WorkspaceSymbolRecord]:
    line_starts = _line_start_offsets(content)
    records: list[WorkspaceSymbolRecord] = []
    lines = content.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        for pattern, kind in _SCRIPT_SYMBOL_PATTERNS:
            match = pattern.match(line)
            if match is None:
                continue
            name = match.group("name")
            line_start = line_starts[line_number - 1]
            start_index = line_start + match.start()
            end_index = _script_symbol_end_index(
                content=content,
                declaration_start=start_index,
                search_start=line_start + match.end(),
                kind=kind,
            )
            end_line = _index_to_line(line_starts, max(start_index, end_index - 1))
            end_col = end_index - line_starts[end_line - 1] + 1
            records.append(
                WorkspaceSymbolRecord(
                    path=path,
                    language="typescript"
                    if path.lower().endswith((".ts", ".tsx"))
                    else "javascript",
                    name=name,
                    qualname=name,
                    kind=kind,
                    signature=line.strip(),
                    start_line=line_number,
                    end_line=end_line,
                    start_column=match.start() + 1,
                    end_column=max(match.start() + 1, end_col),
                    content=content[start_index:end_index],
                    start_index=start_index,
                    end_index=end_index,
                )
            )
            break
    return records


def _script_symbol_end_index(
    *,
    content: str,
    declaration_start: int,
    search_start: int,
    kind: str,
) -> int:
    arrow_index = content.find("=>", search_start)
    open_brace = content.find("{", search_start)
    semicolon = content.find(";", search_start)
    newline = content.find("\n", search_start)
    if kind == "arrow_function" and arrow_index >= 0:
        open_brace = content.find("{", arrow_index)
        semicolon = content.find(";", arrow_index)
    if open_brace >= 0 and (semicolon < 0 or open_brace < semicolon):
        end_index = _scan_braced_block_end(content, open_brace)
        if end_index < len(content) and content[end_index] == ";":
            end_index += 1
        return end_index
    if semicolon >= 0:
        return semicolon + 1
    if newline >= 0:
        return newline
    return len(content)


def _scan_braced_block_end(content: str, open_brace: int) -> int:
    depth = 0
    in_string = False
    string_quote = ""
    escape = False
    in_line_comment = False
    in_block_comment = False
    index = open_brace
    while index < len(content):
        char = content[index]
        next_char = content[index + 1] if index + 1 < len(content) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == string_quote:
                in_string = False
            index += 1
            continue
        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char in {'"', "'", "`"}:
            in_string = True
            string_quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(content)


def _line_start_offsets(content: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(content):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def _index_to_line(line_starts: list[int], index: int) -> int:
    return bisect_right(line_starts, index) or 1


def _line_end_index(content: str, line_starts: list[int], line_number: int) -> int:
    if line_number >= len(line_starts):
        return len(content)
    candidate = content.find("\n", line_starts[line_number - 1])
    return len(content) if candidate < 0 else candidate


def _line_text(content: str, line_starts: list[int], line_number: int) -> str:
    start = line_starts[line_number - 1]
    end = _line_end_index(content, line_starts, line_number)
    return content[start:end]
