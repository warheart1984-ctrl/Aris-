from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RECOGNIZED_PROOF_KEYS = {
    "tests",
    "validation",
    "trace",
    "proof",
    "review",
    "checksum",
    "verification_artifacts",
}


@dataclass
class DecisionContext:
    actor: str
    action_type: str
    input_payload: dict[str, Any]
    proposed_output: dict[str, Any]
    interpreted_intent: str | None = None
    weights: dict[str, float] = field(default_factory=dict)
    values_claimed: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    mutation: bool = False
    conflict_present: bool = False
