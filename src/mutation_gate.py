from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .constants_runtime import DISPOSITION_REJECTED, DISPOSITION_VALID, MUTATION_ACTION_TYPES
from .law_context_builder import RuntimeLawContext
from .law_ledger import LawLedger


@dataclass(frozen=True, slots=True)
class MutationAdmission:
    allowed: bool
    disposition: str
    reason: str
    required_recovery: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "disposition": self.disposition,
            "reason": self.reason,
            "required_recovery": list(self.required_recovery),
        }


class MutationGate:
    def __init__(
        self,
        *,
        ledger: LawLedger,
        observation_blocked: Callable[[str], bool],
    ) -> None:
        self.ledger = ledger
        self.observation_blocked = observation_blocked

    def review(
        self,
        *,
        context: RuntimeLawContext,
        action: dict[str, Any],
    ) -> MutationAdmission:
        if context.action_type not in MUTATION_ACTION_TYPES:
            return MutationAdmission(
                allowed=True,
                disposition=DISPOSITION_VALID,
                reason="Action is not a mutation path.",
                required_recovery=(),
            )
        recovery: list[str] = []
        if not context.lineage:
            recovery.append("add_lineage")
        if str(action.get("operator_decision") or "").strip() not in {
            "approved",
            "recorded",
            "system",
        }:
            recovery.append("obtain_review")
        if not context.identity_verified or not context.host_attested:
            recovery.append("verify_identity_and_host")
        if context.protected_target:
            recovery.append("redesign_away_from_foundational_or_protected_target")
        if self.observation_blocked(context.session_id):
            recovery.append("complete_observation_window")
        allowed = not recovery
        if allowed:
            reason = "Mutation gate admitted the change."
        else:
            reason = "Mutation gate rejected the change."
            if recovery:
                reason = f"{reason} Required recovery: {', '.join(recovery)}."
        admission = MutationAdmission(
            allowed=allowed,
            disposition=DISPOSITION_VALID if allowed else DISPOSITION_REJECTED,
            reason=reason,
            required_recovery=tuple(recovery),
        )
        self.ledger.record(
            "mutation_gate",
            {
                "context": context.payload(),
                "action_type": context.action_type,
                "admission": admission.payload(),
            },
            require_success=True,
        )
        return admission
