from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants_runtime import ARIS_HANDBOOK_ID, FOUNDATION_STORE_FILENAME, UL_ROOT_LAW_ID
from .law_spine import ROOT_LAW_TEXT


DEFAULT_FOUNDATION_ENTRIES = {
    UL_ROOT_LAW_ID: {
        "id": UL_ROOT_LAW_ID,
        "class": "UL_ROOT_LAW",
        "content": ROOT_LAW_TEXT,
        "mutable": False,
    },
    ARIS_HANDBOOK_ID: {
        "id": ARIS_HANDBOOK_ID,
        "class": "FOUNDATIONAL_MEMORY",
        "content": (
            "ARIS foundational handbook: 1001 first, immutable laws first, governance before execution, "
            "verification before success, halls remain separated, and protected identities require legitimacy."
        ),
        "mutable": False,
    },
}


class FoundationStore:
    def __init__(self, root: Path) -> None:
        self.path = root / FOUNDATION_STORE_FILENAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(DEFAULT_FOUNDATION_ENTRIES, indent=2), encoding="utf-8")
        self._entries = json.loads(self.path.read_text(encoding="utf-8"))

    def entries(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)

    def get(self, entry_id: str) -> dict[str, Any] | None:
        item = self._entries.get(str(entry_id or "").strip())
        return dict(item) if isinstance(item, dict) else None

    def is_foundational_id(self, value: str) -> bool:
        return str(value or "").strip() in self._entries

    def overwrite(self, entry_id: str, content: str) -> None:
        raise PermissionError(f"{entry_id} is foundational and cannot be overwritten.")
