from __future__ import annotations

import os
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from evolving_ai.app.config import AppConfig
from evolving_ai.app.model_switchboard import ModelSwitchboard
from evolving_ai.app.server import _build_service, create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "model-switchboard-tests"


def _case_root(prefix: str) -> Path:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"{prefix}-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class ModelSwitchboardTests(unittest.TestCase):
    def test_auto_routes_general_coding_and_light_coding(self) -> None:
        root = _case_root("route")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        with patch.dict(
            os.environ,
            {
                "GENERAL_MODEL": "gemma3:12b",
                "CODING_MODEL": "devstral",
                "LIGHT_CODING_MODEL": "qwen2.5-coder:7b",
            },
            clear=False,
        ):
            config = AppConfig.from_env(root)
            switchboard = ModelSwitchboard(
                config,
                state_path=root / ".forge_chat" / "model-switchboard.json",
            )

            general = switchboard.choose(
                prompt="Explain the current workspace strategy to me.",
                fast_mode=False,
                mode="chat",
                attachments=[],
            )
            coding = switchboard.choose(
                prompt="Build the patch, edit the file, and run the tests.",
                fast_mode=False,
                mode="agent",
                attachments=[],
            )
            light = switchboard.choose(
                prompt="Inspect the repo seams and review the changed code.",
                fast_mode=True,
                mode="chat",
                attachments=[],
            )

        self.assertEqual(general.model, "gemma3:12b")
        self.assertEqual(coding.model, "devstral")
        self.assertEqual(light.model, "qwen2.5-coder:7b")

    def test_manual_pin_overrides_auto_routing(self) -> None:
        root = _case_root("manual")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        with patch.dict(
            os.environ,
            {
                "GENERAL_MODEL": "gemma3:12b",
                "CODING_MODEL": "devstral",
                "LIGHT_CODING_MODEL": "qwen2.5-coder:7b",
            },
            clear=False,
        ):
            config = AppConfig.from_env(root)
            state_path = root / ".forge_chat" / "model-switchboard.json"
            switchboard = ModelSwitchboard(config, state_path=state_path)
            switchboard.set_mode(mode="manual", pinned_system="general")

            decision = switchboard.choose(
                prompt="Build a patch and run tests.",
                fast_mode=False,
                mode="agent",
                attachments=[],
            )
            reloaded = ModelSwitchboard(config, state_path=state_path).status_payload()

        self.assertEqual(decision.model, "gemma3:12b")
        self.assertEqual(decision.selection_mode, "manual")
        self.assertEqual(reloaded["mode"], "manual")
        self.assertEqual(reloaded["pinned_system"], "general")


class ModelSwitchboardApiTests(unittest.TestCase):
    def test_config_and_update_endpoint_expose_router(self) -> None:
        root = _case_root("api")
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        original_cwd = Path.cwd()
        original_env = dict(os.environ)
        try:
            os.chdir(root)
            os.environ["FORGE_PROVIDER_MODE"] = "mock"
            os.environ["FORGE_EXECUTION_BACKEND"] = "local"
            os.environ["GENERAL_MODEL"] = "gemma3:12b"
            os.environ["CODING_MODEL"] = "devstral"
            os.environ["LIGHT_CODING_MODEL"] = "qwen2.5-coder:7b"
            _build_service.cache_clear()
            with TestClient(create_app()) as client:
                config_response = client.get("/api/config")
                self.assertEqual(config_response.status_code, 200)
                config_payload = config_response.json()
                self.assertEqual(config_payload["model_router"]["mode"], "auto")

                update_response = client.post(
                    "/api/model-router",
                    json={"mode": "manual", "pinned_system": "coding"},
                )
                self.assertEqual(update_response.status_code, 200)
                update_payload = update_response.json()
                self.assertTrue(update_payload["ok"])
                self.assertEqual(update_payload["model_router"]["pinned_system"], "coding")

                next_config = client.get("/api/config").json()
                self.assertEqual(next_config["model_router"]["pinned_system"], "coding")
        finally:
            _build_service.cache_clear()
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)
