"""Core ForgeEval evaluator runtime."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

from forge_eval.evaluators import EVALUATORS, InvalidEvaluationRequest
from forge_eval.sandbox.local_runner import SandboxError
from forge_eval.schemas import (
    EvaluationError,
    EvaluationErrorResponse,
    EvaluationResult,
    EvaluationRequest,
    EvaluationSuccessResponse,
    ForgeEvalHealthResponse,
    SchemaValidationError,
)
from forge_eval.utils.scoring import clamp_score


class ForgeEvalService:
    """Dispatcher for ForgeEval modes."""

    def __init__(self, storage_root: str | Path | None = None) -> None:
        self.storage_root = Path(
            storage_root
            or os.getenv("FORGE_EVAL_STORAGE")
            or (Path.cwd() / ".runtime" / "forge_eval")
        ).expanduser().resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.trace_root = self.storage_root / "history"
        self.trace_root.mkdir(parents=True, exist_ok=True)

    def health(self) -> ForgeEvalHealthResponse:
        return ForgeEvalHealthResponse(
            status="ready",
            service="forge_eval",
            storage_root=str(self.storage_root),
        )

    def evaluate(
        self, request_payload: dict[str, Any] | EvaluationRequest
    ) -> tuple[EvaluationSuccessResponse | EvaluationErrorResponse, int]:
        raw_payload = (
            dict(request_payload or {})
            if isinstance(request_payload, dict)
            else request_payload.model_dump()
        )
        task_id = str(raw_payload.get("task_id") or "").strip() or "unknown_task"
        mode = str(raw_payload.get("mode") or "").strip()

        try:
            payload = (
                request_payload
                if isinstance(request_payload, EvaluationRequest)
                else EvaluationRequest.model_validate(request_payload)
            )
        except SchemaValidationError as exc:
            return (
                EvaluationErrorResponse(
                    task_id=task_id,
                    mode=mode,
                    error=EvaluationError(
                        code="invalid_request",
                        message=str(exc),
                    ),
                ),
                400,
            )

        evaluator = EVALUATORS[payload.mode]
        try:
            result = evaluator(payload)
        except InvalidEvaluationRequest as exc:
            response = EvaluationErrorResponse(
                task_id=payload.task_id,
                mode=payload.mode,
                error=EvaluationError(code="invalid_request", message=str(exc)),
            )
            self._write_record(payload.task_id, payload.mode, response.model_dump(exclude_none=True))
            return response, 400
        except SandboxError as exc:
            response = EvaluationErrorResponse(
                task_id=payload.task_id,
                mode=payload.mode,
                error=EvaluationError(code="sandbox_error", message=str(exc)),
            )
            self._write_record(payload.task_id, payload.mode, response.model_dump(exclude_none=True))
            return response, 503
        except Exception as exc:
            response = EvaluationErrorResponse(
                task_id=payload.task_id,
                mode=payload.mode,
                error=EvaluationError(code="evaluator_failure", message=str(exc)),
            )
            self._write_record(payload.task_id, payload.mode, response.model_dump(exclude_none=True))
            return response, 500

        response = EvaluationSuccessResponse(
            task_id=payload.task_id,
            mode=payload.mode,
            result=EvaluationResult(
                score=clamp_score(result.score),
                details=dict(result.details or {}),
            ),
        )
        self._write_record(payload.task_id, payload.mode, response.model_dump(exclude_none=True))
        return response, 200

    def _write_record(self, task_id: str, mode: str, payload: dict[str, Any]) -> None:
        target = self.trace_root / f"{task_id}-{mode}.json"
        record = {
            "task_id": task_id,
            "mode": mode,
            "recorded_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        target.write_text(json.dumps(record, indent=2), encoding="utf-8")
