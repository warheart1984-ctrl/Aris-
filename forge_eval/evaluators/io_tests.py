"""Deterministic text-based IO test evaluation."""

from __future__ import annotations

from forge_eval.evaluators.analyze_shared import InvalidEvaluationRequest
from forge_eval.schemas import EvaluationRequest, EvaluationResult
from forge_eval.utils.scoring import average


def evaluate_io_tests(request: EvaluationRequest) -> EvaluationResult:
    """Evaluate a candidate program against declarative text checks."""

    program = str(request.payload.program or "")
    if not program.strip():
        raise InvalidEvaluationRequest("payload.program is required for io_tests mode.")

    config = dict(request.payload.config or {})
    must_contain = [str(item) for item in list(config.get("must_contain") or []) if str(item).strip()]
    must_not_contain = [str(item) for item in list(config.get("must_not_contain") or []) if str(item).strip()]

    checks: list[dict[str, object]] = []
    scores: list[float] = []

    for needle in must_contain:
        passed = needle in program
        checks.append({"type": "must_contain", "needle": needle, "passed": passed})
        scores.append(1.0 if passed else 0.0)

    for needle in must_not_contain:
        passed = needle not in program
        checks.append({"type": "must_not_contain", "needle": needle, "passed": passed})
        scores.append(1.0 if passed else 0.0)

    if not checks:
        checks.append({"type": "presence", "needle": "program", "passed": True})
        scores.append(1.0)

    passed_count = sum(1 for item in checks if item["passed"])
    return EvaluationResult(
        score=average(scores),
        details={
            "checks": checks,
            "passed": passed_count,
            "total": len(checks),
        },
    )
