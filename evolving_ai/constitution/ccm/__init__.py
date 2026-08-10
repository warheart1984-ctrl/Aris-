"""CCM (Constitutional Contract Model) - Meta-constitutional infrastructure.

This layer is shared across ALL constitutional specifications.
It defines the ontology, relations, semantics, lifecycle, and evidence protocol
that every specification must use.
"""

from .state.lifecycle import (
    ConstitutionalState,
    Transition,
    ConstitutionalEvent,
    ConstitutionalLifecycle,
    LifecycleRegistry,
)

from .evidence.verification import (
    VerificationReport,
    EvidenceStore,
    verify_bundle,
)

__all__ = [
    # State
    "ConstitutionalState",
    "Transition",
    "ConstitutionalEvent",
    "ConstitutionalLifecycle",
    "LifecycleRegistry",
    # Evidence
    "VerificationReport",
    "EvidenceStore",
    "verify_bundle",
]