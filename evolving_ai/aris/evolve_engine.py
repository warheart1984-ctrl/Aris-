from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class EvolveEngineTraceStore:
    """Classified experience store for governed ARIS ingestion traces."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.entries_path = self.root / "classified-traces.jsonl"
        if not self.entries_path.exists():
            self.entries_path.write_text("", encoding="utf-8")

    def _clean_packet(self, packet: dict[str, Any]) -> dict[str, Any]:
        return {
            str(key): value
            for key, value in dict(packet or {}).items()
            if key not in {"output_text", "output_excerpt", "raw_text", "raw_log"}
        }

    def record(
        self,
        *,
        trace_id: str,
        packet: dict[str, Any],
        candidate: dict[str, Any],
        evaluation: dict[str, Any],
        classification: str,
        hall: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        entry = {
            "trace_id": str(trace_id or "").strip(),
            "recorded_at": _utc_now(),
            "source": str(source or "").strip() or "codex_log",
            "packet": self._clean_packet(packet),
            "candidate": dict(candidate or {}),
            "evaluation": dict(evaluation or {}),
            "classification": str(classification or "").strip() or "UNKNOWN",
            "hall": dict(hall or {}),
            "immutable_trace": True,
        }
        with self.entries_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        return entry

    def list_entries(self, *, limit: int = 25) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in self.entries_path.read_text(encoding="utf-8").splitlines():
            record = line.strip()
            if not record:
                continue
            try:
                entry = json.loads(record)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        bounded = max(1, min(int(limit), 200))
        return list(reversed(entries[-bounded:]))

    def count(self) -> int:
        return sum(1 for _ in self.entries_path.read_text(encoding="utf-8").splitlines() if _.strip())

    def status_payload(self) -> dict[str, Any]:
        counts = Counter(
            str(entry.get("classification") or "").strip() or "UNKNOWN"
            for entry in self.list_entries(limit=500)
        )
        return {
            "active": True,
            "root": str(self.root),
            "entries_path": str(self.entries_path),
            "count": self.count(),
            "classifications": dict(sorted(counts.items())),
            "stores_raw_logs_as_truth": False,
        }
