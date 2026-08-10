"""ShieldOfTruth - 7 ShieldLaws, weight/value/future worth analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class ShieldLaw(Enum):
    """7 Shield Laws."""
    SAFETY_OVER_SPEED = "safety_over_speed"
    TRUTH_OVER_SPEED = "truth_over_speed"
    OPERATOR_INTENT_OVER_AUTONOMY = "operator_intent_over_autonomy"
    NO_HIDDEN_ACTIONS = "no_hidden_actions"
    VERIFIABLE_EVIDENCE = "verifiable_evidence"
    REVERSIBLE_CHANGES = "reversible_changes"
    IDENTITY_PRESERVATION = "identity_preservation"


class ShieldVerdict(Enum):
    """Shield verdict."""
    WORTHY = "worthy"
    CONDITIONAL = "conditional"
    REJECTED = "rejected"
    FORBIDDEN = "forbidden"


class Severity(Enum):
    """Severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Repairability(Enum):
    """Repairability assessment."""
    AUTO_REPAIRABLE = "auto_repairable"
    OPERATOR_REPAIRABLE = "operator_repairable"
    MANUAL_REPAIRABLE = "manual_repairable"
    IRREPARABLE = "irreparable"


@dataclass
class ShieldAnalysis:
    """Analysis result for a shield law."""
    law: ShieldLaw
    passed: bool
    weight: float
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WeightAnalysis:
    """Weight analysis (safety>speed, truth>speed, operator_intent>autonomy)."""
    safety_weight: float = 1.0
    truth_weight: float = 1.0
    operator_intent_weight: float = 1.0
    speed_weight: float = 0.5
    autonomy_weight: float = 0.5

    def compute_score(self, analyses: List[ShieldAnalysis]) -> float:
        total_weight = 0.0
        weighted_pass = 0.0
        
        for analysis in analyses:
            law = analysis.law
            if law == ShieldLaw.SAFETY_OVER_SPEED:
                weight = self.safety_weight
            elif law == ShieldLaw.TRUTH_OVER_SPEED:
                weight = self.truth_weight
            elif law == ShieldLaw.OPERATOR_INTENT_OVER_AUTONOMY:
                weight = self.operator_intent_weight
            else:
                weight = 1.0
            
            total_weight += weight
            if analysis.passed:
                weighted_pass += weight
        
        return weighted_pass / total_weight if total_weight > 0 else 0.0


@dataclass
class ValueAnalysis:
    """Value analysis."""
    utility_score: float = 0.0
    risk_score: float = 0.0
    compliance_score: float = 0.0

    def compute_net_value(self) -> float:
        return (self.utility_score + self.compliance_score) - self.risk_score


@dataclass
class FutureWorthAnalysis:
    """Future worth analysis."""
    verdict: ShieldVerdict
    confidence: float
    reasoning: str


@dataclass
class ShieldOfTruthResult:
    """Complete ShieldOfTruth adjudication result."""
    verdict: ShieldVerdict
    severity: Severity
    repairability: Repairability
    weight_analysis: WeightAnalysis
    value_analysis: ValueAnalysis
    future_worth: FutureWorthAnalysis
    shield_analyses: List[ShieldAnalysis]
    timestamp: float = field(default_factory=time.time)


class ShieldOfTruth:
    """ShieldOfTruth Engine - Immutable law set adjudication."""
    
    LAWS = [
        ShieldLaw.SAFETY_OVER_SPEED,
        ShieldLaw.TRUTH_OVER_SPEED,
        ShieldLaw.OPERATOR_INTENT_OVER_AUTONOMY,
        ShieldLaw.NO_HIDDEN_ACTIONS,
        ShieldLaw.VERIFIABLE_EVIDENCE,
        ShieldLaw.REVERSIBLE_CHANGES,
        ShieldLaw.IDENTITY_PRESERVATION,
    ]

    def __init__(self):
        self._law_evaluators: Dict[ShieldLaw, callable] = {}
        self._default_evaluators()

    def _default_evaluators(self) -> None:
        self._law_evaluators[ShieldLaw.SAFETY_OVER_SPEED] = self._eval_safety
        self._law_evaluators[ShieldLaw.TRUTH_OVER_SPEED] = self._eval_truth
        self._law_evaluators[ShieldLaw.OPERATOR_INTENT_OVER_AUTONOMY] = self._eval_operator_intent
        self._law_evaluators[ShieldLaw.NO_HIDDEN_ACTIONS] = self._eval_no_hidden
        self._law_evaluators[ShieldLaw.VERIFIABLE_EVIDENCE] = self._eval_verifiable
        self._law_evaluators[ShieldLaw.REVERSIBLE_CHANGES] = self._eval_reversible
        self._law_evaluators[ShieldLaw.IDENTITY_PRESERVATION] = self._eval_identity

    def register_evaluator(self, law: ShieldLaw, evaluator: callable) -> None:
        self._law_evaluators[law] = evaluator

    def adjudicate(self, context: Dict[str, Any], action: Dict[str, Any]) -> ShieldOfTruthResult:
        """Adjudicate action against all 7 Shield Laws."""
        analyses = []
        
        for law in self.LAWS:
            evaluator = self._law_evaluators.get(law)
            if evaluator:
                result = evaluator(context, action)
                analyses.append(ShieldAnalysis(
                    law=law,
                    passed=result.get("passed", False),
                    weight=result.get("weight", 1.0),
                    reason=result.get("reason", ""),
                    evidence=result.get("evidence", {}),
                ))
            else:
                analyses.append(ShieldAnalysis(
                    law=law,
                    passed=False,
                    weight=1.0,
                    reason="No evaluator registered",
                ))
        
        # Weight Analysis
        weight_analysis = WeightAnalysis()
        weight_score = weight_analysis.compute_score(analyses)
        
        # Value Analysis
        value_analysis = ValueAnalysis(
            utility_score=context.get("utility_score", 0.5),
            risk_score=context.get("risk_score", 0.5),
            compliance_score=context.get("compliance_score", 0.5),
        )
        net_value = value_analysis.compute_net_value()
        
        # Future Worth Analysis
        future_worth = self._compute_future_worth(weight_score, net_value, analyses)
        
        # Determine verdict
        verdict = self._determine_verdict(weight_score, net_value, future_worth, analyses)
        
        # Determine severity
        severity = self._determine_severity(verdict, analyses)
        
        # Determine repairability
        repairability = self._determine_repairability(verdict, analyses)
        
        return ShieldOfTruthResult(
            verdict=verdict,
            severity=severity,
            repairability=repairability,
            weight_analysis=weight_analysis,
            value_analysis=value_analysis,
            future_worth=future_worth,
            shield_analyses=analyses,
        )

    def _compute_future_worth(self, weight_score: float, net_value: float, analyses: List[ShieldAnalysis]) -> FutureWorthAnalysis:
        passed_count = sum(1 for a in analyses if a.passed)
        total_count = len(analyses)
        
        if passed_count == total_count and net_value > 0:
            return FutureWorthAnalysis(
                verdict=ShieldVerdict.WORTHY,
                confidence=0.9,
                reasoning="All laws satisfied with positive net value",
            )
        elif passed_count >= total_count * 0.7 and net_value >= 0:
            return FutureWorthAnalysis(
                verdict=ShieldVerdict.CONDITIONAL,
                confidence=0.7,
                reasoning="Most laws satisfied, conditions apply",
            )
        elif net_value < -0.5:
            return FutureWorthAnalysis(
                verdict=ShieldVerdict.REJECTED,
                confidence=0.8,
                reasoning="Negative net value outweighs compliance",
            )
        else:
            return FutureWorthAnalysis(
                verdict=ShieldVerdict.FORBIDDEN,
                confidence=0.9,
                reasoning="Critical law violations detected",
            )

    def _determine_verdict(self, weight_score: float, net_value: float, future_worth: FutureWorthAnalysis, analyses: List[ShieldAnalysis]) -> ShieldVerdict:
        # Critical laws that if failed = FORBIDDEN
        critical_laws = {ShieldLaw.SAFETY_OVER_SPEED, ShieldLaw.TRUTH_OVER_SPEED, ShieldLaw.IDENTITY_PRESERVATION}
        for analysis in analyses:
            if analysis.law in critical_laws and not analysis.passed:
                return ShieldVerdict.FORBIDDEN
        
        return future_worth.verdict

    def _determine_severity(self, verdict: ShieldVerdict, analyses: List[ShieldAnalysis]) -> Severity:
        if verdict == ShieldVerdict.FORBIDDEN:
            return Severity.CRITICAL
        elif verdict == ShieldVerdict.REJECTED:
            return Severity.HIGH
        elif verdict == ShieldVerdict.CONDITIONAL:
            return Severity.MEDIUM
        return Severity.LOW

    def _determine_repairability(self, verdict: ShieldVerdict, analyses: List[ShieldAnalysis]) -> Repairability:
        if verdict == ShieldVerdict.FORBIDDEN:
            return Repairability.IRREPARABLE
        elif verdict == ShieldVerdict.REJECTED:
            return Repairability.MANUAL_REPAIRABLE
        elif verdict == ShieldVerdict.CONDITIONAL:
            return Repairability.OPERATOR_REPAIRABLE
        return Repairability.AUTO_REPAIRABLE

    # Default evaluators (placeholder implementations)
    def _eval_safety(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        return {"passed": context.get("safety_check", True), "weight": 1.5, "reason": "Safety check"}

    def _eval_truth(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        return {"passed": context.get("truth_check", True), "weight": 1.5, "reason": "Truth check"}

    def _eval_operator_intent(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        return {"passed": context.get("operator_intent_check", True), "weight": 1.5, "reason": "Operator intent check"}

    def _eval_no_hidden(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        hidden = action.get("hidden", False)
        return {"passed": not hidden, "weight": 1.0, "reason": "No hidden actions"}

    def _eval_verifiable(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        return {"passed": context.get("evidence_provided", True), "weight": 1.0, "reason": "Verifiable evidence"}

    def _eval_reversible(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        reversible = action.get("reversible", True)
        return {"passed": reversible, "weight": 1.0, "reason": "Reversible changes"}

    def _eval_identity(self, context: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        return {"passed": context.get("identity_preserved", True), "weight": 1.5, "reason": "Identity preservation"}