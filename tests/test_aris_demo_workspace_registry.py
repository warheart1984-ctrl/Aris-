from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from evolving_ai.aris_demo.feedback import build_feedback_packet, write_feedback_packet
from evolving_ai.aris_demo.workspace_registry import WorkspaceRegistry


class WorkspaceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(tempfile.mkdtemp(prefix="aris-registry-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    def test_registry_seeds_and_can_activate_added_workspace(self) -> None:
        seed_root = self.temp_root / "seed"
        second_root = self.temp_root / "second"
        seed_root.mkdir(parents=True, exist_ok=True)
        second_root.mkdir(parents=True, exist_ok=True)
        registry = WorkspaceRegistry(self.temp_root / "registry.json", seed_root=seed_root)

        seeded = registry.active()
        added = registry.add_workspace(second_root, name="Second Workspace")
        activated = registry.set_active(added["id"])

        self.assertEqual(seeded["root_path"], str(seed_root))
        self.assertEqual(activated["id"], added["id"])
        self.assertEqual(registry.active()["id"], added["id"])

    def test_registry_preview_search_and_action_stay_within_root(self) -> None:
        seed_root = self.temp_root / "seed"
        seed_root.mkdir(parents=True, exist_ok=True)
        target_file = seed_root / "alpha.txt"
        target_file.write_text("bounded search content\n", encoding="utf-8")
        registry = WorkspaceRegistry(self.temp_root / "registry.json", seed_root=seed_root)

        preview = registry.preview_file(target_file)
        results = registry.search_files("search content")
        action = registry.action("send_to_aris", target_file).as_payload()

        self.assertEqual(preview["relative_path"], "alpha.txt")
        self.assertIn("bounded search content", preview["content"])
        self.assertTrue(results)
        self.assertIn("alpha.txt", action["summary"])
        with self.assertRaises(ValueError):
            registry.validate_target(self.temp_root.parent)


class FeedbackPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(tempfile.mkdtemp(prefix="aris-feedback-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    def test_feedback_packet_writes_structured_export(self) -> None:
        packet = build_feedback_packet(
            app_version="ARIS Demo 0.1.0",
            feedback_type="feature_request",
            user_note="Please add stronger repo compare controls.",
            active_brain="Inspect",
            active_tier="Read Only",
            active_workspace="Project Infi Code",
            recent_events=[{"title": "Workspace activated"}],
            recent_logs=[{"detail": "Worker lane idle."}],
            runtime_profile="demo",
        )
        export_path = write_feedback_packet(self.temp_root / "feedback", packet)

        self.assertTrue(export_path.exists())
        self.assertEqual(packet["feedback_type"], "feature_request")
        self.assertIn("active_workspace", packet)


if __name__ == "__main__":
    unittest.main()
