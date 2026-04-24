from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .adapter_protocol import AdapterProtocol
from .bootstrap_law import BootstrapLaw
from .cisiv import CISIVGovernanceModel
from .constants_runtime import CISIV_STAGE_SEQUENCE, SPEECH_CHAIN, UL_IDENTITY_SOURCE
from .foundation_store import FoundationStore
from .host_attestation import HostAttestation
from .identity_registry import IdentityRegistry
from .identity_verifier import IdentityVerifier
from .law_context_builder import LawContextBuilder
from .law_ledger import LawLedger
from .law_spine import LawSpine
from .mutation_broker import MutationBroker
from .mutation_gate import MutationGate
from .verification_engine import VerificationEngine


@dataclass(frozen=True, slots=True)
class RuntimePrimitiveInventory:
    identity_source: str
    governance_model: str
    binding_layer: str
    speech_chain: tuple[str, ...]
    core_primitives: tuple[str, ...]
    runtime_laws: tuple[str, ...]
    outside_core_bindings: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "identity_source": self.identity_source,
            "governance_model": self.governance_model,
            "binding_layer": self.binding_layer,
            "speech_chain": list(self.speech_chain),
            "core_primitives": list(self.core_primitives),
            "runtime_laws": list(self.runtime_laws),
            "outside_core_bindings": list(self.outside_core_bindings),
        }


class ULRuntimeSubstrate:
    def __init__(
        self,
        *,
        runtime_root: Path,
        observation_blocked: Callable[[str], bool],
    ) -> None:
        law_root = runtime_root / "law"
        self.inventory = RuntimePrimitiveInventory(
            identity_source=UL_IDENTITY_SOURCE,
            governance_model="CISIV",
            binding_layer="Universal Adapter Protocol",
            speech_chain=SPEECH_CHAIN,
            core_primitives=(
                "law_spine",
                "bootstrap_law",
                "law_ledger",
                "foundation_store",
                "adapter_protocol",
                "host_attestation",
                "identity_registry",
                "identity_verifier",
                "law_context_builder",
                "cisiv_governance",
                "mutation_gate",
                "mutation_broker",
                "verification_engine",
            ),
            runtime_laws=(
                "identity",
                "structure",
                "formation_cisiv",
                "speech_0001_1000_1001",
                "verification",
                "lineage",
                "boundaries",
                "legitimacy_non_copy",
                "execution",
                "containment_degradation",
            ),
            outside_core_bindings=(
                "http_api_bridge",
                "jarvis_operator_binding",
                "forge_binding",
                "forge_eval_binding",
            ),
        )
        self.adapter_protocol = AdapterProtocol()
        self.law_spine = LawSpine()
        self.bootstrap = BootstrapLaw(spine=self.law_spine)
        self.ledger = LawLedger(law_root / "law_ledger.jsonl")
        self.foundation_store = FoundationStore(law_root)
        self.host_attestation = HostAttestation(protocol=self.adapter_protocol)
        self.identity_registry = IdentityRegistry()
        self.identity_verifier = IdentityVerifier(self.identity_registry)
        self.context_builder = LawContextBuilder(
            host_attestation=self.host_attestation,
            identity_verifier=self.identity_verifier,
        )
        self.cisiv = CISIVGovernanceModel()
        self.mutation_gate = MutationGate(
            ledger=self.ledger,
            observation_blocked=observation_blocked,
        )
        self.mutation_broker = MutationBroker(gate=self.mutation_gate, ledger=self.ledger)
        self.verification_engine = VerificationEngine(self.ledger)

    def primitive_inventory(self) -> RuntimePrimitiveInventory:
        return self.inventory

    def status_payload(self) -> dict[str, Any]:
        return {
            "inventory": self.inventory.payload(),
            "foundation_entries": sorted(self.foundation_store.entries().keys()),
            "cisiv_stage_sequence": list(CISIV_STAGE_SEQUENCE),
        }
