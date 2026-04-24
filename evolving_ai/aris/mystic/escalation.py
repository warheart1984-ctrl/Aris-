from __future__ import annotations

from dataclasses import dataclass

from .cooldowns import MysticCooldowns
from .session_monitor import MysticState


@dataclass(frozen=True)
class MysticDecision:
    should_speak: bool
    level: int = 0
    category: str = ""
    reason: str = ""
    cooldown_minutes: int = 0


class MysticEscalationPolicy:
    @classmethod
    def evaluate(cls, state: MysticState, now: float) -> MysticDecision:
        if not state.voice_enabled:
            return MysticDecision(False, reason="voice_disabled")
        if state.is_muted(now):
            return MysticDecision(False, reason="muted")
        session_minutes = state.session_minutes(now)
        break_minutes = state.minutes_since_break(now)
        voice_minutes = state.minutes_since_voice(now)
        if (
            session_minutes >= 240
            or break_minutes >= 180
            or state.consecutive_errors >= 8
            or state.repeated_loop_count >= 6
        ):
            cooldown = MysticCooldowns.for_level(3)
            if voice_minutes >= cooldown:
                category = "loop_reset" if state.repeated_loop_count >= 6 else "rest"
                return MysticDecision(True, 3, category, "critical_threshold", cooldown)
        if (
            session_minutes >= 120
            or break_minutes >= 90
            or state.consecutive_errors >= 4
            or state.repeated_loop_count >= 3
        ):
            cooldown = MysticCooldowns.for_level(2)
            if voice_minutes >= cooldown:
                category = "loop_reset" if state.repeated_loop_count >= 3 else "hydration"
                return MysticDecision(True, 2, category, "moderate_threshold", cooldown)
        if session_minutes >= 75 or break_minutes >= 60:
            cooldown = MysticCooldowns.for_level(1)
            if voice_minutes >= cooldown:
                return MysticDecision(True, 1, "hydration", "soft_threshold", cooldown)
        return MysticDecision(False, reason="no_threshold")
