"""Result normalization for `generate_diff` contractor requests."""

from __future__ import annotations

from forge.schemas import ContractorResult, UnifiedDiff
from forge.utils.bounded_output import bound_text


guidance = (
    "Generate unified diffs only. Each diff must target one relative path and should be "
    "ready for human review."
)

response_schema = """{
  "diffs": [
    {
      "path": "relative/path.ext",
      "unified_diff": "diff --git ..."
    }
  ]
}"""


def normalize_result(
    parsed: object,
    *,
    max_output_chars: int,
    context: dict[str, object] | None = None,
) -> ContractorResult | None:
    if not isinstance(parsed, dict):
        return None
    raw_diffs = parsed.get("diffs")
    if not isinstance(raw_diffs, list) or not raw_diffs:
        return None

    diffs: list[UnifiedDiff] = []
    for item in raw_diffs:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().replace("\\", "/")
        unified_diff = item.get("unified_diff")
        if not path or not isinstance(unified_diff, str):
            continue
        diffs.append(
            UnifiedDiff(
                path=path,
                unified_diff=bound_text(unified_diff, max_output_chars),
            )
        )
    if not diffs:
        return None
    return ContractorResult(diffs=diffs)
