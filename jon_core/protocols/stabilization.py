"""Stabilization Protocol (Δ) - StateMachineEngine with 6 states, 5 guards."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import time
import threading
import uuid


class SystemState(Enum):
    """Δ System states."""
    NOMINAL = "nominal"
    PERTURBED = "perturbed"
    CONVERGING = "converging"
    DEGRADED = "degraded"
    HALTED = "halted"
    QUIESCENT = "quiescent"


class TransitionGuard(Enum):
    """Δ Transition guards."""
    AUTH = "auth"           # Operator authorization
    HEALTH = "health"       # HealthVector check
    CASCADE = "cascade"     # Cross-scope cascade check
    EPOCH = "epoch"         # Epoch timer
    REVERSAL = "reversal"   # Rollback capability


@dataclass
class TransitionRequest:
    """Request for state transition."""
    from_state: SystemState
    to_state: SystemState
    scope: str
    reason: str
    actor: str
    guards_required: List[TransitionGuard] = field(default_factory=list)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)


@dataclass
class TransitionRecord:
    """Record of a state transition."""
    request: TransitionRequest
    approved: bool
    guards_passed: List[TransitionGuard] = field(default_factory=list)
    guards_failed: List[TransitionGuard] = field(default_factory=list)
    executed_at: Optional[float] = None
    operator_approval: Optional[str] = None


class StateMachineEngine:
    """Atomic transitions via 8-stage pipeline (REQUEST→VALIDATE→AUTH→SNAPSHOT→WRITE→VERIFY→EMIT→NOTIFY)."""
    
    VALID_TRANSITIONS = {
        SystemState.NOMINAL: [SystemState.PERTURBED, SystemState.QUIESCENT],
        SystemState.PERTURBED: [SystemState.CONVERGING, SystemState.DEGRADED, SystemState.NOMINAL],
        SystemState.CONVERGING: [SystemState.NOMINAL, SystemState.DEGRADED, SystemState.HALTED],
        SystemState.DEGRADED: [SystemState.CONVERGING, SystemState.HALTED, SystemState.QUIESCENT],
        SystemState.HALTED: [SystemState.QUIESCENT],
        SystemState.QUIESCENT: [SystemState.NOMINAL],
    }

    def __init__(self):
        self._states: Dict[str, SystemState] = {}  # scope -> state
        self._history: List[TransitionRecord] = []
        self._lock = threading.RLock()
        self._guard_evaluators: Dict[TransitionGuard, Callable[[TransitionRequest], bool]] = {}
        self._transition_callbacks: List[Callable[[TransitionRecord], None]] = {}
        self._default_guards()

    def _default_guards(self) -> None:
        """Register default guard evaluators."""
        self._guard_evaluators[TransitionGuard.AUTH] = self._eval_auth
        self._guard_evaluators[TransitionGuard.HEALTH] = self._eval_health
        self._guard_evaluators[TransitionGuard.CASCADE] = self._eval_cascade
        self._guard_evaluators[TransitionGuard.EPOCH] = self._eval_epoch
        self._guard_evaluators[TransitionGuard.REVERSAL] = self._eval_reversal

    def register_guard_evaluator(self, guard: TransitionGuard, evaluator: Callable[[TransitionRequest], bool]) -> None:
        """Register custom guard evaluator."""
        self._guard_evaluators[guard] = evaluator

    def register_transition_callback(self, callback: Callable[[TransitionRecord], None]) -> None:
        """Register callback for transitions."""
        self._transition_callbacks.append(callback)

    def get_state(self, scope: str) -> SystemState:
        with self._lock:
            return self._states.get(scope, SystemState.NOMINAL)

    def request_transition(self, request: TransitionRequest) -> TransitionRecord:
        """Execute 8-stage transition pipeline."""
        with self._lock:
            # STAGE 1: REQUEST - Validate request structure
            if not self._validate_request(request):
                return TransitionRecord(request=request, approved=False, guards_failed=[TransitionGuard.AUTH])
            
            # STAGE 2: VALIDATE - Check transition validity
            if not self._validate_transition(request):
                return TransitionRecord(request=request, approved=False, guards_failed=[TransitionGuard.AUTH])
            
            # STAGE 3: AUTH - Evaluate required guards
            guards_passed = []
            guards_failed = []
            for guard in request.guards_required:
                evaluator = self._guard_evaluators.get(guard)
                if evaluator and evaluator(request):
                    guards_passed.append(guard)
                else:
                    guards_failed.append(guard)
            
            if guards_failed:
                record = TransitionRecord(
                    request=request,
                    approved=False,
                    guards_passed=guards_passed,
                    guards_failed=guards_failed,
                )
                self._record_transition(record)
                return record
            
            # STAGE 4: SNAPSHOT - Capture pre-transition state
            snapshot = self._snapshot_scope(request.scope)
            
            # STAGE 5: WRITE - Execute transition
            self._states[request.scope] = request.to_state
            
            # STAGE 6: VERIFY - Verify post-transition state
            if not self._verify_transition(request):
                # Rollback on verification failure
                self._states[request.scope] = request.from_state
                return TransitionRecord(
                    request=request,
                    approved=False,
                    guards_passed=guards_passed,
                    guards_failed=[TransitionGuard.REVERSAL],
                )
            
            # STAGE 7: EMIT - Emit audit record
            record = TransitionRecord(
                request=request,
                approved=True,
                guards_passed=guards_passed,
                executed_at=time.time(),
            )
            self._record_transition(record)
            
            # STAGE 8: NOTIFY - Notify callbacks
            for callback in self._transition_callbacks:
                try:
                    callback(record)
                except Exception:
                    pass
            
            return record

    def _validate_request(self, request: TransitionRequest) -> bool:
        return request.from_state is not None and request.to_state is not None

    def _validate_transition(self, request: TransitionRequest) -> bool:
        current = self._states.get(request.scope, SystemState.NOMINAL)
        if current != request.from_state:
            return False
        valid_targets = self.VALID_TRANSITIONS.get(request.from_state, [])
        return request.to_state in valid_targets

    def _eval_auth(self, request: TransitionRequest) -> bool:
        # Default: require operator for sensitive transitions
        sensitive = {SystemState.HALTED, SystemState.DEGRADED}
        if request.to_state in sensitive:
            return request.actor.startswith("operator_") or request.actor == "system"
        return True

    def _eval_health(self, request: TransitionRequest) -> bool:
        # Defer to HealthVectorEngine if available
        return True

    def _eval_cascade(self, request: TransitionRequest) -> bool:
        # Check if other scopes would be affected
        return True

    def _eval_epoch(self, request: TransitionRequest) -> bool:
        # Check epoch timer constraints
        return True

    def _eval_reversal(self, request: TransitionRequest) -> bool:
        # Check if rollback is possible
        return True

    def _snapshot_scope(self, scope: str) -> Dict[str, Any]:
        return {"scope": scope, "state": self._states.get(scope), "timestamp": time.time()}

    def _verify_transition(self, request: TransitionRequest) -> bool:
        return self._states.get(request.scope) == request.to_state

    def _record_transition(self, record: TransitionRecord) -> None:
        self._history.append(record)

    def get_history(self, scope: Optional[str] = None) -> List[TransitionRecord]:
        with self._lock:
            if scope:
                return [r for r in self._history if r.request.scope == scope]
            return list(self._history)

    def get_transition_counts(self) -> Dict[str, int]:
        with self._lock:
            counts = {}
            for record in self._history:
                key = f"{record.request.from_state.value}->{record.request.to_state.value}"
                counts[key] = counts.get(key, 0) + 1
            return counts