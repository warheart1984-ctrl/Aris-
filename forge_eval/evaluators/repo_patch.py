"""Repo-aware patch evaluation helpers."""

from __future__ import annotations

from forge_eval.evaluators.analyze_shared import InvalidEvaluationRequest
from forge_eval.sandbox.local_runner import resolve_repo_path
from forge_eval.schemas import EvaluationRequest, EvaluationResult
from forge_eval.utils.scoring import average


def _extract_touched_files(patch: str) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for line in str(patch or "").splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
        elif line.startswith("diff --git "):
            pieces = line.split()
            path = pieces[3][2:] if len(pieces) >= 4 and pieces[3].startswith("b/") else ""
        else:
            continue
        normalized = path.replace("\\", "/")
        if normalized and normalized not in seen and normalized != "/dev/null":
            seen.add(normalized)
            touched.append(normalized)
    return touched


def evaluate_repo_patch(request: EvaluationRequest) -> EvaluationResult:
    """Score a patch against repo-relative expectations."""

    patch = str(request.payload.patch or "")
    if not patch.strip():
        raise InvalidEvaluationRequest("payload.patch is required for repo_patch mode.")

    repo_path = resolve_repo_path(request.payload.repo)
    config = dict(request.payload.config or {})
    expected_files = [
        str(item).strip().replace("\\", "/")
        for item in list(config.get("expected_files") or [])
        if str(item).strip()
    ]
    touched_files = _extract_touched_files(patch)

    scores = [1.0 if touched_files else 0.0]
    if expected_files:
        expected_hits = len(set(expected_files) & set(touched_files))
        scores.append(expected_hits / len(expected_files))
    else:
        scores.append(1.0 if touched_files else 0.0)

    existing_hits = sum(1 for path in touched_files if (repo_path / path).exists())
    if touched_files:
        scores.append(existing_hits / len(touched_files))

    return EvaluationResult(
        score=average(scores),
        details={
            "repo": str(repo_path),
            "touched_files": touched_files,
            "expected_files": expected_files,
            "existing_hits": existing_hits,
        },
    )
