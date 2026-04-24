from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class GovernanceHall:
    """Separate persistent hall store used by one ARIS disposition class."""

    def __init__(
        self,
        *,
        root: Path,
        hall_id: str,
        entry_prefix: str,
        track_reentry: bool,
        reentry_requirements: list[str] | None = None,
    ) -> None:
        self.root = root
        self.hall_id = hall_id
        self.entry_prefix = entry_prefix
        self.track_reentry = track_reentry
        self.reentry_requirements = list(reentry_requirements or [])
        self.root.mkdir(parents=True, exist_ok=True)
        self.entries_path = self.root / f"{hall_id}.jsonl"
        self.index_path = self.root / f"{hall_id}-index.json"
        self._entries: list[dict[str, Any]] = []
        self._fingerprints: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        self._entries = []
        self._fingerprints = {}
        if self.entries_path.exists():
            for line in self.entries_path.read_text(encoding="utf-8").splitlines():
                record = line.strip()
                if not record:
                    continue
                try:
                    entry = json.loads(record)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                self._entries.append(entry)
                if not self.track_reentry:
                    continue
                fingerprint = str(entry.get("fingerprint", "")).strip()
                if fingerprint:
                    self._fingerprints[fingerprint] = str(entry.get("id", "")).strip()
        if self.track_reentry and self.index_path.exists():
            try:
                payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                for fingerprint, entry_id in payload.items():
                    if str(fingerprint).strip() and str(entry_id).strip():
                        self._fingerprints[str(fingerprint)] = str(entry_id)

    def _persist_index(self) -> None:
        if not self.track_reentry:
            return
        self.index_path.write_text(
            json.dumps(self._fingerprints, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def fingerprint_for(
        self,
        *,
        action_type: str,
        purpose: str,
        target: str,
        patch: str = "",
        command: list[str] | None = None,
        code: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "action_type": action_type,
            "purpose": " ".join(str(purpose or "").split()).strip(),
            "target": str(target or "").strip(),
            "patch": str(patch or ""),
            "command": [str(item) for item in list(command or [])],
            "code": str(code or ""),
            "metadata": dict(metadata or {}),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def find_reentry_blocker(self, fingerprint: str) -> dict[str, Any] | None:
        if not self.track_reentry:
            return None
        entry_id = self._fingerprints.get(str(fingerprint or "").strip())
        if not entry_id:
            return None
        for entry in reversed(self._entries):
            if str(entry.get("id", "")).strip() == entry_id:
                return dict(entry)
        return None

    def find_latest_by_lineage(self, lineage_key: str) -> dict[str, Any] | None:
        normalized = str(lineage_key or "").strip()
        if not normalized:
            return None
        for entry in reversed(self._entries):
            if str(entry.get("lineage_key", "")).strip() == normalized:
                return dict(entry)
        return None

    def record(
        self,
        *,
        fingerprint: str = "",
        lineage_key: str = "",
        action: dict[str, Any],
        reason: str,
        law_results: list[dict[str, Any]],
        guardrails: list[dict[str, Any]],
        operator_decision: str,
        forge_eval: list[dict[str, Any]],
        source: str,
        notes: str = "",
        containment_status: str = "contained",
        metadata: dict[str, Any] | None = None,
        re_evaluation_of: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": f"{self.entry_prefix}_{uuid.uuid4().hex[:12]}",
            "hall": self.hall_id,
            "created_at": _utc_now(),
            "fingerprint": fingerprint,
            "lineage_key": str(lineage_key or "").strip(),
            "source": source,
            "action": dict(action),
            "reason": reason,
            "law_results": [dict(item) for item in law_results],
            "guardrails": [dict(item) for item in guardrails],
            "operator_decision": operator_decision,
            "forge_eval": [dict(item) for item in forge_eval],
            "containment_status": containment_status,
            "notes": notes,
            "metadata": dict(metadata or {}),
            "immutable_hall": True,
            "hall_transition_rule": "explicit_re_evaluation_only",
        }
        if re_evaluation_of is not None:
            entry["re_evaluation_of"] = dict(re_evaluation_of)
        if self.reentry_requirements:
            entry["reentry_requirements"] = list(self.reentry_requirements)
        with self.entries_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        self._entries.append(entry)
        if self.track_reentry and fingerprint:
            self._fingerprints[fingerprint] = entry["id"]
            self._persist_index()
        return entry

    def list_entries(self, *, limit: int = 25) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 200))
        return [dict(entry) for entry in reversed(self._entries[-bounded:])]

    def count(self) -> int:
        return len(self._entries)
