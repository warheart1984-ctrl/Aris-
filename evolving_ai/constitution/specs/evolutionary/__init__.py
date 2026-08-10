"""Constitutional Specification: Evolutionary Engines.

This specification defines the laws that any evolutionary engine must satisfy
to be considered constitutionally conformant.

CCM provides: Contract, Law, Evidence, Lifecycle, Verification protocols.
This spec provides: EngineContract, GenomeContract, TaskContract, ArchiveContract.
"""

from .contracts.engine import (
    EngineContract,
    ContractResult,
    EvidenceBundle,
    ProvenanceTrace,
    DeterministicReplay,
    ConformanceSuite,
)

from .contracts.engine_impl import StandardEngineContract

__all__ = [
    "EngineContract",
    "ContractResult",
    "EvidenceBundle",
    "ProvenanceTrace",
    "DeterministicReplay",
    "ConformanceSuite",
    "StandardEngineContract",
]