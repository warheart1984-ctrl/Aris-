"""Interfaces - Reference Architecture protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from jon_core.contexts import RuntimeLawContext, LawPreflightResult, PostExecuteResult, CISIVGovernanceStatus


class GovernanceAware(ABC):
    """All modules must implement."""
    
    @abstractmethod
    def get_contract(self) -> Dict[str, Any]:
        """Return module contract."""
        pass

    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input against contract."""
        pass

    @abstractmethod
    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output against contract."""
        pass

    @abstractmethod
    def report_drift(self, drift_data: Dict[str, Any]) -> None:
        """Report drift to HealthVectorEngine."""
        pass

    @abstractmethod
    def accept_interrupt(self, interrupt: Dict[str, Any]) -> bool:
        """Accept and handle interrupt."""
        pass


class AuditEmitter(ABC):
    """Tamper-evident audit chain."""
    
    @abstractmethod
    def emit_record(self, event_type: str, payload: Dict[str, Any]) -> str:
        """Emit audit record, return record hash."""
        pass

    @abstractmethod
    def query_by_module(self, module: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def query_by_time_range(self, start: float, end: float) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def verify_chain_integrity(self) -> tuple[bool, List[str]]:
        pass


class HealthReporter(ABC):
    """Dimensional health reporting."""
    
    @abstractmethod
    def report_health(self) -> Dict[str, float]:
        """Return dimensional health: module, lane, agent, system."""
        pass

    @abstractmethod
    def get_drift_scores(self) -> Dict[str, float]:
        pass

    @abstractmethod
    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        pass


class StateAware(ABC):
    """Δ State machine integration."""
    
    @abstractmethod
    def get_current_state(self) -> str:
        pass

    @abstractmethod
    def request_transition(self, target_state: str, reason: str) -> bool:
        pass

    @abstractmethod
    def get_transition_history(self) -> List[Dict[str, Any]]:
        pass


class Convergeable(ABC):
    """Δ Convergence protocol."""
    
    @abstractmethod
    def prepare_for_convergence(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute_recovery_action(self, action: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def verify_post_recovery(self) -> bool:
        pass

    @abstractmethod
    def rollback(self) -> bool:
        pass


class HealthContributor(ABC):
    """HealthVector sources."""
    
    @abstractmethod
    def get_dimensional_health(self) -> Dict[str, float]:
        pass

    @abstractmethod
    def get_drift_scores(self) -> Dict[str, float]:
        pass

    @abstractmethod
    def get_contract_compliance_percentage(self) -> float:
        pass


class OperatorGated(ABC):
    """Operator checkpoint integration."""
    
    @abstractmethod
    def generate_checkpoint_report(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def await_operator_decision(self, timeout_seconds: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def apply_operator_modification(self, modification: Dict[str, Any]) -> bool:
        pass


class LawBoundForgeClient(ABC):
    """Client contract for Forge operations."""
    
    @abstractmethod
    def plan_repo(self, goal: str, focus_paths: List[str], operation_mode: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def apply_patch(self, patch: str, target: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute_command(self, cmd: str, target: str) -> Dict[str, Any]:
        pass


class LawBoundForgeEvalClient(ABC):
    """Client contract for ForgeEval verification."""
    
    @abstractmethod
    def evaluate(self, request_payload: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        """Returns (response, status_code)."""
        pass