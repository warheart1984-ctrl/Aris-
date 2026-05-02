from __future__ import annotations

from typing import Any

from forge_eval.schemas import EvaluationResult, EvaluationSuccessResponse

from .doc_channel import evaluate_program_against_doc_channel
from .law_decorators import law_wrapped
from .runtime_law import RuntimeLaw


class LawBoundForgeEvalClient:
    def __init__(self, inner: Any, runtime_law: RuntimeLaw) -> None:
        self.inner = inner
        self.runtime_law = runtime_law

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @law_wrapped(actor="forge_eval", route_name="forge_eval_client")
    def evaluate(self, request_payload: dict[str, Any]) -> tuple[Any, int]:
        payload = dict(request_payload or {})
        metadata = payload.setdefault("payload", {})
        config = metadata.setdefault("config", {})
        if self.runtime_law.doc_channel is not None:
            for key, value in self.runtime_law.doc_channel.evaluation_config_payload().items():
                config.setdefault(key, value)
        if payload.get("mode") == "repo_patch":
            patch = str(metadata.get("patch") or "")
            expected_files = list(config.get("expected_files") or [])
            if not patch or not expected_files or not str(payload.get("task_id") or "").strip():
                raise RuntimeError("Forge Eval requires task lineage, target scope, and diff presence.")
        response, status_code = self.inner.evaluate(payload)
        if status_code != 200:
            return response, status_code
        program = str(metadata.get("program") or "").strip()
        if not program or self.runtime_law.doc_channel is None:
            return response, status_code
        violations = evaluate_program_against_doc_channel(program, self.runtime_law.doc_channel)
        if not violations:
            return response, status_code
        raw = response.model_dump(exclude_none=True)
        result = dict(raw.get("result") or {})
        details = dict(result.get("details") or {})
        checks = list(details.get("checks") or [])
        criteria = list(details.get("criteria") or [])
        details["doc_channel"] = {
            "namespace": self.runtime_law.doc_channel.namespace,
            "version": self.runtime_law.doc_channel.version,
            "goal": self.runtime_law.doc_channel.goal,
        }
        details["violations"] = list(violations)
        reason = f"{len(violations)} doc channel violation(s) detected."
        checks.append({"label": "doc_channel_laws", "passed": False, "reason": reason})
        criteria.append({"label": "doc_channel_laws", "score": 0.0, "reason": reason})
        details["checks"] = checks
        details["criteria"] = criteria
        hardened = EvaluationSuccessResponse(
            task_id=str(raw.get("task_id") or payload.get("task_id") or ""),
            mode=str(raw.get("mode") or payload.get("mode") or ""),
            result=EvaluationResult(
                score=min(float(result.get("score", 0.0)), 0.1),
                details=details,
            ),
        )
        return hardened, 200
