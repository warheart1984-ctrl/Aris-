from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shutil
import threading
import tempfile
import time
from typing import Any
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from evolving_ai.aris_runtime.desktop import main as desktop_main
from evolving_ai.aris_runtime.desktop_app import ArisRuntimeDesktopWindow
from evolving_ai.aris_runtime.desktop_build import build_pyinstaller_command
from evolving_ai.aris_runtime.desktop_support import (
    ArisRuntimeDesktopHost,
    default_desktop_data_root,
    parse_sse_events,
    select_active_task,
    select_project_folder,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-v2-desktop-test"
_QT_APP = QApplication.instance() or QApplication([])


def _make_host(profile_id: str = "v2", *, start_workers: bool = False) -> tuple[ArisRuntimeDesktopHost, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return ArisRuntimeDesktopHost(data_root=root, start_workers=start_workers, profile_id=profile_id), root


def _pump_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _QT_APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    _QT_APP.processEvents()
    return bool(predicate())


def _cleanup_host_root(host: ArisRuntimeDesktopHost, root: Path) -> None:
    host.close()
    shutil.rmtree(root, ignore_errors=True)


class ArisRuntimeDesktopSupportTests(unittest.TestCase):
    def test_default_desktop_data_root_honors_override(self) -> None:
        override = Path(tempfile.gettempdir()) / "aris-runtime-override"
        with patch.dict(os.environ, {"ARIS_RUNTIME_DESKTOP_ROOT": str(override)}, clear=False):
            self.assertEqual(default_desktop_data_root("windows"), override.resolve())

    def test_default_desktop_data_root_is_v2_only(self) -> None:
        self.assertEqual(default_desktop_data_root("windows").name, "ARIS V2")
        self.assertEqual(default_desktop_data_root("windows", profile_id="v2").name, "ARIS V2")
        with self.assertRaises(ValueError):
            default_desktop_data_root("windows", profile_id="demo")

    def test_snapshot_exposes_ul_runtime_and_packaging_targets(self) -> None:
        host, root = _make_host()
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        session_id = host.ensure_session()
        snapshot = host.snapshot(session_id)
        features = {item.id: item for item in snapshot.features}
        targets = {item.id for item in snapshot.packaging_targets}
        artifacts = {item.artifact for item in snapshot.packaging_targets}
        repo_names = {item["name"] for item in snapshot.workspace_surface["repos"]}
        task_titles = {item["title"] for item in snapshot.workspace_surface["tasks"]}
        workspaces = snapshot.workspace_surface["workspaces"]
        active_workspace = snapshot.workspace_surface["active_workspace"]
        feedback_payload = snapshot.workspace_surface["feedback"]

        self.assertEqual(snapshot.status["system_name"], "ARIS V2")
        self.assertEqual(snapshot.status["runtime_profile"], "v2")
        self.assertEqual(snapshot.status["model_router"]["mode"], "auto")
        self.assertIsNone(snapshot.current_project_path)
        self.assertTrue(snapshot.workspace_surface["repos"])
        self.assertTrue(snapshot.workspace_surface["tasks"])
        self.assertIn("worker", snapshot.workspace_surface)
        self.assertTrue(workspaces)
        self.assertIn("file_explorer", snapshot.workspace_surface)
        self.assertIn("event_stream", snapshot.workspace_surface)
        self.assertTrue({"AAIS-main", "ARIS-runtime", "Repo-AI"}.issubset(repo_names))
        self.assertIn("Inspect protected execution boundaries", task_titles)
        self.assertEqual(active_workspace["id"], workspaces[0]["id"])
        self.assertIn("categories", feedback_payload)
        self.assertEqual(features["ul_runtime"].status, "extracted")
        self.assertEqual(features["identity_source"].status, "UL")
        self.assertEqual(features["model_switchboard"].status, "auto")
        self.assertEqual(features["forge_planning"].status, "available")
        self.assertEqual(features["evolving_engine"].status, "active")
        self.assertEqual(snapshot.workspace_surface["worker"]["title"], "Forge Worker Lane")
        self.assertEqual(targets, {"windows", "macos", "linux"})
        self.assertEqual(artifacts, {"ARIS V2.exe", "ARIS V2.app", "dist/ARIS V2/"})

    def test_v2_snapshot_exposes_evolving_runtime_profile(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        snapshot = host.snapshot(host.ensure_session())
        features = {item.id: item for item in snapshot.features}
        artifacts = {item.artifact for item in snapshot.packaging_targets}

        self.assertEqual(snapshot.status["system_name"], "ARIS V2")
        self.assertEqual(snapshot.status["runtime_profile"], "v2")
        self.assertTrue(snapshot.status["evolving_engine"]["active"])
        self.assertEqual(features["evolving_engine"].status, "active")
        self.assertEqual(snapshot.status["model_router"]["mode"], "auto")
        self.assertEqual(artifacts, {"ARIS V2.exe", "ARIS V2.app", "dist/ARIS V2/"})

    def test_snapshot_exposes_bridge_intelligence_task_memory_and_replay(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        session_id = host.ensure_session()
        snapshot = host.snapshot(session_id)
        active_task = select_active_task(snapshot.workspace_surface["tasks"])
        self.assertIsNotNone(active_task)
        task_id = str(active_task.get("id", "")).strip()
        host.save_task_memory(
            task_id=task_id,
            title=str(active_task.get("title", "Task")).strip(),
            goals=["Keep approvals visible"],
            constraints=["Do not bypass runtime law"],
            notes=["Prefer deterministic summaries"],
            do_not_touch=["Protected core"],
        )

        refreshed = host.snapshot(session_id)
        bridge = refreshed.workspace_surface["bridge_intelligence"]

        self.assertIn("approval_summary", bridge)
        self.assertEqual(bridge["task_memory"]["task_id"], task_id)
        self.assertIn("Keep approvals visible", bridge["task_memory"]["goals"])
        self.assertIn("timeline", bridge["replay"])
        self.assertIsInstance(refreshed.workspace_surface["branches"], list)

    def test_chat_stream_consumes_existing_service_sse(self) -> None:
        host, root = _make_host()
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        session_id = host.ensure_session()
        events = list(
            host.iter_chat_events(
                session_id=session_id,
                user_message="Explain the UL runtime surfaces.",
                mode="chat",
                fast_mode=True,
            )
        )
        transcript = host.session_messages(session_id)

        self.assertTrue(events)
        self.assertEqual(events[0].event, "meta")
        self.assertTrue(any(event.event == "token" for event in events))
        self.assertEqual(events[-1].event, "done")
        self.assertEqual([message["role"] for message in transcript], ["user", "assistant"])
        self.assertIn("mock brain", transcript[-1]["content"])

    def test_agent_runs_surface_promotes_real_runtime_tasks(self) -> None:
        host, root = _make_host(start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        session_id = host.ensure_session()
        events = list(
            host.iter_chat_events(
                session_id=session_id,
                user_message="Inspect the workspace and summarize the governed route.",
                mode="agent",
                fast_mode=False,
            )
        )
        snapshot = host.snapshot(session_id)
        tasks = snapshot.workspace_surface["tasks"]
        agent_tasks = [item for item in tasks if item.get("task_type") == "agent_run"]

        self.assertTrue(any(event.event == "agent_step" for event in events))
        self.assertTrue(agent_tasks)
        self.assertIn(agent_tasks[0]["status"], {"Running", "Pending", "Blocked", "Done"})
        self.assertEqual(snapshot.transcript[0]["role"], "user")
        self.assertEqual(snapshot.transcript[-1]["role"], "assistant")

    def test_host_scheduler_prioritizes_ready_tasks_and_blocks_dependencies(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        session_id = host.ensure_session()
        first = host.enqueue_operator_task(
            session_id=session_id,
            title="Build repo manager",
            prompt="Build the repo manager through the governed runtime.",
            priority=3,
        )
        blocked = host.enqueue_operator_task(
            session_id=session_id,
            title="Review repo manager follow-up",
            prompt="Review the repo manager after the first task finishes.",
            priority=5,
            depends_on=[str(first.get("id", ""))],
        )
        second = host.enqueue_operator_task(
            session_id=session_id,
            title="Inspect protected execution boundaries",
            prompt="Inspect the protected execution boundaries and summarize any weak seams.",
            priority=4,
        )

        launched: list[str] = []

        def fake_enqueue_agent_run(**kwargs):
            launched.append(str(kwargs.get("title", "")))
            return {
                "ok": True,
                "run": {
                    "id": f"run-{len(launched)}",
                    "status": "queued",
                    "created_at": "2026-05-01T13:40:00+00:00",
                    "updated_at": "2026-05-01T13:40:00+00:00",
                    "user_message": kwargs.get("user_message", ""),
                    "title": kwargs.get("title", ""),
                },
            }

        with patch.object(host.service, "enqueue_agent_run", side_effect=fake_enqueue_agent_run):
            tick = host.scheduler_tick(session_id=session_id, max_concurrency=2)

        items = {item["title"]: item for item in host.list_operator_queue(session_id=session_id)}
        self.assertEqual([item["title"] for item in tick["started"]], ["Inspect protected execution boundaries", "Build repo manager"])
        self.assertEqual(launched, ["Inspect protected execution boundaries", "Build repo manager"])
        self.assertEqual(items["Inspect protected execution boundaries"]["status"], "pending")
        self.assertEqual(items["Build repo manager"]["status"], "pending")
        self.assertEqual(items["Review repo manager follow-up"]["status"], "blocked")
        self.assertEqual(
            items["Review repo manager follow-up"]["latest_update"],
            "Waiting on 1 dependency task(s) before launch.",
        )
        self.assertEqual(str(items["Review repo manager follow-up"]["id"]), str(blocked.get("id", "")))

    def test_self_improve_tasks_require_operator_review_before_done(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        session_id = host.ensure_session()
        self_improve = next(
            item
            for item in host.list_operator_queue(session_id=session_id)
            if item.get("queue_name") == "SELF_IMPROVE"
        )
        host.operator_queue.update_item(
            str(self_improve.get("id", "")),
            linked_run_id="run-self-improve",
            status="pending",
        )

        with patch.object(
            host,
            "list_agent_runs",
            return_value=[
                {
                    "id": "run-self-improve",
                    "status": "completed",
                    "completed_at": "2026-05-01T13:45:00+00:00",
                    "updated_at": "2026-05-01T13:45:00+00:00",
                    "title": self_improve.get("title", ""),
                    "user_message": self_improve.get("prompt", ""),
                    "final_message": "Diff summary improved and is ready for review.",
                    "blocked_on_approval_id": "",
                    "blocked_on_kind": "",
                }
            ],
        ):
            host.scheduler_tick(session_id=session_id, max_concurrency=1)

        blocked_item = host.operator_queue.get_item(str(self_improve.get("id", "")))
        self.assertIsNotNone(blocked_item)
        self.assertEqual(blocked_item["status"], "blocked")
        self.assertEqual(blocked_item["review_gate"], "operator_review")

        resolved = host.resolve_operator_review(
            task_id=str(self_improve.get("id", "")),
            approved=True,
            notes="Admitted after governed operator review.",
        )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["status"], "done")
        self.assertTrue(resolved["approved"])
        self.assertTrue(resolved["outcome_recorded"])
        history_lines = host._self_improve_history_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(history_lines)
        self.assertIn(str(self_improve.get("id", "")), history_lines[-1])

    def test_parse_sse_events_and_build_command(self) -> None:
        parsed = parse_sse_events('event: meta\ndata: {"ok": true}\n\n')
        command = build_pyinstaller_command()

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].event, "meta")
        self.assertTrue(parsed[0].payload["ok"])
        self.assertIn("--windowed", command)
        self.assertIn("tkinter", command)
        self.assertTrue(any(str(item).endswith("desktop.py") for item in command))
        self.assertIn("ARIS V2", command)
        with self.assertRaises(ValueError):
            build_pyinstaller_command(profile_id="v1")

    def test_select_project_folder_returns_none_on_cancel(self) -> None:
        root = unittest.mock.Mock()
        with patch("evolving_ai.aris_runtime.desktop_support.tk.Tk", return_value=root), patch(
            "evolving_ai.aris_runtime.desktop_support.filedialog.askdirectory",
            return_value="",
        ):
            selected = select_project_folder()

        self.assertIsNone(selected)
        root.withdraw.assert_called_once_with()
        root.update_idletasks.assert_called_once_with()
        root.destroy.assert_called_once_with()

    def test_select_project_folder_sets_current_project_on_host(self) -> None:
        host, root = _make_host()
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        selected_root = root / "selected-project"
        selected_root.mkdir(parents=True, exist_ok=True)
        with patch(
            "evolving_ai.aris_runtime.desktop_support.select_project_folder",
            return_value=str(selected_root),
        ):
            selected = host.select_current_project()

        snapshot = host.snapshot(host.ensure_session())
        self.assertEqual(selected, str(selected_root.resolve()))
        self.assertEqual(snapshot.current_project_path, str(selected_root.resolve()))
        self.assertEqual(snapshot.workspace_surface["repos"][0]["path"], str(selected_root.resolve()))
        self.assertEqual(snapshot.workspace_surface["active_workspace"]["root_path"], str(selected_root.resolve()))

    def test_host_workspace_preview_search_and_feedback_are_bounded(self) -> None:
        host, root = _make_host()
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        workspace_root = root / "workspace-a"
        workspace_root.mkdir(parents=True, exist_ok=True)
        target_file = workspace_root / "notes.txt"
        target_file.write_text("ARIS workspace search target\n", encoding="utf-8")
        workspace = host.add_workspace(workspace_root, name="Workspace A")

        preview = host.preview_workspace_target(target_file, workspace_id=workspace["id"])
        results = host.search_workspace("search target", workspace_id=workspace["id"])
        feedback = host.submit_feedback(
            feedback_type="bug",
            user_note="Explorer did not refresh after selection.",
            active_brain="Inspect",
            active_tier="Read Only",
            active_workspace="Workspace A",
            recent_logs=[{"kind": "worker", "detail": "Worker lane idle."}],
        )

        self.assertEqual(preview["relative_path"], "notes.txt")
        self.assertTrue(results)
        self.assertTrue(Path(feedback["path"]).exists())
        with self.assertRaises(ValueError):
            host.preview_workspace_target(root.parent, workspace_id=workspace["id"])

    def test_host_recovers_when_knowledge_path_is_a_file(self) -> None:
        root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
        knowledge_file = root / ".forge_chat" / "knowledge"
        knowledge_file.parent.mkdir(parents=True, exist_ok=True)
        knowledge_file.write_text("stale file", encoding="utf-8")

        host = ArisRuntimeDesktopHost(data_root=root, start_workers=False)
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        self.assertTrue(host.service.knowledge.root.is_dir())
        self.assertNotEqual(host.service.knowledge.root, knowledge_file)

    def test_desktop_entry_headless_smokecheck_returns_json(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = desktop_main(["--headless-smokecheck", "--no-workers"])

        self.assertEqual(exit_code, 0)
        payload = output.getvalue()
        self.assertIn('"system_name": "ARIS V2"', payload)
        self.assertIn('"ul_runtime_present": true', payload.lower())
        self.assertIn('"model_router"', payload)

    def test_desktop_entry_headless_smokecheck_supports_v2_profile(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = desktop_main(["--headless-smokecheck", "--no-workers", "--profile", "v2"])

        self.assertEqual(exit_code, 0)
        payload = output.getvalue()
        self.assertIn('"profile_id": "v2"', payload)
        self.assertIn('"system_name": "ARIS V2"', payload)
        self.assertIn('"packaging_artifacts"', payload)

    def test_window_enters_syncing_state_before_runtime_snapshot(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))
        current_session = window.current_session_id
        settled_snapshot = host.snapshot(current_session)
        observed: dict[str, str] = {}
        release_snapshot = threading.Event()

        def fake_snapshot(session_id: str | None = None):
            del session_id
            observed["health"] = window.health_badge.text()
            observed["mode"] = window.mode_badge.text()
            observed["kill"] = window.kill_badge.text()
            observed["route"] = window.route_label.text()
            observed["prompt_context"] = window.workspace_prompt_context.text()
            observed["brain"] = window.workspace_brain_state.toPlainText()
            release_snapshot.wait(timeout=2.0)
            return settled_snapshot

        with patch.object(host, "snapshot", side_effect=fake_snapshot):
            started = time.monotonic()
            window.refresh_from_runtime(select_session_id=current_session)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.25)
            self.assertEqual(window.health_badge.text(), "SYNCING")
            self.assertTrue(_pump_until(lambda: bool(observed), timeout=1.0))
            release_snapshot.set()
            self.assertTrue(_pump_until(lambda: window._refresh_thread is None, timeout=2.0))

        self.assertEqual(observed["health"], "SYNCING")
        self.assertEqual(observed["mode"], "1001 SYNC")
        self.assertEqual(observed["kill"], "SYNCING")
        self.assertIn("Input -> Forge -> Eval -> Outcome -> Evolve", observed["route"])
        self.assertIn("hydrating", observed["prompt_context"].lower())
        self.assertIn("loading mode, scope, target, and permission state", observed["brain"].lower())
        self.assertEqual(window.health_badge.text(), "READY")

    def test_v2_window_defaults_to_forge_governed_brain_state(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        self.assertEqual(window.brain_target.currentText(), "Forge")
        self.assertEqual(window.brain_permission.currentText(), "Approval Required")
        self.assertIn("Forge", window.workspace_route_summary.text())
        self.assertEqual(window.tabs.count(), 1)
        self.assertEqual(window.tabs.tabText(0), "Studio")
        self.assertEqual(window.hero_title.text(), "ARIS Studio V2")

    def test_v2_window_uses_real_transcript_surface_after_chat(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        session_id = host.ensure_session()
        list(
            host.iter_chat_events(
                session_id=session_id,
                user_message="Summarize the runtime law spine.",
                mode="chat",
                fast_mode=True,
            )
        )

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))
        self.assertIn("mock brain", window.chat_output.toPlainText())
        self.assertNotIn("ARIS workspace is online.", window.chat_output.toPlainText())

    def test_v2_window_shows_run_task_when_workers_are_available(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))
        self.assertEqual(window.send_button.text(), "Run Task")
        self.assertFalse(window.task_queue_frame.isVisible())
        self.assertTrue(window.active_run_title.text())

    def test_v2_window_collapses_secondary_surfaces_into_inspect_panel(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        self.assertTrue(window.inspect_panel.isHidden())
        self.assertEqual(window.inspect_toggle_button.text(), "Inspect ▼")
        self.assertFalse(window.home_run_button.isVisible())
        self.assertFalse(window.home_cancel_button.isVisible())

    def test_v2_window_uses_codex_style_project_and_task_rails(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        self.assertEqual(window.new_session_button.text(), "Add Repo")
        self.assertGreater(window.project_list.count(), 0)
        self.assertGreater(window.sidebar_task_list.count(), 0)
        self.assertIn("/", window.hero_subtitle.text())
        self.assertIn("Status:", window.route_label.text())
        self.assertNotIn("Route:", window.route_label.text())

    def test_v2_window_inspect_button_expands_secondary_surfaces_for_active_run(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        window._inspect_active_run()

        self.assertFalse(window.inspect_panel.isHidden())
        self.assertEqual(window.inspect_toggle_button.text(), "Inspect ▲")
        self.assertEqual(window.studio_surface_tabs.tabText(window.studio_surface_tabs.currentIndex()), "Runtime")

    def test_v2_window_run_task_queues_operator_work(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        window.chat_input.setPlainText("Build repo connection manager through the governed runtime.")
        window._start_chat()
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None, timeout=5.0))
        task_titles = {item.get("title", "") for item in window.snapshot.workspace_surface["tasks"]}
        self.assertTrue(any("Build repo connection manager" in title for title in task_titles))

    def test_v2_window_start_chat_uses_runtime_stream(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        window.brain_mode.setCurrentText("Chat")
        window.chat_input.setPlainText("Summarize the runtime law spine.")
        window._start_chat()

        self.assertTrue(_pump_until(lambda: window._chat_thread is None and window.snapshot is not None, timeout=5.0))
        self.assertIn("mock brain", window.chat_output.toPlainText())
        self.assertEqual(window.send_button.text(), "Ask ARIS")

    def test_v2_window_changes_panel_uses_passive_review_bridge(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        original_workspace_payload = host.service.workspace_payload

        def fake_workspace_payload(session_id: str):
            payload = dict(original_workspace_payload(session_id))
            payload["applied_changes"] = [
                {
                    "path": "evolving_ai/aris_runtime/desktop_app.py",
                    "summary": "Updated the current task lane.",
                    "diff": (
                        "diff --git a/evolving_ai/aris_runtime/desktop_app.py "
                        "b/evolving_ai/aris_runtime/desktop_app.py\n"
                        "@@ -1,1 +1,2 @@\n"
                        "-old\n+new\n"
                    ),
                }
            ]
            return payload

        with patch.object(host.service, "workspace_payload", side_effect=fake_workspace_payload):
            window = ArisRuntimeDesktopWindow(host)
            self.addCleanup(window.close)
            self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        self.assertGreater(window.workspace_changes_list.count(), 0)
        self.assertIn("desktop_app.py", window.workspace_changes_list.item(0).text())
        self.assertIn("diff --git", window.workspace_diff_preview.toPlainText())

    def test_v2_window_exposes_replay_tab_and_task_memory_controls(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        tab_names = [window.studio_surface_tabs.tabText(index) for index in range(window.studio_surface_tabs.count())]
        self.assertIn("Replay", tab_names)
        self.assertEqual(window.task_memory_save_button.text(), "Save Task Memory")
        self.assertTrue(hasattr(window, "workspace_replay_summary"))

    def test_v2_window_save_task_memory_persists_to_host(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        task = window._active_workspace_task()
        self.assertIsInstance(task, dict)
        task_id = str(task.get("id", "")).strip()
        window.task_memory_goals.setPlainText("Keep operator review central")
        window.task_memory_constraints.setPlainText("Do not bypass 1001")
        window.task_memory_do_not_touch.setPlainText("Protected core")
        window.task_memory_notes.setPlainText("Show intent before diff")
        window._save_task_memory()

        record = host.task_memory(task_id, title=str(task.get("title", "")).strip())
        self.assertIn("Keep operator review central", record["goals"])
        self.assertIn("Do not bypass 1001", record["constraints"])

    def test_v2_window_run_task_entry_injects_task_memory_into_queue_prompt(self) -> None:
        host, root = _make_host("v2", start_workers=True)
        self.addCleanup(lambda host=host, root=root: _cleanup_host_root(host, root))

        window = ArisRuntimeDesktopWindow(host)
        self.addCleanup(window.close)
        self.assertTrue(_pump_until(lambda: window.snapshot is not None and window._refresh_thread is None))

        task = window._active_workspace_task()
        self.assertIsInstance(task, dict)
        task_id = str(task.get("id", "")).strip()
        host.save_task_memory(
            task_id=task_id,
            title=str(task.get("title", "")).strip(),
            goals=["Protect approval flow"],
            constraints=["Stay in bounded runtime"],
        )

        captured: dict[str, Any] = {}

        def fake_enqueue_operator_task(**kwargs):
            captured.update(kwargs)
            return {
                "id": "queued-memory-task",
                "title": kwargs.get("title", "Task"),
            }

        with patch.object(host, "enqueue_operator_task", side_effect=fake_enqueue_operator_task):
            window._run_task_entry(task)

        prompt = str(captured.get("prompt", ""))
        self.assertIn("Protect approval flow", prompt)
        self.assertIn("Stay in bounded runtime", prompt)


if __name__ == "__main__":
    unittest.main()
