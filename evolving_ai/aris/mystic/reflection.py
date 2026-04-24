from __future__ import annotations

from typing import Any

from .reading import MysticReading, STATE_HINTS, STATE_ORDER


class MysticReflectionEngine:
    """Jarvis-merged reflection engine preserved under the Mystic Reflection identity."""

    def __init__(self) -> None:
        self.component_id = "mystic_reflection.core.jarvis-merged"
        self.lineage = {
            "source_repo": "mystic",
            "source_engine": "mythic-engine.ts",
            "jarvis_port": "AAIS src/mystic_engine.py",
            "merged_with_jarvis": True,
            "governed_by_aris": True,
            "role": "reflection",
        }

    def status_payload(self) -> dict[str, Any]:
        return {
            "active": True,
            "component_id": self.component_id,
            "merged_with_jarvis": True,
            "governed": True,
            "mode": "deterministic_reflection",
            "role": "reflection",
            "lineage": dict(self.lineage),
        }

    def detect_state(self, input_text: str) -> tuple[str, list[str]]:
        lower = " ".join(str(input_text or "").lower().split())
        scores = {state: 0 for state in STATE_ORDER}
        matched_signals: list[str] = []
        for state, hints in STATE_HINTS.items():
            for hint in hints:
                if hint in lower:
                    scores[state] += 1
                    if hint not in matched_signals:
                        matched_signals.append(hint)
        best_state = max(STATE_ORDER, key=lambda state: scores[state])
        if scores[best_state] <= 0:
            return "seeking", []
        return best_state, matched_signals

    def assign_archetypes(self, state: str) -> tuple[str, str]:
        if state == "lost":
            return "shadow", "guide"
        if state == "burdened":
            return "shadow", "builder"
        if state == "struggling":
            return "hero", "shadow"
        if state == "awakening":
            return "guide", "trickster"
        if state == "building":
            return "builder", "shadow"
        if state == "transforming":
            return "hero", "shadow"
        if state == "steady":
            return "builder", "trickster"
        return "witness", "trickster"

    def generate_trial(self, state: str) -> str:
        if state == "lost":
            return "Meaning vs numbness"
        if state == "burdened":
            return "Guilt vs understanding"
        if state == "struggling":
            return "Survival vs collapse"
        if state == "awakening":
            return "Vision vs distraction"
        if state == "building":
            return "Discipline vs inconsistency"
        if state == "transforming":
            return "Reaction vs control"
        if state == "steady":
            return "Maintenance vs drift"
        return "Action vs avoidance"

    def suggest_next_action(self, state: str) -> str:
        if state == "lost":
            return "Complete one grounding action in the next hour."
        if state == "burdened":
            return "Name the guilt clearly and replace self-attack with one honest sentence."
        if state == "struggling":
            return "Do one survival action now: water, food, walk, or rest."
        if state == "awakening":
            return "Write the idea clearly in five sentences."
        if state == "building":
            return "Finish one concrete system task today."
        if state == "transforming":
            return "Pause for 10 seconds before acting when anger rises."
        if state == "steady":
            return "Reinforce your daily protocol and track one win before bed."
        return "Choose one small action and complete it fully."

    def build_meaning(self, state: str, trial: str) -> str:
        if state == "transforming":
            return "You are replacing reaction with deliberate choice."
        if state == "steady":
            return "The work now is maintenance with awareness, not dramatic reinvention."
        if state == "awakening":
            return "Something new is trying to take form, but it still needs structure."
        return f"Your current path is {trial.lower()}."

    def build_risk(self, state: str) -> str:
        if state == "transforming":
            return "Ignoring the pause can reactivate regret loops."
        if state == "steady":
            return "Drift usually returns quietly through skipped rituals and small neglect."
        return "Inaction reinforces the current negative pattern."

    def render_response(self, reading: dict[str, Any]) -> str:
        state = reading.get("state_label") or reading.get("state") or "Seeking"
        dominant = reading.get("dominant_archetype_label") or reading.get("dominant_archetype") or "Witness"
        opposing = reading.get("opposing_archetype_label") or reading.get("opposing_archetype") or "Trickster"
        trial = reading.get("trial") or "Action vs avoidance"
        next_action = reading.get("next_action") or "Choose one small action and complete it fully."
        return (
            f"Mystic reflection: {state} is active. {dominant} leads, opposed by {opposing}. "
            f"Trial: {trial}. Next action: {next_action}"
        )

    def read(self, input_text: str, *, session_id: str, source: str) -> dict[str, Any]:
        cleaned = " ".join(str(input_text or "").split()).strip()
        state, signals = self.detect_state(cleaned)
        dominant, opposing = self.assign_archetypes(state)
        trial = self.generate_trial(state)
        reading = MysticReading(
            input_text=cleaned,
            state=state,
            dominant_archetype=dominant,
            opposing_archetype=opposing,
            trial=trial,
            next_action=self.suggest_next_action(state),
            meaning=self.build_meaning(state, trial),
            risk=self.build_risk(state),
            detected_signals=signals,
        ).to_dict()
        summary = self.render_response(reading)
        return {
            "type": "mystic_reflection",
            "tool": "mystic_reflection",
            "status": "completed",
            "input": cleaned,
            "result": reading,
            "summary": summary,
            "route": [
                {"stage": "Jarvis Blueprint", "status": "merged"},
                {"stage": "Mystic Reflection", "status": "interpreted"},
                {"stage": "ARIS Governance", "status": "required"},
                {"stage": "Outcome", "status": "completed"},
            ],
            "session_id": session_id,
            "source": source,
            "lineage": dict(self.lineage),
        }


class MysticReflectionRuntime(MysticReflectionEngine):
    pass


MysticRuntime = MysticReflectionEngine
