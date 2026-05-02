from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any


TERMINAL_QUEUE_STATUSES = {"done", "error", "rejected"}
ACTIVE_QUEUE_STATUSES = {"pending", "running", "blocked"}
SELF_IMPROVE_QUEUE = "SELF_IMPROVE"
OPERATOR_QUEUE = "OPERATOR"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def seed_self_improve_prompts() -> tuple[dict[str, Any], ...]:
    return (
        {
            "title": "Refactor task selection function for clarity",
            "prompt": "Refactor the active task selection logic for clarity, without weakening governance, approvals, or observability.",
            "priority": 1,
        },
        {
            "title": "Add retry for transient runtime errors",
            "prompt": "Improve transient runtime retry handling while keeping failures visible and bounded under law.",
            "priority": 1,
        },
        {
            "title": "Improve diff summarization",
            "prompt": "Tighten diff summarization so operator review is faster without hiding risk or approval-sensitive changes.",
            "priority": 1,
        },
    )


class OperatorQueueStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            if self.path.exists():
                return
            self._write([])

    def _read(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            return _dict_list(payload)

    def _write(self, items: list[dict[str, Any]]) -> None:
        serialized = json.dumps(items, indent=2, ensure_ascii=True)
        self.path.write_text(serialized + "\n", encoding="utf-8")

    def list_items(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        items = self._read()
        if session_id is None:
            return items
        return [
            dict(item)
            for item in items
            if str(item.get("session_id", "")).strip() == str(session_id).strip()
        ]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        item_id = str(item_id).strip()
        for item in self._read():
            if str(item.get("id", "")).strip() == item_id:
                return dict(item)
        return None

    def enqueue(
        self,
        *,
        session_id: str,
        title: str,
        prompt: str,
        queue_name: str,
        priority: int = 1,
        depends_on: list[str] | None = None,
        requires_approval: bool = False,
        source: str = "operator",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        item = {
            "id": uuid.uuid4().hex,
            "session_id": str(session_id).strip(),
            "title": str(title).strip() or "Queued task",
            "prompt": str(prompt).strip(),
            "queue_name": str(queue_name).strip().upper() or OPERATOR_QUEUE,
            "priority": max(1, int(priority)),
            "depends_on": [str(entry).strip() for entry in list(depends_on or []) if str(entry).strip()],
            "status": "pending",
            "requires_approval": bool(requires_approval),
            "approved": False,
            "rejected": False,
            "source": str(source).strip() or "operator",
            "metadata": dict(metadata or {}),
            "linked_run_id": "",
            "approval_id": "",
            "review_gate": "",
            "latest_update": "Queued for governed execution.",
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "completed_at": "",
            "outcome_recorded": False,
            "notes": "",
        }
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return dict(item)

    def update_item(self, item_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "title",
            "prompt",
            "queue_name",
            "priority",
            "depends_on",
            "status",
            "requires_approval",
            "approved",
            "rejected",
            "metadata",
            "linked_run_id",
            "approval_id",
            "review_gate",
            "latest_update",
            "started_at",
            "completed_at",
            "outcome_recorded",
            "notes",
        }
        updated: dict[str, Any] | None = None
        with self._lock:
            items = self._read()
            for index, item in enumerate(items):
                if str(item.get("id", "")).strip() != str(item_id).strip():
                    continue
                merged = dict(item)
                for key, value in fields.items():
                    if key not in allowed:
                        continue
                    if key == "depends_on":
                        merged[key] = [str(entry).strip() for entry in list(value or []) if str(entry).strip()]
                    elif key == "metadata":
                        merged[key] = dict(value or {})
                    elif key == "priority":
                        merged[key] = max(1, int(value))
                    else:
                        merged[key] = value
                merged["updated_at"] = _utc_now()
                items[index] = merged
                updated = dict(merged)
                break
        if updated is None:
            return None
        with self._lock:
            self._write(items)
        return updated

    def ensure_self_improve_seed(self, *, session_id: str) -> list[dict[str, Any]]:
        existing = [
            item
            for item in self.list_items(session_id=session_id)
            if str(item.get("queue_name", "")).strip().upper() == SELF_IMPROVE_QUEUE
        ]
        if existing:
            return existing
        seeded: list[dict[str, Any]] = []
        for prompt in seed_self_improve_prompts():
            seeded.append(
                self.enqueue(
                    session_id=session_id,
                    title=str(prompt.get("title", "")).strip(),
                    prompt=str(prompt.get("prompt", "")).strip(),
                    queue_name=SELF_IMPROVE_QUEUE,
                    priority=int(prompt.get("priority", 1) or 1),
                    requires_approval=True,
                    source="self_improve_seed",
                )
            )
        return seeded
