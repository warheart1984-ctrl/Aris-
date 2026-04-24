"""Scoring helpers for ForgeEval."""

from __future__ import annotations


def clamp_score(value: object) -> float:
    """Clamp any score into the canonical 0..1 range."""

    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def average(values: list[float]) -> float:
    """Return the bounded mean of a score list."""

    if not values:
        return 0.0
    return clamp_score(sum(values) / len(values))
