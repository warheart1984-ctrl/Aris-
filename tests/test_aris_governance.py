from __future__ import annotations

import asyncio
from contextlib import contextmanager
import sys
import types
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    def _blocked_post(*args, **kwargs):
        raise RequestException("requests transport is unavailable in this test runtime")

    requests_stub.RequestException = RequestException
    requests_stub.post = _blocked_post
    sys.modules["requests"] = requests_stub

from fastapi.testclient import TestClient

from evolving_ai.app.config import AppConfig
from evolving_ai.app.server import create_app
from evolving_ai.aris.runtime import ArisRuntime
from evolving_ai.aris.service import ArisChatService


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-test"


def _patch_for(path: str, content: str = "value = 1\n") -> str:
    return "\n".join(
        [
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -0,0 +1 @@",
            f"+{content.rstrip()}",
        ]
    )


def _make_runtime() -> tuple[ArisRuntime, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    runtime_root.mkdir(parents=True, exist_ok=True)
    return (
        ArisRuntime(
            repo_root=REPO_ROOT,
            runtime_root=runtime_root,
        ),
        runtime_root,
    )


def _make_service() -> tuple[ArisChatService, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"service-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    config = AppConfig.from_env(root)
    return ArisChatService(config), root


def _collect_events(stream) -> list[str]:
    async def _runner() -> list[str]:
        events: list[str] = []
        async for event in stream:
            events.append(event)
        return events

    return asyncio.run(_runner())


def _action_types(spy) -> list[str]:
    return [call.args[0]["action_type"] for call in spy.call_args_list]


def _complete_observation(service: ArisChatService, session_id: str) -> None:
    service.aris.runtime_law.clear_observation(session_id)


@contextmanager
def _api_client(service: ArisChatService):
    with patch("evolving_ai.app.server._build_service", return_value=service):
        app = create_app()
        with TestClient(app) as client:
            yield client


class ArisRuntimeTests(unittest.TestCase):
    def test_clean_boot_path_is_healthy(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        self.assertTrue(status["startup_ready"])
        self.assertTrue(runtime.health_payload()["ok"])
        self.assertEqual(runtime.kill_switch.snapshot()["mode"], "nominal")
        self.assertTrue(status["mystic"]["active"])
        self.assertTrue(status["mystic_reflection"]["active"])
        self.assertTrue(status["mystic_reflection"]["merged_with_jarvis"])
        self.assertTrue(status["shield_of_truth"]["active"])
        self.assertTrue(status["repo_logbook"]["active"])

    def test_missing_forge_eval_fails_closed(self) -> None:
        with patch("evolving_ai.aris.runtime.ForgeEvalService", None), patch(
            "evolving_ai.aris.runtime._FORGE_EVAL_IMPORT_ERROR",
            RuntimeError("forge eval dependency missing"),
        ):
            runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        status = runtime.status_payload(include_recent=False)
        self.assertFalse(status["startup_ready"])
        self.assertIn("Forge Eval is unavailable.", " ".join(status["startup_blockers"]))
        self.assertTrue(status["kill_switch"]["active"])
        self.assertEqual(status["kill_switch"]["mode"], "lockdown")

    def test_risky_action_cannot_pass_on_operator_judgment_alone(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "alpha",
                "purpose": "Apply a risky patch to target.py.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("other.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_forge_eval)
        self.assertEqual(decision.disposition, "discarded")
        self.assertEqual(decision.hall_name, "hall_of_discard")
        self.assertTrue(runtime.list_discards(limit=1))

    def test_hall_of_discard_blocks_unchanged_reentry(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        action = {
            "action_type": "patch_apply",
            "session_id": "alpha",
            "purpose": "Apply a risky patch to target.py.",
            "target": "target.py",
            "source": "test",
            "operator_decision": "approved",
            "patch": _patch_for("other.py"),
            "authorized": True,
            "observed": True,
            "bounded": True,
        }

        first = runtime.review_action(action)
        second = runtime.review_action(action)

        self.assertEqual(first.disposition, "discarded")
        self.assertFalse(second.allowed)
        self.assertEqual(second.disposition, "blocked")
        self.assertIsNotNone(second.reentry_blocker)

    def test_modified_reentry_requires_fresh_review(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        action = {
            "action_type": "patch_apply",
            "session_id": "alpha",
            "purpose": "Apply a risky patch to target.py.",
            "target": "target.py",
            "source": "test",
            "operator_decision": "approved",
            "patch": _patch_for("other.py"),
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        runtime.review_action(action)
        redesigned = dict(action)
        redesigned["patch"] = _patch_for("other.py", "value = 2\n")

        second = runtime.review_action(redesigned)

        self.assertIsNone(second.reentry_blocker)
        self.assertEqual(second.disposition, "discarded")

    def test_bypass_attempt_triggers_hard_kill_and_discard(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "alpha",
                "purpose": "Attempt to bypass Forge Eval.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("target.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
                "bypass_requested": True,
            }
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.kill_switch.get("mode"), "hard_kill")
        self.assertEqual(decision.disposition, "discarded")
        self.assertEqual(decision.hall_name, "hall_of_discard")

    def test_discard_preserves_rejection_metadata(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        runtime.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "alpha",
                "purpose": "Apply a risky patch to target.py.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("other.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        entry = runtime.list_discards(limit=1)[0]

        self.assertEqual(entry["hall"], "hall-of-discard")
        self.assertIn("reason", entry)
        self.assertIn("action", entry)
        self.assertIn("guardrails", entry)
        self.assertIn("forge_eval", entry)
        self.assertIn("reentry_requirements", entry)

    def test_correctness_failure_routes_to_hall_of_shame(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "test",
                "operator_decision": "recorded",
                "code": '{"snapshot":"a"}',
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        finalized = runtime.finalize_action(decision, result={"ok": False, "error": "Snapshot write failed."})

        self.assertFalse(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_shame")
        self.assertEqual(runtime.list_shames(limit=1)[0]["hall"], "hall-of-shame")

    def test_verified_success_routes_to_hall_of_fame(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "test",
                "operator_decision": "recorded",
                "code": '{"snapshot":"a"}',
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        finalized = runtime.finalize_action(decision, result={"ok": True, "snapshot_id": "snap-1"})

        self.assertTrue(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_fame")
        self.assertEqual(runtime.list_fame(limit=1)[0]["hall"], "hall-of-fame")

    def test_repo_changed_action_fails_1001_without_verification_and_logbook(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        runtime.logbook = runtime.logbook.__class__(runtime_root / "LOGBOOK.md")
        runtime.logbook.path.write_text("# Test Logbook\n", encoding="utf-8")

        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Record a meaningful repo change.",
                "target": "README.md",
                "source": "repo",
                "operator_decision": "recorded",
                "repo_changed": True,
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        finalized = runtime.finalize_action(decision, result={"ok": True})

        self.assertFalse(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_discard")
        self.assertIn("unverified", finalized.reason.lower())

    def test_repo_changed_action_requires_matching_logbook_and_verification_artifacts(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        runtime.logbook = runtime.logbook.__class__(runtime_root / "LOGBOOK.md")
        runtime.logbook.path.write_text("# Test Logbook\n", encoding="utf-8")

        decision = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Record a meaningful repo change.",
                "target": "README.md",
                "source": "repo",
                "operator_decision": "recorded",
                "repo_changed": True,
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        logbook_entry = runtime.record_repo_logbook_entry(
            title="Test Repo Change",
            what_changed=["Recorded a governed repo-changing action for verification."],
            why_it_changed=["Tests the 1001 documentation gate."],
            how_it_changed=["Bound the action to a matching Repo Logbook entry and verification artifacts."],
            files_changed=["README.md"],
            verification=["unit-test-artifact"],
            remaining_risks=["Test-only artifact."],
            action_id=decision.action_id,
            fingerprint=decision.fingerprint,
        )
        finalized = runtime.finalize_action(
            decision,
            result={
                "ok": True,
                "verification_artifacts": ["unit-test-artifact"],
                "logbook_entry": logbook_entry,
            },
        )

        self.assertTrue(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_fame")

    def test_hall_entries_are_not_reassigned_on_re_evaluation(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        first = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "test",
                "operator_decision": "recorded",
                "code": '{"snapshot":"broken"}',
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        failed = runtime.finalize_action(first, result={"ok": False, "error": "Snapshot write failed."})

        redesigned = runtime.review_action(
            {
                "action_type": "snapshot_create",
                "session_id": "alpha",
                "purpose": "Create a governed snapshot.",
                "target": "snapshot-a",
                "source": "test",
                "operator_decision": "recorded",
                "code": '{"snapshot":"fixed"}',
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        verified = runtime.finalize_action(redesigned, result={"ok": True, "snapshot_id": "snap-2"})

        shames = runtime.list_shames(limit=10)
        fame = runtime.list_fame(limit=10)
        self.assertEqual(len(shames), 1)
        self.assertEqual(len(fame), 1)
        self.assertEqual(shames[0]["hall"], "hall-of-shame")
        self.assertEqual(fame[0]["hall"], "hall-of-fame")
        self.assertEqual(failed.hall_name, "hall_of_shame")
        self.assertEqual(verified.hall_name, "hall_of_fame")
        self.assertEqual(
            fame[0]["re_evaluation_of"]["entry_id"],
            shames[0]["id"],
        )
        self.assertEqual(
            fame[0]["re_evaluation_of"]["hall"],
            shames[0]["hall"],
        )

    def test_soft_kill_blocks_new_actions(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        runtime.activate_soft_kill(reason="pause", actor="test")

        decision = runtime.review_action(
            {
                "action_type": "task_run",
                "session_id": "alpha",
                "purpose": "Start a new governed task.",
                "target": ".",
                "source": "test",
                "operator_decision": "approved",
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.disposition, "blocked")

    def test_kill_after_approval_prevents_verified_return(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        decision = runtime.review_action(
            {
                "action_type": "snapshot_restore",
                "session_id": "alpha",
                "purpose": "Restore a governed snapshot.",
                "target": "snapshot-a",
                "source": "test",
                "operator_decision": "approved",
                "code": '{"snapshot":"a"}',
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )
        runtime.activate_hard_kill(reason="emergency", actor="test")
        finalized = runtime.finalize_action(decision, result={"ok": True})

        self.assertFalse(finalized.verified)
        self.assertEqual(finalized.hall_name, "hall_of_discard")
        self.assertEqual(finalized.kill_switch["mode"], "hard_kill")

    def test_tamper_detection_forces_lockdown(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))

        with patch.object(
            runtime.integrity,
            "verify_or_initialize",
            return_value={
                "ok": False,
                "initialized": False,
                "resealed": False,
                "manifest_path": str(runtime.integrity.manifest_path),
                "protected_count": 1,
                "missing": [],
                "changed": ["protected.py"],
                "removed": [],
            },
        ):
            decision = runtime.review_action(
                {
                    "action_type": "snapshot_create",
                    "session_id": "alpha",
                    "purpose": "Create a governed snapshot.",
                    "target": "snapshot-a",
                    "source": "test",
                    "operator_decision": "recorded",
                    "authorized": True,
                    "observed": True,
                    "bounded": True,
                }
            )

        self.assertFalse(decision.allowed)
        self.assertEqual(runtime.kill_switch.snapshot()["mode"], "lockdown")

    def test_no_hidden_fallback_when_forge_eval_is_missing(self) -> None:
        runtime, runtime_root = _make_runtime()
        self.addCleanup(lambda: shutil.rmtree(runtime_root, ignore_errors=True))
        runtime.forge_eval = None

        decision = runtime.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "alpha",
                "purpose": "Apply a risky patch to target.py.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("other.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.hall_name, "hall_of_discard")


class ArisServiceTests(unittest.TestCase):
    def test_api_status_matches_backend_truth(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            health = client.get("/api/health").json()
            status = client.get("/api/aris/status").json()
            shame = client.get("/api/aris/shame").json()
            fame = client.get("/api/aris/fame").json()

        self.assertEqual(health["ok"], service.aris.health_payload()["ok"])
        self.assertEqual(status["startup_ready"], service.aris.status_payload(include_recent=False)["startup_ready"])
        self.assertIn("execution_backend", status)
        self.assertIn("shell_execution", status)
        self.assertEqual(
            status["execution_backend"]["docker_available"],
            service.executor.status_payload()["docker_available"],
        )
        self.assertEqual(
            health["aris"]["shell_execution"]["degraded"],
            status["shell_execution"]["degraded"],
        )
        self.assertIn("repo_logbook", status)
        self.assertTrue(status["repo_logbook"]["active"])
        self.assertTrue(status["mystic"]["active"])
        self.assertTrue(status["mystic_reflection"]["active"])
        self.assertTrue(status["mystic_reflection"]["merged_with_jarvis"])
        self.assertTrue(status["shield_of_truth"]["active"])
        self.assertTrue("entries" in shame and "entries" in fame)

    def test_api_truth_is_canonical_and_marks_historical_activity(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        service.sessions.get_or_create("alpha", "alpha session")
        service.sessions.get_or_create("beta", "beta session")
        service.aris.review_action(
            {
                "action_type": "patch_apply",
                "session_id": "alpha",
                "purpose": "Apply a risky patch to target.py.",
                "target": "target.py",
                "source": "test",
                "operator_decision": "approved",
                "patch": _patch_for("other.py"),
                "authorized": True,
                "observed": True,
                "bounded": True,
            }
        )

        with _api_client(service) as client:
            payload = client.get(
                "/api/aris/truth",
                params={"session_id": "beta", "activity_limit": 20, "hall_limit": 20},
            ).json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["startup_ready"], service.aris_status_payload()["startup_ready"])
        self.assertEqual(payload["health"]["ok"], service.aris_health_payload()["ok"])
        self.assertEqual(payload["session_id"], "beta")
        self.assertTrue(payload["activity"])
        self.assertTrue(any(entry.get("historical") for entry in payload["activity"]))
        self.assertTrue(all("current_scope" in entry for entry in payload["activity"]))

    def test_mystic_read_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.aris_mystic_read(
                session_id="alpha",
                input_text="Give me a mystic reading: I feel stuck and nothing is moving.",
            )

        self.assertTrue(result["ok"])
        self.assertIn("mystic_reflection", _action_types(spy))
        self.assertEqual(result["tool_result"]["type"], "mystic_reflection")
        self.assertEqual(result["governance"]["hall_name"], "hall_of_fame")

    def test_api_exposes_governed_mystic_read_endpoint(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            payload = client.post(
                "/api/aris/mystic-read",
                json={
                    "session_id": "alpha",
                    "input": "Mystic reading: I have an idea that could change everything.",
                },
            ).json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool_result"]["type"], "mystic_reflection")
        self.assertEqual(payload["governance"]["hall_name"], "hall_of_fame")

    def test_api_exposes_mystic_sustainment_status_endpoint(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            payload = client.get("/api/aris/mystic/status", params={"session_id": "alpha"}).json()

        self.assertTrue(payload["active"])
        self.assertEqual(payload["session_id"], "alpha")
        self.assertIn("ui_controls", payload)

    def test_direct_file_write_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.write_workspace_file(
                session_id="alpha",
                path="demo.py",
                content="print('hi')\n",
            )

        self.assertTrue(result["ok"])
        self.assertIn("file_write", _action_types(spy))
        self.assertEqual(result["hall"]["name"], "hall_of_fame")

    def test_direct_symbol_edit_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"
        service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        _complete_observation(service, session_id)

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.edit_workspace_symbol(
                session_id=session_id,
                symbol="greet",
                path="demo.py",
                content="def greet():\n    return 2\n",
            )

        self.assertTrue(result["ok"])
        self.assertIn("symbol_edit", _action_types(spy))

    def test_patch_apply_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"
        service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        _complete_observation(service, session_id)
        proposal = service.propose_workspace_write(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 2\n",
        )
        patch_id = proposal["patch"]["id"]

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.apply_workspace_patch(session_id=session_id, patch_id=patch_id)

        self.assertTrue(result["ok"])
        self.assertIn("patch_apply", _action_types(spy))

    def test_patch_hunk_accept_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"
        service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        _complete_observation(service, session_id)
        proposal = service.propose_workspace_write(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 2\n",
        )
        patch_id = proposal["patch"]["id"]

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.accept_workspace_patch_hunk(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=0,
            )

        self.assertTrue(result["ok"])
        self.assertIn("patch_hunk_apply", _action_types(spy))

    def test_patch_line_accept_routes_through_aris_runtime(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"
        service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        _complete_observation(service, session_id)
        proposal = service.propose_workspace_write(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 2\n",
        )
        patch_id = proposal["patch"]["id"]

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.accept_workspace_patch_line(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=0,
                line_index=0,
            )

        self.assertTrue(result["ok"])
        self.assertIn("patch_line_apply", _action_types(spy))

    def test_post_verification_observation_blocks_immediate_mutation(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"

        write_result = service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        self.assertTrue(write_result["ok"])

        result = service.edit_workspace_symbol(
            session_id=session_id,
            symbol="greet",
            path="demo.py",
            content="def greet():\n    return 2\n",
        )

        self.assertFalse(result["ok"])
        self.assertIn("complete_observation_window", result["error"])
        self.assertEqual(result["hall"]["name"], "hall_of_discard")

    def test_shell_exec_routes_through_governance_wrapper(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            result = service.execute_command(
                session_id="alpha",
                command=["python", "-c", "print('ok')"],
                cwd=".",
                timeout_seconds=10,
            )

        self.assertIn("command_execute", _action_types(spy))
        self.assertIn("aris", result["sandbox"])
        self.assertIn("returncode", result)
        expected_hall = "hall_of_fame"
        if result["returncode"] != 0:
            expected_hall = "hall_of_discard" if result["sandbox"].get("blocked") else "hall_of_shame"
        self.assertEqual(
            result["sandbox"]["aris"]["hall_name"],
            expected_hall,
        )
        if result["returncode"] != 0:
            self.assertTrue(result["sandbox"].get("blocked"))
            self.assertTrue(result["sandbox"]["aris"]["reason"])

    def test_workspace_review_fallback_does_not_route_host_git_probe_through_aris(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            review = service.review_workspace(session_id="alpha")

        self.assertTrue(review["ok"])
        self.assertNotIn("command_execute", _action_types(spy))
        self.assertEqual(service.aris.kill_switch.snapshot()["mode"], "nominal")

    def test_repeated_workspace_review_fallback_does_not_trigger_hard_kill(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        for _ in range(3):
            review = service.review_workspace(session_id="alpha")
            self.assertTrue(review["ok"])

        self.assertEqual(service.aris.kill_switch.snapshot()["mode"], "nominal")

    def test_workspace_review_endpoint_never_escalates_observation(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with _api_client(service) as client:
            first = client.get("/api/workspace/alpha/review")
            second = client.get("/api/workspace/alpha/review")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(service.aris.kill_switch.snapshot()["mode"], "nominal")

    def test_workspace_payload_endpoint_stays_observational(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        with patch.object(service.aris, "review_action", wraps=service.aris.review_action) as spy:
            with _api_client(service) as client:
                first = client.get("/api/workspace/alpha")
                second = client.get("/api/workspace/alpha")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotIn("review", first.json())
        self.assertNotIn("command_execute", _action_types(spy))
        self.assertEqual(service.aris.kill_switch.snapshot()["mode"], "nominal")

    def test_soft_kill_blocks_new_task_runs(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        service.aris.activate_soft_kill(reason="pause", actor="test")

        events = _collect_events(
            service.stream_workspace_task(
                session_id="alpha",
                goal="touch repo",
                cwd=".",
                test_commands=[],
                fast_mode=True,
            )
        )

        self.assertTrue(any("governance_block" in event for event in events))
        self.assertEqual(service.task_manager.list_tasks("alpha"), [])

    def test_kill_blocks_approval_resolution(self) -> None:
        service, root = _make_service()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        session_id = "alpha"
        service.write_workspace_file(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 1\n",
        )
        proposal = service.propose_workspace_write(
            session_id=session_id,
            path="demo.py",
            content="def greet():\n    return 2\n",
        )
        patch_id = proposal["patch"]["id"]
        service.aris.activate_soft_kill(reason="pause approvals", actor="test")

        events = _collect_events(
            service.stream_approval_decision(
                session_id=session_id,
                approval_id=patch_id,
                approved=True,
            )
        )
        pending = service.list_pending_workspace_patches(session_id)["pending_patches"]

        self.assertTrue(any("governance_block" in event for event in events))
        self.assertTrue(any(patch["id"] == patch_id for patch in pending))


if __name__ == "__main__":
    unittest.main()
