from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.adapter_protocol import HostDeclaration
from src.law_ledger import LawLedger
from src.mutation_gate import MutationGate
from src.runtime_law import RuntimeLaw
from src.law_context_builder import RuntimeLawContext


class MutationGateTests(unittest.TestCase):
    def test_mutation_rejection_without_lineage_review_and_verification(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="mutation-gate-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        gate = MutationGate(ledger=LawLedger(root / "ledger.jsonl"), observation_blocked=lambda _: False)
        context = RuntimeLawContext(
            request_id="alpha",
            actor="api",
            claimed_identity="api",
            lineage="",
            legitimacy_token="token",
            requested_scope="workspace_mutation",
            allowed_scopes=frozenset({"workspace_mutation"}),
            state_present=True,
            code_present=True,
            verification_present=False,
            route_name="file_write",
            target="target.py",
            session_id="alpha",
            host_name="aris-runtime",
            host_version="1.0",
            host_attested=True,
            identity_verified=True,
            repo_changed=True,
            protected_target=False,
            action_type="file_write",
            caller_claims=(),
        )
        admission = gate.review(context=context, action={"operator_decision": "pending"})
        self.assertFalse(admission.allowed)
        self.assertIn("add_lineage", admission.required_recovery)
        self.assertIn("obtain_review", admission.required_recovery)

    def test_boundary_overreach_is_rejected(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="mutation-boundary-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        runtime_law = RuntimeLaw(repo_root=root, runtime_root=root / "law")
        preflight = runtime_law.preflight_action(
            {
                "action_id": "beta",
                "action_type": "foundation_mutation",
                "purpose": "Rewrite foundational law.",
                "target": "UL_ROOT_LAW_LOCKED",
                "session_id": "beta",
                "source": "api",
            },
            actor="api",
            route_name="foundation_mutation",
            repo_changed=True,
            protected_target=True,
        )
        self.assertFalse(preflight.allowed)
        self.assertIn(preflight.disposition, {"degraded", "rejected"})
