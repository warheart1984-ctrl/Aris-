from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.bootstrap_law import BootstrapLaw
from src.host_attestation import HostAttestation
from src.law_context_builder import LawContextBuilder
from src.law_ledger import LawLedger
from src.law_spine import LawSpine
from src.ul_runtime import ULRuntimeSubstrate
from src.verification_engine import VerificationEngine


class LawSpineTests(unittest.TestCase):
    def test_root_law_integrity_boot_failure_behavior(self) -> None:
        state = BootstrapLaw(spine=LawSpine(expected_hash="bad-hash")).load()
        self.assertFalse(state.ok)
        self.assertEqual(state.disposition, "degraded")

    def test_speech_chain_rejection_when_1001_missing(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="law-spine-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        ledger = LawLedger(root / "ledger.jsonl")
        engine = VerificationEngine(ledger)
        builder = LawContextBuilder()
        host = HostAttestation().build_internal_host(
            name="aris-runtime",
            version="1.0",
            capabilities=("governance",),
            session_binding="alpha",
        )
        context = builder.build_action_context(
            {
                "action_id": "alpha",
                "action_type": "file_write",
                "purpose": "Write target.py",
                "target": "target.py",
                "session_id": "alpha",
                "code": "print('x')",
            },
            actor="api",
            route_name="file_write",
            host=host,
            repo_changed=True,
            protected_target=False,
        )
        report = engine.verify(
            context=context,
            result={"ok": True},
            repo_changed=True,
            payload_ok=True,
        )
        self.assertFalse(report.passed)
        self.assertEqual(report.speech_state, "1000")

    def test_ul_runtime_substrate_exposes_canonical_primitives(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ul-runtime-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        substrate = ULRuntimeSubstrate(
            runtime_root=root,
            observation_blocked=lambda _: False,
        )

        inventory = substrate.primitive_inventory().payload()

        self.assertEqual(inventory["identity_source"], "UL")
        self.assertEqual(inventory["governance_model"], "CISIV")
        self.assertEqual(inventory["binding_layer"], "Universal Adapter Protocol")
        self.assertIn("law_spine", inventory["core_primitives"])
        self.assertIn("http_api_bridge", inventory["outside_core_bindings"])
