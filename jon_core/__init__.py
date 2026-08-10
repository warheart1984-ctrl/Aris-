"""Jon Core - Constitutional Runtime Kernel.

Immutable axioms (Λ), protocols (SpeechChain, CISIV, Δ), and governed services.
"""

__version__ = "0.1.0"

from .laws import (
    DeterminismEnforcer,
    AuditEmitter,
    AppendOnlyAuditEmitter,
    CircuitBreaker,
    CircuitState,
    IdentityBoundaryEnforcer,
    IdentityLeakDetector,
    DriftMonitor,
    DriftScore,
    InterruptHandler,
    KillSwitch,
    SupremacyValidator,
    OverrideLockout,
)

from .protocols import (
    SpeechChain,
    SpeechPhase,
    CISIVGovernanceModel,
    CISIVStage,
    StateMachineEngine,
    SystemState,
    ConvergenceOrchestrator,
    HealthVectorEngine,
)

from .services import (
    MutationGate,
    MutationAdmission,
    MutationBroker,
    HallRouter,
    HallEntry,
    HallType,
    OverrideReckoning,
    OverrideRecord,
    ShieldOfTruth,
    ShieldVerdict,
    LawLedger,
    FoundationStore,
    IdentityRegistry,
    ContractRegistry,
    ModuleLifecycleEngine,
)

from .contexts import (
    RuntimeLawContext,
    HostDeclaration,
    AdapterBindingResult,
    LawPreflightResult,
    PostExecuteResult,
    CISIVStageStatus,
    CISIVGovernanceStatus,
)

__all__ = [
    # Laws
    "DeterminismEnforcer",
    "AuditEmitter",
    "AppendOnlyAuditEmitter",
    "CircuitBreaker",
    "CircuitState",
    "IdentityBoundaryEnforcer",
    "IdentityLeakDetector",
    "DriftMonitor",
    "DriftScore",
    "InterruptHandler",
    "KillSwitch",
    "SupremacyValidator",
    "OverrideLockout",
    # Protocols
    "SpeechChain",
    "SpeechPhase",
    "CISIVGovernanceModel",
    "CISIVStage",
    "StateMachineEngine",
    "SystemState",
    "ConvergenceOrchestrator",
    "HealthVectorEngine",
    # Services
    "MutationGate",
    "MutationAdmission",
    "MutationBroker",
    "HallRouter",
    "HallEntry",
    "HallType",
    "OverrideReckoning",
    "OverrideRecord",
    "ShieldOfTruth",
    "ShieldVerdict",
    "LawLedger",
    "FoundationStore",
    "IdentityRegistry",
    "ContractRegistry",
    "ModuleLifecycleEngine",
    # Contexts
    "RuntimeLawContext",
    "HostDeclaration",
    "AdapterBindingResult",
    "LawPreflightResult",
    "PostExecuteResult",
    "CISIVStageStatus",
    "CISIVGovernanceStatus",
]