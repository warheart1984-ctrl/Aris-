"""Contexts - Canonical data structures for Reference Architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass(frozen=True, slots=True)
class HostDeclaration:
    """Host declaration for Universal Adapter Protocol."""
    name: str
    version: str
    capabilities: List[str]
    legitimacy_token: str
    session_binding: str
    host_class: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterBindingResult:
    """Result of adapter binding evaluation."""
    allowed: bool
    reason: str
    identity_preserving: bool
    declared_capabilities: List[str]
    required_capabilities: List[str]
    missing_capabilities: List[str]
    host_class: str


@dataclass(frozen=True, slots=True)
class RuntimeLawContext:
    """Frozen, slotted immutable context for law enforcement."""
    identity: str
    scope: str
    speech: str  # 0001, 1000, 1001
    host: str
    verification: Dict[str, Any]
    action: Dict[str, Any]
    caller_claims: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def payload(self) -> Dict[str, Any]:
        """Serialize for hashing/lineage."""
        return {
            "identity": self.identity,
            "scope": self.scope,
            "speech": self.speech,
            "host": self.host,
            "verification": self.verification,
            "action": self.action,
            "caller_claims": self.caller_claims,
            "timestamp": self.timestamp,
        }

    def lineage_hash(self) -> str:
        """Derive lineage via SHA256."""
        import hashlib
        import json
        content = json.dumps(self.payload(), sort_keys=True)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LawPreflightResult:
    """Preflight validation result."""
    allowed: bool
    disposition: str  # allowed, rejected, conditional
    reason: str
    context: RuntimeLawContext
    derived_flags: Dict[str, Any] = field(default_factory=dict)
    override: Optional[Dict[str, Any]] = None
    mutation_admission: Optional[Dict[str, Any]] = None
    cisiv: Optional[Dict[str, Any]] = None


@dataclass(frozen=True, slots=True)
class PostExecuteResult:
    """Post-execution result."""
    report: Dict[str, Any]
    override: Optional[Dict[str, Any]] = None
    cisiv: Optional[Dict[str, Any]] = None


@dataclass(frozen=True, slots=True)
class CISIVStageStatus:
    """CISIV stage status."""
    stage: str
    status: str  # satisfied, blocked, pending
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CISIVGovernanceStatus:
    """CISIV overall governance status."""
    phase: str
    lawful: bool
    reason: str
    stages: List[CISIVStageStatus] = field(default_factory=list)