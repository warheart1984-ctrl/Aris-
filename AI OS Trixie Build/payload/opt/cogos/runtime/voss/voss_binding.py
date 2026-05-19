"""
Project Infi / ARIS Runtime
The Voss Binding (Λ) — Cycle Boundary Operator
Formal Specification v1.0 — Jon Halstead

Position: Post-Δ, Pre-next_1000
Domain:   MetaDomain
Symbol:   Λ

Cycle placement (binary):
    0001 → 1000 → 1001 → 1010 → 1111 → 1001 → 0001′ → Δ → Λ → next_1000

Invariants:
    - Λ executes unconditionally after Δ, regardless of admit/wait path.
    - Every binding incurs non-zero coupling cost.
    - Bound state is non-reversible within cycle scope.
    - All future cycles reflect prior coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Disposition ───────────────────────────────────────────────────────────────

class BindingDisposition(Enum):
    BOUND    = "BOUND"
    PARTIAL  = "PARTIAL"
    REJECTED = "REJECTED"


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class FateLine:
    """
    The trajectory of a single participant entering the binding.

    Fields
    ------
    state   : Current state identifier.
    bound   : Whether this line is already bound. Default: False.
    context : Contextual payload. Default: {}.
    valid   : Structural validity flag. Default: True.
    """
    state:   str
    bound:   bool                       = False
    context: Optional[Dict[str, Any]]   = field(default_factory=dict)
    valid:   bool                       = True

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = {}


@dataclass
class MergedFateLine:
    """
    Output trajectory produced by a successful binding.

    Fields
    ------
    state               : Merged state identifier.
    bound               : Always True after binding.
    protagonist_origin  : Origin state of the protagonist fate line.
    influence_origin    : Origin state of the external influence.
    coupling_cost       : Cost incurred by this binding.
    context             : Merged contextual payload.
    """
    state:              str
    bound:              bool             = True
    protagonist_origin: str              = ""
    influence_origin:   str              = ""
    coupling_cost:      int              = 0
    context:            Dict[str, Any]   = field(default_factory=dict)


@dataclass
class BindingResult:
    """
    Full result record returned by voss_binding().

    Fields
    ------
    disposition     : BOUND | PARTIAL | REJECTED.
    merged          : The output trajectory. None if REJECTED.
    coupling_added  : Coupling cost applied in this binding.
    bound_flag      : Resulting bound state.
    notes           : Operational notes generated during execution.
    """
    disposition:    BindingDisposition
    merged:         Optional[MergedFateLine]
    coupling_added: int
    bound_flag:     bool
    notes:          List[str] = field(default_factory=list)


@dataclass
class DebtRecord:
    """
    Accumulated debt record for the current cycle context.

    Fields
    ------
    total    : Total accumulated debt.
    coupling : Coupling-specific debt (added by Λ).
    base     : Base debt from other operators (e.g. 1111).
    """
    total:    float = 0.0
    coupling: float = 0.0
    base:     float = 0.0


@dataclass
class CycleContext:
    """
    Runtime context passed through the ARIS cycle.

    Fields
    ------
    current_state   : Current state identifier.
    prime_depth     : Depth of prime stabilization.
    debt            : Accumulated debt record.
    risk_profile    : Current risk profile level.
    stability_score : Current stability score.
    bound_flag      : Whether the system is currently bound.
    scar            : Accumulated scar value.
    event_log       : Chronological event log (append-only).
    """
    current_state:   str         = "0001"
    prime_depth:     int         = 0
    debt:            DebtRecord  = field(default_factory=DebtRecord)
    risk_profile:    int         = 0
    stability_score: float       = 1.0
    bound_flag:      bool        = False
    scar:            float       = 0.0
    event_log:       List[Dict[str, Any]] = field(default_factory=list)

    def log(self, event_name: str, metadata: Dict[str, Any]) -> None:
        """Append a structured entry to the event log."""
        self.event_log.append({"event": event_name, **metadata})


# ── Constants ─────────────────────────────────────────────────────────────────

COUPLING_COST_NORMAL: int = 5   # Base coupling cost (clean BOUND path)
COUPLING_COST_DOUBLE: int = 10  # Double penalty (PARTIAL path)


# ── Operator ──────────────────────────────────────────────────────────────────

def voss_binding(
    ctx:                CycleContext,
    protagonist_fate:   FateLine,
    external_influence: FateLine,
) -> BindingResult:
    """
    Λ — The Voss Binding.

    Executes unconditionally after Δ (stabilization) and before next_1000.
    Merges the stabilized protagonist trajectory with external influence,
    applying coupling cost and marking the system as permanently bound.

    Parameters
    ----------
    ctx                 : Active CycleContext. Mutated in place.
    protagonist_fate    : Stabilized system trajectory (from 0001′).
    external_influence  : External operator, input, or environmental factor.

    Returns
    -------
    BindingResult with disposition BOUND | PARTIAL | REJECTED.

    Side effects (on ctx)
    ---------------------
    - BOUND / PARTIAL : debt.coupling += cost, debt.total += cost,
                        bound_flag = True, event logged.
    - REJECTED        : risk_profile += 1, event logged.
                        No merge. bound_flag unchanged.
    """
    notes: List[str] = []

    # ── REJECTED: invalid fate line ───────────────────────────────────────────
    if not protagonist_fate.valid or not external_influence.valid:
        ctx.risk_profile += 1
        notes.append("REJECTED — invalid fate line detected; no merge performed.")
        ctx.log("voss_binding", {
            "disposition":   BindingDisposition.REJECTED.value,
            "coupling_added": 0,
            "bound_flag":    ctx.bound_flag,
            "notes":         notes,
        })
        return BindingResult(
            disposition=BindingDisposition.REJECTED,
            merged=None,
            coupling_added=0,
            bound_flag=ctx.bound_flag,
            notes=notes,
        )

    # ── REJECTED: missing context on both lines ───────────────────────────────
    if not protagonist_fate.context and not external_influence.context:
        ctx.risk_profile += 1
        notes.append("REJECTED — missing context on both fate lines.")
        ctx.log("voss_binding", {
            "disposition":   BindingDisposition.REJECTED.value,
            "coupling_added": 0,
            "bound_flag":    ctx.bound_flag,
            "notes":         notes,
        })
        return BindingResult(
            disposition=BindingDisposition.REJECTED,
            merged=None,
            coupling_added=0,
            bound_flag=ctx.bound_flag,
            notes=notes,
        )

    # ── Determine disposition and coupling cost ───────────────────────────────
    already_bound = protagonist_fate.bound or external_influence.bound
    coupling_cost = COUPLING_COST_DOUBLE if already_bound else COUPLING_COST_NORMAL

    if already_bound:
        disposition = BindingDisposition.PARTIAL
        notes.append(f"PARTIAL — double coupling penalty applied ({coupling_cost}).")
    else:
        disposition = BindingDisposition.BOUND
        notes.append(f"BOUND — clean binding; coupling cost {coupling_cost}.")

    # ── Merge ─────────────────────────────────────────────────────────────────
    merged_context: Dict[str, Any] = {
        **protagonist_fate.context,
        **external_influence.context,
    }
    merged = MergedFateLine(
        state=protagonist_fate.state,
        bound=True,
        protagonist_origin=protagonist_fate.state,
        influence_origin=external_influence.state,
        coupling_cost=coupling_cost,
        context=merged_context,
    )

    # ── Side effects ──────────────────────────────────────────────────────────
    ctx.debt.coupling += coupling_cost
    ctx.debt.total    += coupling_cost
    ctx.bound_flag     = True

    ctx.log("voss_binding", {
        "disposition":        disposition.value,
        "coupling_added":     coupling_cost,
        "bound_flag":         ctx.bound_flag,
        "merged_state":       merged.state,
        "protagonist_origin": merged.protagonist_origin,
        "influence_origin":   merged.influence_origin,
        "notes":              notes,
    })

    return BindingResult(
        disposition=disposition,
        merged=merged,
        coupling_added=coupling_cost,
        bound_flag=True,
        notes=notes,
    )


# ── Extended computation ──────────────────────────────────────────────────────

def compute_next_1000_context(ctx: CycleContext) -> Dict[str, Any]:
    """
    Derive the seed context for next_1000 after Λ has executed.

    Formula (spec §12):
        next_1000 = f(S1, accumulated_debt, scar, risk_profile, bound_flag)
    """
    return {
        "state":           ctx.current_state,
        "accumulated_debt": ctx.debt.total,
        "scar":            ctx.scar,
        "risk_profile":    ctx.risk_profile,
        "bound_flag":      ctx.bound_flag,
    }


# ── System guarantee assertions ───────────────────────────────────────────────

def assert_system_guarantees(result: BindingResult, ctx: CycleContext) -> None:
    """
    Assert the four system guarantees defined in spec §13.

    Only called on non-REJECTED results. Raises AssertionError on violation.

    Guarantee 1 — No cycle proceeds without a merged fate line.
    Guarantee 2 — No binding is cost-free.
    Guarantee 3 — bound_flag is True after any successful binding.
    Guarantee 4 — Coupling debt is non-zero after any successful binding.
    """
    if result.disposition != BindingDisposition.REJECTED:
        assert result.merged is not None,  "Guarantee 1 violated: merged is None on non-REJECTED result."
        assert result.coupling_added > 0,  "Guarantee 2 violated: coupling_added is zero."
        assert ctx.bound_flag is True,     "Guarantee 3 violated: bound_flag not set."
        assert ctx.debt.coupling > 0,      "Guarantee 4 violated: ctx.debt.coupling is zero."
