"""Core Forge contractor runtime."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import requests

from forge.config import ForgeConfig, load_forge_config
from forge.handlers import get_handler
from forge.profiles import build_profile_prompt, default_profile_for_kind, list_profiles, resolve_profile_name
from forge.schemas import (
    ContractorErrorResponse,
    ContractorRequest,
    ContractorSuccessResponse,
    ForgeError,
    ForgeHealthResponse,
    SchemaValidationError,
    TraceEvent,
)
from forge.utils import (
    ForgePreflightError,
    bound_trace_events,
    clamp_output_chars,
    extract_json_object,
    sanitize_context,
)


logger = logging.getLogger("forge")
INVALID_JSON_RETRY_HINT = "\n\nYour last response was invalid JSON. Return ONLY valid JSON."


class ForgeProviderUnavailableError(RuntimeError):
    """Raised when the external Forge model cannot be reached."""


class ForgeModelCaller(Protocol):
    """Callable transport used by Forge to reach an external model."""

    def __call__(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """Return raw text plus a provider trace ID."""


def build_system_prompt(kind: str, *, profile_name: str = "default") -> str:
    """Return the canonical contractor prompt for one handler."""

    handler = get_handler(kind)  # type: ignore[arg-type]
    profile_prompt = build_profile_prompt(profile_name)
    return (
        "You are Forge, a bounded code contractor.\n"
        "Only use the provided task-local files and goal.\n"
        "Do not mention AAIS, Jarvis, Nova, memory, operators, or hidden systems.\n"
        "Do not run code, run tests, apply patches, validate repos, compute scores, or plan long loops.\n"
        f"You are fulfilling kind `{kind}`.\n"
        f"Active contractor profile: `{profile_name}`.\n"
        f"{profile_prompt}\n"
        f"{handler.guidance}\n"
        "Return strict JSON matching exactly this shape:\n"
        f"{handler.response_schema}\n"
        "Return only JSON with no markdown fences."
    )


def build_user_prompt(task_id: str, kind: str, context: dict[str, Any]) -> str:
    """Encode one contractor request for the model."""

    payload = {
        "task_id": task_id,
        "kind": kind,
        "context": context,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


class AnthropicForgeCaller:
    """Small requests-based Anthropic transport for Forge."""

    def __init__(self, config: ForgeConfig) -> None:
        self.config = config

    def __call__(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        if not self.config.provider_configured:
            raise ForgeProviderUnavailableError(
                "Forge contractor unavailable: missing CLAUDE_API_KEY or ANTHROPIC_API_KEY."
            )

        trace_id = str(uuid4())
        last_error: Exception | None = None
        timeout_seconds = max(1.0, self.config.timeout_ms / 1000)
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.anthropic_version,
            "content-type": "application/json",
        }

        for attempt in range(1, self.config.max_retries + 2):
            try:
                response = requests.post(
                    self.config.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
                if response.status_code >= 400:
                    raise ForgeProviderUnavailableError(
                        f"Claude HTTP {response.status_code}: {response.text[:500]}"
                    )
                data = response.json()
                blocks = data.get("content") or []
                text_blocks = [
                    str(block.get("text") or "")
                    for block in blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                text = "".join(text_blocks).strip()
                if not text:
                    raise ForgeProviderUnavailableError(
                        "Claude response missing content[0].text."
                    )
                return text, trace_id
            except (requests.RequestException, ValueError, ForgeProviderUnavailableError) as exc:
                last_error = exc
                logger.error(
                    "[Forge][Claude] trace_id=%s attempt=%s error=%s",
                    trace_id,
                    attempt,
                    exc,
                )
                if attempt > self.config.max_retries:
                    break

        raise ForgeProviderUnavailableError(f"Claude call failed after retries: {last_error}")


class ForgeService:
    """End-to-end Forge contractor handling with bounded preflight and validation."""

    def __init__(
        self,
        config: ForgeConfig | None = None,
        *,
        model_caller: ForgeModelCaller | None = None,
    ) -> None:
        self.config = config or load_forge_config()
        self.storage_root = Path(self.config.storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.trace_root = self.storage_root / "traces"
        self.trace_root.mkdir(parents=True, exist_ok=True)
        self.model_caller = model_caller or AnthropicForgeCaller(self.config)

    def health(self) -> ForgeHealthResponse:
        """Return a health payload for the isolated Forge runtime."""

        return ForgeHealthResponse(
            status="ready",
            service="forge",
            provider_configured=self.config.provider_configured,
            model=self.config.model,
            storage_root=str(self.storage_root),
            available_profiles=list_profiles(),
        )

    def handle_contractor_request(
        self, request_payload: dict[str, Any] | ContractorRequest
    ) -> tuple[ContractorSuccessResponse | ContractorErrorResponse, int, str | None]:
        """Process one contractor request and return a strict response envelope."""

        raw_payload = (
            dict(request_payload or {})
            if isinstance(request_payload, dict)
            else request_payload.model_dump()
        )
        task_id = str(raw_payload.get("task_id") or "").strip() or "unknown_task"
        kind = str(raw_payload.get("kind") or "").strip()
        trace_events = [TraceEvent(event="request_received", data=f"kind={kind or 'unknown'}")]
        trace_id = str(uuid4())

        try:
            payload = (
                request_payload
                if isinstance(request_payload, ContractorRequest)
                else ContractorRequest.model_validate(request_payload)
            )
        except SchemaValidationError as exc:
            response = self._build_error(
                task_id=task_id,
                kind=kind,
                code="invalid_request",
                message=str(exc),
                trace_events=trace_events,
            )
            return response, 400, None

        try:
            safe_context = sanitize_context(payload.context.model_dump())
        except ForgePreflightError as exc:
            response = self._build_error(
                task_id=payload.task_id,
                kind=payload.kind,
                code="invalid_request",
                message=str(exc),
                trace_events=trace_events,
            )
            return response, 400, None

        handler = get_handler(payload.kind)
        max_output_chars = clamp_output_chars(
            safe_context.constraints.get("max_output_chars"),
            self.config.default_output_chars,
        )
        try:
            profile_name = resolve_profile_name(
                safe_context.constraints.get("profile")
                or safe_context.constraints.get("contractor_profile")
                or default_profile_for_kind(payload.kind)
            )
        except ValueError as exc:
            response = self._build_error(
                task_id=payload.task_id,
                kind=payload.kind,
                code="invalid_request",
                message=str(exc),
                trace_events=trace_events,
            )
            return response, 400, None

        system_prompt = build_system_prompt(payload.kind, profile_name=profile_name)
        user_prompt = build_user_prompt(
            payload.task_id,
            payload.kind,
            safe_context.model_dump(exclude_none=True),
        )
        trace_events.append(
            TraceEvent(
                event="preflight_ok",
                data=f"files={len(safe_context.files)} max_output_chars={max_output_chars}",
            )
        )
        trace_events.append(
            TraceEvent(
                event="profile_selected",
                data=profile_name,
            )
        )

        try:
            raw_response, trace_id = self.model_caller(system_prompt, user_prompt)
        except ForgeProviderUnavailableError as exc:
            response = self._build_error(
                task_id=payload.task_id,
                kind=payload.kind,
                code="model_error",
                message=str(exc),
                trace_events=trace_events,
            )
            self._write_trace(
                trace_id,
                task_id=payload.task_id,
                kind=payload.kind,
                context=safe_context.model_dump(exclude_none=True),
                response=response.model_dump(exclude_none=True),
            )
            return response, 503, trace_id

        parsed = extract_json_object(raw_response)
        if parsed is None:
            trace_events.append(TraceEvent(event="invalid_json_retry", data="retrying_once"))
            try:
                retry_response, retry_trace_id = self.model_caller(
                    system_prompt,
                    user_prompt + INVALID_JSON_RETRY_HINT,
                )
            except ForgeProviderUnavailableError as exc:
                response = self._build_error(
                    task_id=payload.task_id,
                    kind=payload.kind,
                    code="model_error",
                    message=str(exc),
                    trace_events=trace_events,
                )
                self._write_trace(
                    trace_id,
                    task_id=payload.task_id,
                    kind=payload.kind,
                    context=safe_context.model_dump(exclude_none=True),
                    response=response.model_dump(exclude_none=True),
                )
                return response, 503, trace_id
            trace_id = retry_trace_id
            parsed = extract_json_object(retry_response)
            if parsed is None:
                response = self._build_error(
                    task_id=payload.task_id,
                    kind=payload.kind,
                    code="invalid_json",
                    message="Forge returned malformed JSON after one retry.",
                    trace_events=trace_events,
                )
                self._write_trace(
                    trace_id,
                    task_id=payload.task_id,
                    kind=payload.kind,
                    context=safe_context.model_dump(exclude_none=True),
                    response=response.model_dump(exclude_none=True),
                )
                return response, 502, trace_id

        normalized_result = handler.normalize_result(
            parsed,
            max_output_chars=max_output_chars,
            context=safe_context.model_dump(exclude_none=True),
        )
        if normalized_result is None:
            response = self._build_error(
                task_id=payload.task_id,
                kind=payload.kind,
                code="contract_violation",
                message=f"Forge returned a payload that does not match `{payload.kind}`.",
                trace_events=trace_events,
            )
            self._write_trace(
                trace_id,
                task_id=payload.task_id,
                kind=payload.kind,
                context=safe_context.model_dump(exclude_none=True),
                response=response.model_dump(exclude_none=True),
            )
            return response, 502, trace_id

        trace_events.append(TraceEvent(event="result_normalized", data=f"kind={payload.kind}"))
        response = ContractorSuccessResponse(
            task_id=payload.task_id,
            kind=payload.kind,
            result=normalized_result,
            trace=self._trace_payload(trace_events),
        )
        self._write_trace(
            trace_id,
            task_id=payload.task_id,
            kind=payload.kind,
            context=safe_context.model_dump(exclude_none=True),
            response=response.model_dump(exclude_none=True),
        )
        return response, 200, trace_id

    def _build_error(
        self,
        *,
        task_id: str,
        kind: str,
        code: str,
        message: str,
        trace_events: list[TraceEvent],
    ) -> ContractorErrorResponse:
        return ContractorErrorResponse(
            task_id=task_id,
            kind=kind,
            error=ForgeError(code=code, message=message),
            trace=self._trace_payload(trace_events),
        )

    def _trace_payload(self, trace_events: list[TraceEvent]) -> list[TraceEvent] | None:
        if not self.config.trace_enabled:
            return None
        return bound_trace_events(trace_events)

    def _write_trace(
        self,
        trace_id: str,
        *,
        task_id: str,
        kind: str,
        context: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        """Persist a small per-call record without raw user code or model output."""

        payload = {
            "trace_id": trace_id,
            "task_id": task_id,
            "kind": kind,
            "recorded_at": datetime.now(UTC).isoformat(),
            "model": self.config.model,
            "context": {
                "file_count": len(context.get("files") or []),
                "files": [item.get("path") for item in context.get("files") or []],
                "constraint_keys": sorted(
                    str(key) for key in (context.get("constraints") or {}).keys()
                ),
            },
            "response": {
                "ok": response.get("ok"),
                "error_code": (
                    (response.get("error") or {}).get("code")
                    if isinstance(response.get("error"), dict)
                    else None
                ),
                "result_keys": (
                    sorted((response.get("result") or {}).keys())
                    if isinstance(response.get("result"), dict)
                    else []
                ),
            },
        }
        target = self.trace_root / f"{trace_id}.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
