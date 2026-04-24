from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


REASONING_STAGES = ("observe", "orient", "decide", "act", "verify")
BLUEPRINT_ID = "jarvis.blueprint.aris-rebound"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class BlueprintTrace:
    blueprint_id: str
    created_at: str
    stages: list[dict[str, Any]]
    summary: str

    def payload(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "created_at": self.created_at,
            "stages": [dict(stage) for stage in self.stages],
            "summary": self.summary,
        }


class JarvisBlueprintReasoner:
    """AAIS/Jarvis-derived bounded reasoning spine for ARIS decisions."""

    def build_trace(
        self,
        *,
        action_type: str,
        purpose: str,
        session_id: str,
        target: str,
        risk_flags: list[str],
        requires_forge_eval: bool,
        startup_blockers: list[str],
    ) -> BlueprintTrace:
        normalized_purpose = " ".join(str(purpose or "").split()).strip() or "No declared purpose."
        normalized_target = str(target or "").strip() or "runtime"
        stages = [
            {
                "stage": "observe",
                "detail": (
                    f"Action `{action_type}` entered ARIS for session `{session_id or 'system'}` "
                    f"with target `{normalized_target}`."
                ),
            },
            {
                "stage": "orient",
                "detail": (
                    f"Jarvis blueprint rebound under ARIS law. Purpose: {normalized_purpose}"
                ),
            },
            {
                "stage": "decide",
                "detail": (
                    "Risk flags present: "
                    + (", ".join(risk_flags) if risk_flags else "none")
                    + ". Startup blockers: "
                    + (", ".join(startup_blockers) if startup_blockers else "none")
                ),
            },
            {
                "stage": "act",
                "detail": (
                    "Operator may request progression, but ARIS treats risky paths as non-final "
                    "until Forge Eval completes."
                    if requires_forge_eval
                    else "Action remains inside law-bounded handling."
                ),
            },
            {
                "stage": "verify",
                "detail": (
                    "1001 requires verified return."
                    if requires_forge_eval
                    else "1001 still requires explicit validation before return."
                ),
            },
        ]
        summary = (
            f"Jarvis blueprint trace prepared for `{action_type}` with "
            f"{'Forge Eval required' if requires_forge_eval else 'direct law validation'}."
        )
        return BlueprintTrace(
            blueprint_id=BLUEPRINT_ID,
            created_at=_utc_now(),
            stages=stages,
            summary=summary,
        )
