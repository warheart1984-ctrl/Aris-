"""Shared evaluator helpers."""

from __future__ import annotations


class InvalidEvaluationRequest(ValueError):
    """Raised when one evaluation request is missing required payload fields."""
