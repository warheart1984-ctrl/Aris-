from __future__ import annotations

from random import choice
from time import time
from typing import Any
import uuid

from .escalation import MysticEscalationPolicy
from .session_monitor import MysticState
from .ui_controls import build_mystic_ui_controls
from .voice import NullVoiceAdapter, VoiceAdapter


MESSAGE_LIBRARY: dict[str, dict[int, list[str]]] = {
    "hydration": {
        1: ["Quick reminder. Drink some water.", "Hydration check. Take a sip.", "Pause and get water."],
        2: [
            "You have been going a while. Get water and reset.",
            "Pause here. Drink some water before the next pass.",
            "Go get water and take a short break.",
        ],
        3: [
            "Stop for a moment. Hydrate before continuing.",
            "You are overdue for water. Step away now.",
            "Pause. Water first, then continue.",
        ],
    },
    "nutrition": {
        1: ["Quick check. Eat soon."],
        2: [
            "Pause here. Eat something before you continue.",
            "You need food, not just momentum.",
            "Refuel, then come back.",
        ],
        3: [
            "Stop for a moment. You need food before continuing.",
            "You are running too long without eating. Break now.",
        ],
    },
    "rest": {
        1: ["Stand up for a minute and reset.", "Take a short break soon."],
        2: [
            "Step away for five minutes and reset.",
            "You have been pushing for a while. Take a break.",
            "Pause now and rest for a few minutes.",
        ],
        3: [
            "Stop for a moment. You need rest before continuing.",
            "Performance is dropping. Take a real break now.",
            "You are pushing too long without recovery. Walk away and reset.",
        ],
    },
    "loop_reset": {
        1: ["You may be looping. Reset your approach."],
        2: [
            "You are looping. Step away for five minutes.",
            "Same pattern, same friction. Take five.",
            "Pause. Fresh pass next.",
        ],
        3: [
            "Stop. You are stuck in a loop. Reset before continuing.",
            "Break the loop now. Step away and return fresh.",
        ],
    },
}


class MysticSustainmentService:
    """Operator sustainment layer with per-session state, thresholds, and cooldowns."""

    def __init__(self, *, voice: VoiceAdapter | None = None) -> None:
        self.voice = voice or NullVoiceAdapter()
        self._states: dict[str, MysticState] = {}
        self._latest_reminders: list[dict[str, Any]] = []

    def _state_for(self, session_id: str) -> MysticState:
        normalized = str(session_id or "system").strip() or "system"
        if normalized not in self._states:
            self._states[normalized] = MysticState()
        return self._states[normalized]

    def _remember(self, payload: dict[str, Any]) -> None:
        self._latest_reminders.append(dict(payload))
        del self._latest_reminders[:-20]

    def build_message(self, category: str, level: int) -> str:
        pool = MESSAGE_LIBRARY.get(category, {}).get(level, [])
        if not pool:
            return "Take a short break and reset."
        return choice(pool)

    def observe_activity(self, *, session_id: str) -> dict[str, Any] | None:
        state = self._state_for(session_id)
        state.record_activity()
        return self.tick(session_id=session_id)

    def tick(self, *, session_id: str) -> dict[str, Any] | None:
        state = self._state_for(session_id)
        now = time()
        decision = MysticEscalationPolicy.evaluate(state, now)
        if not decision.should_speak:
            return None
        message = self.build_message(decision.category, decision.level)
        self.voice.speak(message)
        state.record_voice(decision.category, decision.level, message, now)
        payload = {
            "id": f"mystic_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "level": decision.level,
            "category": decision.category,
            "reason": decision.reason,
            "cooldown_minutes": decision.cooldown_minutes,
            "message": message,
            "spoken_at": now,
        }
        self._remember(payload)
        return payload

    def record_error(self, *, session_id: str) -> None:
        self._state_for(session_id).consecutive_errors += 1

    def clear_error_streak(self, *, session_id: str) -> None:
        self._state_for(session_id).consecutive_errors = 0

    def record_loop(self, *, session_id: str) -> None:
        self._state_for(session_id).repeated_loop_count += 1

    def clear_loop_streak(self, *, session_id: str) -> None:
        self._state_for(session_id).repeated_loop_count = 0

    def record_break(self, *, session_id: str) -> dict[str, Any]:
        state = self._state_for(session_id)
        state.record_break()
        return self.session_payload(session_id=session_id)

    def acknowledge(self, *, session_id: str) -> dict[str, Any]:
        state = self._state_for(session_id)
        state.acknowledge()
        return self.session_payload(session_id=session_id)

    def mute_for_minutes(self, *, session_id: str, minutes: float) -> dict[str, Any]:
        state = self._state_for(session_id)
        state.mute_for_minutes(minutes)
        return self.session_payload(session_id=session_id)

    def session_payload(self, *, session_id: str) -> dict[str, Any]:
        state = self._state_for(session_id)
        now = time()
        latest = next(
            (item for item in reversed(self._latest_reminders) if item.get("session_id") == session_id),
            None,
        )
        minutes_since_voice = state.minutes_since_voice(now)
        payload = {
            "session_id": session_id,
            "active": True,
            "alert_level": state.alert_level,
            "session_minutes": round(state.session_minutes(now), 2),
            "minutes_since_break": round(state.minutes_since_break(now), 2),
            "minutes_since_voice": (
                None if minutes_since_voice == float("inf") else round(minutes_since_voice, 2)
            ),
            "consecutive_errors": state.consecutive_errors,
            "repeated_loop_count": state.repeated_loop_count,
            "last_category": state.last_category,
            "last_message": state.last_message,
            "voice_enabled": state.voice_enabled,
            "muted": state.is_muted(now),
            "latest_reminder": latest,
        }
        payload["ui_controls"] = build_mystic_ui_controls(payload)
        return payload

    def status_payload(self) -> dict[str, Any]:
        return {
            "active": True,
            "component_id": "mystic.sustainment",
            "role": "human_sustainment_layer",
            "session_count": len(self._states),
            "latest_reminders": list(self._latest_reminders),
            "ui_controls": build_mystic_ui_controls({"active": True}),
        }
