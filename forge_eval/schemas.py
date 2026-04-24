"""Schema models for the ForgeEval evaluator boundary."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


VALID_MODES = {"io_tests", "llm_rubric", "repo_patch"}
VALID_ERROR_CODES = {"invalid_request", "evaluator_failure", "sandbox_error"}


class SchemaValidationError(ValueError):
    """Raised when one evaluator payload does not match the contract."""


def _dump(value: Any, *, exclude_none: bool = False) -> Any:
    if isinstance(value, SchemaMixin):
        return value.model_dump(exclude_none=exclude_none)
    if isinstance(value, list):
        return [_dump(item, exclude_none=exclude_none) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _dump(item, exclude_none=exclude_none)
            for key, item in value.items()
            if not (exclude_none and item is None)
        }
    return value


def _require_dict(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"{name} must be an object")
    return dict(payload)


def _require_string(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SchemaValidationError(f"{name} is required")
    return text


def _validate_mode(value: Any, name: str = "mode") -> str:
    mode = _require_string(value, name)
    if mode not in VALID_MODES:
        raise SchemaValidationError(f"{name} must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


class SchemaMixin:
    """Small compatibility mixin that mirrors the Pydantic calls used in this repo."""

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        return {
            item.name: _dump(getattr(self, item.name), exclude_none=exclude_none)
            for item in fields(self)
            if not (exclude_none and getattr(self, item.name) is None)
        }


@dataclass(slots=True)
class EvaluationPayload(SchemaMixin):
    """Inbound evaluator payload."""

    program: str | None = None
    patch: str | None = None
    repo: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationPayload:
        data = _require_dict(payload, "payload")
        config = data.get("config") or {}
        if not isinstance(config, dict):
            raise SchemaValidationError("payload.config must be an object")
        return cls(
            program=str(data.get("program")) if data.get("program") is not None else None,
            patch=str(data.get("patch")) if data.get("patch") is not None else None,
            repo=str(data.get("repo")) if data.get("repo") is not None else None,
            config=dict(config),
        )


@dataclass(slots=True)
class EvaluationRequest(SchemaMixin):
    """Public request contract for `POST /evaluate`."""

    task_id: str
    mode: str
    payload: EvaluationPayload = field(default_factory=EvaluationPayload)

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationRequest:
        data = _require_dict(payload, "request")
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            mode=_validate_mode(data.get("mode")),
            payload=EvaluationPayload.model_validate(data.get("payload") or {}),
        )


@dataclass(slots=True)
class EvaluationResult(SchemaMixin):
    """Successful evaluator result."""

    score: float
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationResult:
        data = _require_dict(payload, "result")
        try:
            score = float(data.get("score", 0.0))
        except (TypeError, ValueError) as exc:
            raise SchemaValidationError("result.score must be numeric") from exc
        details = data.get("details") or {}
        if not isinstance(details, dict):
            raise SchemaValidationError("result.details must be an object")
        return cls(score=score, details=dict(details))


@dataclass(slots=True)
class EvaluationError(SchemaMixin):
    """Machine-readable evaluator error."""

    code: str
    message: str

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationError:
        data = _require_dict(payload, "error")
        code = _require_string(data.get("code"), "error.code")
        if code not in VALID_ERROR_CODES:
            raise SchemaValidationError(
                f"error.code must be one of: {', '.join(sorted(VALID_ERROR_CODES))}"
            )
        return cls(code=code, message=str(data.get("message") or ""))


@dataclass(slots=True)
class EvaluationSuccessResponse(SchemaMixin):
    """Successful evaluation envelope."""

    task_id: str
    mode: str
    result: EvaluationResult
    ok: bool = True

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationSuccessResponse:
        data = _require_dict(payload, "response")
        if data.get("ok") is not True:
            raise SchemaValidationError("response.ok must be true")
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            mode=_validate_mode(data.get("mode")),
            result=EvaluationResult.model_validate(data.get("result") or {}),
        )


@dataclass(slots=True)
class EvaluationErrorResponse(SchemaMixin):
    """Failed evaluation envelope."""

    task_id: str
    mode: str
    error: EvaluationError
    ok: bool = False

    @classmethod
    def model_validate(cls, payload: Any) -> EvaluationErrorResponse:
        data = _require_dict(payload, "response")
        if data.get("ok") is not False:
            raise SchemaValidationError("response.ok must be false")
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            mode=str(data.get("mode") or ""),
            error=EvaluationError.model_validate(data.get("error") or {}),
        )


@dataclass(slots=True)
class ForgeEvalHealthResponse(SchemaMixin):
    """Health payload for the evaluator service."""

    status: str
    service: str
    storage_root: str
