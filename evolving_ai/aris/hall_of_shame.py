from __future__ import annotations

from pathlib import Path

from .hall_base import GovernanceHall


class HallOfShame(GovernanceHall):
    """Correctness failures and core-law defects."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root=root,
            hall_id="hall-of-shame",
            entry_prefix="shame",
            track_reentry=True,
            reentry_requirements=[
                "correctness_fix_required",
                "re_evaluation_required",
                "treat_as_fresh_proposal",
            ],
        )

    def shame(self, **kwargs):
        return self.record(**kwargs)
