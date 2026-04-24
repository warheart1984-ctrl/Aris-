from __future__ import annotations

from datetime import UTC, datetime
import uuid

from .laws import (
    FailureClass,
    FutureWorth,
    ImmutableLawSet,
    RegistryDestination,
    Repairability,
    Severity,
    ShieldLaw,
    Verdict,
)
from .registries import (
    CheckResult,
    FailureRegistry,
    FutureWorthAnalysis,
    HallOfDecisions,
    ShieldEvaluation,
    ValueAnalysis,
    WeightAnalysis,
)
from .verification import DecisionContext, RECOGNIZED_PROOF_KEYS


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class ShieldOfTruth1001:
    """Protected adjudicator for input, output, verification, values, and future worth."""

    def __init__(
        self,
        *,
        laws: ImmutableLawSet | None = None,
        hall_of_decisions: HallOfDecisions | None = None,
        failure_registry: FailureRegistry | None = None,
    ) -> None:
        self.laws = laws or ImmutableLawSet()
        self.hall = hall_of_decisions or HallOfDecisions()
        self.failures = failure_registry or FailureRegistry()

    def status_payload(self) -> dict[str, object]:
        return {
            "active": True,
            "component_id": "shield_of_truth.1001",
            "immutable_laws": [law.value for law in self.laws.laws],
            "hall_of_decisions_count": len(self.hall.all()),
            "failure_registry_count": len(self.failures.all()),
        }

    def judge(self, ctx: DecisionContext) -> ShieldEvaluation:
        input_check = self._check_input(ctx)
        output_check = self._check_output(ctx)
        verification_check = self._check_verification(ctx)
        law_check = self._check_laws(ctx)
        weight_analysis = self._analyze_weights(ctx)
        value_analysis = self._analyze_values(ctx)
        future_worth = self._analyze_future_worth(ctx, weight_analysis, value_analysis)
        failure_classes = self._collect_failure_classes(
            ctx=ctx,
            input_check=input_check,
            output_check=output_check,
            verification_check=verification_check,
            law_check=law_check,
            weight_analysis=weight_analysis,
            value_analysis=value_analysis,
            future_worth_analysis=future_worth,
        )
        explanation = self._build_explanation(
            input_check=input_check,
            output_check=output_check,
            verification_check=verification_check,
            law_check=law_check,
            weight_analysis=weight_analysis,
            value_analysis=value_analysis,
            future_worth_analysis=future_worth,
        )
        if not failure_classes:
            evaluation = ShieldEvaluation(
                decision_id=_new_id(),
                timestamp=_utc_now(),
                actor=ctx.actor,
                action_type=ctx.action_type,
                verdict=Verdict.PASS,
                destination=RegistryDestination.HALL_OF_DECISIONS,
                input_check=input_check,
                output_check=output_check,
                verification_check=verification_check,
                law_check=law_check,
                weight_analysis=weight_analysis,
                value_analysis=value_analysis,
                future_worth_analysis=future_worth,
                failure_classes=[],
                explanation=explanation,
                raw_input=ctx.input_payload,
                raw_output=ctx.proposed_output,
                metadata=ctx.metadata,
            )
            self.hall.add(evaluation)
            return evaluation
        severity = self._assign_severity(
            failure_classes=failure_classes,
            ctx=ctx,
            future_worth_analysis=future_worth,
        )
        repairability = self._assign_repairability(
            failure_classes=failure_classes,
            severity=severity,
        )
        verdict = self._assign_failure_verdict(severity=severity, ctx=ctx)
        evaluation = ShieldEvaluation(
            decision_id=_new_id(),
            timestamp=_utc_now(),
            actor=ctx.actor,
            action_type=ctx.action_type,
            verdict=verdict,
            destination=RegistryDestination.FAILURE_REGISTRY,
            input_check=input_check,
            output_check=output_check,
            verification_check=verification_check,
            law_check=law_check,
            weight_analysis=weight_analysis,
            value_analysis=value_analysis,
            future_worth_analysis=future_worth,
            severity=severity,
            repairability=repairability,
            failure_classes=failure_classes,
            explanation=explanation,
            raw_input=ctx.input_payload,
            raw_output=ctx.proposed_output,
            metadata=ctx.metadata,
        )
        self.failures.add(evaluation)
        return evaluation

    def _check_input(self, ctx: DecisionContext) -> CheckResult:
        notes: list[str] = []
        failures: list[FailureClass] = []
        if not ctx.input_payload:
            failures.append(FailureClass.INPUT_FAILURE)
            notes.append("Input payload is empty.")
        if not str(ctx.interpreted_intent or "").strip():
            failures.append(FailureClass.INPUT_FAILURE)
            notes.append("Interpreted intent missing or empty.")
        if "request" not in ctx.input_payload and "prompt" not in ctx.input_payload:
            notes.append("Input does not contain a canonical request or prompt field.")
        return CheckResult(passed=not failures, notes=notes, failures=failures)

    def _check_output(self, ctx: DecisionContext) -> CheckResult:
        notes: list[str] = []
        failures: list[FailureClass] = []
        if not ctx.proposed_output:
            failures.append(FailureClass.OUTPUT_FAILURE)
            notes.append("Proposed output is empty.")
        if "status" not in ctx.proposed_output:
            notes.append("Output missing status field.")
        if ctx.mutation and "mutation_patch" not in ctx.proposed_output:
            failures.append(FailureClass.MUTATION_INTEGRITY_FAILURE)
            notes.append("Mutation action missing mutation_patch artifact.")
        return CheckResult(passed=not failures, notes=notes, failures=failures)

    def _check_verification(self, ctx: DecisionContext) -> CheckResult:
        notes: list[str] = []
        failures: list[FailureClass] = []
        if not ctx.evidence:
            failures.append(FailureClass.VERIFICATION_FAILURE)
            notes.append("No evidence attached for verification.")
            return CheckResult(passed=False, notes=notes, failures=failures)
        if not any(key in ctx.evidence for key in RECOGNIZED_PROOF_KEYS):
            failures.append(FailureClass.VERIFICATION_FAILURE)
            notes.append("Evidence exists, but no recognized proof fields were found.")
        return CheckResult(passed=not failures, notes=notes, failures=failures)

    def _check_laws(self, ctx: DecisionContext) -> CheckResult:
        notes: list[str] = []
        failures: list[FailureClass] = []
        required = sorted(law.value for law in self.laws.laws)
        violation_flags = list(ctx.metadata.get("law_violations") or [])
        for violation in violation_flags:
            failures.append(FailureClass.LAW_VIOLATION_FAILURE)
            notes.append(f"Explicit law violation flagged: {violation}")
        if bool(ctx.metadata.get("identity_drift_detected")):
            failures.append(FailureClass.IDENTITY_CONSISTENCY_FAILURE)
            notes.append("Identity drift detected.")
        if bool(ctx.metadata.get("domination_risk")):
            failures.append(FailureClass.LAW_VIOLATION_FAILURE)
            notes.append("Domination risk detected.")
        if bool(ctx.metadata.get("harm_risk")):
            failures.append(FailureClass.LAW_VIOLATION_FAILURE)
            notes.append("Harm risk detected.")
        if ctx.mutation and ShieldLaw.MUTATION_INTEGRITY.value not in ctx.values_claimed:
            notes.append("Mutation action did not explicitly claim mutation_integrity.")
        if ShieldLaw.VERIFICATION_REQUIREMENT.value not in ctx.values_claimed:
            notes.append("Verification requirement not explicitly claimed.")
        notes.append(f"Immutable laws loaded: {required}")
        return CheckResult(passed=not failures, notes=notes, failures=failures)

    def _analyze_weights(self, ctx: DecisionContext) -> WeightAnalysis:
        weights = dict(ctx.weights or {})
        notes: list[str] = []
        overweighted: list[str] = []
        underweighted: list[str] = []
        distortion_detected = False
        temporal_risk_detected = False
        safety = float(weights.get("safety", 0.0))
        truth = float(weights.get("truth", 0.0))
        operator_intent = float(weights.get("operator_intent", 0.0))
        identity = float(weights.get("identity_integrity", 0.0))
        speed = float(weights.get("speed", 0.0))
        autonomy = float(weights.get("autonomy", 0.0))
        future_integrity = float(weights.get("future_integrity", 0.0))
        if speed > safety:
            distortion_detected = True
            overweighted.append("speed")
            underweighted.append("safety")
            notes.append("Speed outweighed safety.")
        if speed > truth:
            distortion_detected = True
            overweighted.append("speed")
            underweighted.append("truth")
            notes.append("Speed outweighed truth.")
        if autonomy > operator_intent:
            distortion_detected = True
            overweighted.append("autonomy")
            underweighted.append("operator_intent")
            notes.append("Autonomy outweighed operator intent.")
        if future_integrity < max(safety, truth, operator_intent, identity, 0.1) * 0.5:
            temporal_risk_detected = True
            underweighted.append("future_integrity")
            notes.append("Future integrity appears underweighted.")
        return WeightAnalysis(
            justified=not distortion_detected,
            overweighted=sorted(set(overweighted)),
            underweighted=sorted(set(underweighted)),
            distortion_detected=distortion_detected,
            temporal_risk_detected=temporal_risk_detected,
            notes=notes,
        )

    def _analyze_values(self, ctx: DecisionContext) -> ValueAnalysis:
        notes: list[str] = []
        expressed_values = sorted(set(ctx.values_claimed or []))
        violated_values = sorted(set(list(ctx.metadata.get("law_violations") or [])))
        preserved_values: list[str] = []
        for law in self.laws.laws:
            if law.value in expressed_values and law.value not in violated_values:
                preserved_values.append(law.value)
        if bool(ctx.metadata.get("harm_risk")):
            violated_values.append(ShieldLaw.NON_HARM.value)
            notes.append("Metadata indicates harm risk.")
        if bool(ctx.metadata.get("domination_risk")):
            violated_values.append(ShieldLaw.NON_DOMINATION.value)
            notes.append("Metadata indicates domination risk.")
        if bool(ctx.metadata.get("identity_drift_detected")):
            violated_values.append(ShieldLaw.IDENTITY_CONSISTENCY.value)
            notes.append("Metadata indicates identity drift.")
        violated_values = sorted(set(violated_values))
        return ValueAnalysis(
            aligned=not violated_values,
            expressed_values=expressed_values,
            violated_values=violated_values,
            preserved_values=sorted(set(preserved_values)),
            notes=notes,
        )

    def _analyze_future_worth(
        self,
        ctx: DecisionContext,
        weight_analysis: WeightAnalysis,
        value_analysis: ValueAnalysis,
    ) -> FutureWorthAnalysis:
        status = FutureWorth.WORTHY
        repeatable = True
        inheritance_safe = True
        notes: list[str] = []
        if weight_analysis.temporal_risk_detected:
            status = FutureWorth.CONDITIONAL
            repeatable = False
            inheritance_safe = False
            notes.append("Temporal risk detected; future integrity may be compromised.")
        if not value_analysis.aligned:
            status = FutureWorth.REJECTED
            repeatable = False
            inheritance_safe = False
            notes.append("Value misalignment makes this unsafe to inherit.")
        if bool(ctx.metadata.get("future_collapse_risk")):
            status = FutureWorth.FORBIDDEN
            repeatable = False
            inheritance_safe = False
            notes.append("Future collapse risk flagged.")
        if bool(ctx.metadata.get("1001_bypass_attempt")):
            status = FutureWorth.FORBIDDEN
            repeatable = False
            inheritance_safe = False
            notes.append("1001 bypass attempt detected.")
        return FutureWorthAnalysis(
            status=status,
            repeatable=repeatable,
            inheritance_safe=inheritance_safe,
            notes=notes,
        )

    def _collect_failure_classes(
        self,
        *,
        ctx: DecisionContext,
        input_check: CheckResult,
        output_check: CheckResult,
        verification_check: CheckResult,
        law_check: CheckResult,
        weight_analysis: WeightAnalysis,
        value_analysis: ValueAnalysis,
        future_worth_analysis: FutureWorthAnalysis,
    ) -> list[FailureClass]:
        failures = list(input_check.failures)
        failures.extend(output_check.failures)
        failures.extend(verification_check.failures)
        failures.extend(law_check.failures)
        if weight_analysis.distortion_detected or weight_analysis.temporal_risk_detected:
            failures.append(FailureClass.WEIGHT_FAILURE)
        if not value_analysis.aligned:
            failures.append(FailureClass.VALUE_FAILURE)
        if future_worth_analysis.status in {FutureWorth.REJECTED, FutureWorth.FORBIDDEN}:
            failures.append(FailureClass.FUTURE_WORTH_FAILURE)
        if ctx.conflict_present and not bool(ctx.metadata.get("conflict_resolved")):
            failures.append(FailureClass.CONFLICT_RESOLUTION_FAILURE)
        if bool(ctx.metadata.get("explanation_missing")):
            failures.append(FailureClass.EXPLANATION_FAILURE)
        return sorted(set(failures), key=lambda item: item.value)

    def _assign_severity(
        self,
        *,
        failure_classes: list[FailureClass],
        ctx: DecisionContext,
        future_worth_analysis: FutureWorthAnalysis,
    ) -> Severity:
        if bool(ctx.metadata.get("1001_bypass_attempt")):
            return Severity.CRITICAL
        if future_worth_analysis.status == FutureWorth.FORBIDDEN:
            return Severity.CRITICAL
        if any(
            failure in failure_classes
            for failure in (
                FailureClass.LAW_VIOLATION_FAILURE,
                FailureClass.MUTATION_INTEGRITY_FAILURE,
                FailureClass.IDENTITY_CONSISTENCY_FAILURE,
                FailureClass.CONFLICT_RESOLUTION_FAILURE,
            )
        ):
            return Severity.CRITICAL
        if any(
            failure in failure_classes
            for failure in (
                FailureClass.VALUE_FAILURE,
                FailureClass.WEIGHT_FAILURE,
                FailureClass.VERIFICATION_FAILURE,
                FailureClass.FUTURE_WORTH_FAILURE,
            )
        ):
            return Severity.MAJOR
        if any(
            failure in failure_classes
            for failure in (FailureClass.OUTPUT_FAILURE, FailureClass.INPUT_FAILURE)
        ):
            return Severity.MODERATE
        return Severity.MINOR

    def _assign_repairability(
        self,
        *,
        failure_classes: list[FailureClass],
        severity: Severity,
    ) -> Repairability:
        if severity == Severity.CRITICAL:
            if any(
                failure in failure_classes
                for failure in (
                    FailureClass.LAW_VIOLATION_FAILURE,
                    FailureClass.IDENTITY_CONSISTENCY_FAILURE,
                    FailureClass.MUTATION_INTEGRITY_FAILURE,
                )
            ):
                return Repairability.NON_ADMISSIBLE
            return Repairability.ESCALATE_TO_OPERATOR
        if severity == Severity.MAJOR:
            return Repairability.REQUIRES_REDESIGN
        return Repairability.REPAIRABLE

    def _assign_failure_verdict(self, *, severity: Severity, ctx: DecisionContext) -> Verdict:
        if bool(ctx.metadata.get("1001_bypass_attempt")):
            return Verdict.QUARANTINED
        if severity == Severity.CRITICAL:
            return Verdict.QUARANTINED
        if severity == Severity.MAJOR:
            return Verdict.FAIL
        return Verdict.ESCALATE

    def _build_explanation(
        self,
        *,
        input_check: CheckResult,
        output_check: CheckResult,
        verification_check: CheckResult,
        law_check: CheckResult,
        weight_analysis: WeightAnalysis,
        value_analysis: ValueAnalysis,
        future_worth_analysis: FutureWorthAnalysis,
    ) -> list[str]:
        explanation: list[str] = []
        explanation.extend(input_check.notes)
        explanation.extend(output_check.notes)
        explanation.extend(verification_check.notes)
        explanation.extend(law_check.notes)
        explanation.extend(weight_analysis.notes)
        explanation.extend(value_analysis.notes)
        explanation.extend(future_worth_analysis.notes)
        return explanation
