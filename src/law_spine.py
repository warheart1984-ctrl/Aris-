from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any

from .constants_runtime import (
    LAW_CLASS_ROOT,
    ROOT_LAW_EXECUTION_PHASE,
    ROOT_LAW_MUTABILITY,
    ROOT_LAW_PRIORITY,
    ROOT_LAW_SCOPE,
    SPEECH_CODE,
    SPEECH_STATE,
    SPEECH_VERIFICATION,
    UL_ROOT_LAW_ID,
)


ROOT_LAW_TEXT = (
    "UL is the language of identity, law, and structure. "
    "CISIV governs formation lifecycle. CISLR governs runtime enforcement. "
    "The law spine is immutable, foundational, and always pre-execution. "
    "Speech must follow 0001 -> 1000 -> 1001. "
    "Identity cannot be copy-claimed without legitimacy. "
    "Containment or explicit degradation is required when law cannot be satisfied."
)

ROOT_LAW_MANIFEST: dict[str, Any] = {
    "id": UL_ROOT_LAW_ID,
    "class": LAW_CLASS_ROOT,
    "mutability": ROOT_LAW_MUTABILITY,
    "scope": ROOT_LAW_SCOPE,
    "priority": ROOT_LAW_PRIORITY,
    "execution_phase": ROOT_LAW_EXECUTION_PHASE,
    "speech_chain": [SPEECH_STATE, SPEECH_CODE, SPEECH_VERIFICATION],
    "laws": {
        "ul": "Language of identity, law, and structure.",
        "cisiv": "Formation lifecycle must remain lawful and attributable.",
        "cislr": "Runtime enforcement must happen before and after execution.",
        "law_spine": "Immutable kernel loaded at boot and verified continuously.",
        "ledger": "Truth surface for preflight, postflight, mutation, override, and degradation.",
        "law_of_speech": "No valid action may end at 1000 without 1001 verification.",
        "non_copy_clause": "Protected identities require legitimacy and lineage.",
        "containment_degradation": "When law fails, rejection or explicit degradation is mandatory.",
        "internal_authority": "No caller may declare facts that law depends on.",
        "post_verification_stability": (
            "After 1001, mutation freezes until observation and validation complete."
        ),
        "override_reckoning": (
            "Bypass attempts incur structural cost, escalation, recovery, and quarantine."
        ),
    },
    "text": ROOT_LAW_TEXT,
}


def _canonical_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"))


EXPECTED_ROOT_LAW_HASH = hashlib.sha256(
    _canonical_manifest(ROOT_LAW_MANIFEST).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class LawSpineSnapshot:
    manifest: MappingProxyType
    manifest_hash: str
    expected_hash: str
    frozen: bool

    @property
    def ok(self) -> bool:
        return self.frozen and self.manifest_hash == self.expected_hash

    def payload(self) -> dict[str, Any]:
        return {
            "manifest": dict(self.manifest),
            "manifest_hash": self.manifest_hash,
            "expected_hash": self.expected_hash,
            "frozen": self.frozen,
            "ok": self.ok,
        }


class LawSpine:
    def __init__(
        self,
        *,
        manifest: dict[str, Any] | None = None,
        expected_hash: str | None = None,
    ) -> None:
        raw_manifest = dict(manifest or ROOT_LAW_MANIFEST)
        self._manifest = MappingProxyType(raw_manifest)
        self._manifest_hash = hashlib.sha256(
            _canonical_manifest(raw_manifest).encode("utf-8")
        ).hexdigest()
        self._expected_hash = str(expected_hash or EXPECTED_ROOT_LAW_HASH)

    def snapshot(self) -> LawSpineSnapshot:
        return LawSpineSnapshot(
            manifest=self._manifest,
            manifest_hash=self._manifest_hash,
            expected_hash=self._expected_hash,
            frozen=True,
        )

    def verify_integrity(self) -> tuple[bool, str]:
        snapshot = self.snapshot()
        if snapshot.ok:
            return True, "Root law manifest hash verified."
        return False, "Root law manifest hash mismatch."
