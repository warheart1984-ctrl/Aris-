from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from evolving_ai.aris.memory_bank import GovernedMemoryBank
from evolving_ai.aris_runtime.bridge_intelligence import BridgeIntelligenceEngine


class BridgeIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aris-bridge-intel-")).resolve()
        self.memory_bank = GovernedMemoryBank(
            self.root / "memory_bank",
            foundation_root=self.root / "foundation",
        )
        self.engine = BridgeIntelligenceEngine(
            self.root / "bridge_intelligence",
            memory_bank=self.memory_bank,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_build_for_task_classifies_runtime_refactor_and_persists_pattern(self) -> None:
        intelligence = self.engine.build_for_task(
            task={
                "id": "task-runtime-refactor",
                "title": "Refactor runtime approval flow",
                "summary": "Fix the runtime approval handoff and keep review visible.",
                "status": "Blocked",
                "latest_update": "Changes are waiting for review before apply.",
                "approval_id": "approval-123",
            },
            review={
                "summary": "Pending review: runtime approval flow refactor",
                "changed_files": [
                    "evolving_ai/aris/runtime.py",
                    "evolving_ai/aris_runtime/desktop_app.py",
                ],
            },
            run={
                "id": "run-runtime-refactor",
                "status": "completed",
                "created_at": "2026-05-02T00:00:00+00:00",
                "updated_at": "2026-05-02T00:00:05+00:00",
            },
            run_events=[
                {"kind": "status", "message": "Refactor runtime approval flow"},
                {"kind": "validation", "message": "Validation passed after retry"},
            ],
            local_events=[],
        )

        self.assertEqual(intelligence["intent"], "refactor")
        self.assertEqual(intelligence["semantic_intent"], "transform")
        self.assertEqual(intelligence["risk"], "high")
        self.assertTrue({"aris", "aris_runtime"}.issubset(set(intelligence["affected_modules"])))
        self.assertTrue(intelligence["decision"]["chain"]["mean"] > 0)
        self.assertTrue(self.engine.pattern_store.list_patterns(limit=10))

    def test_task_memory_round_trip_and_prompt_context(self) -> None:
        record = self.engine.save_task_memory(
            task_id="task-memory-1",
            title="Build repo manager",
            goals=["Build the repo manager"],
            constraints=["Keep approvals visible"],
            notes=["Prefer bounded runtime actions"],
            do_not_touch=["Law spine"],
        )
        context = self.engine.task_memory.prompt_context("task-memory-1")

        self.assertEqual(record["title"], "Build repo manager")
        self.assertTrue(any("Goals:" in line for line in context))
        self.assertTrue(any("Do not touch:" in line for line in context))
        retrieved = self.memory_bank.retrieve(query="Build repo manager", limit=10)
        self.assertTrue(any(item["type"] == "task_memory" for item in retrieved))

    def test_record_rejection_updates_task_memory_and_rejected_patterns(self) -> None:
        record = self.engine.record_rejection(
            task_id="task-reject-1",
            title="Touch protected runtime path",
            reason="Touches forbidden area",
            note="Do not modify runtime law files from this task.",
            intelligence={
                "intent": "bugfix",
                "risk": "high",
                "affected_modules": ["runtime"],
            },
        )

        self.assertTrue(record["reject_reasons"])
        rejected = self.memory_bank.retrieve(
            query="Touches forbidden area",
            limit=10,
            include_rejected=True,
        )
        self.assertTrue(any(item["layer"] == "rejected_patterns" for item in rejected))

    def test_build_for_task_records_branch_and_replay(self) -> None:
        intelligence = self.engine.build_for_task(
            task={
                "id": "task-branch-1",
                "title": "Inspect protected execution boundaries",
                "summary": "Inspect the protected execution boundaries.",
                "status": "Blocked",
                "latest_update": "Approval required before continuation.",
                "approval_id": "approval-branch-1",
            },
            review={
                "summary": "Pending review for protected execution boundaries.",
                "changed_files": ["evolving_ai/aris_runtime/desktop_support.py"],
            },
            run={
                "id": "run-branch-1",
                "status": "blocked",
                "created_at": "2026-05-02T00:00:00+00:00",
                "updated_at": "2026-05-02T00:00:10+00:00",
                "blocked_on_approval_id": "approval-branch-1",
            },
            run_events=[
                {"kind": "approval_required", "message": "Approval is required before changes can continue."},
                {"kind": "status", "message": "Inspect protected execution boundaries"},
            ],
            local_events=[{"kind": "scheduler", "title": "Task started", "detail": "Inspect protected execution boundaries"}],
        )

        self.assertTrue(intelligence["branches"])
        self.assertTrue(intelligence["replay"]["timeline"])
        counterfactual = self.engine.build_for_task(
            task={"id": "task-branch-1b", "title": "Inspect"},
            review={},
        )["decision"]["counterfactual"]
        self.assertIn("altMean", counterfactual)
        self.assertTrue(str(counterfactual["reason"]).strip())


if __name__ == "__main__":
    unittest.main()
