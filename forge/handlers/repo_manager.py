"""Result normalization for `repo_manager` contractor requests."""

from __future__ import annotations

from forge.schemas import ContractorResult, RepoManagerPayload, RepoPlanStep, RepoRiskItem
from forge.utils.bounded_output import bound_text


guidance = (
    "Act as a bounded repo manager. Inspect the provided repository slice against the goal, "
    "identify the most relevant files, call out concrete risks, propose the smallest safe plan, "
    "and suggest validation steps. Stay read-first by default. Do not edit, execute, or claim authority. "
    "Only mark execution_ready true when the request explicitly asks for execution handoff."
)

response_schema = """{
  "repo_manager": {
    "repo_summary": "short repo-level summary",
    "target_scope": "what part of the repo is in scope",
    "focus_files": ["path/one.py", "path/two.ts"],
    "risks": [
      {
        "file": "src/example.py",
        "issue": "short grounded risk callout",
        "evidence": "specific evidence from the provided context",
        "confidence": "high|medium|low"
      }
    ],
    "plan": [
      {
        "step": "step one",
        "file": "src/example.py",
        "purpose": "why this step exists",
        "expected_effect": "what should change",
        "rollback_note": "how to undo or back out",
        "validation": "how to verify the step"
      }
    ],
    "validations": ["test suggestion", "manual check"],
    "execution_ready": false
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
    raw_repo_manager = parsed.get("repo_manager")
    if not isinstance(raw_repo_manager, dict):
        return None

    repo_summary = bound_text(raw_repo_manager.get("repo_summary"), max_output_chars)
    target_scope = bound_text(raw_repo_manager.get("target_scope"), 320)
    if not repo_summary.strip() or not target_scope.strip():
        return None
    focus_files = [
        bound_text(item, 240)
        for item in list(raw_repo_manager.get("focus_files") or [])
        if str(item).strip()
    ][:12]
    validations = [
        bound_text(item, 240)
        for item in list(raw_repo_manager.get("validations") or [])
        if str(item).strip()
    ][:12]
    risks: list[RepoRiskItem] = []
    for item in list(raw_repo_manager.get("risks") or [])[:20]:
        if not isinstance(item, dict):
            continue
        file_value = bound_text(item.get("file"), 240)
        issue_value = bound_text(item.get("issue"), min(600, max_output_chars))
        evidence_value = bound_text(item.get("evidence"), min(800, max_output_chars))
        confidence_value = bound_text(item.get("confidence"), 32)
        if not file_value.strip() or not issue_value.strip() or not evidence_value.strip() or not confidence_value.strip():
            continue
        risks.append(
            RepoRiskItem(
                file=file_value,
                issue=issue_value,
                evidence=evidence_value,
                confidence=confidence_value,
            )
        )
    plan: list[RepoPlanStep] = []
    for item in list(raw_repo_manager.get("plan") or [])[:12]:
        if not isinstance(item, dict):
            continue
        step_value = bound_text(item.get("step"), 160)
        purpose_value = bound_text(item.get("purpose"), 320)
        expected_effect_value = bound_text(item.get("expected_effect"), 320)
        validation_value = bound_text(item.get("validation"), 240)
        if not step_value.strip() or not purpose_value.strip() or not expected_effect_value.strip() or not validation_value.strip():
            continue
        file_value = bound_text(item.get("file"), 240)
        rollback_value = bound_text(item.get("rollback_note"), 240)
        plan.append(
            RepoPlanStep(
                step=step_value,
                file=file_value or None,
                purpose=purpose_value,
                expected_effect=expected_effect_value,
                rollback_note=rollback_value or None,
                validation=validation_value,
            )
        )
    change_intent = str((context or {}).get("change_intent") or "").strip().lower()
    execution_ready_requested = change_intent in {
        "execution_handoff",
        "handoff_for_execution",
        "patch_ready",
    }
    execution_ready = bool(raw_repo_manager.get("execution_ready")) and execution_ready_requested
    if not focus_files:
        return None
    if not risks:
        return None
    if not plan:
        return None

    return ContractorResult(
        repo_manager=RepoManagerPayload(
            repo_summary=repo_summary,
            target_scope=target_scope,
            focus_files=focus_files,
            risks=risks,
            plan=plan,
            validations=validations,
            execution_ready=execution_ready,
        )
    )
