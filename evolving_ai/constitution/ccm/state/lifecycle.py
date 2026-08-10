from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Set, TypeVar
from datetime import datetime
import uuid

T = TypeVar("T")


class ConstitutionalState(Enum):
    PROPOSED = "proposed"
    EVALUATED = "evaluated"
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    ARCHIVED = "archived"


class Transition(Enum):
    PROPOSE = "propose"
    EVALUATE = "evaluate"
    VERIFY = "verify"
    ACCEPT = "accept"
    ARCHIVE = "archive"
    REJECT = "reject"
    REOPEN = "reopen"


VALID_TRANSITIONS: Dict[ConstitutionalState, Set[Transition]] = {
    ConstitutionalState.PROPOSED: {Transition.EVALUATE, Transition.REJECT},
    ConstitutionalState.EVALUATED: {Transition.VERIFY, Transition.REOPEN},
    ConstitutionalState.VERIFIED: {Transition.ACCEPT, Transition.REOPEN},
    ConstitutionalState.ACCEPTED: {Transition.ARCHIVE, Transition.REOPEN},
    ConstitutionalState.ARCHIVED: {Transition.REOPEN},
}

TRANSITION_TARGET: Dict[Transition, ConstitutionalState] = {
    Transition.PROPOSE: ConstitutionalState.PROPOSED,
    Transition.EVALUATE: ConstitutionalState.EVALUATED,
    Transition.VERIFY: ConstitutionalState.VERIFIED,
    Transition.ACCEPT: ConstitutionalState.ACCEPTED,
    Transition.ARCHIVE: ConstitutionalState.ARCHIVED,
    Transition.REJECT: ConstitutionalState.ARCHIVED,
    Transition.REOPEN: ConstitutionalState.PROPOSED,
}


@dataclass(frozen=True, slots=True)
class ConstitutionalEvent:
    transition: Transition
    timestamp: datetime
    actor: str
    evidence_ref: Optional[str] = None
    rationale: str = ""


@dataclass
class ConstitutionalLifecycle(Generic[T]):
    subject_id: str
    subject_type: str
    state: ConstitutionalState = ConstitutionalState.PROPOSED
    history: List[ConstitutionalEvent] = field(default_factory=list)
    payload: Optional[T] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_transition(self, transition: Transition) -> bool:
        return transition in VALID_TRANSITIONS.get(self.state, set())

    def transition(self, transition: Transition, actor: str, evidence_ref: Optional[str] = None, rationale: str = "") -> bool:
        if not self.can_transition(transition):
            return False

        event = ConstitutionalEvent(
            transition=transition,
            timestamp=datetime.utcnow(),
            actor=actor,
            evidence_ref=evidence_ref,
            rationale=rationale,
        )
        self.history.append(event)
        self.state = TRANSITION_TARGET[transition]
        return True

    def current_state(self) -> ConstitutionalState:
        return self.state

    def get_evidence_chain(self) -> List[str]:
        return [e.evidence_ref for e in self.history if e.evidence_ref is not None]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "state": self.state.value,
            "history": [
                {
                    "transition": e.transition.value,
                    "timestamp": e.timestamp.isoformat(),
                    "actor": e.actor,
                    "evidence_ref": e.evidence_ref,
                    "rationale": e.rationale,
                }
                for e in self.history
            ],
            "metadata": self.metadata,
        }


class LifecycleRegistry(Generic[T]):
    def __init__(self) -> None:
        self._lifecycles: Dict[str, ConstitutionalLifecycle[T]] = {}

    def create(self, subject_type: str, payload: Optional[T] = None, metadata: Optional[Dict[str, Any]] = None) -> ConstitutionalLifecycle[T]:
        subject_id = str(uuid.uuid4())
        lifecycle = ConstitutionalLifecycle(
            subject_id=subject_id,
            subject_type=subject_type,
            payload=payload,
            metadata=metadata or {},
        )
        self._lifecycles[subject_id] = lifecycle
        return lifecycle

    def get(self, subject_id: str) -> Optional[ConstitutionalLifecycle[T]]:
        return self._lifecycles.get(subject_id)

    def transition(self, subject_id: str, transition: Transition, actor: str, evidence_ref: Optional[str] = None, rationale: str = "") -> bool:
        lifecycle = self._lifecycles.get(subject_id)
        if lifecycle is None:
            return False
        return lifecycle.transition(transition, actor, evidence_ref, rationale)

    def list_by_state(self, state: ConstitutionalState) -> List[ConstitutionalLifecycle[T]]:
        return [lc for lc in self._lifecycles.values() if lc.state == state]

    def list_by_type(self, subject_type: str) -> List[ConstitutionalLifecycle[T]]:
        return [lc for lc in self._lifecycles.values() if lc.subject_type == subject_type]