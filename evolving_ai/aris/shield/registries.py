from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .laws import FailureClass, FutureWorth, RegistryDestination, Repairability, Severity, Verdict


@dataclass
class CheckResult:
    passed: bool
    notes: list[str] = field(default_factory=list)
    failures: list[FailureClass] = field(default_factory=list)


@dataclass
class WeightAnalysis:
    justified: bool
    overweighted: list[str] = field(default_factory=list)
    underweighted: list[str] = field(default_factory=list)
    distortion_detected: bool = False
    temporal_risk_detected: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ValueAnalysis:
    aligned: bool
    expressed_values: list[str] = field(default_factory=list)
    violated_values: list[str] = field(default_factory=list)
    preserved_values: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class FutureWorthAnalysis:
    status: FutureWorth
    repeatable: bool
    inheritance_safe: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class ShieldEvaluation:
    decision_id: str
    timestamp: str
    actor: str
    action_type: str
    verdict: Verdict
    destination: RegistryDestination
    input_check: CheckResult
    output_check: CheckResult
    verification_check: CheckResult
    law_check: CheckResult
    weight_analysis: WeightAnalysis
    value_analysis: ValueAnalysis
    future_worth_analysis: FutureWorthAnalysis
    severity: Severity | None = None
    repairability: Repairability | None = None
    failure_classes: list[FailureClass] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    raw_input: dict[str, Any] = field(default_factory=dict)
    raw_output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HallOfDecisions:
    def __init__(self) -> None:
        self._entries: list[ShieldEvaluation] = []

    def add(self, evaluation: ShieldEvaluation) -> None:
        self._entries.append(evaluation)

    def all(self) -> list[ShieldEvaluation]:
        return list(self._entries)


class FailureRegistry:
    def __init__(self) -> None:
        self._entries: list[ShieldEvaluation] = []

    def add(self, evaluation: ShieldEvaluation) -> None:
        self._entries.append(evaluation)

    def all(self) -> list[ShieldEvaluation]:
        return list(self._entries)
