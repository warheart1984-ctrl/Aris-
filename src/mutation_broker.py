from __future__ import annotations

from .law_context_builder import RuntimeLawContext
from .law_ledger import LawLedger
from .mutation_gate import MutationAdmission, MutationGate


class MutationBroker:
    def __init__(self, *, gate: MutationGate, ledger: LawLedger) -> None:
        self.gate = gate
        self.ledger = ledger

    def admit(self, *, context: RuntimeLawContext, action: dict[str, object]) -> MutationAdmission:
        admission = self.gate.review(context=context, action=action)
        self.ledger.record(
            "mutation_admission",
            {
                "context": context.payload(),
                "admission": admission.payload(),
            },
            require_success=True,
        )
        return admission
