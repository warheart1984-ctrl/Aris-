"""Evolving AI Constitutional Layer.

CCM (Constitutional Contract Model) - Meta-constitutional infrastructure shared across all specs.
Constitutional Specifications - Domain-specific contract sets (evolutionary, planning, symbolic, ...).
"""

# CCM - Meta-constitutional infrastructure
from .ccm import (
    ConstitutionalState,
    Transition,
    ConstitutionalEvent,
    ConstitutionalLifecycle,
    LifecycleRegistry,
    VerificationReport,
    EvidenceStore,
    verify_bundle,
)

# Specifications - Domain-specific contracts
from .specs.evolutionary import (
    EngineContract,
    ContractResult,
    EvidenceBundle,
    ProvenanceTrace,
    DeterministicReplay,
    ConformanceSuite,
    StandardEngineContract,
)

__all__ = [
    # CCM
    "ConstitutionalState",
    "Transition",
    "ConstitutionalEvent",
    "ConstitutionalLifecycle",
    "LifecycleRegistry",
    "VerificationReport",
    "EvidenceStore",
    "verify_bundle",
    # Evolutionary Specification
    "EngineContract",
    "ContractResult",
    "EvidenceBundle",
    "ProvenanceTrace",
    "DeterministicReplay",
    "ConformanceSuite",
    "StandardEngineContract",
]