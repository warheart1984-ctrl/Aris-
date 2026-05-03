from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_governance_bundle() -> dict[str, Any]:
    """Load bundled Voss Binding governance metadata."""

    payload = resources.files("evolving_ai.voss_binding").joinpath("governance.json").read_text(
        encoding="utf-8"
    )
    return json.loads(payload)
