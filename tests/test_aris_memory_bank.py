from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from evolving_ai.app.memory import MemoryStore
from evolving_ai.aris.memory_bank import GovernedMemoryBank
from src.constants_runtime import ARIS_DOC_CHANNEL_ID, ARIS_HANDBOOK_ID


class GovernedMemoryBankTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="aris-memory-bank-"))
        self.addCleanup(lambda: shutil.rmtree(self._temp_dir, ignore_errors=True))

    def test_foundational_root_memory_is_present_and_locked(self) -> None:
        bank = GovernedMemoryBank(
            self._temp_dir / "memory_bank",
            foundation_root=self._temp_dir / "foundation",
        )

        handbook = bank.get(ARIS_HANDBOOK_ID)
        doc_channel = bank.get(ARIS_DOC_CHANNEL_ID)
        self.assertIsNotNone(handbook)
        self.assertIsNotNone(doc_channel)
        self.assertEqual(handbook.layer, "foundational")
        self.assertEqual(handbook.status, "locked")
        self.assertEqual(doc_channel.layer, "foundational")
        self.assertEqual(doc_channel.status, "locked")
        with self.assertRaises(PermissionError):
            bank.update_entry(ARIS_HANDBOOK_ID, summary="overwrite attempt")
        with self.assertRaises(PermissionError):
            bank.update_entry(ARIS_DOC_CHANNEL_ID, summary="overwrite attempt")
        with self.assertRaises(PermissionError):
            bank.admit_entry(
                layer="foundational",
                entry_type="note",
                source="test",
                summary="illegal",
                content="illegal",
            )

    def test_retrieval_prefers_higher_authority_layers(self) -> None:
        bank = GovernedMemoryBank(
            self._temp_dir / "memory_bank",
            foundation_root=self._temp_dir / "foundation",
        )
        bank.admit_entry(
            layer="operational",
            entry_type="repo",
            source="test",
            summary="Current repo: ARIS-runtime",
            content="ARIS-runtime selected for the active session.",
            tags=("runtime",),
        )
        bank.admit_learned_pattern(
            name="safe_plan",
            summary="Plan before apply",
            content="Use planning before repo changes.",
            source="test",
            tags=("pattern",),
        )

        retrieved = bank.retrieve(limit=5)

        self.assertGreaterEqual(len(retrieved), 3)
        self.assertEqual(retrieved[0]["layer"], "foundational")
        self.assertEqual(retrieved[0]["id"], ARIS_HANDBOOK_ID)

    def test_rejected_patterns_are_separate_from_live_context(self) -> None:
        bank = GovernedMemoryBank(
            self._temp_dir / "memory_bank",
            foundation_root=self._temp_dir / "foundation",
        )
        bank.reject_pattern(
            name="unstable_patch",
            summary="Rejected unstable patch flow",
            content="This path caused repeated failed applies.",
            source="test",
            tags=("reject", "patch"),
        )

        live = bank.retrieve(query="unstable", limit=5)
        with_rejected = bank.retrieve(query="unstable", limit=5, include_rejected=True)

        self.assertFalse(any(item["layer"] == "rejected_patterns" for item in live))
        self.assertTrue(any(item["layer"] == "rejected_patterns" for item in with_rejected))

    def test_corrupt_non_foundational_layer_is_recovered(self) -> None:
        bank = GovernedMemoryBank(
            self._temp_dir / "memory_bank",
            foundation_root=self._temp_dir / "foundation",
        )
        operational_path = bank.layer_paths["operational"]
        operational_path.write_text("{bad json", encoding="utf-8")

        entries = bank.entries(layer="operational")

        self.assertEqual(entries, [])
        self.assertEqual(operational_path.read_text(encoding="utf-8").strip(), "[]")
        self.assertTrue(operational_path.with_suffix(".json.corrupt").exists())


class MemoryStoreAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="aris-memory-store-"))
        self.addCleanup(lambda: shutil.rmtree(self._temp_dir, ignore_errors=True))

    def test_memory_store_routes_user_memory_into_governed_bank(self) -> None:
        store = MemoryStore(self._temp_dir / "memory.json")

        store.remember_from_user_text("My name is Alice. I prefer governed builds.")

        facts = store.facts()
        categories = {item["category"] for item in facts}
        self.assertIn("name", categories)
        self.assertIn("preference", categories)
        self.assertTrue(store.summary())
        self.assertTrue(store.locked_entries())
