"""Heuristic rubric evaluation without external model calls."""

from __future__ import annotations

from forge_eval.evaluators.analyze_shared import InvalidEvaluationRequest
from forge_eval.schemas import EvaluationRequest, EvaluationResult
from forge_eval.utils.scoring import average


def _normalize_criterion(item: object) -> tuple[str, list[str]]:
    if isinstance(item, dict):
        label = str(item.get("label") or item.get("name") or "criterion").strip() or "criterion"
        terms = [
            str(term).strip()
            for term in list(item.get("required_terms") or item.get("terms") or [])
            if str(term).strip()
        ]
        return label, terms
    label = str(item).strip() or "criterion"
    return label, [label]


def evaluate_llm_rubric(request: EvaluationRequest) -> EvaluationResult:
    """Score a candidate artifact against declarative rubric terms."""

    text = str(request.payload.program or request.payload.patch or "")
    if not text.strip():
        raise InvalidEvaluationRequest(
            "payload.program or payload.patch is required for llm_rubric mode."
        )

    config = dict(request.payload.config or {})
    raw_criteria = list(config.get("criteria") or config.get("rubric") or [])
    if not raw_criteria:
        raw_criteria = ["clear structure", "goal coverage"]

    criteria_details: list[dict[str, object]] = []
    scores: list[float] = []
    lowered = text.lower()

    for raw in raw_criteria:
        label, terms = _normalize_criterion(raw)
        if not terms:
            score = 1.0 if text.strip() else 0.0
            matched_terms: list[str] = []
        else:
            matched_terms = [term for term in terms if term.lower() in lowered]
            score = len(matched_terms) / len(terms)
        scores.append(score)
        criteria_details.append(
            {
                "label": label,
                "required_terms": terms,
                "matched_terms": matched_terms,
                "score": score,
            }
        )

    return EvaluationResult(
        score=average(scores),
        details={"criteria": criteria_details},
    )
