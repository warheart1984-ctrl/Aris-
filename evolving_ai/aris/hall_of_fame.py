from __future__ import annotations

from pathlib import Path

from .hall_base import GovernanceHall


class HallOfFame(GovernanceHall):
    """Verified successful governed outcomes."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root=root,
            hall_id="hall-of-fame",
            entry_prefix="fame",
            track_reentry=False,
        )

    def celebrate(self, **kwargs):
        return self.record(**kwargs)
