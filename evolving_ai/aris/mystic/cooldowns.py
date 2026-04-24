from __future__ import annotations


class MysticCooldowns:
    TIER_1_MINUTES = 40
    TIER_2_MINUTES = 25
    TIER_3_MINUTES = 15

    @classmethod
    def for_level(cls, level: int) -> int:
        if level >= 3:
            return cls.TIER_3_MINUTES
        if level == 2:
            return cls.TIER_2_MINUTES
        return cls.TIER_1_MINUTES
