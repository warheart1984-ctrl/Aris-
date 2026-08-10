"""Λ.7 SupremacyValidator + OverrideLockout - Pre-apply validation against Λ.1–Λ.7."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import hashlib
import json


class ValidationResult(Enum):
    ALLOWED = "allowed"
    REJECTED = "rejected"
    CONDITIONAL = "conditional"


@dataclass
class ValidationReport:
    """Report from SupremacyValidator."""
    result: ValidationResult
    reason: str
    violated_laws: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class OverrideLockout(Exception):
    """Raised when override is attempted but locked out."""
    pass


class SupremacyValidator:
    """Pre-apply validation of all config/deployment changes against Λ.1–Λ.7.
    
    No admin backdoor, no debug bypass.
    """
    
    def __init__(self):
        self._validators: Dict[str, Callable[[Any], ValidationReport]] = {}
        self._lockout_active = True  # Always active - no bypass

    def register_validator(self, law: str, validator: Callable[[Any], ValidationReport]) -> None:
        """Register validator for a constitutional law."""
        self._validators[law] = validator

    def validate(self, change: Any, context: Dict[str, Any]) -> ValidationReport:
        """Validate change against all registered constitutional laws."""
        violated = []
        conditions = []
        
        for law_name, validator in self._validators.items():
            try:
                report = validator(change)
                if report.result == ValidationResult.REJECTED:
                    violated.append(law_name)
                    conditions.extend(report.conditions)
                elif report.result == ValidationResult.CONDITIONAL:
                    conditions.extend(report.conditions)
            except Exception as e:
                violated.append(f"{law_name}: validator error - {e}")
        
        if violated:
            return ValidationReport(
                result=ValidationResult.REJECTED,
                reason=f"Violates constitutional laws: {', '.join(violated)}",
                violated_laws=violated,
                conditions=conditions,
                metadata={"change_hash": self._hash_change(change)},
            )
        
        if conditions:
            return ValidationReport(
                result=ValidationResult.CONDITIONAL,
                reason="Allowed with conditions",
                violated_laws=[],
                conditions=conditions,
                metadata={"change_hash": self._hash_change(change)},
            )
        
        return ValidationReport(
            result=ValidationResult.ALLOWED,
            reason="All constitutional laws satisfied",
            violated_laws=[],
            conditions=[],
            metadata={"change_hash": self._hash_change(change)},
        )

    def assert_valid(self, change: Any, context: Dict[str, Any]) -> ValidationReport:
        """Validate and raise if rejected."""
        report = self.validate(change, context)
        if report.result == ValidationResult.REJECTED:
            raise OverrideLockout(f"SupremacyValidator rejection: {report.reason}")
        return report

    def _hash_change(self, change: Any) -> str:
        """Hash change for audit trail."""
        if isinstance(change, dict):
            serialized = json.dumps(change, sort_keys=True, separators=(",", ":"))
        else:
            serialized = str(change)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    @property
    def lockout_active(self) -> bool:
        return self._lockout_active

    # No disable method - lockout is permanent per Λ.7