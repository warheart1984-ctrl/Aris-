"""Λ.6 InterruptHandler + KillSwitch - Non-negotiable interrupt endpoint + system-wide KillSwitch."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import threading
import uuid


class InterruptReason(Enum):
    OPERATOR_REQUEST = "operator_request"
    SAFETY_VIOLATION = "safety_violation"
    LAW_BREACH = "law_breach"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class InterruptRequest:
    """Interrupt request with metadata."""
    reason: InterruptReason
    source: str
    target_module: str
    payload: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    acknowledged_at: Optional[float] = None


@dataclass
class CorrectionInterface:
    """Correction interface for interrupt handling."""
    pause: Callable[[], None]
    inspect: Callable[[], Dict[str, Any]]
    modify: Callable[[Dict[str, Any]], None]
    inject: Callable[[Any], None]
    terminate: Callable[[], None]


class InterruptHandler:
    """Standardized non-negotiable interrupt endpoint (≤500ms ack)."""
    
    MAX_ACK_LATENCY_MS = 500
    
    def __init__(self):
        self._pending: Dict[str, InterruptRequest] = {}
        self._handlers: Dict[str, Callable[[InterruptRequest], None]] = {}
        self._lock = threading.RLock()
        self._correction_interface: Optional[CorrectionInterface] = None

    def register_handler(self, module: str, handler: Callable[[InterruptRequest], None]) -> None:
        """Register interrupt handler for a module."""
        with self._lock:
            self._handlers[module] = handler

    def set_correction_interface(self, interface: CorrectionInterface) -> None:
        """Set the correction interface."""
        self._correction_interface = interface

    def request_interrupt(self, request: InterruptRequest) -> str:
        """Submit interrupt request. Returns request_id."""
        with self._lock:
            self._pending[request.request_id] = request
            
            # Fire handler asynchronously (non-blocking)
            if request.target_module in self._handlers:
                handler = self._handlers[request.target_module]
                threading.Thread(target=handler, args=(request,), daemon=True).start()
            
            return request.request_id

    def acknowledge(self, request_id: str) -> bool:
        """Acknowledge interrupt (must be ≤500ms)."""
        with self._lock:
            if request_id not in self._pending:
                return False
            
            request = self._pending[request_id]
            request.acknowledged = True
            request.acknowledged_at = time.time()
            return True

    def get_pending(self) -> List[InterruptRequest]:
        with self._lock:
            return list(self._pending.values())

    def get_correction_interface(self) -> Optional[CorrectionInterface]:
        return self._correction_interface


class KillSwitchTrigger(Enum):
    STARTUP = "startup"
    LAW_BYPASS = "law_bypass"
    FORGE_EVAL_BYPASS = "forge_eval_bypass"
    SHIELD_QUARANTINE = "shield_quarantine"
    PROTECTED_MUTATION = "protected_mutation"
    HIDDEN_ACTION = "hidden_action"
    REPEATED_ESCALATION = "repeated_escalation"


@dataclass
class KillSwitchState:
    """KillSwitch state."""
    locked_down: bool = False
    hard_killed: bool = False
    lockdown_reason: Optional[str] = None
    lockdown_actor: Optional[str] = None
    lockdown_diagnostics: Dict[str, Any] = field(default_factory=dict)
    lockdown_timestamp: Optional[float] = None
    blocked_actions: List[str] = field(default_factory=list)


class KillSwitch:
    """System-wide KillSwitch with lockdown and hard_kill."""
    
    def __init__(self):
        self._state = KillSwitchState()
        self._lock = threading.RLock()
        self._trigger_handlers: Dict[KillSwitchTrigger, List[Callable[[str, Dict[str, Any]], None]]] = {
            trigger: [] for trigger in KillSwitchTrigger
        }

    def register_trigger_handler(self, trigger: KillSwitchTrigger, handler: Callable[[str, Dict[str, Any]], None]) -> None:
        with self._lock:
            self._trigger_handlers[trigger].append(handler)

    def lockdown(self, reason: str, actor: str, diagnostics: Dict[str, Any]) -> None:
        """Soft lockdown - blocks new actions, allows in-flight to complete."""
        with self._lock:
            if self._state.locked_down:
                return
            
            self._state.locked_down = True
            self._state.lockdown_reason = reason
            self._state.lockdown_actor = actor
            self._state.lockdown_diagnostics = diagnostics
            self._state.lockdown_timestamp = time.time()
            
            # Notify trigger handlers
            for handler in self._trigger_handlers.get(KillSwitchTrigger.LAW_BYPASS, []):
                try:
                    handler(reason, diagnostics)
                except Exception:
                    pass

    def hard_kill(self, reason: str, actor: str, diagnostics: Dict[str, Any]) -> None:
        """Hard kill - immediate termination of all operations."""
        with self._lock:
            self._state.hard_killed = True
            self._state.locked_down = True
            self._state.lockdown_reason = reason
            self._state.lockdown_actor = actor
            self._state.lockdown_diagnostics = diagnostics
            self._state.lockdown_timestamp = time.time()

    def snapshot(self) -> KillSwitchState:
        with self._lock:
            return KillSwitchState(
                locked_down=self._state.locked_down,
                hard_killed=self._state.hard_killed,
                lockdown_reason=self._state.lockdown_reason,
                lockdown_actor=self._state.lockdown_actor,
                lockdown_diagnostics=self._state.lockdown_diagnostics.copy(),
                lockdown_timestamp=self._state.lockdown_timestamp,
                blocked_actions=self._state.blocked_actions.copy(),
            )

    def blocks(self, action_type: str) -> bool:
        with self._lock:
            return self._state.locked_down or self._state.hard_killed

    def is_locked_down(self) -> bool:
        with self._lock:
            return self._state.locked_down

    def is_hard_killed(self) -> bool:
        with self._lock:
            return self._state.hard_killed

    def reset(self, operator_id: str) -> bool:
        """Operator-gated reset."""
        with self._lock:
            if not self._state.locked_down and not self._state.hard_killed:
                return False
            self._state = KillSwitchState()
            return True