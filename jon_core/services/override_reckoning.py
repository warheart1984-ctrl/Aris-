"""OverrideReckoning - Escalating cost/severity tracking with quarantine for foundational."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import time
import uuid


class OverrideKind(Enum):
    """Override kind."""
    LAW_BYPASS = "law_bypass"
    CONFIG_CHANGE = "config_change"
    DEPLOYMENT_CHANGE = "deployment_change"
    IDENTITY_ASSUMPTION = "identity_assumption"
    PROTECTED_TARGET = "protected_target"


class OverrideSeverity(Enum):
    """Override severity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    QUARANTINE = "quarantine"


@dataclass
class OverrideRecord:
    """Record of an override."""
    override_id: str
    kind: OverrideKind
    identity: str
    route: str
    scope: str
    reason: str
    foundational: bool
    cost: int
    severity: OverrideSeverity
    timestamp: float = field(default_factory=time.time)
    recovery_actions: Tuple[str, ...] = field(default_factory=tuple)
    actor: str = ""


class OverrideReckoning:
    """Track overrides by composite key with escalating cost/severity."""
    
    BASE_COST = 10
    ESCALATION_COST = 5
    FOUNDATIONAL_PENALTY = 20
    
    def __init__(self):
        self._records: Dict[str, List[OverrideRecord]] = {}  # composite_key -> records
        self._severity_thresholds = {
            OverrideSeverity.LOW: (0, 15),
            OverrideSeverity.MEDIUM: (15, 30),
            OverrideSeverity.HIGH: (30, 50),
            OverrideSeverity.CRITICAL: (50, 100),
            OverrideSeverity.QUARANTINE: (100, float('inf')),
        }

    def _composite_key(self, kind: OverrideKind, identity: str, route: str, scope: str) -> str:
        return f"{kind.value}:{identity}:{route}:{scope}"

    def record(
        self,
        kind: OverrideKind,
        context: Dict[str, Any],
        reason: str,
        foundational: bool = False,
        actor: str = "",
    ) -> OverrideRecord:
        """Record an override and compute escalating cost/severity."""
        identity = context.get("identity", "unknown")
        route = context.get("route", "unknown")
        scope = context.get("scope", "unknown")
        
        key = self._composite_key(kind, identity, route, scope)
        existing = self._records.get(key, [])
        
        count = len(existing) + 1
        cost = self.BASE_COST + (count - 1) * self.ESCALATION_COST
        if foundational:
            cost += self.FOUNDATIONAL_PENALTY
        
        severity = self._compute_severity(cost, foundational)
        recovery_actions = self._determine_recovery_actions(severity, foundational)
        
        record = OverrideRecord(
            override_id=str(uuid.uuid4())[:8],
            kind=kind,
            identity=identity,
            route=route,
            scope=scope,
            reason=reason,
            foundational=foundational,
            cost=cost,
            severity=severity,
            recovery_actions=tuple(recovery_actions),
            actor=actor,
        )
        
        if key not in self._records:
            self._records[key] = []
        self._records[key].append(record)
        
        return record

    def _compute_severity(self, cost: int, foundational: bool) -> OverrideSeverity:
        if foundational:
            return OverrideSeverity.QUARANTINE
        
        for severity, (low, high) in self._severity_thresholds.items():
            if low <= cost < high:
                return severity
        return OverrideSeverity.QUARANTINE

    def _determine_recovery_actions(self, severity: OverrideSeverity, foundational: bool) -> List[str]:
        actions = []
        if severity in (OverrideSeverity.HIGH, OverrideSeverity.CRITICAL, OverrideSeverity.QUARANTINE):
            actions.append("operator_review_required")
        if severity in (OverrideSeverity.CRITICAL, OverrideSeverity.QUARANTINE):
            actions.append("automated_rollback")
        if severity == OverrideSeverity.QUARANTINE or foundational:
            actions.extend(["quarantine", "block_future_overrides"])
        return actions

    def get_records(self, kind: Optional[OverrideKind] = None, identity: Optional[str] = None) -> List[OverrideRecord]:
        results = []
        for records in self._records.values():
            for record in records:
                if kind and record.kind != kind:
                    continue
                if identity and record.identity != identity:
                    continue
                results.append(record)
        return results

    def get_composite_key_status(self, kind: OverrideKind, identity: str, route: str, scope: str) -> Dict[str, Any]:
        key = self._composite_key(kind, identity, route, scope)
        records = self._records.get(key, [])
        if not records:
            return {"count": 0, "total_cost": 0, "max_severity": OverrideSeverity.LOW.value}
        
        total_cost = sum(r.cost for r in records)
        max_severity = max(r.severity for r in records)
        
        return {
            "count": len(records),
            "total_cost": total_cost,
            "max_severity": max_severity.value,
            "foundational": any(r.foundational for r in records),
            "latest": records[-1].timestamp,
        }

    def is_quarantined(self, kind: OverrideKind, identity: str, route: str, scope: str) -> bool:
        status = self.get_composite_key_status(kind, identity, route, scope)
        return status["max_severity"] == OverrideSeverity.QUARANTINE.value