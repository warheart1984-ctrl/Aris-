"""Minimal local runner helpers for repo-aware evaluation."""

from __future__ import annotations

from pathlib import Path


class SandboxError(RuntimeError):
    """Raised when evaluator sandbox assumptions are not met."""


def resolve_repo_path(repo: str | None) -> Path:
    """Resolve and validate a repo path for repo_patch evaluation."""

    repo_text = str(repo or "").strip()
    if not repo_text:
        raise SandboxError("payload.repo is required for repo_patch mode.")
    target = Path(repo_text).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        raise SandboxError(f"Repo path does not exist: {target}")
    return target
