from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class ArisKillSwitch:
    """System-wide ARIS halt controller with soft, hard, and lockdown modes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "kill-switch.json"
        self.events_path = self.root / "kill-switch-events.jsonl"
        self._state = {
            "mode": "nominal",
            "active": False,
            "reason": "",
            "summary": "ARIS is nominal.",
            "triggered_at": "",
            "actor": "system",
            "requires_manual_reset": False,
            "startup_blocker": False,
            "diagnostics": {},
        }
        self._events: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                self._state.update(payload)
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    self._events.append(event)

    def _persist(self) -> None:
        self.state_path.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _record_event(
        self, *, mode: str, reason: str, actor: str, diagnostics: dict[str, Any]
    ) -> None:
        event = {
            "triggered_at": _utc_now(),
            "mode": mode,
            "reason": reason,
            "actor": actor,
            "diagnostics": dict(diagnostics),
        }
        self._events.append(event)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")

    def snapshot(self, *, limit_events: int = 12) -> dict[str, Any]:
        payload = dict(self._state)
        payload["recent_events"] = [
            dict(item) for item in self._events[-max(0, int(limit_events)) :]
        ][::-1]
        return payload

    def activate(
        self,
        *,
        mode: str,
        reason: str,
        actor: str,
        summary: str,
        diagnostics: dict[str, Any] | None = None,
        startup_blocker: bool = False,
    ) -> dict[str, Any]:
        self._state = {
            "mode": mode,
            "active": mode != "nominal",
            "reason": reason,
            "summary": summary,
            "triggered_at": _utc_now(),
            "actor": actor,
            "requires_manual_reset": mode != "nominal",
            "startup_blocker": bool(startup_blocker),
            "diagnostics": dict(diagnostics or {}),
        }
        self._persist()
        self._record_event(
            mode=mode,
            reason=reason,
            actor=actor,
            diagnostics=dict(diagnostics or {}),
        )
        return self.snapshot()

    def soft_kill(
        self, *, reason: str, actor: str, diagnostics: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.activate(
            mode="soft_kill",
            reason=reason,
            actor=actor,
            summary=(
                "Soft kill active. New ARIS actions are blocked, while diagnostics and "
                "Hall of Discard access remain available."
            ),
            diagnostics=diagnostics,
        )

    def hard_kill(
        self, *, reason: str, actor: str, diagnostics: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.activate(
            mode="hard_kill",
            reason=reason,
            actor=actor,
            summary=(
                "Hard kill active. Execution authority, approvals, and mutation application "
                "are halted."
            ),
            diagnostics=diagnostics,
        )

    def lockdown(
        self,
        *,
        reason: str,
        actor: str,
        diagnostics: dict[str, Any] | None = None,
        startup_blocker: bool = False,
    ) -> dict[str, Any]:
        return self.activate(
            mode="lockdown",
            reason=reason,
            actor=actor,
            summary=(
                "Lockdown active. Protected-component integrity failed or a tamper condition "
                "was detected, so ARIS is fail-closed."
            ),
            diagnostics=diagnostics,
            startup_blocker=startup_blocker,
        )

    def reset(
        self,
        *,
        actor: str,
        reason: str,
        integrity_verified: bool,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not integrity_verified:
            raise RuntimeError("ARIS reset refused: protected-component integrity is not verified.")
        self._state = {
            "mode": "nominal",
            "active": False,
            "reason": reason,
            "summary": "ARIS returned to nominal operation after explicit human reset.",
            "triggered_at": _utc_now(),
            "actor": actor,
            "requires_manual_reset": False,
            "startup_blocker": False,
            "diagnostics": dict(diagnostics or {}),
        }
        self._persist()
        self._record_event(
            mode="reset",
            reason=reason,
            actor=actor,
            diagnostics=dict(diagnostics or {}),
        )
        return self.snapshot()

    def blocks(self, *, action_type: str) -> bool:
        mode = str(self._state.get("mode", "nominal")).strip()
        if mode == "nominal":
            return False
        allowlisted = {
            "status",
            "diagnostics",
            "discard_read",
            "shame_read",
            "fame_read",
            "kill_reset",
            "kill_soft",
            "kill_hard",
            "run_cancel",
        }
        return action_type not in allowlisted
