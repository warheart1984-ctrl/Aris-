"""Schema models for the Forge contractor boundary."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


VALID_KINDS = {"generate_code", "generate_diff", "generate_tests", "analyze", "repo_manager"}
VALID_ERROR_CODES = {"invalid_request", "invalid_json", "model_error", "contract_violation"}


class SchemaValidationError(ValueError):
    """Raised when one schema payload does not match the contract."""


def _dump(value: Any, *, exclude_none: bool = False) -> Any:
    if isinstance(value, SchemaMixin):
        return value.model_dump(exclude_none=exclude_none)
    if isinstance(value, list):
        return [_dump(item, exclude_none=exclude_none) for item in value]
    if isinstance(value, dict):
        dumped = {
            str(key): _dump(item, exclude_none=exclude_none)
            for key, item in value.items()
            if not (exclude_none and item is None)
        }
        return dumped
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


def _validate_kind(value: Any, name: str = "kind") -> str:
    kind = _require_string(value, name)
    if kind not in VALID_KINDS:
        raise SchemaValidationError(f"{name} must be one of: {', '.join(sorted(VALID_KINDS))}")
    return kind


class SchemaMixin:
    """Small compatibility mixin that mirrors the Pydantic calls used in this repo."""

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        return {
            item.name: _dump(getattr(self, item.name), exclude_none=exclude_none)
            for item in fields(self)
            if not (exclude_none and getattr(self, item.name) is None)
        }


@dataclass(slots=True)
class ContractorFileContext(SchemaMixin):
    """One task-local source file sent to Forge."""

    path: str = ""
    content: str = ""
    truncated: bool = False

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorFileContext:
        data = _require_dict(payload, "context.files[]")
        path = str(data.get("path") or "").strip()
        content = str(data.get("content") or "")
        return cls(path=path, content=content, truncated=bool(data.get("truncated")))


@dataclass(slots=True)
class ContractorContext(SchemaMixin):
    """Bounded code-only context for one contractor request."""

    files: list[ContractorFileContext] = field(default_factory=list)
    goal: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    target_scope: str = ""
    focus_files: list[str] = field(default_factory=list)
    excluded_files: list[str] = field(default_factory=list)
    change_intent: str = ""
    max_change_budget: str = ""
    validation_target: str = ""
    operation_mode: str = ""
    max_files_to_inspect: int | None = None
    max_directory_depth: int | None = None
    file_path_allowlist: list[str] = field(default_factory=list)
    explicit_denylist: list[str] = field(default_factory=list)
    no_execution_without_handoff: bool = True

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorContext:
        data = _require_dict(payload, "context")
        raw_files = data.get("files") or []
        if raw_files is None:
            raw_files = []
        if not isinstance(raw_files, list):
            raise SchemaValidationError("context.files must be an array")
        constraints = data.get("constraints") or {}
        if not isinstance(constraints, dict):
            raise SchemaValidationError("context.constraints must be an object")
        focus_files = [str(item) for item in list(data.get("focus_files") or []) if str(item).strip()]
        excluded_files = [str(item) for item in list(data.get("excluded_files") or []) if str(item).strip()]
        file_path_allowlist = [
            str(item) for item in list(data.get("file_path_allowlist") or []) if str(item).strip()
        ]
        explicit_denylist = [
            str(item) for item in list(data.get("explicit_denylist") or []) if str(item).strip()
        ]
        max_files_to_inspect = data.get("max_files_to_inspect")
        if max_files_to_inspect in ("", None):
            max_files_value = None
        else:
            try:
                max_files_value = int(max_files_to_inspect)
            except (TypeError, ValueError) as exc:
                raise SchemaValidationError("context.max_files_to_inspect must be an integer") from exc
        max_directory_depth = data.get("max_directory_depth")
        if max_directory_depth in ("", None):
            max_depth_value = None
        else:
            try:
                max_depth_value = int(max_directory_depth)
            except (TypeError, ValueError) as exc:
                raise SchemaValidationError("context.max_directory_depth must be an integer") from exc
        return cls(
            files=[ContractorFileContext.model_validate(item) for item in raw_files],
            goal=str(data.get("goal") or ""),
            constraints=dict(constraints),
            target_scope=str(data.get("target_scope") or ""),
            focus_files=focus_files,
            excluded_files=excluded_files,
            change_intent=str(data.get("change_intent") or ""),
            max_change_budget=str(data.get("max_change_budget") or ""),
            validation_target=str(data.get("validation_target") or ""),
            operation_mode=str(data.get("operation_mode") or ""),
            max_files_to_inspect=max_files_value,
            max_directory_depth=max_depth_value,
            file_path_allowlist=file_path_allowlist,
            explicit_denylist=explicit_denylist,
            no_execution_without_handoff=bool(data.get("no_execution_without_handoff", True)),
        )


@dataclass(slots=True)
class ContractorRequest(SchemaMixin):
    """Public request contract for `POST /contractor`."""

    task_id: str
    kind: str
    context: ContractorContext = field(default_factory=ContractorContext)

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorRequest:
        data = _require_dict(payload, "request")
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            kind=_validate_kind(data.get("kind")),
            context=ContractorContext.model_validate(data.get("context") or {}),
        )


@dataclass(slots=True)
class GeneratedFile(SchemaMixin):
    """One generated file artifact."""

    path: str
    content: str

    @classmethod
    def model_validate(cls, payload: Any) -> GeneratedFile:
        data = _require_dict(payload, "result.files[]")
        return cls(
            path=_require_string(data.get("path"), "result.files[].path"),
            content=str(data.get("content") or ""),
        )


@dataclass(slots=True)
class UnifiedDiff(SchemaMixin):
    """One generated unified diff artifact."""

    path: str
    unified_diff: str

    @classmethod
    def model_validate(cls, payload: Any) -> UnifiedDiff:
        data = _require_dict(payload, "result.diffs[]")
        return cls(
            path=_require_string(data.get("path"), "result.diffs[].path"),
            unified_diff=str(data.get("unified_diff") or ""),
        )


@dataclass(slots=True)
class AnalysisPayload(SchemaMixin):
    """Structured analysis payload for `analyze` responses."""

    summary: str = ""
    issues: list[str] = field(default_factory=list)
    notes: str = ""
    focus_files: list[str] = field(default_factory=list)
    plan_steps: list[str] = field(default_factory=list)
    validations: list[str] = field(default_factory=list)

    @classmethod
    def model_validate(cls, payload: Any) -> AnalysisPayload:
        data = _require_dict(payload, "result.analysis")
        summary = str(data.get("summary") or "")
        issues = [str(item) for item in list(data.get("issues") or []) if str(item).strip()]
        notes = str(data.get("notes") or "")
        focus_files = [str(item) for item in list(data.get("focus_files") or []) if str(item).strip()]
        plan_steps = [str(item) for item in list(data.get("plan_steps") or []) if str(item).strip()]
        validations = [str(item) for item in list(data.get("validations") or []) if str(item).strip()]
        return cls(
            summary=summary,
            issues=issues,
            notes=notes,
            focus_files=focus_files,
            plan_steps=plan_steps,
            validations=validations,
        )


@dataclass(slots=True)
class RepoRiskItem(SchemaMixin):
    file: str
    issue: str
    evidence: str
    confidence: str

    @classmethod
    def model_validate(cls, payload: Any) -> RepoRiskItem:
        data = _require_dict(payload, "result.repo_manager.risks[]")
        return cls(
            file=_require_string(data.get("file"), "result.repo_manager.risks[].file"),
            issue=_require_string(data.get("issue"), "result.repo_manager.risks[].issue"),
            evidence=_require_string(data.get("evidence"), "result.repo_manager.risks[].evidence"),
            confidence=_require_string(data.get("confidence"), "result.repo_manager.risks[].confidence"),
        )


@dataclass(slots=True)
class RepoPlanStep(SchemaMixin):
    step: str
    file: str | None = None
    purpose: str = ""
    expected_effect: str = ""
    rollback_note: str | None = None
    validation: str = ""

    @classmethod
    def model_validate(cls, payload: Any) -> RepoPlanStep:
        data = _require_dict(payload, "result.repo_manager.plan[]")
        file_value = str(data.get("file") or "").strip() or None
        rollback_value = str(data.get("rollback_note") or "").strip() or None
        return cls(
            step=_require_string(data.get("step"), "result.repo_manager.plan[].step"),
            file=file_value,
            purpose=_require_string(data.get("purpose"), "result.repo_manager.plan[].purpose"),
            expected_effect=_require_string(
                data.get("expected_effect"),
                "result.repo_manager.plan[].expected_effect",
            ),
            rollback_note=rollback_value,
            validation=_require_string(data.get("validation"), "result.repo_manager.plan[].validation"),
        )


@dataclass(slots=True)
class RepoManagerPayload(SchemaMixin):
    repo_summary: str
    target_scope: str
    focus_files: list[str] = field(default_factory=list)
    risks: list[RepoRiskItem] = field(default_factory=list)
    plan: list[RepoPlanStep] = field(default_factory=list)
    validations: list[str] = field(default_factory=list)
    execution_ready: bool = False

    @classmethod
    def model_validate(cls, payload: Any) -> RepoManagerPayload:
        data = _require_dict(payload, "result.repo_manager")
        focus_files = [str(item) for item in list(data.get("focus_files") or []) if str(item).strip()]
        validations = [str(item) for item in list(data.get("validations") or []) if str(item).strip()]
        raw_risks = data.get("risks") or []
        raw_plan = data.get("plan") or []
        if not isinstance(raw_risks, list):
            raise SchemaValidationError("result.repo_manager.risks must be an array")
        if not isinstance(raw_plan, list):
            raise SchemaValidationError("result.repo_manager.plan must be an array")
        return cls(
            repo_summary=_require_string(data.get("repo_summary"), "result.repo_manager.repo_summary"),
            target_scope=_require_string(data.get("target_scope"), "result.repo_manager.target_scope"),
            focus_files=focus_files,
            risks=[RepoRiskItem.model_validate(item) for item in raw_risks],
            plan=[RepoPlanStep.model_validate(item) for item in raw_plan],
            validations=validations,
            execution_ready=bool(data.get("execution_ready")),
        )


@dataclass(slots=True)
class ContractorResult(SchemaMixin):
    """Result body for successful contractor responses."""

    files: list[GeneratedFile] | None = None
    diffs: list[UnifiedDiff] | None = None
    analysis: AnalysisPayload | None = None
    repo_manager: RepoManagerPayload | None = None

    def __post_init__(self) -> None:
        populated = sum(
            1 for value in (self.files, self.diffs, self.analysis, self.repo_manager) if value not in (None, [])
        )
        if populated != 1:
            raise SchemaValidationError("Exactly one of files, diffs, analysis, or repo_manager must be populated.")

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorResult:
        data = _require_dict(payload, "result")
        files = data.get("files")
        diffs = data.get("diffs")
        analysis = data.get("analysis")
        return cls(
            files=[GeneratedFile.model_validate(item) for item in files] if isinstance(files, list) else None,
            diffs=[UnifiedDiff.model_validate(item) for item in diffs] if isinstance(diffs, list) else None,
            analysis=AnalysisPayload.model_validate(analysis) if isinstance(analysis, dict) else None,
            repo_manager=RepoManagerPayload.model_validate(data.get("repo_manager"))
            if isinstance(data.get("repo_manager"), dict)
            else None,
        )


@dataclass(slots=True)
class ForgeError(SchemaMixin):
    """Machine-readable Forge contractor error."""

    code: str
    message: str

    @classmethod
    def model_validate(cls, payload: Any) -> ForgeError:
        data = _require_dict(payload, "error")
        code = _require_string(data.get("code"), "error.code")
        if code not in VALID_ERROR_CODES:
            raise SchemaValidationError(
                f"error.code must be one of: {', '.join(sorted(VALID_ERROR_CODES))}"
            )
        return cls(code=code, message=str(data.get("message") or ""))


@dataclass(slots=True)
class TraceEvent(SchemaMixin):
    """Small optional debug trace event."""

    event: str
    data: str

    @classmethod
    def model_validate(cls, payload: Any) -> TraceEvent:
        data = _require_dict(payload, "trace[]")
        return cls(
            event=_require_string(data.get("event"), "trace[].event"),
            data=str(data.get("data") or ""),
        )


@dataclass(slots=True)
class ContractorSuccessResponse(SchemaMixin):
    """Successful contractor response envelope."""

    task_id: str
    kind: str
    result: ContractorResult
    ok: bool = True
    trace: list[TraceEvent] | None = None

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorSuccessResponse:
        data = _require_dict(payload, "response")
        if data.get("ok") is not True:
            raise SchemaValidationError("response.ok must be true")
        raw_trace = data.get("trace")
        trace = (
            [TraceEvent.model_validate(item) for item in raw_trace]
            if isinstance(raw_trace, list)
            else None
        )
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            kind=_validate_kind(data.get("kind")),
            result=ContractorResult.model_validate(data.get("result") or {}),
            trace=trace,
        )


@dataclass(slots=True)
class ContractorErrorResponse(SchemaMixin):
    """Error contractor response envelope."""

    task_id: str
    kind: str
    error: ForgeError
    ok: bool = False
    trace: list[TraceEvent] | None = None

    @classmethod
    def model_validate(cls, payload: Any) -> ContractorErrorResponse:
        data = _require_dict(payload, "response")
        if data.get("ok") is not False:
            raise SchemaValidationError("response.ok must be false")
        raw_trace = data.get("trace")
        trace = (
            [TraceEvent.model_validate(item) for item in raw_trace]
            if isinstance(raw_trace, list)
            else None
        )
        return cls(
            task_id=_require_string(data.get("task_id"), "task_id"),
            kind=str(data.get("kind") or ""),
            error=ForgeError.model_validate(data.get("error") or {}),
            trace=trace,
        )


@dataclass(slots=True)
class ForgeHealthResponse(SchemaMixin):
    """Lightweight service health payload."""

    status: str
    service: str
    provider_configured: bool
    model: str
    storage_root: str
    available_profiles: list[str] = field(default_factory=list)
