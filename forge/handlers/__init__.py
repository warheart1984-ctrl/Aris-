"""Forge contractor handler registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from forge.handlers import analyze, generate_code, generate_diff, generate_tests, repo_manager
from forge.schemas import ContractorResult


@dataclass(frozen=True)
class HandlerSpec:
    """Descriptor for one contractor capability."""

    kind: str
    guidance: str
    response_schema: str
    normalize_result: Callable[..., ContractorResult | None]


HANDLERS: dict[str, HandlerSpec] = {
    "generate_code": HandlerSpec(
        kind="generate_code",
        guidance=generate_code.guidance,
        response_schema=generate_code.response_schema,
        normalize_result=generate_code.normalize_result,
    ),
    "generate_diff": HandlerSpec(
        kind="generate_diff",
        guidance=generate_diff.guidance,
        response_schema=generate_diff.response_schema,
        normalize_result=generate_diff.normalize_result,
    ),
    "generate_tests": HandlerSpec(
        kind="generate_tests",
        guidance=generate_tests.guidance,
        response_schema=generate_tests.response_schema,
        normalize_result=generate_tests.normalize_result,
    ),
    "analyze": HandlerSpec(
        kind="analyze",
        guidance=analyze.guidance,
        response_schema=analyze.response_schema,
        normalize_result=analyze.normalize_result,
    ),
    "repo_manager": HandlerSpec(
        kind="repo_manager",
        guidance=repo_manager.guidance,
        response_schema=repo_manager.response_schema,
        normalize_result=repo_manager.normalize_result,
    ),
}


def get_handler(kind: str) -> HandlerSpec:
    """Return the registered handler spec for one contractor kind."""

    return HANDLERS[kind]
