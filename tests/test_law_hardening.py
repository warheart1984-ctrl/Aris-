from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from evolving_ai.app.config import AppConfig
from evolving_ai.app.server import create_app
from evolving_ai.aris.runtime import ArisRuntime
from evolving_ai.aris.service import ArisChatService
from src.bootstrap_law import BootstrapLaw
from src.law_spine import LawSpine


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "law-hardening-test"


def _make_runtime() -> tuple[ArisRuntime, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    runtime_root.mkdir(parents=True, exist_ok=True)
    return ArisRuntime(repo_root=REPO_ROOT, runtime_root=runtime_root), runtime_root


def _make_service() -> tuple[ArisChatService, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"service-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    config = AppConfig.from_env(root)
    return ArisChatService(config), root


@contextmanager
def _api_client(service: ArisChatService):
    with patch("evolving_ai.app.server._build_service", return_value=service):
        app = create_app()
        with TestClient(app) as client:
            yield client


class LawHardeningTests(unittest.TestCase):
    def test_identity_spoofing_rejected(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "api",
                "operator_decision": "recorded",
                "claimed_identity": "AAIS",
            }
        )
        self.assertFalse(decision.allowed)
        self.assertIn("identity", decision.reason.lower())

    def test_fake_verification_rejected(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "api",
                "operator_decision": "recorded",
            }
        )
        finalized = runtime.finalize_action(decision, result={"ok": True, "verified": True})
        self.assertFalse(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_discard")

    def test_host_legitimacy_spoof_rejected_by_api(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        with _api_client(service) as client:
            response = client.get(
                "/api/health",
                headers={
                    "x-aris-identity": "ARIS",
                    "x-aris-legitimacy-token": "trusted",
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_protected_identity_requires_identity_preserving_host_capabilities(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        token = runtime.runtime_law.host_attestation.issue_token(
            name="mirror-host",
            version="1.0",
            session_binding="alpha",
        )
        preflight = runtime.runtime_law.preflight_action(
            {
                "action_type": "snapshot_create",
                "purpose": "Mirror AAIS through an incomplete host binding.",
                "target": "snapshot-a",
                "session_id": "alpha",
                "lineage": "root/bootstrap",
                "host_name": "mirror-host",
                "host_version": "1.0",
                "host_capabilities": ["read"],
                "legitimacy_token": token,
                "host_class": "external",
            },
            actor="AAIS",
            route_name="snapshot_create",
            repo_changed=False,
            protected_target=False,
        )

        self.assertFalse(preflight.allowed)
        self.assertIn("identity-preserving", preflight.reason.lower())

    def test_repeated_override_attempts_escalate(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        severities = []
        for _ in range(3):
            preflight = runtime.runtime_law.preflight_action(
                {
                    "action_type": "snapshot_create",
                    "purpose": "Spoof protected identity.",
                    "target": "snapshot-a",
                    "session_id": "alpha",
                    "claimed_identity": "AAIS",
                },
                actor="api",
                route_name="snapshot_create",
                repo_changed=False,
                protected_target=False,
            )
            severities.append(preflight.override.severity if preflight.override else "none")
        self.assertEqual(severities, ["elevated", "high", "critical"])

    def test_ledger_omission_triggers_failure(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        with patch.object(runtime.runtime_law.ledger, "record", return_value={"recorded": False}):
            preflight = runtime.runtime_law.preflight_action(
                {
                    "action_type": "snapshot_create",
                    "purpose": "Test ledger omission.",
                    "target": "snapshot-a",
                    "session_id": "alpha",
                },
                actor="api",
                route_name="snapshot_create",
            )
        self.assertFalse(preflight.allowed)
        self.assertIn("ledger", preflight.reason.lower())

    def test_integrity_change_detected_after_boot(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        runtime.runtime_law.bootstrap_state = BootstrapLaw(spine=LawSpine(expected_hash="bad")).load()
        preflight = runtime.runtime_law.preflight_action(
            {
                "action_type": "snapshot_create",
                "purpose": "Test integrity drift.",
                "target": "snapshot-a",
                "session_id": "alpha",
            },
            actor="api",
            route_name="snapshot_create",
        )
        self.assertFalse(preflight.allowed)
        self.assertEqual(preflight.disposition, "degraded")
