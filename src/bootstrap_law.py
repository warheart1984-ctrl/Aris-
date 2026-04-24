from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .constants_runtime import DISPOSITION_DEGRADED, DISPOSITION_VALID
from .law_spine import LawSpine, LawSpineSnapshot


@dataclass(frozen=True, slots=True)
class BootstrapLawState:
    ok: bool
    disposition: str
    loaded_at: str
    reason: str
    snapshot: LawSpineSnapshot

    def payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "disposition": self.disposition,
            "loaded_at": self.loaded_at,
            "reason": self.reason,
            "snapshot": self.snapshot.payload(),
        }


class BootstrapLaw:
    def __init__(self, *, spine: LawSpine | None = None) -> None:
        self.spine = spine or LawSpine()

    def load(self) -> BootstrapLawState:
        ok, reason = self.spine.verify_integrity()
        return BootstrapLawState(
            ok=ok,
            disposition=DISPOSITION_VALID if ok else DISPOSITION_DEGRADED,
            loaded_at=datetime.now(UTC).isoformat(),
            reason=reason,
            snapshot=self.spine.snapshot(),
        )
