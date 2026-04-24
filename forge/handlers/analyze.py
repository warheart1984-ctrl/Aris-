"""Result normalization for `analyze` contractor requests."""

from __future__ import annotations

from forge.schemas import AnalysisPayload, ContractorResult
from forge.utils.bounded_output import bound_text


guidance = (
    "Analyze the provided code context against the goal and return a concise structured review. "
    "Do not suggest running code or external tools."
)

response_schema = """{
  "analysis": {
    "summary": "short overall summary",
    "issues": ["issue one", "issue two"],
    "notes": "extra implementation notes"
  }
}"""


def normalize_result(
    parsed: object,
    *,
    max_output_chars: int,
    context: dict[str, object] | None = None,
) -> ContractorResult | None:
    if not isinstance(parsed, dict):
        return None
    raw_analysis = parsed.get("analysis")
    if not isinstance(raw_analysis, dict):
        return None

    summary = bound_text(raw_analysis.get("summary"), max_output_chars)
    if not summary.strip():
        return None
    issues = [
        bound_text(item, min(600, max_output_chars))
        for item in list(raw_analysis.get("issues") or [])
        if str(item).strip()
    ][:20]
    notes = bound_text(raw_analysis.get("notes"), max_output_chars)

    return ContractorResult(
        analysis=AnalysisPayload(
            summary=summary,
            issues=issues,
            notes=notes,
        )
    )
