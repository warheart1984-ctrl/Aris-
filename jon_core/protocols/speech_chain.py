"""SpeechChain Protocol - Codify SpeechChain(0001→1000→1001) as executable state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time


class SpeechPhase(Enum):
    """Speech Chain phases."""
    PHASE_0001 = "0001"  # Intent declaration
    PHASE_1000 = "1000"  # Verification
    PHASE_1001 = "1001"  # Finalization


@dataclass
class SpeechState:
    """Current state in the speech chain."""
    current_phase: SpeechPhase = SpeechPhase.PHASE_0001
    intent: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None
    finalization: Optional[Dict[str, Any]] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


class SpeechChain:
    """Executable state machine for SpeechChain(0001→1000→1001).
    
    Enforced at GRE EXECUTION_SANDBOX stage.
    """
    
    VALID_TRANSITIONS = {
        SpeechPhase.PHASE_0001: [SpeechPhase.PHASE_1000],
        SpeechPhase.PHASE_1000: [SpeechPhase.PHASE_1001],
        SpeechPhase.PHASE_1001: [],  # Terminal
    }

    def __init__(self):
        self._state = SpeechState()
        self._phase_handlers: Dict[SpeechPhase, List[Callable[[Dict[str, Any]], Dict[str, Any]]]] = {
            phase: [] for phase in SpeechPhase
        }
        self._transition_callbacks: List[Callable[[SpeechPhase, SpeechPhase], None]] = []

    def register_phase_handler(self, phase: SpeechPhase, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Register handler for a speech phase."""
        self._phase_handlers[phase].append(handler)

    def register_transition_callback(self, callback: Callable[[SpeechPhase, SpeechPhase], None]) -> None:
        """Register callback for phase transitions."""
        self._transition_callbacks.append(callback)

    def declare_intent(self, intent: Dict[str, Any]) -> SpeechState:
        """Phase 0001: Declare intent."""
        if self._state.current_phase != SpeechPhase.PHASE_0001:
            raise ValueError(f"Invalid phase for intent declaration: {self._state.current_phase}")
        
        self._state.intent = intent
        # Execute phase handlers
        for handler in self._phase_handlers[SpeechPhase.PHASE_0001]:
            result = handler(intent)
            self._state.intent.update(result)
        
        return self._state

    def verify(self, verification: Dict[str, Any]) -> SpeechState:
        """Phase 1000: Verify."""
        self._transition(SpeechPhase.PHASE_1000)
        
        self._state.verification = verification
        for handler in self._phase_handlers[SpeechPhase.PHASE_1000]:
            result = handler(verification)
            self._state.verification.update(result)
        
        return self._state

    def finalize(self, finalization: Dict[str, Any]) -> SpeechState:
        """Phase 1001: Finalize."""
        self._transition(SpeechPhase.PHASE_1001)
        
        self._state.finalization = finalization
        self._state.completed_at = time.time()
        for handler in self._phase_handlers[SpeechPhase.PHASE_1001]:
            result = handler(finalization)
            self._state.finalization.update(result)
        
        return self._state

    def _transition(self, new_phase: SpeechPhase) -> None:
        old_phase = self._state.current_phase
        if new_phase not in self.VALID_TRANSITIONS.get(old_phase, []):
            raise ValueError(f"Invalid transition: {old_phase.value} -> {new_phase.value}")
        
        self._state.current_phase = new_phase
        for callback in self._transition_callbacks:
            try:
                callback(old_phase, new_phase)
            except Exception:
                pass

    def get_state(self) -> SpeechState:
        return self._state

    def is_complete(self) -> bool:
        return self._state.current_phase == SpeechPhase.PHASE_1001

    def reset(self) -> None:
        """Reset to initial state."""
        self._state = SpeechState()


# Contract tests for each phase transition
def test_speech_chain_transitions():
    """Contract tests for SpeechChain phase transitions."""
    chain = SpeechChain()
    
    # Test 0001 -> 1000
    state = chain.declare_intent({"action": "test", "target": "module"})
    assert state.current_phase == SpeechPhase.PHASE_0001
    assert state.intent is not None
    
    state = chain.verify({"verified": True, "checks": ["check1"]})
    assert state.current_phase == SpeechPhase.PHASE_1000
    assert state.verification is not None
    
    # Test 1000 -> 1001
    state = chain.finalize({"finalized": True, "artifact_hash": "abc123"})
    assert state.current_phase == SpeechPhase.PHASE_1001
    assert state.finalization is not None
    assert state.completed_at is not None
    assert chain.is_complete()
    
    # Test invalid transition
    chain2 = SpeechChain()
    chain2.declare_intent({"action": "test"})
    try:
        chain2.finalize({})  # Skip 1000
        assert False, "Should have raised"
    except ValueError:
        pass
    
    print("All SpeechChain contract tests passed")


if __name__ == "__main__":
    test_speech_chain_transitions()