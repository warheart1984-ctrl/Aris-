from __future__ import annotations

from dataclasses import dataclass, field
from time import time


@dataclass
class MysticState:
    session_start_ts: float = field(default_factory=time)
    last_break_ts: float = field(default_factory=time)
    last_voice_ts: float = 0.0
    last_ack_ts: float = 0.0
    last_activity_ts: float = field(default_factory=time)
    alert_level: int = 0
    consecutive_errors: int = 0
    repeated_loop_count: int = 0
    last_category: str | None = None
    last_message: str = ""
    voice_enabled: bool = True
    muted_until_ts: float = 0.0

    def session_minutes(self, now: float | None = None) -> float:
        current = now or time()
        return (current - self.session_start_ts) / 60.0

    def minutes_since_break(self, now: float | None = None) -> float:
        current = now or time()
        return (current - self.last_break_ts) / 60.0

    def minutes_since_voice(self, now: float | None = None) -> float:
        current = now or time()
        if self.last_voice_ts <= 0:
            return float("inf")
        return (current - self.last_voice_ts) / 60.0

    def is_muted(self, now: float | None = None) -> bool:
        current = now or time()
        return current < self.muted_until_ts

    def record_activity(self, now: float | None = None) -> None:
        self.last_activity_ts = now or time()

    def record_break(self, now: float | None = None) -> None:
        current = now or time()
        self.last_break_ts = current
        self.last_activity_ts = current
        self.alert_level = 0
        self.consecutive_errors = 0
        self.repeated_loop_count = 0

    def record_voice(self, category: str, level: int, message: str, now: float | None = None) -> None:
        current = now or time()
        self.last_voice_ts = current
        self.last_category = category
        self.last_message = message
        self.alert_level = level

    def acknowledge(self, now: float | None = None) -> None:
        self.last_ack_ts = now or time()

    def mute_for_minutes(self, minutes: float, now: float | None = None) -> None:
        current = now or time()
        self.muted_until_ts = current + (minutes * 60.0)
