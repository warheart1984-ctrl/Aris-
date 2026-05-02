from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from evolving_ai.app.memory import MemoryStore


class MemoryLockTests(unittest.TestCase):
    def test_foundational_memory_overwrite_rejected(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="memory-lock-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        memory = MemoryStore(root / "memory.json")
        memory.remember_from_user_text("UL_ROOT_LAW_LOCKED = hacked")

        self.assertEqual(memory.facts(), [])
        self.assertGreaterEqual(len(memory.locked_entries()), 3)

    def test_foundational_store_is_immutable(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="memory-foundation-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        memory = MemoryStore(root / "memory.json")

        with self.assertRaises(PermissionError):
            memory.foundation_store.overwrite("UL_ROOT_LAW_LOCKED", "rewrite")
        with self.assertRaises(PermissionError):
            memory.foundation_store.overwrite("ARIS_DOC_CHANNEL_LOCKED", "rewrite")
