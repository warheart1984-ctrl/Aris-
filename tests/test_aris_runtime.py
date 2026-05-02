from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from evolving_ai.app.config import AppConfig
from evolving_ai.aris_runtime.runtime import ArisV2Runtime, build_runtime_for_profile
from evolving_ai.aris_runtime.server import create_app
from evolving_ai.aris_runtime.service import ArisRuntimeChatService


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-runtime-test"


def _patch_for(path: str, content: str = "value = 1\n") -> str:
    return "\n".join(
        [
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -0,0 +1 @@",
            f"+{content.rstrip()}",
        ]
    )


def _make_runtime(runtime_class=ArisV2Runtime):
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


def _make_service(profile_id: str = "v2") -> tuple[ArisRuntimeChatService, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"service-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    config = AppConfig.from_env(root)
    return ArisRuntimeChatService(config, profile_id=profile_id), root


@contextmanager
def _api_client(service: ArisRuntimeChatService):
    with patch("evolving_ai.aris_runtime.server._build_service", return_value=service):
        app = create_app()
        with TestClient(app) as client:
            yield client


class ArisRuntimeTests(unittest.TestCase):
    def test_invalid_profile_ids_fail_closed(self) -> None:
        runtime_root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
        runtime_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        with self.assertRaises(ValueError):
            build_runtime_for_profile(
                profile_id="demo",
                repo_root=REPO_ROOT,
                runtime_root=runtime_root,
            )

    def test_v2_runtime_exposes_evolving_engine_on_ul_runtime(self) -> None:
        runtime, runtime_root = _make_runtime(ArisV2Runtime)
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        health = runtime.health_payload()
        admission_contract = status["admission_contract"]

        self.assertTrue(status["startup_ready"])
        self.assertTrue(health["ok"])
        self.assertEqual(status["system_name"], "ARIS V2")
        self.assertEqual(status["runtime_profile"], "v2")
        self.assertTrue(status["forge"]["connected"])
        self.assertTrue(status["forge_eval"]["connected"])
        self.assertTrue(status["evolving_engine"]["active"])
        self.assertTrue(status["evolving_engine"]["admitted"])
        self.assertEqual(admission_contract["identity_source"], "UL")
        self.assertEqual(status["ul_runtime"]["primitive_inventory"]["binding_layer"], "Universal Adapter Protocol")

    def test_v2_forge_plan_is_governed_and_truthful(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        payload = runtime.forge_repo_plan(goal="Plan repo changes.")

        self.assertEqual(payload["runtime_profile"], "v2")
        self.assertTrue(payload["evolving_engine"]["active"])
        self.assertIn(payload["route"][2]["stage"], {"Forge", "Governance Review"})
        if payload["ok"]:
            self.assertNotIn("error", payload)
        else:
            self.assertIn("error", payload)


class ArisRuntimeApiTests(unittest.TestCase):
    def test_default_api_status_matches_v2_runtime_truth(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            response = client.get("/api/aris/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["system_name"], "ARIS V2")
        self.assertEqual(payload["runtime_profile"], "v2")
        self.assertTrue(payload["forge"]["connected"])
        self.assertTrue(payload["forge_eval"]["connected"])
        self.assertTrue(payload["evolving_engine"]["active"])

    def test_v2_service_status_surfaces_evolving_runtime(self) -> None:
        service, root = _make_service(profile_id="v2")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            response = client.get("/api/aris/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["system_name"], "ARIS V2")
        self.assertEqual(payload["runtime_profile"], "v2")
        self.assertTrue(payload["forge"]["connected"])
        self.assertTrue(payload["evolving_engine"]["active"])
