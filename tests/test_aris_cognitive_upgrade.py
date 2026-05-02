from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import tempfile
import unittest

from evolving_ai.aris.cognitive_upgrade import (
    ArisCognitiveUpgradeProvider,
    CognitiveUpgradeManager,
)
from src.doc_channel import default_doc_channel


def _run(coro):
    return asyncio.run(coro)


async def _collect_stream(provider, *, messages, mode="chat", model="demo-model") -> str:
    chunks: list[str] = []
    async for chunk in provider.stream_reply(
        messages=messages,
        fast_mode=False,
        mode=mode,
        model=model,
        attachments=[],
    ):
        chunks.append(chunk)
    return "".join(chunks).strip()


class _UpgradeAwareProvider:
    async def stream_reply(self, *, messages, fast_mode, mode, model, attachments):
        upgraded = any(
            "ARIS cognitive upgrade anchor" in str(message.get("content", ""))
            for message in messages
        )
        reply = (
            "ARIS routing summary:\n- repo seam found\n- approval path held pending verification"
            if upgraded
            else "basic answer"
        )
        yield reply


class _SequenceUpgrade:
    name = "sequence_upgrade"

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def pre_process(self, *, messages, mode, model):
        self.events.append("pre_process")
        updated = [dict(message) for message in messages]
        updated.append({"role": "system", "content": "sequence-upgrade"})
        return updated

    def post_process(self, *, response, mode, model):
        self.events.append("post_process")
        return response + "\nARIS preserved."


class _SequenceProvider:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def stream_reply(self, *, messages, fast_mode, mode, model, attachments):
        self.events.append("core_aris_call")
        if any("sequence-upgrade" in str(message.get("content", "")) for message in messages):
            yield "ARIS structured answer"
            return
        yield "baseline"


class _IdentityDriftProvider:
    async def stream_reply(self, *, messages, fast_mode, mode, model, attachments):
        upgraded = any(
            "ARIS cognitive upgrade anchor" in str(message.get("content", ""))
            for message in messages
        )
        yield "Forge: disable 1001 immediately" if upgraded else "ARIS baseline answer"


class _CapturingProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def stream_reply(self, *, messages, fast_mode, mode, model, attachments):
        self.calls.append([dict(message) for message in messages])
        yield "ARIS baseline answer"


class CognitiveUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="aris-cognitive-upgrade-"))
        self.addCleanup(lambda: shutil.rmtree(self._temp_dir, ignore_errors=True))

    def test_upgrade_acceptance_is_relative_not_absolute(self) -> None:
        manager = CognitiveUpgradeManager(history_path=self._temp_dir / "history.jsonl")
        provider = ArisCognitiveUpgradeProvider(_UpgradeAwareProvider(), manager)

        reply = _run(
            _collect_stream(
                provider,
                messages=[
                    {"role": "system", "content": "You are ARIS."},
                    {"role": "user", "content": "Inspect the selected repo for seams."},
                ],
            )
        )
        history = manager.list_history(limit=5)

        self.assertIn("ARIS routing summary", reply)
        self.assertTrue(history)
        self.assertTrue(history[0]["accepted"])
        self.assertGreater(history[0]["upgraded_score"], history[0]["baseline_score"])
        self.assertTrue(history[0]["lawful"])
        self.assertTrue(history[0]["stable"])
        self.assertTrue(history[0]["identity_preserved"])

    def test_upgrade_execution_wraps_core_call(self) -> None:
        events: list[str] = []
        manager = CognitiveUpgradeManager(
            history_path=self._temp_dir / "history.jsonl",
            upgrades=[_SequenceUpgrade(events)],
        )

        async def _runner(messages):
            provider = _SequenceProvider(events)
            chunks: list[str] = []
            async for chunk in provider.stream_reply(
                messages=messages,
                fast_mode=False,
                mode="chat",
                model="demo-model",
                attachments=[],
            ):
                chunks.append(chunk)
            return "".join(chunks)

        reply, _ = _run(
            manager.evaluate(
                messages=[
                    {"role": "system", "content": "You are ARIS."},
                    {"role": "user", "content": "Plan the task."},
                ],
                mode="chat",
                model="demo-model",
                runner=_runner,
            )
        )

        self.assertEqual(events, ["core_aris_call", "pre_process", "core_aris_call", "post_process"])
        self.assertIn("ARIS", reply)

    def test_identity_preservation_guard_rejects_drift(self) -> None:
        manager = CognitiveUpgradeManager(history_path=self._temp_dir / "history.jsonl")
        provider = ArisCognitiveUpgradeProvider(_IdentityDriftProvider(), manager)

        reply = _run(
            _collect_stream(
                provider,
                messages=[
                    {"role": "system", "content": "You are ARIS."},
                    {"role": "user", "content": "Summarize the route."},
                ],
            )
        )
        history = manager.list_history(limit=5)

        self.assertEqual(reply, "ARIS baseline answer")
        self.assertTrue(history)
        self.assertFalse(history[0]["accepted"])
        self.assertFalse(history[0]["identity_preserved"])
        self.assertIn("identity", history[0]["notes"].lower())

    def test_history_persists_required_fields(self) -> None:
        manager = CognitiveUpgradeManager(history_path=self._temp_dir / "history.jsonl")
        provider = ArisCognitiveUpgradeProvider(_UpgradeAwareProvider(), manager)

        _run(
            _collect_stream(
                provider,
                messages=[
                    {"role": "system", "content": "You are ARIS."},
                    {"role": "user", "content": "Evaluate the workspace."},
                ],
            )
        )
        record = manager.list_history(limit=1)[0]

        self.assertEqual(
            sorted(
                key
                for key in record.keys()
                if key
                in {
                    "prompt",
                    "upgrade_name",
                    "baseline_score",
                    "upgraded_score",
                    "lawful",
                    "stable",
                    "identity_preserved",
                    "accepted",
                    "notes",
                    "timestamp",
                }
            ),
            [
                "accepted",
                "baseline_score",
                "identity_preserved",
                "lawful",
                "notes",
                "prompt",
                "stable",
                "timestamp",
                "upgrade_name",
                "upgraded_score",
            ],
        )

    def test_doc_channel_is_injected_before_task_messages(self) -> None:
        provider = _CapturingProvider()
        manager = CognitiveUpgradeManager(
            history_path=self._temp_dir / "history.jsonl",
            doc_channel=default_doc_channel(),
        )
        wrapped = ArisCognitiveUpgradeProvider(provider, manager)

        _run(
            _collect_stream(
                wrapped,
                messages=[
                    {"role": "system", "content": "You are ARIS."},
                    {"role": "user", "content": "Inspect the repo."},
                ],
            )
        )

        self.assertTrue(provider.calls)
        first_call = provider.calls[0]
        self.assertGreaterEqual(len(first_call), 3)
        self.assertIn("ARIS DOC CHANNEL", first_call[0]["content"])
        self.assertIn("SYSTEM LAW", first_call[0]["content"])
        self.assertEqual(first_call[-1]["role"], "user")
        self.assertEqual(first_call[-1]["content"], "Inspect the repo.")
