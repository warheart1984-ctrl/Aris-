from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from evolving_ai.aris_demo.desktop import main as desktop_main
from evolving_ai.aris_demo.desktop_app import ArisDemoDesktopWindow
from evolving_ai.aris_demo.desktop_build import build_pyinstaller_command
from evolving_ai.aris_demo.desktop_support import (
    ArisDemoDesktopHost,
    default_desktop_data_root,
    parse_sse_events,
    select_project_folder,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_RUNTIME_ROOT = REPO_ROOT / ".runtime" / "aris-demo-desktop-test"
_QT_APP = QApplication.instance() or QApplication([])


def _make_host(profile_id: str = "demo") -> tuple[ArisDemoDesktopHost, Path]:
    TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    root = TEST_RUNTIME_ROOT / f"case-{uuid.uuid4().hex[:10]}"
    root.mkdir(parents=True, exist_ok=True)
    return ArisDemoDesktopHost(data_root=root, start_workers=False, profile_id=profile_id), root


class ArisDemoDesktopSupportTests(unittest.TestCase):
    def test_default_desktop_data_root_honors_override(self) -> None:
        override = Path(tempfile.gettempdir()) / "aris-demo-override"
        with patch.dict(os.environ, {"ARIS_DEMO_DESKTOP_ROOT": str(override)}, clear=False):
            self.assertEqual(default_desktop_data_root("windows"), override.resolve())

    def test_default_desktop_data_root_is_profile_specific(self) -> None:
        self.assertEqual(default_desktop_data_root("windows").name, "ARIS Demo")
        self.assertEqual(default_desktop_data_root("windows", profile_id="v1").name, "ARIS Demo V1")
        self.assertEqual(default_desktop_data_root("windows", profile_id="v2").name, "ARIS Demo V2")

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

        self.assertEqual(snapshot.status["system_name"], "ARIS Demo")
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
        self.assertEqual(features["forge_planning"].status, "stripped")
        self.assertEqual(targets, {"windows", "macos", "linux"})
        self.assertEqual(artifacts, {"ARIS Demo.exe", "ARIS Demo.app", "dist/ARIS Demo/"})

    def test_v1_snapshot_exposes_forge_profile(self) -> None:
        host, root = _make_host("v1")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        snapshot = host.snapshot(host.ensure_session())
        features = {item.id: item for item in snapshot.features}
        artifacts = {item.artifact for item in snapshot.packaging_targets}

        self.assertEqual(snapshot.status["system_name"], "ARIS Demo V1")
        self.assertEqual(snapshot.status["runtime_profile"], "v1")
        self.assertEqual(snapshot.status["model_router"]["mode"], "auto")
        self.assertFalse(snapshot.status["demo_mode"]["active"])
        self.assertFalse(snapshot.status["evolving_engine"]["active"])
        self.assertIn(features["forge_planning"].status, {"available", "offline"})
        self.assertEqual(snapshot.workspace_surface["worker"]["title"], "Forge Worker Lane")
        self.assertIn("Forge is connected", snapshot.workspace_surface["worker"]["lines"][0])
        self.assertEqual(artifacts, {"ARIS Demo V1.exe", "ARIS Demo V1.app", "dist/ARIS Demo V1/"})

    def test_v2_snapshot_exposes_evolving_runtime_profile(self) -> None:
        host, root = _make_host("v2")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        snapshot = host.snapshot(host.ensure_session())
        features = {item.id: item for item in snapshot.features}
        artifacts = {item.artifact for item in snapshot.packaging_targets}

        self.assertEqual(snapshot.status["system_name"], "ARIS Demo V2")
        self.assertEqual(snapshot.status["runtime_profile"], "v2")
        self.assertTrue(snapshot.status["evolving_engine"]["active"])
        self.assertEqual(features["evolving_engine"].status, "active")
        self.assertEqual(snapshot.status["model_router"]["mode"], "auto")
        self.assertEqual(artifacts, {"ARIS Demo V2.exe", "ARIS Demo V2.app", "dist/ARIS Demo V2/"})

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

    def test_parse_sse_events_and_build_command(self) -> None:
        parsed = parse_sse_events('event: meta\ndata: {"ok": true}\n\n')
        command = build_pyinstaller_command()
        v1_command = build_pyinstaller_command(profile_id="v1")
        v2_command = build_pyinstaller_command(profile_id="v2")

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].event, "meta")
        self.assertTrue(parsed[0].payload["ok"])
        self.assertIn("--windowed", command)
        self.assertIn("tkinter", command)
        self.assertTrue(any(str(item).endswith("desktop.py") for item in command))
        self.assertIn("ARIS Demo V1", v1_command)
        self.assertIn("ARIS Demo V2", v2_command)
        self.assertTrue(any(str(item).endswith("desktop_v1.py") for item in v1_command))
        self.assertTrue(any(str(item).endswith("desktop_v2.py") for item in v2_command))

    def test_select_project_folder_returns_none_on_cancel(self) -> None:
        root = unittest.mock.Mock()
        with patch("evolving_ai.aris_demo.desktop_support.tk.Tk", return_value=root), patch(
            "evolving_ai.aris_demo.desktop_support.filedialog.askdirectory",
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
            "evolving_ai.aris_demo.desktop_support.select_project_folder",
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

        host = ArisDemoDesktopHost(data_root=root, start_workers=False)
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
        self.assertIn('"system_name": "ARIS Demo"', payload)
        self.assertIn('"ul_runtime_present": true', payload.lower())
        self.assertIn('"model_router"', payload)

    def test_desktop_entry_headless_smokecheck_supports_v2_profile(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = desktop_main(["--headless-smokecheck", "--no-workers", "--profile", "v2"])

        self.assertEqual(exit_code, 0)
        payload = output.getvalue()
        self.assertIn('"profile_id": "v2"', payload)
        self.assertIn('"system_name": "ARIS Demo V2"', payload)
        self.assertIn('"packaging_artifacts"', payload)

    def test_v1_window_defaults_to_forge_governed_brain_state(self) -> None:
        host, root = _make_host("v1")
        self.addCleanup(host.close)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        window = ArisDemoDesktopWindow(host)
        self.addCleanup(window.close)

        self.assertEqual(window.brain_target.currentText(), "Forge")
        self.assertEqual(window.brain_permission.currentText(), "Approval Required")
        self.assertIn("Forge", window.workspace_route_summary.text())
        self.assertEqual(window.tabs.count(), 1)
        self.assertEqual(window.tabs.tabText(0), "Studio")
        self.assertEqual(window.hero_title.text(), "ARIS Studio V1")


if __name__ == "__main__":
    unittest.main()
