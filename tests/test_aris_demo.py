from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from evolving_ai.app.config import AppConfig
from evolving_ai.aris_demo.runtime import ArisDemoRuntime, ArisDemoV1Runtime, ArisDemoV2Runtime
from evolving_ai.aris_demo.server import create_app
from evolving_ai.aris_demo.service import ArisDemoChatService


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-demo-test"


def _patch_for(path: str, content: str = "value = 1\n") -> str:
    return "\n".join(
        [
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -0,0 +1 @@",
            f"+{content.rstrip()}",
        ]
    )


def _make_runtime(runtime_class=ArisDemoRuntime):
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    runtime_root.mkdir(parents=True, exist_ok=True)
    return (
        runtime_class(
            repo_root=REPO_ROOT,
            runtime_root=runtime_root,
        ),
        runtime_root,
    )


def _make_service(profile_id: str = "demo") -> tuple[ArisDemoChatService, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"service-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    config = AppConfig.from_env(root)
    return ArisDemoChatService(config, profile_id=profile_id), root


@contextmanager
def _api_client(service: ArisDemoChatService):
    with patch("evolving_ai.aris_demo.server._build_service", return_value=service):
        app = create_app()
        with TestClient(app) as client:
            yield client


class ArisDemoRuntimeTests(unittest.TestCase):
    def test_demo_boots_cleanly_without_forge(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        health = runtime.health_payload()

        self.assertTrue(status["startup_ready"])
        self.assertTrue(health["ok"])
        self.assertEqual(status["system_name"], "ARIS Demo")
        self.assertEqual(status["runtime_profile"], "demo")
        self.assertTrue(status["demo_mode"]["active"])
        self.assertFalse(status["forge"]["connected"])
        self.assertFalse(status["forge_eval"]["connected"])
        self.assertFalse(status["evolving_engine"]["active"])

    def test_v1_runtime_exposes_forge_without_evolving_engine(self) -> None:
        runtime, runtime_root = _make_runtime(ArisDemoV1Runtime)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        health = runtime.health_payload()

        self.assertTrue(status["startup_ready"])
        self.assertTrue(health["ok"])
        self.assertEqual(status["system_name"], "ARIS Demo V1")
        self.assertEqual(status["runtime_profile"], "v1")
        self.assertFalse(status["demo_mode"]["active"])
        self.assertTrue(status["forge"]["connected"])
        self.assertTrue(status["forge_eval"]["connected"])
        self.assertFalse(status["evolving_engine"]["active"])
        self.assertIn("Forge", status["demo_mode"]["route"])

    def test_v2_runtime_exposes_evolving_engine_on_ul_runtime(self) -> None:
        runtime, runtime_root = _make_runtime(ArisDemoV2Runtime)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        health = runtime.health_payload()
        admission_contract = status["admission_contract"]

        self.assertTrue(status["startup_ready"])
        self.assertTrue(health["ok"])
        self.assertEqual(status["system_name"], "ARIS Demo V2")
        self.assertEqual(status["runtime_profile"], "v2")
        self.assertTrue(status["forge"]["connected"])
        self.assertTrue(status["forge_eval"]["connected"])
        self.assertTrue(status["evolving_engine"]["active"])
        self.assertTrue(status["evolving_engine"]["admitted"])
        self.assertEqual(admission_contract["identity_source"], "UL")
        self.assertEqual(status["ul_runtime"]["primitive_inventory"]["binding_layer"], "Universal Adapter Protocol")

    def test_demo_blocks_risky_repo_change_without_forge_eval(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "demo-alpha",
                "purpose": "Attempt a repo mutation inside demo mode.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("target.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_forge_eval)
        self.assertEqual(decision.hall_name, "hall_of_discard")

    def test_demo_forge_plan_is_explicitly_stripped(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        payload = runtime.forge_repo_plan(goal="Plan repo changes.")

        self.assertFalse(payload["ok"])
        self.assertIn("stripped", payload["error"].lower())
        self.assertEqual(payload["route"][2]["stage"], "Governance Review")


class ArisDemoApiTests(unittest.TestCase):
    def test_demo_api_status_matches_demo_runtime_truth(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            response = client.get("/api/aris/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["system_name"], "ARIS Demo")
        self.assertTrue(payload["demo_mode"]["active"])
        self.assertFalse(payload["forge"]["connected"])
        self.assertFalse(payload["forge_eval"]["connected"])
        self.assertFalse(payload["evolving_engine"]["active"])

    def test_v2_service_status_surfaces_evolving_runtime(self) -> None:
        service, root = _make_service(profile_id="v2")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            response = client.get("/api/aris/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["system_name"], "ARIS Demo V2")
        self.assertEqual(payload["runtime_profile"], "v2")
        self.assertTrue(payload["forge"]["connected"])
        self.assertTrue(payload["evolving_engine"]["active"])
