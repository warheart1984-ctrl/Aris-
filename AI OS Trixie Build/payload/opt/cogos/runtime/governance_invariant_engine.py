"""
governance_invariant_engine.py — Governance Runtime Engine (GRE)

Six-stage fail-closed pipeline for CoGOS Phase 0.
Shapes align with AAIS Voss Binding §4 and Stabilization Protocol drift model.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def cogos_root() -> Path:
    return Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))


class Checkpoint(str, Enum):
    INPUT_GATE = "INPUT_GATE"
    GOVERNANCE_CHECK = "GOVERNANCE_CHECK"
    EXECUTE = "EXECUTE"
    OUTPUT_GATE = "OUTPUT_GATE"
    DRIFT_MEASUREMENT = "DRIFT_MEASUREMENT"
    AUDIT_COMMIT = "AUDIT_COMMIT"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CorrectionPolicy(str, Enum):
    BLOCK_ESCALATE = "BLOCK_ESCALATE"
    REWRITE_REROUTE = "REWRITE_REROUTE"
    FAIL_CLOSED = "FAIL_CLOSED"
    CLAMP_CORRECT = "CLAMP_CORRECT"
    REJECT = "REJECT"


class CircuitBreakerAction(str, Enum):
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class Invariant:
    id: str
    subject: str
    constraint: str
    severity: Severity = Severity.HIGH
    correction_policy: CorrectionPolicy = CorrectionPolicy.FAIL_CLOSED
    lambda_bindings: List[str] = field(default_factory=list)


@dataclass
class DriftScores:
    behavioral: float = 0.0
    schema: float = 0.0
    identity: float = 0.0
    temporal: float = 0.0

    def validate(self) -> None:
        for name in ("behavioral", "schema", "identity", "temporal"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"drift.{name} out of range: {value}")

    def composite(self) -> float:
        self.validate()
        return max(self.behavioral, self.schema, self.identity, self.temporal)

    def severity(self) -> Severity:
        c = self.composite()
        if c >= 0.85:
            return Severity.CRITICAL
        if c >= 0.6:
            return Severity.HIGH
        if c >= 0.35:
            return Severity.MEDIUM
        return Severity.LOW


@dataclass
class ExecutionContext:
    module_id: str
    lane_id: str
    subject: str
    checkpoint: Checkpoint
    input_data: Dict[str, Any]
    input_hash: str
    output_data: Optional[Dict[str, Any]] = None
    output_hash: Optional[str] = None
    declared_bindings: List[str] = field(default_factory=list)
    drift_scores: DriftScores = field(default_factory=DriftScores)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class Violation:
    invariant_id: str
    description: str
    severity: Severity
    checkpoint: Checkpoint
    correction_policy: CorrectionPolicy


@dataclass
class CorrectionDirective:
    policy: CorrectionPolicy
    message: str


@dataclass
class AuditRecord:
    trace_id: str
    module_id: str
    lane_id: str
    subject: str
    passed: bool
    checkpoint: Checkpoint
    input_hash: str
    output_hash: Optional[str]
    violations: List[Dict[str, Any]]
    drift_composite: float
    timestamp: str
    stages_completed: List[str]


@dataclass
class EnforcementResult:
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    correction_directives: List[CorrectionDirective] = field(default_factory=list)
    audit_record: Optional[AuditRecord] = None
    circuit_breaker_action: Optional[CircuitBreakerAction] = None
    output: Any = None


@dataclass
class ModuleContract:
    module_id: str
    lane_id: str
    subject: str
    required_input_fields: List[str] = field(default_factory=list)
    governance_bindings: List[str] = field(default_factory=list)
    allowed_subjects: List[str] = field(default_factory=list)


# Λ spine invariants enforced at GRE (Phase 0 core set)
CORE_INVARIANTS: List[Invariant] = [
    Invariant("Λ.1", "ALL", "Outputs must be deterministic and replayable", Severity.CRITICAL,
              CorrectionPolicy.FAIL_CLOSED, ["Λ.1"]),
    Invariant("Λ.2", "ALL", "Every decision must emit an audit record", Severity.CRITICAL,
              CorrectionPolicy.FAIL_CLOSED, ["Λ.2"]),
    Invariant("Λ.3", "ALL", "When uncertain, halt — fail closed", Severity.CRITICAL,
              CorrectionPolicy.FAIL_CLOSED, ["Λ.3"]),
    Invariant("Λ.4", "ALL", "Agents maintain identity separation", Severity.HIGH,
              CorrectionPolicy.BLOCK_ESCALATE, ["Λ.4"]),
    Invariant("Λ.5", "ALL", "Drift beyond threshold must surface immediately", Severity.HIGH,
              CorrectionPolicy.BLOCK_ESCALATE, ["Λ.5"]),
    Invariant("Λ.6", "ALL", "Recovery requires governed correction", Severity.HIGH,
              CorrectionPolicy.REWRITE_REROUTE, ["Λ.6"]),
    Invariant("Λ.7", "ALL", "Operator supremacy over agent autonomy", Severity.CRITICAL,
              CorrectionPolicy.FAIL_CLOSED, ["Λ.7"]),
    Invariant("INV-BOOT", "CoGOS", "Boot must declare governance bindings", Severity.CRITICAL,
              CorrectionPolicy.FAIL_CLOSED, ["Λ.3", "Λ.7"]),
    Invariant("INV-UL-DANGEROUS", "ULVM", "Dangerous substrate verbs require manual mode", Severity.HIGH,
              CorrectionPolicy.REJECT, ["Λ.3", "Λ.7"]),
]

DRIFT_BLOCK_THRESHOLD = 0.85


def canonical_hash(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_execution_context(
    gre: "GovernanceRuntimeEngine",
    module_id: str,
    input_data: Dict[str, Any],
    *,
    lane_id: Optional[str] = None,
    subject: Optional[str] = None,
    declared_bindings: Optional[List[str]] = None,
) -> ExecutionContext:
    contract = gre.get_contract(module_id)
    lane = lane_id or (contract.lane_id if contract else "default")
    subj = subject or (contract.subject if contract else module_id)
    bindings = declared_bindings or (contract.governance_bindings if contract else [])
    return ExecutionContext(
        module_id=module_id,
        lane_id=lane,
        subject=subj,
        checkpoint=Checkpoint.INPUT_GATE,
        input_data=input_data,
        input_hash=canonical_hash(input_data),
        declared_bindings=list(bindings),
    )


class GovernanceRuntimeEngine:
    def __init__(self, invariants: Optional[List[Invariant]] = None) -> None:
        self.invariants = list(invariants or CORE_INVARIANTS)
        self._contracts: Dict[str, ModuleContract] = {}
        self.audit_chain: List[AuditRecord] = []
        self._circuit_open: Dict[str, bool] = {}
        self._load_root_law_invariants()

    def _load_root_law_invariants(self) -> None:
        path = cogos_root() / "law" / "root_law.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return
        for name in data.get("invariants", []):
            inv_id = f"ROOT-{name}"
            if any(i.id == inv_id for i in self.invariants):
                continue
            self.invariants.append(
                Invariant(
                    id=inv_id,
                    subject="ALL",
                    constraint=f"root_law requires: {name}",
                    severity=Severity.HIGH,
                    correction_policy=CorrectionPolicy.FAIL_CLOSED,
                    lambda_bindings=["Λ.3"],
                )
            )

    def register_module(self, contract: ModuleContract) -> None:
        self._contracts[contract.module_id] = contract

    def get_contract(self, module_id: str) -> Optional[ModuleContract]:
        return self._contracts.get(module_id)

    def enforce(
        self,
        ctx: ExecutionContext,
        execute: Optional[Callable[[ExecutionContext], Any]] = None,
        *,
        mode: str = "automatic",
    ) -> EnforcementResult:
        violations: List[Violation] = []
        directives: List[CorrectionDirective] = []
        stages: List[str] = []
        cb_action: Optional[CircuitBreakerAction] = None
        output: Any = None

        if self._circuit_open.get(ctx.module_id):
            violations.append(
                Violation("GRE-CB", "Circuit breaker open for module", Severity.CRITICAL,
                          Checkpoint.INPUT_GATE, CorrectionPolicy.FAIL_CLOSED)
            )
            cb_action = CircuitBreakerAction.OPEN
            return self._finalize(ctx, False, violations, directives, stages, cb_action, output)

        # Stage 1 — INPUT_GATE
        ctx.checkpoint = Checkpoint.INPUT_GATE
        stages.append(Checkpoint.INPUT_GATE.value)
        contract = self.get_contract(ctx.module_id)
        if contract is None and ctx.module_id not in ("PID1",):
            violations.append(
                Violation("GRE-REG", f"Unregistered module: {ctx.module_id}", Severity.CRITICAL,
                          Checkpoint.INPUT_GATE, CorrectionPolicy.FAIL_CLOSED)
            )
        elif contract:
            for req in contract.required_input_fields:
                if req not in ctx.input_data:
                    violations.append(
                        Violation("GRE-IN", f"Missing required field: {req}", Severity.HIGH,
                                  Checkpoint.INPUT_GATE, CorrectionPolicy.REJECT)
                    )
            if contract.allowed_subjects and ctx.subject not in contract.allowed_subjects:
                violations.append(
                    Violation("Λ.4", f"Subject {ctx.subject!r} not allowed for {ctx.module_id}",
                              Severity.HIGH, Checkpoint.INPUT_GATE, CorrectionPolicy.BLOCK_ESCALATE)
                )

        if self._has_critical(violations):
            return self._finalize(ctx, False, violations, directives, stages, cb_action, output)

        # Stage 2 — GOVERNANCE_CHECK
        ctx.checkpoint = Checkpoint.GOVERNANCE_CHECK
        stages.append(Checkpoint.GOVERNANCE_CHECK.value)
        violations.extend(self._check_invariants(ctx, mode))
        if self._has_critical(violations):
            self._trip_breaker(ctx.module_id)
            return self._finalize(ctx, False, violations, directives, stages, CircuitBreakerAction.OPEN, output)

        # Stage 3 — EXECUTE
        ctx.checkpoint = Checkpoint.EXECUTE
        stages.append(Checkpoint.EXECUTE.value)
        if execute is not None:
            try:
                output = execute(ctx)
                ctx.output_data = output if isinstance(output, dict) else {"result": output}
                ctx.output_hash = canonical_hash(ctx.output_data)
            except Exception as exc:
                violations.append(
                    Violation("GRE-EXEC", str(exc), Severity.CRITICAL, Checkpoint.EXECUTE,
                              CorrectionPolicy.FAIL_CLOSED)
                )
                self._trip_breaker(ctx.module_id)
                return self._finalize(ctx, False, violations, directives, stages,
                                      CircuitBreakerAction.OPEN, output)

        # Stage 4 — OUTPUT_GATE
        ctx.checkpoint = Checkpoint.OUTPUT_GATE
        stages.append(Checkpoint.OUTPUT_GATE.value)
        if execute is not None and ctx.output_data is None:
            violations.append(
                Violation("GRE-OUT", "Execution produced no output record", Severity.HIGH,
                          Checkpoint.OUTPUT_GATE, CorrectionPolicy.FAIL_CLOSED)
            )

        # Stage 5 — DRIFT_MEASUREMENT
        ctx.checkpoint = Checkpoint.DRIFT_MEASUREMENT
        stages.append(Checkpoint.DRIFT_MEASUREMENT.value)
        ctx.drift_scores = self._measure_drift(ctx, violations)
        if ctx.drift_scores.composite() >= DRIFT_BLOCK_THRESHOLD:
            violations.append(
                Violation("Λ.5", f"Drift composite {ctx.drift_scores.composite():.3f} exceeds threshold",
                          Severity.CRITICAL, Checkpoint.DRIFT_MEASUREMENT,
                          CorrectionPolicy.BLOCK_ESCALATE)
            )
            directives.append(CorrectionDirective(CorrectionPolicy.BLOCK_ESCALATE, "drift threshold exceeded"))

        passed = not self._has_critical(violations) and not any(
            v.severity in (Severity.CRITICAL, Severity.HIGH) for v in violations
        )

        # Stage 6 — AUDIT_COMMIT
        ctx.checkpoint = Checkpoint.AUDIT_COMMIT
        stages.append(Checkpoint.AUDIT_COMMIT.value)
        return self._finalize(ctx, passed, violations, directives, stages, cb_action, output)

    def _check_invariants(self, ctx: ExecutionContext, mode: str) -> List[Violation]:
        out: List[Violation] = []
        for inv in self.invariants:
            if inv.subject not in ("ALL", ctx.subject, ctx.module_id, "CoGOS"):
                continue

            if inv.id == "INV-BOOT" and ctx.module_id == "PID1":
                if not ctx.declared_bindings:
                    out.append(Violation(inv.id, inv.constraint, inv.severity, ctx.checkpoint,
                                         inv.correction_policy))

            if inv.id == "INV-UL-DANGEROUS" and ctx.module_id == "ULVM":
                action = str(ctx.input_data.get("action", ""))
                cap = str(ctx.input_data.get("capability", ""))
                if cap == "dangerous" and mode != "manual":
                    out.append(Violation(inv.id, "Dangerous UL action blocked in automatic mode",
                                         inv.severity, ctx.checkpoint, inv.correction_policy))

            if inv.id == "Λ.7" and ctx.input_data.get("bypass_governance"):
                out.append(Violation(inv.id, "Governance bypass refused", inv.severity, ctx.checkpoint,
                                     inv.correction_policy))

        binding_set = set(ctx.declared_bindings)
        for inv in self.invariants:
            if inv.lambda_bindings and inv.subject in ("ALL", ctx.module_id):
                for binding in inv.lambda_bindings:
                    if binding.startswith("Λ") and ctx.module_id == "PID1" and binding not in binding_set:
                        pass  # boot declares subset; optional strict mode later

        return out

    def _measure_drift(self, ctx: ExecutionContext, violations: List[Violation]) -> DriftScores:
        v_weight = min(1.0, len(violations) * 0.2)
        schema = 0.1 if ctx.output_data is None and ctx.checkpoint == Checkpoint.DRIFT_MEASUREMENT else 0.0
        identity = 0.15 if ctx.subject not in ("Nova", "CoGOS", "Jarvis", "ULVM", "PID1") else 0.0
        temporal = 0.05
        return DriftScores(
            behavioral=v_weight,
            schema=schema,
            identity=identity,
            temporal=temporal,
        )

    def _has_critical(self, violations: List[Violation]) -> bool:
        return any(v.severity == Severity.CRITICAL for v in violations)

    def _trip_breaker(self, module_id: str) -> None:
        self._circuit_open[module_id] = True

    def _finalize(
        self,
        ctx: ExecutionContext,
        passed: bool,
        violations: List[Violation],
        directives: List[CorrectionDirective],
        stages: List[str],
        cb_action: Optional[CircuitBreakerAction],
        output: Any,
    ) -> EnforcementResult:
        record = AuditRecord(
            trace_id=ctx.trace_id,
            module_id=ctx.module_id,
            lane_id=ctx.lane_id,
            subject=ctx.subject,
            passed=passed,
            checkpoint=ctx.checkpoint,
            input_hash=ctx.input_hash,
            output_hash=ctx.output_hash,
            violations=[
                {
                    "invariant_id": v.invariant_id,
                    "description": v.description,
                    "severity": v.severity.value,
                    "checkpoint": v.checkpoint.value,
                }
                for v in violations
            ],
            drift_composite=ctx.drift_scores.composite() if ctx.drift_scores else 0.0,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            stages_completed=stages,
        )
        self.audit_chain.append(record)
        return EnforcementResult(
            passed=passed,
            violations=violations,
            correction_directives=directives,
            audit_record=record,
            circuit_breaker_action=cb_action,
            output=output,
        )


def build_gre() -> GovernanceRuntimeEngine:
    return GovernanceRuntimeEngine()
