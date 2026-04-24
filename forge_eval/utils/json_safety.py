"""Small JSON safety helpers for ForgeEval."""

from __future__ import annotations

from typing import Any


def ensure_dict(value: Any) -> dict[str, Any]:
    """Return a shallow dict for evaluator details."""

    return dict(value or {}) if isinstance(value, dict) else {}
