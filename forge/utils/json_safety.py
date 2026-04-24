"""JSON extraction helpers for Forge model responses."""

from __future__ import annotations

import json
from typing import Any


def extract_json_object(raw: Any) -> Any:
    """Parse raw model output, including fenced JSON blocks when present."""

    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if "```json" in lowered:
        start = lowered.find("```json")
        fenced = text[start + 7 :]
        end = fenced.find("```")
        if end >= 0:
            text = fenced[:end].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
