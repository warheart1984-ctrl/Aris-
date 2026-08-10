"""ModuleLifecycleEngine - 6 phases with validation gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import threading
import time


class ModulePhase(Enum):
    """Module lifecycle phases."""
    REGISTRATION = "registration"
    INITIALIZATION = "initialization"
    ACTIVATION = "activation"
    OPERATION = "operation"
    SUSPENSION = "suspension"
    TERMINATION = "termination"


@dataclass
class ModuleState:
    """Module lifecycle state."""
    module_name: str
    phase: ModulePhase = ModulePhase.REGISTRATION
    config: Dict[str, Any] = field(default_factory=dict)
    health: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    last_transition: Optional[float] = None
    operator_checkpoint_id: Optional[str] = None


class ModuleLifecycleEngine:
    """6 phases: REGISTRATION(validation-gated) → INITIALIZATION(sandbox+audit+breaker) 
    → ACTIVATION(Operator checkpoint) → OPERATION(GRE pipeline) → SUSPENSION(Operator/auto) 
    → TERMINATION(Operator explicit); reversible except TERMINATION."""
    
    VALID_TRANSITIONS = {
        ModulePhase.REGISTRATION: [ModulePhase.INITIALIZATION],
        ModulePhase.INITIALIZATION: [ModulePhase.ACTIVATION, ModulePhase.SUSPENSION],
        ModulePhase.ACTIVATION: [ModulePhase.OPERATION, ModulePhase.SUSPENSION],
        ModulePhase.OPERATION: [ModulePhase.SUSPENSION, ModulePhase.TERMINATION],
        ModulePhase.SUSPENSION: [ModulePhase.INITIALIZATION, ModulePhase.TERMINATION],
        ModulePhase.TERMINATION: [],  # Terminal
    }

    REVERSIBLE_PHASES = {
        ModulePhase.REGISTRATION,
        ModulePhase.INITIALIZATION,
        ModulePhase.ACTIVATION,
        ModulePhase.OPERATION,
        ModulePhase.SUSPENSION,
    }

    def __init__(self):
        self._modules: Dict[str, ModuleState] = {}
        self._lock = threading.RLock()
        self._phase_validators: Dict[ModulePhase, Callable[[ModuleState], bool]] = {}
        self._phase_hooks: Dict[ModulePhase, List[Callable[[ModuleState], None]]] = {}
        self._default_validators()
        self._default_hooks()

    def _default_validators(self) -> None:
        self._phase_validators[ModulePhase.REGISTRATION] = lambda s: bool(s.config.get("contract_validated"))
        self._phase_validators[ModulePhase.INITIALIZATION] = lambda s: bool(s.config.get("sandbox_ready"))
        self._phase_validators[ModulePhase.ACTIVATION] = lambda s: bool(s.operator_checkpoint_id)
        self._phase_validators[ModulePhase.OPERATION] = lambda s: bool(s.health.get("gre_ready"))

    def _default_hooks(self) -> None:
        for phase in ModulePhase:
            self._phase_hooks[phase] = []

    def register_validator(self, phase: ModulePhase, validator: Callable[[ModuleState], bool]) -> None:
        self._phase_validators[phase] = validator

    def register_hook(self, phase: ModulePhase, hook: Callable[[ModuleState], None]) -> None:
        self._phase_hooks[phase].append(hook)

    def register_module(self, module_name: str, config: Dict[str, Any]) -> ModuleState:
        with self._lock:
            if module_name in self._modules:
                raise ValueError(f"Module {module_name} already registered")
            
            state = ModuleState(module_name=module_name, config=config)
            self._modules[module_name] = state
            
            # Run REGISTRATION validators
            if not self._validate_phase(state, ModulePhase.REGISTRATION):
                raise ValueError(f"Module {module_name} failed REGISTRATION validation")
            
            self._run_hooks(state, ModulePhase.REGISTRATION)
            return state

    def transition(self, module_name: str, target_phase: ModulePhase, operator_id: Optional[str] = None) -> ModuleState:
        with self._lock:
            state = self._modules.get(module_name)
            if not state:
                raise ValueError(f"Module {module_name} not found")
            
            # Validate transition
            valid_targets = self.VALID_TRANSITIONS.get(state.phase, [])
            if target_phase not in valid_targets:
                raise ValueError(f"Invalid transition: {state.phase.value} -> {target_phase.value}")
            
            # Check if reversible
            if state.phase == ModulePhase.TERMINATION:
                raise ValueError("TERMINATION is irreversible")
            
            # Validate target phase
            if not self._validate_phase(state, target_phase):
                raise ValueError(f"Module {module_name} failed {target_phase.value} validation")
            
            # Handle ACTIVATION checkpoint
            if target_phase == ModulePhase.ACTIVATION:
                if not operator_id or not operator_id.startswith("operator_"):
                    raise ValueError("ACTIVATION requires operator checkpoint")
                state.operator_checkpoint_id = operator_id
            
            old_phase = state.phase
            state.phase = target_phase
            state.last_transition = time.time()
            
            if target_phase == ModulePhase.OPERATION:
                state.started_at = time.time()
            
            self._run_hooks(state, target_phase)
            
            return state

    def _validate_phase(self, state: ModuleState, phase: ModulePhase) -> bool:
        validator = self._phase_validators.get(phase)
        if validator:
            return validator(state)
        return True

    def _run_hooks(self, state: ModuleState, phase: ModulePhase) -> None:
        for hook in self._phase_hooks.get(phase, []):
            try:
                hook(state)
            except Exception:
                pass

    def get_state(self, module_name: str) -> Optional[ModuleState]:
        with self._lock:
            return self._modules.get(module_name)

    def is_reversible(self, module_name: str) -> bool:
        with self._lock:
            state = self._modules.get(module_name)
            if not state:
                return False
            return state.phase in self.REVERSIBLE_PHASES

    def list_modules(self) -> List[ModuleState]:
        with self._lock:
            return list(self._modules.values())