from __future__ import annotations

from pathlib import Path

from .hall_base import GovernanceHall


class HallOfDiscard(GovernanceHall):
    """Escalation and verification failures contained for redesign."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root=root,
            hall_id="hall-of-discard",
            entry_prefix="discard",
            track_reentry=True,
            reentry_requirements=[
                "redesign_required",
                "re_evaluation_required",
                "treat_as_fresh_proposal",
            ],
        )

    def discard(self, **kwargs):
        return self.record(**kwargs)
