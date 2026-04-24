from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants_runtime import CISIV_STAGE_SEQUENCE, MUTATION_ACTION_TYPES
from .law_context_builder import RuntimeLawContext


@dataclass(frozen=True, slots=True)
class CISIVStageStatus:
    stage: str
    status: str
    reason: str

    def payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CISIVGovernanceStatus:
    phase: str
    lawful: bool
    reason: str
    stages: tuple[CISIVStageStatus, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "lawful": self.lawful,
            "reason": self.reason,
            "stages": [stage.payload() for stage in self.stages],
        }


class CISIVGovernanceModel:
    def evaluate(
        self,
        *,
        context: RuntimeLawContext,
        action: dict[str, Any],
        phase: str,
        verification_passed: bool | None = None,
    ) -> CISIVGovernanceStatus:
        operator_decision = str(action.get("operator_decision") or "").strip()
        lineage_present = bool(context.declared_lineage or context.lineage)
        review_required = context.action_type in MUTATION_ACTION_TYPES
        review_present = operator_decision in {"approved", "recorded", "system"} or not review_required
        legitimacy_present = (
            context.host_attested
            and context.identity_verified
            and context.adapter_binding_ok
        )
        stages = (
            CISIVStageStatus(
                stage=CISIV_STAGE_SEQUENCE[0],
                status="satisfied" if context.state_present else "blocked",
                reason="State (0001) is present." if context.state_present else "State (0001) is missing.",
            ),
            CISIVStageStatus(
                stage=CISIV_STAGE_SEQUENCE[1],
                status="satisfied" if lineage_present else "blocked",
                reason=(
                    "Lineage is declared."
                    if context.declared_lineage
                    else "Lineage was derived from the action trace."
                    if lineage_present
                    else "Lineage is missing."
                ),
            ),
            CISIVStageStatus(
                stage=CISIV_STAGE_SEQUENCE[2],
                status="satisfied" if legitimacy_present else "blocked",
                reason=(
                    "Legitimacy and adapter binding are satisfied."
                    if legitimacy_present
                    else context.adapter_binding_reason or "Legitimacy requirements failed."
                ),
            ),
            CISIVStageStatus(
                stage=CISIV_STAGE_SEQUENCE[3],
                status="satisfied" if review_present else "blocked",
                reason=(
                    "Review stage is satisfied."
                    if review_present
                    else "Review stage is missing for a mutation-bearing action."
                ),
            ),
            CISIVStageStatus(
                stage=CISIV_STAGE_SEQUENCE[4],
                status=(
                    "pending"
                    if verification_passed is None
                    else "satisfied"
                    if verification_passed
                    else "blocked"
                ),
                reason=(
                    "1001 verification is pending."
                    if verification_passed is None
                    else "1001 verification completed."
                    if verification_passed
                    else "1001 verification failed."
                ),
            ),
        )
        blocked = [stage for stage in stages if stage.status == "blocked"]
        lawful = not blocked
        if blocked:
            reason = blocked[0].reason
        elif verification_passed is None:
            reason = "CISIV formation is satisfied and awaiting 1001."
        else:
            reason = "CISIV staged governance is satisfied."
        return CISIVGovernanceStatus(
            phase=str(phase or "runtime").strip() or "runtime",
            lawful=lawful,
            reason=reason,
            stages=stages,
        )
