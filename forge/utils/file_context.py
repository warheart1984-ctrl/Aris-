"""Preflight helpers that keep Forge context task-local and code-shaped."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from forge.schemas import ContractorContext, ContractorFileContext


MAX_FILES = 20
MAX_FILE_BYTES = 200_000
ALLOWED_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".py", ".json", ".md", ".css", ".html"}
BLOCKED_CONTEXT_KEYS = {
    "memory",
    "memories",
    "prompt",
    "prompts",
    "raw_prompt",
    "system_prompt",
    "transcript",
    "transcripts",
    "logs",
    "log_dump",
    "secret",
    "secrets",
}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)


class ForgePreflightError(ValueError):
    """Raised when inbound context violates the Forge boundary."""


def _truncate_utf8_text(text: str, max_bytes: int) -> tuple[str, bool]:
    payload = str(text or "").encode("utf-8", errors="ignore")
    if len(payload) <= max_bytes:
        return str(text or ""), False
    truncated = payload[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def _is_allowed_extension(path: str) -> bool:
    lowered = str(path or "").lower()
    return any(lowered.endswith(extension) for extension in ALLOWED_EXTENSIONS)


def _contains_secret_like_text(value: str) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _sanitize_constraint_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            lowered = key.lower()
            if lowered in BLOCKED_CONTEXT_KEYS:
                raise ForgePreflightError(
                    f"Blocked constraint keys are not allowed in Forge requests: {key}."
                )
            sanitized[key] = _sanitize_constraint_value(raw_value)
        if _contains_secret_like_text(str(sanitized)):
            raise ForgePreflightError("Forge preflight rejected secret-like data in constraints.")
        return sanitized
    if isinstance(value, list):
        sanitized_list = [_sanitize_constraint_value(item) for item in value]
        if _contains_secret_like_text(str(sanitized_list)):
            raise ForgePreflightError("Forge preflight rejected secret-like data in constraints.")
        return sanitized_list
    if value is None:
        return None
    scalar = str(value) if not isinstance(value, (bool, int, float, str)) else value
    if _contains_secret_like_text(str(scalar)):
        raise ForgePreflightError("Forge preflight rejected secret-like data in constraints.")
    return scalar


def sanitize_context(context: Mapping[str, Any] | None = None) -> ContractorContext:
    """Reduce raw context to the bounded Forge contractor contract."""

    payload = dict(context or {})
    blocked = sorted(
        key for key in payload if str(key).strip().lower() in BLOCKED_CONTEXT_KEYS
    )
    if blocked:
        raise ForgePreflightError(
            f"Blocked context keys are not allowed in Forge requests: {', '.join(blocked)}."
        )

    goal = " ".join(str(payload.get("goal") or "").split()).strip()
    if not goal:
        raise ForgePreflightError("Forge goal is required.")

    raw_files = payload.get("files")
    raw_constraints = payload.get("constraints")

    safe_files: list[ContractorFileContext] = []
    if isinstance(raw_files, list):
        for raw in raw_files[:MAX_FILES]:
            item = dict(raw or {})
            path = str(item.get("path") or "").strip().replace("\\", "/")
            content = str(item.get("content") or "")
            if not path or not _is_allowed_extension(path):
                continue
            if _contains_secret_like_text(content):
                raise ForgePreflightError(
                    f"Forge preflight rejected secret-like content in `{path}`."
                )
            safe_content, truncated = _truncate_utf8_text(content, MAX_FILE_BYTES)
            safe_files.append(
                ContractorFileContext(
                    path=path,
                    content=safe_content,
                    truncated=bool(item.get("truncated") or truncated),
                )
            )

    if raw_constraints is None:
        safe_constraints: dict[str, Any] = {}
    elif isinstance(raw_constraints, Mapping):
        safe_constraints = {
            str(key).strip(): _sanitize_constraint_value(value)
            for key, value in raw_constraints.items()
            if str(key).strip()
        }
    else:
        raise ForgePreflightError("Forge constraints must be an object.")

    return ContractorContext(
        files=safe_files,
        goal=goal,
        constraints=safe_constraints,
        target_scope=" ".join(str(payload.get("target_scope") or "").split()).strip(),
        focus_files=[
            str(item).strip().replace("\\", "/")
            for item in list(payload.get("focus_files") or [])
            if str(item).strip()
        ],
        excluded_files=[
            str(item).strip().replace("\\", "/")
            for item in list(payload.get("excluded_files") or [])
            if str(item).strip()
        ],
        change_intent=" ".join(str(payload.get("change_intent") or "").split()).strip(),
        max_change_budget=" ".join(str(payload.get("max_change_budget") or "").split()).strip(),
        validation_target=" ".join(str(payload.get("validation_target") or "").split()).strip(),
        operation_mode=" ".join(str(payload.get("operation_mode") or "").split()).strip(),
        max_files_to_inspect=(
            max(1, int(payload.get("max_files_to_inspect")))
            if payload.get("max_files_to_inspect") not in ("", None)
            else None
        ),
        max_directory_depth=(
            max(0, int(payload.get("max_directory_depth")))
            if payload.get("max_directory_depth") not in ("", None)
            else None
        ),
        file_path_allowlist=[
            str(item).strip().replace("\\", "/")
            for item in list(payload.get("file_path_allowlist") or [])
            if str(item).strip()
        ],
        explicit_denylist=[
            str(item).strip().replace("\\", "/")
            for item in list(payload.get("explicit_denylist") or [])
            if str(item).strip()
        ],
        no_execution_without_handoff=bool(payload.get("no_execution_without_handoff", True)),
    )
