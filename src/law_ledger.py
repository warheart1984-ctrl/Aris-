from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


class LawLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        require_success: bool = False,
    ) -> dict[str, Any]:
        entry = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_type": str(event_type or "unknown").strip() or "unknown",
            "payload": payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            if require_success:
                raise RuntimeError(f"Law ledger write failed: {exc}") from exc
            return {
                "recorded": False,
                "path": str(self.path),
                "error": str(exc),
                "entry": entry,
            }
        return {
            "recorded": True,
            "path": str(self.path),
            "entry": entry,
        }
