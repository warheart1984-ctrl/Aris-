# SCARS

ARIS did not stay stable by accident. It stayed stable because the repo carries the scars of the failures we expected, tested, and closed before ship.

## What This File Means

This is not a marketing summary.

This is the operator-facing record of the structural problems ARIS was exposed to, the enforcement we added, and why those seams did not become live failures in the shipped runtime lane.

## Why We Did Not Have ARIS Runtime Drift

### 1. Truth Was Centralized

We removed split-truth UI behavior and forced the live shell onto canonical governed truth.

Why that mattered:
- fast local payloads could flicker, snap, or briefly lie
- stale activity could look current
- health and status could diverge

What stopped that:
- canonical truth endpoint
- hydration sync state instead of fake early confidence
- historical activity marked and excluded from current-state derivation

Result:
- ARIS does not guess silently about present state

### 2. Observation Was Separated From Execution

Passive workspace inspection originally risked looking like active governed execution.

Why that mattered:
- refresh paths could trigger review unexpectedly
- harmless observation could accumulate blocked actions
- kill state could be polluted by non-execution behavior

What stopped that:
- bounded passive inspection paths
- no implicit review without real change or review context
- direct rule that observation must not escalate into execution

Result:
- refresh and inspect flows stay informational unless intent changes

### 3. Governance Was Put On The Causal Path

ARIS does not rely on governance text alone.

Why that mattered:
- a system can look governed while still letting risky seams bypass the spine

What stopped that:
- 1001-first startup enforcement
- immutable law classification
- Forge Eval binding on risky paths
- hall routing for failure classes
- kill switch and lockdown enforcement

Result:
- the protected path decides what is real, not surface confidence

### 4. Repo-Changing Success Was Made Harder Than “Code Written”

We explicitly rejected the idea that a repo change is successful just because files changed.

Why that mattered:
- undocumented changes drift
- unverified changes masquerade as progress

What stopped that:
- finalize-time requirement for:
  - verification artifacts
  - matching logbook entry
  - 1001 pass
- otherwise route to Hall of Discard instead of Hall of Fame

Result:
- ARIS only recognizes repo-changing success when code, evidence, and documentation agree

### 5. Demo Paths Were Quarantined Instead Of Left To Rot

We did not pretend demos were runtime.

Why that mattered:
- demo logic quietly contaminates real product assumptions
- multiple entrypoints produce identity drift

What stopped that:
- single live runtime lane under `evolving_ai/aris_runtime`
- demo lineage archived under `archive/demo`
- one supported Windows build path

Result:
- ARIS ships as one runtime, not a pile of competing prototypes

### 6. Generated State Was Removed From Source Authority

Tracked runtime residue and machine-local state were pulled out of the GitHub source surface.

Why that mattered:
- workstation residue looks like product truth
- generated state obscures actual reviewable source

What stopped that:
- publish cleanup
- ignore rules for runtime/build/editor residue
- archival moves for unrelated vendor payloads

Result:
- the repo now presents code and doctrine, not machine exhaust

## The Main Scars

These are the seam classes ARIS carries forward as lessons:
- split-truth hydration
- stale activity influence
- implicit review triggers
- passive inspection escalation
- fake-success startup
- governance surfaces that existed but were not yet causal
- demo identity drift
- repo-change success without evidence
- local runtime residue treated like source

## Why ARIS Did Not Fail In Ship Form

ARIS stayed stable because we forced these rules:
- truth before speed
- one runtime lane
- law before action
- verification before success
- archive instead of amnesia
- fail closed when integrity is uncertain

## What This Means For Future Changes

If a future change:
- adds a second truth source
- hides execution behind inspection
- restores demo shortcuts
- weakens finalize-time evidence
- bypasses the runtime law spine

then it is not an upgrade.

It is a regression against known scars.

## Final Note

ARIS is not “issue free” because nothing went wrong.

ARIS is stable because the repo remembers what went wrong, encoded the lesson, and refused to let those seams define runtime truth again.
