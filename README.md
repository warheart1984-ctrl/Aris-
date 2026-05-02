# ARIS — Adaptive Runtime Intelligence System

**Demo Version** | Part of [Project Infinity](https://github.com/warheart1984-ctrl/Project-Infinity) / AAIS

ARIS is the **governed desktop cockpit and runtime host** for the Adaptive Autonomous Intelligence System (AAIS).

It is the operator-visible surface where the formal runtime calculus defined in **The Voss Binding (Λ)** is made real: every action flows through a canonical semantic packet, passes the ForgeGate, executes under law, and is fully auditable.

### Core Principles

- **Law-first execution** — All actions are governed by the Voss Binding invariants before they reach any model or interpreter.
- **Model-agnostic** — The LLM is interchangeable compute. ARIS currently steps up to 12 different models without changing governance.
- **Operator supremacy** — The human operator holds final authority at all times (corrigibility is structural, not optional).
- **Lawful completion** — Nothing is considered "done" until it is verified, packaged, and proven to run post-packaging (see `LAWFUL_COMPLETION_OF_A_SYSTEM.md`).

### Key Components

- **`evolving_ai/`** — Core framework for small neural agents trained via evolutionary search (genome, mutation, novelty archive, tournament selection).
- **`ul_lang.py` + `ul_substrate.py`** — Dual-language foundation:
  - `ul_lang`: general-purpose governed computation
  - `ul_substrate`: AST-native governed action substrate with ForgeGate
- **`forge/` + `forge_eval/`** — Runtime execution and evaluation services
- **`aris_runtime/`** — Desktop host (PySide6) and sealed runtime
- **Bridge Intelligence** — Canonical `SemanticEvent` packet layer that unifies UI, runtime, and audit

### Architecture
Operator (you)
   ↓
ARIS Cockpit (Task Stream + Eval Gate + Intelligence Blocks)
   ↓
Canonical SemanticEvent Packet
   ↓
ForgeGate + Voss Binding Λ (law enforcement)
   ↓
UL Substrate + UL Lang runtime
   ↓
Interchangeable LLM(s) or evolutionary agents


### Documentation

- `LOGBOOK.md` — What changed and why
- `LAWFUL_COMPLETION_OF_A_SYSTEM.md` — Completion criteria
- `BUILD.md` — How to build the desktop artifact
- `Voss Binding (Λ)` — The governing runtime calculus (in Project Infinity)

### Status

This is the **Demo Version** of ARIS.  
It is actively being wired to the full AAIS governance spine. The goal is a clean, law-first, operator-controlled cockpit that feels like Codex but obeys unbreakable runtime law.

---

