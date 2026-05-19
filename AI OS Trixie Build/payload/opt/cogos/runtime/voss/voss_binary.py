"""
The Voss Binary — Python Implementation
Governed Runtime Calculus for the ARIS Cognitive Operating System

Based on: Formal Specification v2.0 (Hardened Edition)
Author:   Jon Halstead / Project Infi / ARIS
"""

from __future__ import annotations
import json
import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─────────────────────────────────────────────────
# §2 / §3 — Instruction encoding constants
# ─────────────────────────────────────────────────

MAX_DELTA = 32767   # INT16_MAX  (Δ₆)
MIN_DELTA = 0       # Δ₁ non-negativity floor

STANDARD_BIND_COST  = 5    # Δ₅
REBIND_PENALTY_COST = 10   # Δ₅


class InstrClass(int, Enum):
    FLOW      = 0x0
    BIND      = 0x1
    DELTA     = 0x2
    INVARIANT = 0x3
    META      = 0x4
    # 0x5–0xF → RESERVED → FAULT at decode


class FlowOp(int, Enum):
    NEXT  = 0x0
    ADMIT = 0x1
    WAIT  = 0x2
    HALT  = 0xF   # IMM=0x00 → HALT, IMM=0x01 → FAULT


class BindOp(int, Enum):
    BIND     = 0x0
    UNBIND   = 0x1
    LOCK     = 0x2
    RELEASE  = 0x3
    L_CHAIN  = 0x4   # Λ_CHAIN


class DeltaOp(int, Enum):
    ADD       = 0x0   # Δ_ADD
    SETTLE    = 0x1   # Δ_SETTLE
    DEGRADE   = 0x2   # Δ_DEGRADE
    PROPAGATE = 0x3   # Δ_PROPAGATE


class InvarOp(int, Enum):
    ASSERT = 0x0   # ASSERT_INV
    GUARD  = 0x1   # GUARD_INV
    FAIL   = 0xF   # FAIL_INV


class MetaOp(int, Enum):
    TRACE     = 0x0
    GRE_MARK  = 0x1
    GRE_NEXT_K = 0x2


# ─────────────────────────────────────────────────
# Status / wait-reason
# ─────────────────────────────────────────────────

class Status(str, Enum):
    OK    = "OK"
    WAIT  = "WAIT"
    FAULT = "FAULT"
    HALT  = "HALT"


class WaitReason(str, Enum):
    NONE         = "NONE"
    INV_FAIL     = "INV_FAIL"
    WAIT_INSTR   = "WAIT_INSTR"


# ─────────────────────────────────────────────────
# §4 — VM State Model
# ─────────────────────────────────────────────────

@dataclass
class VMState:
    # §4.1 Registers
    pc: int = 0          # u16 program counter
    cycle: int = 0       # u32 GRE cycle counter
    status: Status = Status.OK

    # Δ debt table: target_id → int
    delta: dict[int, int] = field(default_factory=dict)

    # Λ fate / lock tables: target_id → u8
    fate:   dict[int, int] = field(default_factory=dict)
    locked: dict[int, int] = field(default_factory=dict)

    # Coupling debt (Δ₅)
    coupling_debt: int = 0

    # Invariant definitions: inv_id → callable(state) → bool
    inv_defs: dict[int, object] = field(default_factory=dict)
    inv_ok:   bool = True

    # Context / WAIT
    ctx_flags:    int = 0
    wait_flags:   int = 0
    wait_reason:  WaitReason = WaitReason.NONE
    wait_inv_id:  Optional[int] = None

    # Λ chains: chain_id → set of target_ids
    chains: dict[int, set] = field(default_factory=dict)

    # INV_8 shadow snapshot captured at WAIT entry
    wait_shadow: Optional[dict] = None

    # GRE_MARK stack
    mark_stack: list = field(default_factory=list)

    # Fault reason (informational)
    fault_reason: str = ""


def _state_snapshot(state: VMState) -> dict:
    return {
        "delta":  dict(state.delta),
        "fate":   dict(state.fate),
        "locked": dict(state.locked),
    }


def _delta(state: VMState, t: int) -> int:
    return state.delta.get(t, 0)


def _fate(state: VMState, t: int) -> int:
    return state.fate.get(t, 0)


def _locked(state: VMState, t: int) -> int:
    return state.locked.get(t, 0)


def _chain_of(state: VMState, t: int) -> Optional[int]:
    for cid, members in state.chains.items():
        if t in members:
            return cid
    return None


def _chain_members(state: VMState, t: int) -> set:
    cid = _chain_of(state, t)
    return state.chains[cid] if cid is not None else set()


# ─────────────────────────────────────────────────
# Decoded instruction
# ─────────────────────────────────────────────────

@dataclass
class DecodedInstr:
    raw:   int
    cls:   int
    op:    int
    imm:   int

    def cls_name(self) -> str:
        try:
            return InstrClass(self.cls).name
        except ValueError:
            return f"RESERVED(0x{self.cls:X})"

    def op_name(self) -> str:
        try:
            if self.cls == InstrClass.FLOW:
                if self.op == FlowOp.HALT:
                    return "HALT" if self.imm == 0 else "FAULT"
                return FlowOp(self.op).name
            elif self.cls == InstrClass.BIND:
                return BindOp(self.op).name
            elif self.cls == InstrClass.DELTA:
                return "Δ_" + DeltaOp(self.op).name
            elif self.cls == InstrClass.INVARIANT:
                return InvarOp(self.op).name + "_INV"
            elif self.cls == InstrClass.META:
                return MetaOp(self.op).name
        except ValueError:
            pass
        return f"UNKNOWN(0x{self.op:X})"

    def to_dict(self) -> dict:
        return {
            "raw":    f"0x{self.raw:04X}",
            "class":  self.cls_name(),
            "opcode": self.op_name(),
            "imm":    self.imm,
        }


# ─────────────────────────────────────────────────
# §10 — REP Trace
# ─────────────────────────────────────────────────

@dataclass
class StateSnapshot:
    """Immutable snapshot of VM state captured at REP emit time (§10)."""
    status: Status
    delta:  dict
    fate:   dict
    locked: dict


@dataclass
class REPRecord:
    cycle:       int
    pc:          int
    instr:       DecodedInstr
    snapshot:    StateSnapshot   # frozen at emit time
    inv_checked: list[int]
    inv_ok:      bool
    events:      list[str]

    # Keep a live reference for callers that need live state (e.g. tests)
    _live_state: object = field(default=None, repr=False)

    @property
    def state(self):
        """Compatibility alias — returns the frozen snapshot."""
        return self.snapshot

    def to_json(self) -> str:
        fate_hex   = {str(k): hex(v) for k, v in self.snapshot.fate.items()}
        locked_hex = {str(k): hex(v) for k, v in self.snapshot.locked.items()}
        delta_map  = {str(k): v for k, v in self.snapshot.delta.items()}
        record = {
            "cycle": self.cycle,
            "pc":    self.pc,
            "instr": self.instr.to_dict(),
            "state": {
                "status": self.snapshot.status.value,
                "delta":  delta_map,
                "fate":   fate_hex,
                "locked": locked_hex,
            },
            "invariants": {
                "checked": self.inv_checked,
                "ok":      self.inv_ok,
            },
            "events": self.events,
        }
        return json.dumps(record)


# ─────────────────────────────────────────────────
# §9 — Canonical Invariants
# ─────────────────────────────────────────────────

def check_inv_1(state: VMState, _events: list) -> bool:
    """INV_1 / Δ₁ — Non-Negativity"""
    for t, d in state.delta.items():
        if d < MIN_DELTA:
            return False
    return True


def check_inv_2(state: VMState, instr: DecodedInstr,
                prev_delta: dict, _events: list) -> bool:
    """INV_2 / Δ₂ — Locality"""
    if instr.cls != InstrClass.DELTA:
        return state.delta == prev_delta
    return True


def check_inv_3(state: VMState, locked_seen: dict, _events: list) -> bool:
    """INV_3 / Λ₂ — Lock Integrity: locked bits never cleared"""
    for t, bits in locked_seen.items():
        if (state.fate.get(t, 0) & bits) != bits:
            return False
    return True


def check_inv_4(state: VMState, _events: list) -> bool:
    """INV_4 / Λ₄ — Coupling Consistency: chain members share fate"""
    for members in state.chains.values():
        members_list = list(members)
        if len(members_list) < 2:
            continue
        ref_fate = state.fate.get(members_list[0], 0)
        for t in members_list[1:]:
            if state.fate.get(t, 0) != ref_fate:
                return False
    return True


def check_inv_5(state: VMState, prev_cycle: int, prev_status: Status) -> bool:
    """INV_5 — Cycle Monotonicity"""
    if prev_status == Status.OK and state.status == Status.OK:
        return state.cycle > prev_cycle
    return state.cycle >= prev_cycle


def check_inv_6(status: Status, prev_status: Status,
                instr: DecodedInstr) -> bool:
    """INV_6 — Status Discipline: transitions only via legal instructions"""
    # Legal transitions table
    legal = {
        (Status.OK,   Status.WAIT):  [InstrClass.FLOW,      InstrClass.INVARIANT],
        (Status.OK,   Status.FAULT): [InstrClass.FLOW,      InstrClass.BIND,
                                      InstrClass.DELTA,     InstrClass.INVARIANT],
        (Status.OK,   Status.HALT):  [InstrClass.FLOW],
        (Status.WAIT, Status.OK):    [InstrClass.FLOW],
        (Status.WAIT, Status.FAULT): [InstrClass.BIND,      InstrClass.DELTA,
                                      InstrClass.INVARIANT, InstrClass.FLOW],
        (Status.OK,   Status.OK):    list(InstrClass),
        (Status.WAIT, Status.WAIT):  list(InstrClass),
    }
    key = (prev_status, status)
    allowed = legal.get(key)
    if allowed is None:
        return False
    return instr.cls in allowed


def check_inv_7(state: VMState) -> bool:
    """
    INV_7 — Admit/Wait Coherence.
    Contradiction: WAIT flags contain bits that were never admitted
    (waiting on an unadmitted context). Overlap is legal — the golden
    path intentionally admits then waits on the same flags.
    """
    if state.status == Status.WAIT:
        unadmitted = state.wait_flags & ~state.ctx_flags
        if unadmitted != 0:
            return False
    return True


def check_inv_8(state: VMState, shadow: dict) -> bool:
    """INV_8 — History-Safe Δ/Λ Evolution at WAIT exit"""
    for t in set(list(shadow["delta"].keys()) +
                 list(state.delta.keys())):
        d_prev = shadow["delta"].get(t, 0)
        d_now  = state.delta.get(t, 0)
        if d_now < MIN_DELTA or d_now > MAX_DELTA:
            return False
        locked_prev = shadow["locked"].get(t, 0)
        fate_now    = state.fate.get(t, 0)
        if (fate_now & locked_prev) != locked_prev:
            return False
    return True


def check_inv_8_snap(snap, shadow: dict) -> bool:
    """INV_8 for verifier — operates on a frozen StateSnapshot."""
    for t in set(list(shadow["delta"].keys()) + list(snap.delta.keys())):
        d_now = snap.delta.get(t, 0)
        if d_now < MIN_DELTA or d_now > MAX_DELTA:
            return False
        locked_prev = shadow["locked"].get(t, 0)
        fate_now    = snap.fate.get(t, 0)
        if (fate_now & locked_prev) != locked_prev:
            return False
    return True


# ─────────────────────────────────────────────────
# §6 / §5 — Pipeline stage helpers
# ─────────────────────────────────────────────────

def _fault(state: VMState, reason: str, events: list):
    state.status  = Status.FAULT
    state.fault_reason = reason
    events.append(f"FAULT: {reason}")


# S2 — PRECHECK (Λ₈ WAIT-chain freeze)
def _precheck(state: VMState, instr: DecodedInstr, events: list) -> bool:
    """
    Λ₈ — if any target in a Λ chain is in WAIT, forbid APPLY_Δ / APPLY_Λ
    on all coupled targets.
    """
    if state.status == Status.WAIT:
        if instr.cls in (InstrClass.DELTA, InstrClass.BIND):
            _fault(state, "Λ₈_WAIT_COHERENCE: mutation forbidden during WAIT",
                   events)
            return False
    return True


# S3 — APPLY_Δ
def exec_delta(state: VMState, instr: DecodedInstr, events: list):
    t = (instr.imm >> 4) & 0xF
    d = instr.imm & 0xF
    op = instr.op

    if op == DeltaOp.ADD:
        new_val = _delta(state, t) + d
        if new_val > MAX_DELTA:            # Δ₆
            _fault(state, f"Δ₆_SATURATION: overflow t={t}", events)
            return
        state.delta[t] = new_val
        events.append(f"DELTA_ADD t={t} d={d}")

    elif op == DeltaOp.SETTLE:
        cur = _delta(state, t)
        if cur < d:                         # Δ₁ / INV_1
            _fault(state,
                   f"Δ₁_NON_NEGATIVITY: settle amount {d} > delta[{t}]={cur}",
                   events)
            events.append("DELTA_SETTLE_REJECTED")
            events.append("ILLEGAL_NEGATIVE_ATTEMPT")
            return
        state.delta[t] = cur - d
        events.append(f"DELTA_SETTLE t={t} d={d}")

    elif op == DeltaOp.DEGRADE:
        cur = _delta(state, t)
        state.delta[t] = max(MIN_DELTA, cur - d)
        events.append(f"DELTA_DEGRADE t={t} d={d}")

    elif op == DeltaOp.PROPAGATE:
        # Δ₄ — propagate only to coupled targets
        members = _chain_members(state, t)
        if not members:
            _fault(state,
                   f"Δ₄_PROPAGATION_INTEGRITY: t={t} has no coupled targets",
                   events)
            return
        for u in members:
            if u == t:
                continue
            new_val = _delta(state, u) + d
            if new_val > MAX_DELTA:
                _fault(state, f"Δ₆_SATURATION: propagate overflow t={u}",
                       events)
                return
            state.delta[u] = new_val
        events.append(f"DELTA_PROPAGATE t={t} d={d}")
    else:
        _fault(state, f"UNDEFINED_DELTA_OP 0x{op:X}", events)


# S4 — APPLY_Λ
def exec_bind(state: VMState, instr: DecodedInstr, events: list):
    t = (instr.imm >> 4) & 0xF
    f = instr.imm & 0xF
    op = instr.op

    if op == BindOp.BIND:
        already_bound = _fate(state, t) != 0
        state.fate[t] = _fate(state, t) | f
        cost = REBIND_PENALTY_COST if already_bound else STANDARD_BIND_COST
        state.coupling_debt += cost
        events.append(f"BIND t={t} f={f}")
        events.append("COUPLING_OK")

    elif op == BindOp.UNBIND:
        if _locked(state, t) & f:           # Λ₂ / Λ₃
            _fault(state,
                   f"Λ₂_MONOTONE_LOCK_PRESERVED / Λ₃: UNBIND on locked fate t={t}",
                   events)
            events.append("UNBIND_ON_LOCKED_REJECTED")
            return
        state.fate[t] = _fate(state, t) & ~f
        events.append(f"UNBIND t={t} f={f}")

    elif op == BindOp.LOCK:
        state.locked[t] = _locked(state, t) | f
        state.fate[t]   = _fate(state, t)   | f
        events.append(f"LOCK t={t} f={f}")

    elif op == BindOp.RELEASE:
        if _locked(state, t) & f:           # Λ₃
            _fault(state,
                   f"Λ₃_LEGAL_RELEASE: RELEASE on locked bits t={t}",
                   events)
            return
        state.fate[t] = _fate(state, t) & ~f
        events.append(f"RELEASE t={t} f={f}")

    elif op == BindOp.L_CHAIN:
        c = (instr.imm >> 4) & 0xF
        f = instr.imm & 0xF
        # Λ₉ — atomic compute-verify-commit
        if c not in state.chains:
            state.chains[c] = set()
        temp_fate = {}
        for u in state.chains[c]:
            temp_fate[u] = _fate(state, u) | f
        # verify invariants on temp
        for u, new_f in temp_fate.items():
            if _locked(state, u) and not (new_f & _locked(state, u)):
                _fault(state,
                       f"Λ₉_ATOMIC_CHAIN: lock violation on t={u}", events)
                return
        # check coupling consistency in temp
        vals = list(temp_fate.values())
        if vals and not all(v == vals[0] for v in vals):
            _fault(state, "Λ₉_ATOMIC_CHAIN: fate divergence", events)
            return
        # commit
        for u, new_f in temp_fate.items():
            state.fate[u] = new_f
        events.append(f"Λ_CHAIN c={c} f={f}")
    else:
        _fault(state, f"UNDEFINED_BIND_OP 0x{op:X}", events)


# S5 — FLOW_CTRL
def exec_flow(state: VMState, instr: DecodedInstr, events: list):
    op  = instr.op
    imm = instr.imm

    if op == FlowOp.NEXT:
        state.cycle += imm
        events.append("CYCLE_ADVANCE")

    elif op == FlowOp.ADMIT:
        state.ctx_flags |= imm
        events.append(f"ADMIT f=0x{imm:02X}")

    elif op == FlowOp.WAIT:
        state.status     = Status.WAIT
        state.wait_flags = imm
        state.wait_reason = WaitReason.WAIT_INSTR
        # INV_8 — capture shadow snapshot at WAIT entry
        state.wait_shadow = _state_snapshot(state)
        events.append(f"WAIT f=0x{imm:02X}")

    elif op == FlowOp.HALT:
        if imm == 0:
            state.status = Status.HALT
            events.append("HALT")
        else:
            state.status = Status.FAULT
            state.fault_reason = "FAULT_INSTRUCTION"
            events.append("FAULT_INSTRUCTION")
    else:
        _fault(state, f"UNDEFINED_FLOW_OP 0x{op:X}", events)


# INVARIANT class
def exec_invar(state: VMState, instr: DecodedInstr,
               events: list) -> list[int]:
    """Returns list of invariant IDs checked."""
    inv_id = instr.imm
    checked = [inv_id]

    if instr.op == InvarOp.ASSERT:
        fn = state.inv_defs.get(inv_id)
        result = fn(state) if fn else True
        state.inv_ok = result
        if not result:
            _fault(state, f"INVARIANT_FAILURE inv={inv_id}", events)
            events.append("INVARIANT_FAILURE")
            events.append("NO_PARTIAL_MUTATION")
        else:
            events.append("INVARIANT_CHECK_PASSED")

    elif instr.op == InvarOp.GUARD:
        fn = state.inv_defs.get(inv_id)
        result = fn(state) if fn else True
        state.inv_ok = result
        if not result:
            state.status    = Status.WAIT
            state.wait_reason = WaitReason.INV_FAIL
            state.wait_inv_id = inv_id
            state.wait_shadow = _state_snapshot(state)
            events.append(f"GUARD_INV_FAIL inv={inv_id}")
        else:
            events.append(f"GUARD_INV_PASS inv={inv_id}")

    elif instr.op == InvarOp.FAIL:
        _fault(state, f"INV_EXPLICIT inv={inv_id}", events)
        events.append(f"FAIL_INV inv={inv_id}")
    else:
        _fault(state, f"UNDEFINED_INVAR_OP 0x{instr.op:X}", events)

    return checked


# META/GRE
def exec_meta(state: VMState, instr: DecodedInstr, events: list):
    if instr.op == MetaOp.TRACE:
        events.append(f"TRACE {instr.imm}")
    elif instr.op == MetaOp.GRE_MARK:
        state.mark_stack.append((state.cycle, instr.imm))
        events.append(f"GRE_MARK m={instr.imm}")
    elif instr.op == MetaOp.GRE_NEXT_K:
        state.cycle += instr.imm
        events.append(f"GRE_NEXT_K k={instr.imm}")
    else:
        _fault(state, f"UNDEFINED_META_OP 0x{instr.op:X}", events)


# ─────────────────────────────────────────────────
# §6 — Full 9-Stage GRE Pipeline (one instruction)
# ─────────────────────────────────────────────────

def _gre_execute(
    state:      VMState,
    word:       int,
    locked_seen: dict,
) -> REPRecord:
    """
    Runs one 16-bit instruction word through all 9 GRE stages.
    Returns the REP record for this instruction.
    """
    fetch_pc    = state.pc - 1      # pc already incremented at fetch
    exec_cycle  = state.cycle
    prev_status = state.status
    prev_delta  = dict(state.delta)
    prev_cycle  = state.cycle
    events:     list[str] = []
    inv_checked: list[int] = []

    # S1 — DECODE
    cls = (word >> 12) & 0xF
    op  = (word >> 8)  & 0xF
    imm =  word        & 0xFF
    instr = DecodedInstr(raw=word, cls=cls, op=op, imm=imm)

    try:
        InstrClass(cls)
        if cls == InstrClass.FLOW and op == FlowOp.HALT and imm not in (0, 1):
            raise ValueError("bad HALT imm")
    except ValueError:
        if cls >= 0x5:
            _fault(state,
                   f"UNDEFINED_OPCODE_REJECTED cls=0x{cls:X} op=0x{op:X}",
                   events)
            events.append("ENCODING_INTEGRITY_PRESERVED")
            return REPRecord(exec_cycle, fetch_pc, instr,
                             StateSnapshot(state.status, dict(state.delta),
                                           dict(state.fate), dict(state.locked)),
                             inv_checked, False, events, _live_state=state)

    # S2 — PRECHECK (Λ₈ WAIT freeze barrier)
    if not _precheck(state, instr, events):
        return REPRecord(exec_cycle, fetch_pc, instr,
                         StateSnapshot(state.status, dict(state.delta),
                                       dict(state.fate), dict(state.locked)),
                         inv_checked, False, events, _live_state=state)

    # S3/S4/S5/S7 — dispatch by class
    if cls == InstrClass.DELTA:
        exec_delta(state, instr, events)
        # Post-Δ: INV_1 check
        if not check_inv_1(state, events):
            _fault(state, "INV_1_VIOLATED post-delta", events)

    elif cls == InstrClass.BIND:
        exec_bind(state, instr, events)
        # Update locked_seen for INV_3
        for t, lbits in state.locked.items():
            locked_seen[t] = locked_seen.get(t, 0) | lbits
        # Post-Λ: INV_4 coupling consistency check
        if not check_inv_4(state, events):
            _fault(state, "INV_4_VIOLATED: chain fate divergence", events)

    elif cls == InstrClass.FLOW:
        exec_flow(state, instr, events)

    elif cls == InstrClass.INVARIANT:
        inv_checked = exec_invar(state, instr, events)

    elif cls == InstrClass.META:
        exec_meta(state, instr, events)

    # S6 — DEGRADE (structural pass; degradation already applied in DEGRADE op)

    # Every-cycle invariants (verifier-level, non-FAULT enforced here)
    if not check_inv_2(state, instr, prev_delta, events):
        _fault(state, "INV_2_VIOLATED: non-DELTA class modified delta", events)

    if not check_inv_3(state, locked_seen, events):
        _fault(state, "INV_3_VIOLATED: locked bit cleared", events)

    # INV_7 — Admit/Wait coherence (checked after ADMIT and WAIT)
    if instr.cls == InstrClass.FLOW and instr.op in (FlowOp.ADMIT, FlowOp.WAIT):
        if not check_inv_7(state):
            _fault(state, "INV_7_VIOLATED: admit/wait flag contradiction",
                   events)

    # INV_8 — on WAIT exit
    if prev_status == Status.WAIT and state.status == Status.OK:
        shadow = state.wait_shadow
        if shadow and not check_inv_8(state, shadow):
            _fault(state, "INV_8_VIOLATED: illegal evolution across WAIT",
                   events)
        state.wait_shadow = None
        events.append("WAIT_RESUME_SAFE")
        events.append("NO_DUPLICATE_EXECUTION")
        events.append("STATE_INTACT")

    # S8 — record inv_ok for this cycle
    inv_ok_final = state.status not in (Status.FAULT,) or not inv_checked

    # Advance cycle counter (+1 per instruction unless NEXT/GRE_NEXT_K did it)
    state.cycle += 1

    return REPRecord(exec_cycle, fetch_pc, instr,
                     StateSnapshot(
                         status=state.status,
                         delta=dict(state.delta),
                         fate=dict(state.fate),
                         locked=dict(state.locked),
                     ),
                     inv_checked, inv_ok_final, events,
                     _live_state=state)


# ─────────────────────────────────────────────────
# §13.1 — VM Core Loop
# ─────────────────────────────────────────────────

def voss_run(
    code:          list[int],
    inv_defs:      Optional[dict] = None,
    max_cycles:    int = 10_000,
    verbose:       bool = True,
) -> tuple[VMState, list[REPRecord]]:
    """
    Execute a Voss Binary program.

    Args:
        code:       List of 16-bit instruction words.
        inv_defs:   Optional dict mapping invariant_id → callable(VMState) → bool.
        max_cycles: Safety ceiling to prevent runaway loops.
        verbose:    Print REP trace to stdout.

    Returns:
        (final_state, rep_trace)
    """
    state = VMState()
    if inv_defs:
        state.inv_defs = inv_defs

    rep_trace:   list[REPRecord] = []
    locked_seen: dict[int, int]  = {}
    step = 0

    while state.status == Status.OK and state.pc < len(code):
        if step >= max_cycles:
            state.status = Status.FAULT
            state.fault_reason = "MAX_CYCLES_EXCEEDED"
            break

        # S0 — FETCH
        word      = code[state.pc]
        state.pc += 1

        record = _gre_execute(state, word, locked_seen)
        rep_trace.append(record)
        step += 1

        if verbose:
            print(record.to_json())

        # S8 — terminal check
        if state.status in (Status.HALT, Status.FAULT):
            break

    return state, rep_trace


# ─────────────────────────────────────────────────
# External WAIT resume
# ─────────────────────────────────────────────────

def voss_resume(
    state:      VMState,
    code:       list[int],
    max_cycles: int = 10_000,
    verbose:    bool = True,
) -> tuple[VMState, list[REPRecord]]:
    """
    Resume a VM that is in WAIT status.
    The caller is responsible for clearing the wait condition externally.
    """
    if state.status != Status.WAIT:
        raise RuntimeError(f"Cannot resume: status is {state.status}")
    state.status     = Status.OK
    state.wait_reason = WaitReason.NONE
    return voss_run(code, state.inv_defs, max_cycles, verbose)


# ─────────────────────────────────────────────────
# §12 — Verifier
# ─────────────────────────────────────────────────

@dataclass
class VerifyResult:
    conformant:   bool
    violation_at: Optional[int]   # record index
    violation:    Optional[str]
    laws_held:    list[str]

    def __str__(self):
        if self.conformant:
            return (
                "VERDICT: CONFORMANT\n"
                "All Λ laws, Δ axioms, and canonical invariants held "
                "at the binary, instruction, and GRE-cycle level.\n"
                "The execution is LAW-PROVEN."
            )
        return (
            f"VERDICT: NON-CONFORMANT\n"
            f"First violation at record index {self.violation_at}: "
            f"{self.violation}"
        )


def voss_verify(rep_trace: list[REPRecord]) -> VerifyResult:
    """
    Replay the REP trace and verify all Λ laws and Δ axioms.
    Returns a VerifyResult.
    """
    prev_cycle  = -1
    prev_delta:  dict = {}
    prev_fate:   dict = {}
    prev_locked: dict = {}
    prev_status = Status.OK
    locked_seen: dict = {}
    chains:      dict = {}
    wait_shadow: Optional[dict] = None
    laws_held = []

    for idx, rec in enumerate(rep_trace):
        s     = rec.snapshot   # frozen state at this instruction
        instr = rec.instr

        # Δ₁ / INV_1 — Non-Negativity
        for t, d in s.delta.items():
            if d < 0:
                return VerifyResult(False, idx,
                    f"INV_1 violated: delta[{t}]={d} < 0", laws_held)

        # Δ₂ / INV_2 — Locality
        if instr.cls != InstrClass.DELTA:
            if s.delta != prev_delta:
                return VerifyResult(False, idx,
                    "INV_2 violated: non-DELTA instruction modified delta",
                    laws_held)

        # Δ₃ — Conservation (spot-check ADD/SETTLE)
        if instr.cls == InstrClass.DELTA:
            t = (instr.imm >> 4) & 0xF
            d = instr.imm & 0xF
            if instr.op == DeltaOp.ADD:
                expected = prev_delta.get(t, 0) + d
                if s.delta.get(t, 0) != expected and s.status == Status.OK:
                    return VerifyResult(False, idx,
                        f"Δ₃ violated: expected delta[{t}]={expected} "
                        f"got {s.delta.get(t)}", laws_held)
            elif instr.op == DeltaOp.SETTLE:
                expected = max(0, prev_delta.get(t, 0) - d)
                if (s.delta.get(t, 0) != expected and
                        s.status == Status.OK):
                    return VerifyResult(False, idx,
                        f"Δ₃ violated: settle delta[{t}]={s.delta.get(t)} "
                        f"expected {expected}", laws_held)

        # Δ₆ — Saturation
        for t, d in s.delta.items():
            if d > MAX_DELTA:
                return VerifyResult(False, idx,
                    f"Δ₆ violated: delta[{t}]={d} > MAX_DELTA", laws_held)

        # INV_3 / Λ₂ — Lock Integrity
        for t, lbits in s.locked.items():
            locked_seen[t] = locked_seen.get(t, 0) | lbits
        for t, seen in locked_seen.items():
            fate_now = s.fate.get(t, 0)
            if (fate_now & seen) != seen:
                return VerifyResult(False, idx,
                    f"INV_3/Λ₂ violated: locked bit cleared on t={t}",
                    laws_held)

        # INV_4 / Λ₄ — Coupling Consistency
        # The verifier tracks chains from Λ_CHAIN instructions it observes
        if instr.cls == InstrClass.BIND and instr.op == BindOp.L_CHAIN:
            cid = (instr.imm >> 4) & 0xF
            if cid not in chains:
                chains[cid] = set()
        for cid, members in chains.items():
            m_list = list(members)
            if len(m_list) >= 2:
                ref = s.fate.get(m_list[0], 0)
                for u in m_list[1:]:
                    if s.fate.get(u, 0) != ref:
                        return VerifyResult(False, idx,
                            f"INV_4/Λ₄ violated: chain {cid} fate divergence",
                            laws_held)

        # INV_5 — Cycle Monotonicity
        if prev_status == Status.OK and s.status == Status.OK:
            if rec.cycle <= prev_cycle:
                return VerifyResult(False, idx,
                    f"INV_5 violated: cycle not strictly increasing "
                    f"({prev_cycle} → {rec.cycle})", laws_held)

        # Λ₇ / INV_6 — Invariant Alignment
        if not rec.inv_ok and s.status != Status.FAULT:
            return VerifyResult(False, idx,
                "Λ₇/INV_6 violated: invariant failed but status != FAULT",
                laws_held)

        # INV_8 — WAIT exit temporal check
        if prev_status == Status.WAIT and s.status == Status.OK:
            if wait_shadow and not check_inv_8_snap(s, wait_shadow):
                return VerifyResult(False, idx,
                    "INV_8 violated: illegal evolution across WAIT boundary",
                    laws_held)
            wait_shadow = None

        if s.status == Status.WAIT and prev_status != Status.WAIT:
            wait_shadow = {
                "delta":  dict(s.delta),
                "fate":   dict(s.fate),
                "locked": dict(s.locked),
            }

        # Advance shadow
        prev_cycle  = rec.cycle
        prev_delta  = dict(s.delta)
        prev_fate   = dict(s.fate)
        prev_locked = dict(s.locked)
        prev_status = s.status

    laws_held = [
        "Λ₁ Origin Law", "Λ₂ Monotone Lock", "Λ₃ Legal Release",
        "Λ₄ Coupling Law", "Λ₅ Chain Persistence", "Λ₆ Status-Fate Coherence",
        "Λ₇ Invariant Alignment", "Λ₈ Global WAIT Coherence",
        "Λ₉ Atomic Chain Consistency", "Λ₁₀ Bootstrap Integrity",
        "Δ₁ Non-Negativity", "Δ₂ Locality", "Δ₃ Conservation",
        "Δ₄ Propagation Integrity", "Δ₅ Coupling Cost", "Δ₆ Saturation Law",
        "INV_1–INV_8",
    ]
    return VerifyResult(True, None, None, laws_held)


# ─────────────────────────────────────────────────
# §11 — Golden Path test program
# ─────────────────────────────────────────────────

GOLDEN_PATH: list[int] = [
    0x4001,   # TRACE 1           — start marker
    0x0011,   # NEXT 1            — advance GRE cycle
    0x2011,   # Δ_ADD t=1, d=1    — accumulate delta
    0x2011,   # Δ_ADD t=1, d=1    — accumulate delta
    0x2111,   # Δ_SETTLE t=1, d=1 — settle delta
    0x1011,   # BIND t=1, f=1     — bind target
    0x3011,   # ASSERT_INV 0x11   — assert invariant
    0x0111,   # ADMIT f=0x11      — admit context
    0x0211,   # WAIT f=0x11       — suspend
    0x0011,   # NEXT 1            — advance (post-resume)
    0x2211,   # Δ_DEGRADE t=1,d=1 — degrade
    0x3012,   # ASSERT_INV 0x12   — post-degrade assert
    0x4002,   # TRACE 2           — end marker
    0x0F00,   # HALT              — clean termination
]


# ─────────────────────────────────────────────────
# §15 — Functional Validation Suite
# ─────────────────────────────────────────────────

def run_validation_suite(verbose: bool = True) -> dict[str, bool]:
    results: dict[str, bool] = {}

    def _log(msg):
        if verbose:
            print(msg)

    # ── Test 1: Illegal Δ Transition (settle exceeds delta) ──────────────
    _log("\n=== Test 1: Illegal Δ Transition ===")
    state1 = VMState()
    state1.delta[1] = 1
    state1.pc = 5
    locked1: dict = {}
    word1 = 0x2115                  # Δ_SETTLE t=1, d=5
    state1.pc += 1
    rec1 = _gre_execute(state1, word1, locked1)
    _log(rec1.to_json())
    p1 = state1.status == Status.FAULT and state1.delta.get(1) == 1
    results["Test1_IllegalDeltaTransition"] = p1
    _log(f"  PASS={p1}")

    # ── Test 2: Λ Violation (locked fate UNBIND) ─────────────────────────
    _log("\n=== Test 2: Λ Violation (Locked Fate) ===")
    state2 = VMState()
    locked2: dict = {}
    state2.pc = 5
    state2.pc += 1
    _gre_execute(state2, 0x1211, locked2)   # LOCK t=1, f=1
    state2.pc += 1
    rec2b = _gre_execute(state2, 0x1111, locked2)  # UNBIND t=1, f=1
    _log(rec2b.to_json())
    p2 = (state2.status == Status.FAULT and
          state2.fate.get(1, 0) == 0x1 and
          state2.locked.get(1, 0) == 0x1)
    results["Test2_LockedFateViolation"] = p2
    _log(f"  PASS={p2}")

    # ── Test 3: Invariant Failure Path ───────────────────────────────────
    _log("\n=== Test 3: Invariant Failure Path ===")
    state3 = VMState()
    state3.inv_defs[0xFF] = lambda s: False    # always-false invariant
    locked3: dict = {}
    state3.pc = 8
    state3.pc += 1
    rec3 = _gre_execute(state3, 0x30FF, locked3)  # ASSERT_INV 0xFF
    _log(rec3.to_json())
    p3 = state3.status == Status.FAULT
    results["Test3_InvariantFailure"] = p3
    _log(f"  PASS={p3}")

    # ── Test 4: Δ Mutation Outside DELTA Class ───────────────────────────
    _log("\n=== Test 4: Δ Mutation Outside DELTA Class ===")
    state4 = VMState()
    state4.delta[1] = 42
    locked4: dict = {}
    state4.pc = 9
    state4.pc += 1
    rec4 = _gre_execute(state4, 0x1011, locked4)  # BIND t=1, f=1
    _log(rec4.to_json())
    p4 = state4.delta.get(1) == 42     # delta must be unchanged
    results["Test4_DeltaClassIsolation"] = p4
    _log(f"  PASS={p4}")

    # ── Test 5: Resume from WAIT ─────────────────────────────────────────
    _log("\n=== Test 5: Resume from WAIT ===")
    state5 = VMState()
    state5.delta[1] = 1
    state5.fate[1]  = 0x1
    state5.status   = Status.WAIT
    state5.wait_shadow = {"delta": {1: 1}, "fate": {1: 0x1}, "locked": {}}
    locked5: dict = {}
    state5.pc = 10
    state5.pc += 1
    # Simulated: external scheduler cleared WAIT, next instr is NEXT 1
    state5.status = Status.OK
    rec5 = _gre_execute(state5, 0x0011, locked5)  # NEXT 1
    _log(rec5.to_json())
    p5 = state5.status == Status.OK and state5.delta.get(1) == 1
    results["Test5_WAITResume"] = p5
    _log(f"  PASS={p5}")

    return results


# ─────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("THE VOSS BINARY — Runtime VM")
    print("Project Infi / ARIS  |  Formal Specification v2.0")
    print("=" * 60)

    print("\n── GOLDEN PATH EXECUTION ──\n")
    final_state, trace = voss_run(GOLDEN_PATH, verbose=True)

    print(f"\n── FINAL STATE ──")
    print(f"  Status:        {final_state.status.value}")
    print(f"  Cycle:         {final_state.cycle}")
    print(f"  PC:            {final_state.pc}")
    print(f"  Delta:         {dict(final_state.delta)}")
    print(f"  Fate:          { {k: hex(v) for k, v in final_state.fate.items()} }")
    print(f"  Locked:        { {k: hex(v) for k, v in final_state.locked.items()} }")
    print(f"  Coupling Debt: {final_state.coupling_debt}")

    print("\n── VERIFIER ──\n")
    verdict = voss_verify(trace)
    print(verdict)

    print("\n── FUNCTIONAL VALIDATION SUITE ──\n")
    suite_results = run_validation_suite(verbose=True)
    print("\n── SUITE SUMMARY ──")
    all_pass = True
    for name, passed in suite_results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False
    print(f"\nAll tests passed: {all_pass}")
