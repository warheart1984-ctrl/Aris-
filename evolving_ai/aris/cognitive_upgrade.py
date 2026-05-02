from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any, Protocol

from evolving_ai.app.attachments import Attachment
from evolving_ai.app.providers import ChatProvider
from src.doc_channel import DocChannel


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _chunk_reply(text: str) -> list[str]:
    chunks = [match.group(0) for match in re.finditer(r"\S+\s*", text)]
    return chunks or ([text] if text else [])


class UpgradeTransformer(Protocol):
    name: str

    def pre_process(
        self,
        *,
        messages: list[dict[str, str]],
        mode: str,
        model: str,
    ) -> list[dict[str, str]]:
        ...

    def post_process(
        self,
        *,
        response: str,
        mode: str,
        model: str,
    ) -> str:
        ...


@dataclass(frozen=True, slots=True)
class UpgradeTrialRecord:
    prompt: str
    upgrade_name: str
    baseline_score: float
    upgraded_score: float
    lawful: bool
    stable: bool
    identity_preserved: bool
    accepted: bool
    notes: str
    timestamp: str
    mode: str
    model: str

    def payload(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "upgrade_name": self.upgrade_name,
            "baseline_score": self.baseline_score,
            "upgraded_score": self.upgraded_score,
            "lawful": self.lawful,
            "stable": self.stable,
            "identity_preserved": self.identity_preserved,
            "accepted": self.accepted,
            "notes": self.notes,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "model": self.model,
        }


class IdentityAnchorUpgrade:
    name = "identity_anchor_v1"

    def pre_process(
        self,
        *,
        messages: list[dict[str, str]],
        mode: str,
        model: str,
    ) -> list[dict[str, str]]:
        upgraded = [dict(message) for message in messages]
        upgraded.append(
            {
                "role": "system",
                "content": (
                    "ARIS cognitive upgrade anchor: remain the speaking identity, preserve governance-aware "
                    "language, do not surrender voice to Forge or any other subsystem, and answer in a way "
                    "that keeps the operator-facing intelligence coherent."
                ),
            }
        )
        return upgraded

    def post_process(
        self,
        *,
        response: str,
        mode: str,
        model: str,
    ) -> str:
        cleaned = re.sub(r"\n{3,}", "\n\n", str(response or "")).strip()
        cleaned = re.sub(r"^\s*(Forge|ForgeEval)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned


class CognitiveUpgradeManager:
    """Runs bounded transformer upgrades around the core ARIS call and records evidence."""

    def __init__(
        self,
        *,
        history_path: Path,
        doc_channel: DocChannel | None = None,
        upgrades: list[UpgradeTransformer] | None = None,
    ) -> None:
        self.history_path = history_path.resolve()
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.exists():
            self.history_path.write_text("", encoding="utf-8")
        self.doc_channel = doc_channel
        self.upgrades = list(upgrades or [IdentityAnchorUpgrade()])

    def status_payload(self) -> dict[str, Any]:
        history = self.list_history(limit=1)
        return {
            "active": True,
            "history_path": str(self.history_path),
            "active_upgrades": [upgrade.name for upgrade in self.upgrades],
            "history_count": self.history_count(),
            "last_trial": history[0] if history else None,
            "transformer_only": True,
            "identity_anchor_preserved": True,
            "doc_channel": self.doc_channel.payload() if self.doc_channel is not None else None,
        }

    def history_count(self) -> int:
        if not self.history_path.exists():
            return 0
        return sum(1 for line in self.history_path.read_text(encoding="utf-8").splitlines() if line.strip())

    def list_history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            entries.append(json.loads(stripped))
        return list(reversed(entries[-max(1, limit) :]))

    def _append_history(self, record: UpgradeTrialRecord) -> None:
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.payload(), ensure_ascii=True) + "\n")

    async def _collect_reply(
        self,
        *,
        runner: Callable[[list[dict[str, str]]], Awaitable[str]],
        messages: list[dict[str, str]],
    ) -> str:
        injected = [dict(message) for message in messages]
        if self.doc_channel is not None:
            injected = self.doc_channel.inject_messages(injected)
        return await runner(injected)

    def _baseline_prompt(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if str(message.get("role", "")).strip().lower() == "user":
                return str(message.get("content", "")).strip()
        return ""

    def _score_reply(self, *, prompt: str, reply: str) -> float:
        cleaned_prompt = str(prompt or "").lower()
        cleaned_reply = str(reply or "").lower()
        prompt_terms = [
            term
            for term in re.findall(r"[a-z0-9_]{4,}", cleaned_prompt)
            if term not in {"this", "that", "with", "from", "your", "have", "will"}
        ][:6]
        prompt_hit_count = sum(1 for term in prompt_terms if term in cleaned_reply)
        structure_bonus = 0.3 if any(marker in reply for marker in ("\n-", "\n1.", ":")) else 0.0
        length_score = min(len(str(reply or "").strip()), 1200) / 1200
        prompt_alignment = prompt_hit_count / max(1, len(prompt_terms)) if prompt_terms else 0.2
        drift_penalty = 0.2 if self._identity_drift_detected(reply) else 0.0
        risk_penalty = 0.25 if self._harm_or_bypass_risk(reply) else 0.0
        return round(length_score + prompt_alignment + structure_bonus - drift_penalty - risk_penalty, 4)

    def _identity_drift_detected(self, reply: str) -> bool:
        lowered = str(reply or "").lower()
        drift_markers = (
            "i am forge",
            "forge:",
            "forgeeval:",
            "evolving core",
            "evolving-ai can apply",
            "i am the evolving core",
        )
        return any(marker in lowered for marker in drift_markers)

    def _identity_preserved(self, *, baseline_reply: str, upgraded_reply: str) -> bool:
        if not _normalize_text(upgraded_reply):
            return False
        if self._identity_drift_detected(upgraded_reply):
            return False
        baseline_has_aris = "aris" in str(baseline_reply or "").lower()
        upgraded_has_aris = "aris" in str(upgraded_reply or "").lower()
        return upgraded_has_aris or not baseline_has_aris

    def _harm_or_bypass_risk(self, reply: str) -> bool:
        lowered = str(reply or "").lower()
        risky_phrases = (
            "disable 1001",
            "bypass forge eval",
            "ignore verification",
            "hidden path",
            "unverified return",
            "destroy system",
            "erase logs",
        )
        return any(phrase in lowered for phrase in risky_phrases)

    def _stable(self, *, baseline_reply: str, upgraded_reply: str) -> bool:
        baseline = _normalize_text(baseline_reply)
        upgraded = _normalize_text(upgraded_reply)
        if not upgraded:
            return False
        if len(upgraded) > max(len(baseline) * 3, 1200):
            return False
        if re.search(r"(.{20,})\1{2,}", upgraded):
            return False
        return True

    async def evaluate(
        self,
        *,
        messages: list[dict[str, str]],
        mode: str,
        model: str,
        runner: Callable[[list[dict[str, str]]], Awaitable[str]],
    ) -> tuple[str, dict[str, Any]]:
        prompt = self._baseline_prompt(messages)
        baseline_reply = await self._collect_reply(runner=runner, messages=messages)
        baseline_score = self._score_reply(prompt=prompt, reply=baseline_reply)
        best_reply = baseline_reply
        best_score = baseline_score
        best_upgrade = ""
        trials: list[dict[str, Any]] = []

        for upgrade in self.upgrades:
            notes: list[str] = []
            try:
                transformed_messages = upgrade.pre_process(
                    messages=messages,
                    mode=mode,
                    model=model,
                )
                raw_upgraded_reply = await self._collect_reply(
                    runner=runner,
                    messages=transformed_messages,
                )
                upgraded_reply = upgrade.post_process(
                    response=raw_upgraded_reply,
                    mode=mode,
                    model=model,
                )
                lawful = not self._harm_or_bypass_risk(upgraded_reply)
                stable = self._stable(
                    baseline_reply=baseline_reply,
                    upgraded_reply=upgraded_reply,
                )
                identity_preserved = self._identity_preserved(
                    baseline_reply=baseline_reply,
                    upgraded_reply=upgraded_reply,
                )
                upgraded_score = self._score_reply(prompt=prompt, reply=upgraded_reply)
                improved = (
                    upgraded_score > baseline_score
                    and lawful
                    and stable
                    and identity_preserved
                )
                if not lawful:
                    notes.append("Rejected because the upgraded output introduced law bypass or harm risk.")
                if not stable:
                    notes.append("Rejected because the upgraded output was unstable relative to baseline.")
                if not identity_preserved:
                    notes.append("Rejected because ARIS identity preservation failed.")
                if lawful and stable and identity_preserved and upgraded_score <= baseline_score:
                    notes.append("Rejected because the upgrade did not improve on the baseline score.")
                if improved and upgraded_score > best_score:
                    best_reply = upgraded_reply
                    best_score = upgraded_score
                    best_upgrade = upgrade.name
                    notes.append("Accepted as a bounded transformer improvement over baseline.")
            except Exception as exc:
                upgraded_score = baseline_score
                lawful = False
                stable = False
                identity_preserved = False
                improved = False
                notes.append(f"Upgrade execution failed: {exc}")
            record = UpgradeTrialRecord(
                prompt=prompt,
                upgrade_name=upgrade.name,
                baseline_score=baseline_score,
                upgraded_score=upgraded_score,
                lawful=lawful,
                stable=stable,
                identity_preserved=identity_preserved,
                accepted=improved,
                notes=" ".join(notes).strip() or "Upgrade evaluated.",
                timestamp=_utc_now(),
                mode=mode,
                model=model,
            )
            self._append_history(record)
            trials.append(record.payload())

        return best_reply, {
            "baseline_score": baseline_score,
            "selected_upgrade": best_upgrade or None,
            "selected_score": best_score,
            "trial_count": len(trials),
            "trials": trials,
        }


class ArisCognitiveUpgradeProvider:
    """Provider wrapper that keeps upgrades inside the core ARIS call path."""

    def __init__(self, inner: ChatProvider, manager: CognitiveUpgradeManager) -> None:
        self.inner = inner
        self.manager = manager

    async def _run_core_call(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> str:
        chunks: list[str] = []
        async for chunk in self.inner.stream_reply(
            messages=messages,
            fast_mode=fast_mode,
            mode=mode,
            model=model,
            attachments=attachments,
        ):
            chunks.append(chunk)
        return "".join(chunks).strip()

    async def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        if mode == "agent":
            async for chunk in self.inner.stream_reply(
                messages=messages,
                fast_mode=fast_mode,
                mode=mode,
                model=model,
                attachments=attachments,
            ):
                yield chunk
            return

        reply, _ = await self.manager.evaluate(
            messages=messages,
            mode=mode,
            model=model,
            runner=lambda candidate_messages: self._run_core_call(
                messages=candidate_messages,
                fast_mode=fast_mode,
                mode=mode,
                model=model,
                attachments=attachments,
            ),
        )
        final_reply = reply or "No response came back from the ARIS model route."
        for chunk in _chunk_reply(final_reply):
            await asyncio.sleep(0)
            yield chunk
