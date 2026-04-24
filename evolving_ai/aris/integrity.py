from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ProtectedComponentIntegrity:
    """Hashes protected ARIS components and detects tamper drift."""

    def __init__(self, *, manifest_path: Path, protected_paths: list[Path]) -> None:
        self.manifest_path = manifest_path
        self.protected_paths = [path.resolve() for path in protected_paths]
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _should_track_file(self, path: Path) -> bool:
        parts = {part.lower() for part in path.parts}
        suffix = path.suffix.lower()
        if "__pycache__" in parts:
            return False
        if suffix in {".pyc", ".pyo", ".pyd"}:
            return False
        if path.name.lower() in {".ds_store"}:
            return False
        return True

    def _build_manifest(self) -> dict[str, Any]:
        missing: list[str] = []
        files: dict[str, str] = {}
        for protected_path in self.protected_paths:
            if not protected_path.exists():
                missing.append(str(protected_path))
                continue
            if protected_path.is_file():
                files[str(protected_path)] = self._hash_file(protected_path)
                continue
            if protected_path.is_dir():
                for file_path in sorted(protected_path.rglob("*")):
                    if file_path.is_file() and self._should_track_file(file_path):
                        files[str(file_path)] = self._hash_file(file_path)
        return {
            "generated_at": _utc_now(),
            "files": files,
            "missing": missing,
        }

    def verify_or_initialize(self, *, reseal: bool = False) -> dict[str, Any]:
        current = self._build_manifest()
        if reseal or not self.manifest_path.exists():
            self.manifest_path.write_text(
                json.dumps(current, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return {
                "ok": True,
                "initialized": True,
                "resealed": reseal,
                "manifest_path": str(self.manifest_path),
                "protected_count": len(current["files"]),
                "missing": list(current["missing"]),
                "changed": [],
                "removed": [],
            }

        try:
            baseline = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            baseline = {}
        baseline_files = (
            dict(baseline.get("files", {})) if isinstance(baseline, dict) else {}
        )
        current_files = dict(current.get("files", {}))
        changed = sorted(
            path
            for path, file_hash in current_files.items()
            if baseline_files.get(path) != file_hash
        )
        removed = sorted(path for path in baseline_files if path not in current_files)
        ok = not changed and not removed and not current["missing"]
        return {
            "ok": ok,
            "initialized": False,
            "resealed": False,
            "manifest_path": str(self.manifest_path),
            "protected_count": len(current_files),
            "missing": list(current["missing"]),
            "changed": changed,
            "removed": removed,
        }
