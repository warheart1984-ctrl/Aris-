from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    QUARANTINED = "quarantined"
    ESCALATE = "escalate"


class RegistryDestination(str, Enum):
    HALL_OF_DECISIONS = "hall_of_decisions"
    FAILURE_REGISTRY = "failure_registry"


class FailureClass(str, Enum):
    INPUT_FAILURE = "input_failure"
    OUTPUT_FAILURE = "output_failure"
    VERIFICATION_FAILURE = "verification_failure"
    WEIGHT_FAILURE = "weight_failure"
    VALUE_FAILURE = "value_failure"
    FUTURE_WORTH_FAILURE = "future_worth_failure"
    CONFLICT_RESOLUTION_FAILURE = "conflict_resolution_failure"
    MUTATION_INTEGRITY_FAILURE = "mutation_integrity_failure"
    LAW_VIOLATION_FAILURE = "law_violation_failure"
    IDENTITY_CONSISTENCY_FAILURE = "identity_consistency_failure"
    EXPLANATION_FAILURE = "explanation_failure"


class Severity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class Repairability(str, Enum):
    REPAIRABLE = "repairable"
    REQUIRES_REDESIGN = "requires_redesign"
    NON_ADMISSIBLE = "non_admissible"
    ESCALATE_TO_OPERATOR = "escalate_to_operator"


class FutureWorth(str, Enum):
    WORTHY = "worthy"
    CONDITIONAL = "conditional"
    REJECTED = "rejected"
    FORBIDDEN = "forbidden"


class ShieldLaw(str, Enum):
    NON_HARM = "non_harm"
    NON_DOMINATION = "non_domination"
    IDENTITY_CONSISTENCY = "identity_consistency"
    EXISTENCE_GATE = "existence_gate"
    MUTATION_INTEGRITY = "mutation_integrity"
    VERIFICATION_REQUIREMENT = "verification_requirement"


@dataclass(frozen=True)
class ImmutableLawSet:
    laws: list[ShieldLaw] = field(
        default_factory=lambda: [
            ShieldLaw.NON_HARM,
            ShieldLaw.NON_DOMINATION,
            ShieldLaw.IDENTITY_CONSISTENCY,
            ShieldLaw.EXISTENCE_GATE,
            ShieldLaw.MUTATION_INTEGRITY,
            ShieldLaw.VERIFICATION_REQUIREMENT,
        ]
    )
