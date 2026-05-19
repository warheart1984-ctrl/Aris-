"""
adapter_cycle_context.py — DriftScores (GRE) → CycleContext (Λ Voss Binding)
"""

from __future__ import annotations

from typing import Dict

import sys
from pathlib import Path

from governance_invariant_engine import DriftScores

_voss_parent = Path(__file__).resolve().parent
if str(_voss_parent) not in sys.path:
    sys.path.insert(0, str(_voss_parent))

try:
    from voss.voss_binding import CycleContext
except ImportError:
    from voss_binding import CycleContext  # type: ignore


def drift_to_risk_profile(drift: DriftScores) -> Dict[str, float]:
    drift.validate()
    return {
        "behavioral": drift.behavioral,
        "schema": drift.schema,
        "identity": drift.identity,
        "temporal": drift.temporal,
        "composite": drift.composite(),
    }


def drift_to_stability_score(drift: DriftScores) -> float:
    drift.validate()
    return max(0.0, min(1.0, 1.0 - drift.composite()))


def apply_drift_to_cycle(ctx: CycleContext, drift: DriftScores) -> CycleContext:
    """Mutate cycle context from GRE drift measurement."""
    composite = drift.composite()
    profile = drift_to_risk_profile(drift)
    ctx.stability_score = drift_to_stability_score(drift)
    ctx.risk_profile = int(min(10, round(composite * 10)))
    ctx.debt.coupling = round(ctx.debt.coupling + composite * 0.5, 4)
    ctx.debt.total = round(ctx.debt.total + composite * 0.5, 4)
    ctx.scar = round(ctx.scar + composite * 0.1, 4)
    ctx.log("gre_drift_applied", {"risk_profile": profile, "stability": ctx.stability_score})
    return ctx


def seed_cycle_from_drift(drift: DriftScores, *, state: str = "1001") -> CycleContext:
    ctx = CycleContext(current_state=state)
    return apply_drift_to_cycle(ctx, drift)
