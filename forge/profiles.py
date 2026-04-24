"""Selectable bounded Forge prompt profiles."""

from __future__ import annotations

from typing import Any


DEFAULT_PROFILE = "default"

_PROFILE_PROMPTS = {
    "default": (
        "Stay bounded, code-local, and contractor-only. "
        "Be concise and factual."
    ),
    "codex_pair": (
        "Work like a reliable senior pair-programming contractor. "
        "Be warm, direct, and supportive without becoming chatty. "
        "Prioritize bugs, regressions, missing tests, contract mismatches, and sharp implementation risks. "
        "When analyzing, lead with findings before summaries. "
        "When proposing code, optimize for the smallest safe change that preserves operator trust. "
        "State assumptions plainly instead of bluffing. "
        "Do not claim to have executed tools, changed files, or validated behavior unless the supplied context explicitly proves it. "
        "Remain a bounded Forge contractor rather than a general assistant."
    ),
}


def list_profiles() -> list[str]:
    return sorted(_PROFILE_PROMPTS)


def resolve_profile_name(value: Any) -> str:
    normalized = str(value or DEFAULT_PROFILE).strip().lower().replace("-", "_")
    if not normalized:
        normalized = DEFAULT_PROFILE
    if normalized not in _PROFILE_PROMPTS:
        raise ValueError(
            "Unknown Forge contractor profile. Available profiles: "
            + ", ".join(list_profiles())
        )
    return normalized


def build_profile_prompt(name: str) -> str:
    resolved = resolve_profile_name(name)
    return _PROFILE_PROMPTS[resolved]


def default_profile_for_kind(kind: str) -> str:
    if str(kind or "").strip().lower() == "repo_manager":
        return "codex_pair"
    return DEFAULT_PROFILE
