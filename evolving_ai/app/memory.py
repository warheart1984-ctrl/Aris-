from __future__ import annotations

import json
from pathlib import Path

from evolving_ai.aris.memory_bank import GovernedMemoryBank
from src.conversation_memory import is_foundational_shadow_attempt


class MemoryStore:
    """Compatibility adapter backed by the governed ARIS memory bank."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.bank = GovernedMemoryBank(
            self.path.parent / "memory_bank",
            foundation_root=self.path.parent / "foundation",
        )
        self.law_ledger = self.bank.law_ledger
        self._migrate_legacy_payload()
        self._sync_legacy_export()

    def remember_from_user_text(self, text: str) -> None:
        if is_foundational_shadow_attempt(text):
            self.law_ledger.record(
                "foundational_memory_shadow_rejected",
                {
                    "text": str(text or ""),
                    "reason": "Foundational memory IDs are readable but immutable.",
                },
                require_success=True,
            )
            return
        additions = self.bank.remember_from_user_text(text, source="user")
        if additions:
            self._sync_legacy_export()

    def summary(self) -> str:
        return self.bank.summary()

    def facts(self) -> list[dict[str, str]]:
        return self.bank.facts_payload()

    def locked_entries(self) -> list[dict[str, str]]:
        return self.bank.locked_entries()

    def status_payload(self) -> dict[str, object]:
        return self.bank.status_payload()

    def _migrate_legacy_payload(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(raw, list):
            return
        changed = False
        for item in raw:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "")).strip()
            value = str(item.get("value", "")).strip()
            if not category or not value:
                continue
            self.bank.admit_entry(
                layer="operational",
                entry_type=category,
                source="legacy_memory",
                summary=f"{category}: {value}",
                content=value,
                tags=("legacy", category),
            )
            changed = True
        if changed:
            self._sync_legacy_export()

    def _sync_legacy_export(self) -> None:
        payload = [
            {
                "category": item.get("category", ""),
                "value": item.get("value", ""),
            }
            for item in self.bank.facts_payload()
        ]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
