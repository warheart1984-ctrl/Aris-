"""CISIV Governance Model - 5-stage evaluator (State→Lineage→Legitimacy→Review→Verification)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time


class CISIVStage(Enum):
    """CISIV Governance stages."""
    STATE = "state"           # Check state presence
    LINEAGE = "lineage"       # Verify lineage
    LEGITIMACY = "legitimacy" # Check legitimacy
    REVIEW = "review"         # Operator review
    VERIFICATION = "verification"  # Independent verification


class CISIVStageStatus(Enum):
    """Stage evaluation status."""
    SATISFIED = "satisfied"
    BLOCKED = "blocked"
    PENDING = "pending"


@dataclass
class CISIVStageResult:
    """Result of a CISIV stage evaluation."""
    stage: CISIVStage
    status: CISIVStageStatus
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = field(default_factory=time.time)


@dataclass
class CISIVGovernanceStatus:
    """Overall CISIV governance status."""
    phase: str
    lawful: bool
    reason: str
    stages: List[CISIVStageResult] = field(default_factory=list)
    evaluated_at: float = field(default_factory=time.time)

    @property
    def first_blocked_stage(self) -> Optional[CISIVStage]:
        for stage_result in self.stages:
            if stage_result.status == CISIVStageStatus.BLOCKED:
                return stage_result.stage
        return None


class CISIVGovernanceModel:
    """5-stage evaluator with pluggable stages for custom governance flows."""
    
    def __init__(self):
        self._stage_evaluators: Dict[CISIVStage, Callable[[Dict[str, Any]], CISIVStageResult]] = {}
        self._default_evaluators()

    def _default_evaluators(self) -> None:
        """Register default stage evaluators."""
        self._stage_evaluators[CISIVStage.STATE] = self._eval_state
        self._stage_evaluators[CISIVStage.LINEAGE] = self._eval_lineage
        self._stage_evaluators[CISIVStage.LEGITIMACY] = self._eval_legitimacy
        self._stage_evaluators[CISIVStage.REVIEW] = self._eval_review
        self._stage_evaluators[CISIVStage.VERIFICATION] = self._eval_verification

    def register_stage_evaluator(self, stage: CISIVStage, evaluator: Callable[[Dict[str, Any]], CISIVStageResult]) -> None:
        """Register custom evaluator for a stage."""
        self._stage_evaluators[stage] = evaluator

    def evaluate(self, context: Dict[str, Any]) -> CISIVGovernanceStatus:
        """Evaluate all 5 stages sequentially. First blocked = rejection reason."""
        stage_results = []
        lawful = True
        rejection_reason = "All stages satisfied"
        
        for stage in CISIVStage:
            evaluator = self._stage_evaluators.get(stage)
            if evaluator is None:
                result = CISIVStageResult(
                    stage=stage,
                    status=CISIVStageStatus.BLOCKED,
                    reason=f"No evaluator registered for stage {stage.value}",
                )
            else:
                result = evaluator(context)
            
            stage_results.append(result)
            
            if result.status == CISIVStageStatus.BLOCKED and lawful:
                lawful = False
                rejection_reason = f"Blocked at {stage.value}: {result.reason}"
        
        return CISIVGovernanceStatus(
            phase="cisiv",
            lawful=lawful,
            reason=rejection_reason,
            stages=stage_results,
        )

    # Default evaluators (can be overridden)
    def _eval_state(self, context: Dict[str, Any]) -> CISIVStageResult:
        state_present = context.get("state_present", False)
        return CISIVStageResult(
            stage=CISIVStage.STATE,
            status=CISIVStageStatus.SATISFIED if state_present else CISIVStageStatus.BLOCKED,
            reason="State present" if state_present else "State not present",
            evidence={"state_present": state_present},
        )

    def _eval_lineage(self, context: Dict[str, Any]) -> CISIVStageResult:
        lineage_valid = context.get("lineage_valid", False)
        return CISIVStageResult(
            stage=CISIVStage.LINEAGE,
            status=CISIVStageStatus.SATISFIED if lineage_valid else CISIVStageStatus.BLOCKED,
            reason="Lineage valid" if lineage_valid else "Lineage invalid or missing",
            evidence={"lineage_valid": lineage_valid},
        )

    def _eval_legitimacy(self, context: Dict[str, Any]) -> CISIVStageResult:
        host_attested = context.get("host_attested", False)
        identity_verified = context.get("identity_verified", False)
        adapter_binding = context.get("adapter_binding", False)
        
        legitimate = host_attested and identity_verified and adapter_binding
        return CISIVStageResult(
            stage=CISIVStage.LEGITIMACY,
            status=CISIVStageStatus.SATISFIED if legitimate else CISIVStageStatus.BLOCKED,
            reason="Legitimacy confirmed" if legitimate else "Legitimacy check failed",
            evidence={
                "host_attested": host_attested,
                "identity_verified": identity_verified,
                "adapter_binding": adapter_binding,
            },
        )

    def _eval_review(self, context: Dict[str, Any]) -> CISIVStageResult:
        operator_approved = context.get("operator_approved", False)
        return CISIVStageResult(
            stage=CISIVStage.REVIEW,
            status=CISIVStageStatus.SATISFIED if operator_approved else CISIVStageStatus.PENDING,
            reason="Operator approved" if operator_approved else "Awaiting operator review",
            evidence={"operator_approved": operator_approved},
        )

    def _eval_verification(self, context: Dict[str, Any]) -> CISIVStageResult:
        verification_passed = context.get("verification_passed", False)
        return CISIVStageResult(
            stage=CISIVStage.VERIFICATION,
            status=CISIVStageStatus.SATISFIED if verification_passed else CISIVStageStatus.BLOCKED,
            reason="Verification passed" if verification_passed else "Verification failed",
            evidence={"verification_passed": verification_passed},
        )