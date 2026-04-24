from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RepoLogbook:
    """Repo-level what/why/how record for meaningful governed changes."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def exists(self) -> bool:
        return self.path.exists()

    def _heading_count(self) -> int:
        if not self.exists():
            return 0
        return sum(
            1
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        )

    def status_payload(self) -> dict[str, Any]:
        return {
            "active": self.exists(),
            "path": str(self.path),
            "entry_count": self._heading_count(),
            "required_for_meaningful_changes": True,
            "rule": "Undocumented change = unverified change -> automatically fails 1001.",
        }

    def append_entry(
        self,
        *,
        title: str,
        what_changed: list[str],
        why_it_changed: list[str],
        how_it_changed: list[str],
        files_changed: list[str],
        verification: list[str],
        remaining_risks: list[str],
        action_id: str = "",
        fingerprint: str = "",
    ) -> dict[str, Any]:
        if not self.exists():
            raise RuntimeError("Repo Logbook is missing.")
        recorded_at = _utc_now()
        day = recorded_at.split("T", 1)[0]
        section_lines = [
            "",
            f"## {day} - {title.strip() or 'Repo Change'}",
        ]
        if action_id or fingerprint:
            section_lines.extend(
                [
                    "Action linkage:",
                    f"- action_id: {action_id or 'n/a'}",
                    f"- fingerprint: {fingerprint or 'n/a'}",
                ]
            )
        section_lines.extend(
            [
                "What changed:",
                *[f"- {item}" for item in (what_changed or ["Change recorded."])],
                "",
                "Why it changed:",
                *[f"- {item}" for item in (why_it_changed or ["Reason not supplied."])],
                "",
                "How it changed:",
                *[f"- {item}" for item in (how_it_changed or ["Implementation path not supplied."])],
                "",
                "Files changed:",
                *[f"- {item}" for item in (files_changed or ["No files listed."])],
                "",
                "Verification:",
                *[f"- {item}" for item in (verification or ["Verification not supplied."])],
                "",
                "Remaining risks:",
                *[f"- {item}" for item in (remaining_risks or ["No remaining risks recorded."])],
                "",
            ]
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(section_lines))
        return {
            "recorded": True,
            "recorded_at": recorded_at,
            "path": str(self.path),
            "title": title.strip() or "Repo Change",
            "action_id": action_id,
            "fingerprint": fingerprint,
        }
