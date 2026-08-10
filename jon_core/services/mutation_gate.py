"""MutationGate + Broker - Admission review with explicit recovery actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import uuid


class MutationDisposition(Enum):
    """Mutation admission disposition."""
    ALLOWED = "allowed"
    REJECTED = "rejected"
    CONDITIONAL = "conditional"
    OBSERVATION = "observation"


@dataclass
class RecoveryAction:
    """Required recovery action for mutation admission."""
    action_type: str
    target: str
    payload: Dict[str, Any] = field(default_factory=dict)
    deadline_seconds: float = 300.0


@dataclass
class MutationAdmission:
    """Result of mutation admission review."""
    allowed: bool
    disposition: MutationDisposition
    reason: str
    required_recovery: List[RecoveryAction] = field(default_factory=list)
    observation_window_seconds: float = 0.0
    lineage_key: str = ""
    mutation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)


class MutationGate:
    """Review(context, action) -> MutationAdmission with explicit recovery actions."""
    
    def __init__(self):
        self._reviewers: List[Callable[[Dict[str, Any], Dict[str, Any]], MutationAdmission]] = []
        self._ledger: List[Dict[str, Any]] = []

    def register_reviewer(self, reviewer: Callable[[Dict[str, Any], Dict[str, Any]], MutationAdmission]) -> None:
        """Register a mutation reviewer."""
        self._reviewers.append(reviewer)

    def review(self, context: Dict[str, Any], action: Dict[str, Any]) -> MutationAdmission:
        """Review mutation action against context."""
        # Build lineage key
        lineage_key = self._build_lineage_key(context, action)
        
        # Run all reviewers
        final_admission = MutationAdmission(
            allowed=True,
            disposition=MutationDisposition.ALLOWED,
            reason="All reviews passed",
            lineage_key=lineage_key,
        )
        
        for reviewer in self._reviewers:
            result = reviewer(context, action)
            if not result.allowed:
                final_admission = result
                break
            elif result.disposition == MutationDisposition.CONDITIONAL:
                if final_admission.disposition == MutationDisposition.ALLOWED:
                    final_admission = result
            elif result.disposition == MutationDisposition.OBSERVATION:
                if final_admission.disposition in (MutationDisposition.ALLOWED, MutationDisposition.CONDITIONAL):
                    final_admission = result
        
        # Record to ledger (mandatory)
        self._record_to_ledger(context, action, final_admission)
        
        return final_admission

    def _build_lineage_key(self, context: Dict[str, Any], action: Dict[str, Any]) -> str:
        """Build lineage key from context and action."""
        parts = [
            context.get("identity", "unknown"),
            context.get("scope", "unknown"),
            action.get("type", "unknown"),
            action.get("target", "unknown"),
        ]
        return ":".join(parts)

    def _record_to_ledger(self, context: Dict[str, Any], action: Dict[str, Any], admission: MutationAdmission) -> None:
        """Record mutation admission to ledger."""
        record = {
            "timestamp": time.time(),
            "event_type": "mutation_admission",
            "context": context,
            "action": action,
            "admission": {
                "allowed": admission.allowed,
                "disposition": admission.disposition.value,
                "reason": admission.reason,
                "lineage_key": admission.lineage_key,
                "mutation_id": admission.mutation_id,
            },
        }
        self._ledger.append(record)

    def get_ledger(self) -> List[Dict[str, Any]]:
        return list(self._ledger)


class MutationBroker:
    """Admission + ledger recording; delegates to MutationGate."""
    
    def __init__(self, mutation_gate: MutationGate):
        self._gate = mutation_gate

    def submit(self, context: Dict[str, Any], action: Dict[str, Any]) -> MutationAdmission:
        """Submit mutation for admission review."""
        return self._gate.review(context, action)

    def get_admission_history(self) -> List[Dict[str, Any]]:
        return self._gate.get_ledger()