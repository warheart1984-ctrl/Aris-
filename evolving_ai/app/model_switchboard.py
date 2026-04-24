from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .attachments import Attachment
from .config import AppConfig


AUTO_MODE = "auto"
MANUAL_MODE = "manual"

SYSTEM_GENERAL = "general"
SYSTEM_CODING = "coding"
SYSTEM_LIGHT_CODING = "light_coding"

DEFAULT_GENERAL_MODEL = "gemma3:12b"
DEFAULT_CODING_MODEL = "devstral"
DEFAULT_LIGHT_CODING_MODEL = "qwen2.5-coder:7b"

VALID_MODES = frozenset({AUTO_MODE, MANUAL_MODE})
VALID_SYSTEM_IDS = frozenset({SYSTEM_GENERAL, SYSTEM_CODING, SYSTEM_LIGHT_CODING})

_BUILD_TERMS = frozenset(
    {
        "build",
        "implement",
        "write",
        "edit",
        "patch",
        "apply",
        "refactor",
        "fix",
        "change",
        "mutation",
        "task",
        "run",
        "execute",
        "command",
        "worker",
    }
)

_INSPECT_TERMS = frozenset(
    {
        "inspect",
        "review",
        "read",
        "trace",
        "search",
        "symbol",
        "repo",
        "boundary",
        "approval",
        "debug",
        "seam",
        "bug",
        "test",
        "code",
    }
)

_GENERAL_TERMS = frozenset(
    {
        "summarize",
        "explain",
        "strategy",
        "brainstorm",
        "document",
        "message",
        "writeup",
        "compare",
        "plan",
        "overview",
    }
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _word_hits(text: str, terms: frozenset[str]) -> int:
    lowered = str(text or "").lower()
    return sum(1 for term in terms if term in lowered)


@dataclass(frozen=True, slots=True)
class ModelSystemProfile:
    id: str
    label: str
    model: str
    description: str

    def payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "model": self.model,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ModelRouteDecision:
    system_id: str
    model: str
    label: str
    selection_mode: str
    reason: str

    def payload(self) -> dict[str, str]:
        return {
            "system_id": self.system_id,
            "model": self.model,
            "label": self.label,
            "selection_mode": self.selection_mode,
            "reason": self.reason,
        }


def build_model_system_profiles(
    *,
    general_model: str | None = None,
    coding_model: str | None = None,
    light_coding_model: str | None = None,
) -> tuple[ModelSystemProfile, ...]:
    return (
        ModelSystemProfile(
            id=SYSTEM_GENERAL,
            label="General",
            model=_normalize_text(general_model or "") or DEFAULT_GENERAL_MODEL,
            description="General reasoning, operator guidance, and vision-safe response routing.",
        ),
        ModelSystemProfile(
            id=SYSTEM_CODING,
            label="Coding",
            model=_normalize_text(coding_model or "") or DEFAULT_CODING_MODEL,
            description="Heavy coding, build, agent, and mutation-ready repo work.",
        ),
        ModelSystemProfile(
            id=SYSTEM_LIGHT_CODING,
            label="Light Coding",
            model=_normalize_text(light_coding_model or "") or DEFAULT_LIGHT_CODING_MODEL,
            description="Fast repo inspection, code reading, and lighter coding loops.",
        ),
    )


def build_model_router_payload(
    *,
    mode: str = AUTO_MODE,
    pinned_system: str | None = None,
    general_model: str | None = None,
    coding_model: str | None = None,
    light_coding_model: str | None = None,
) -> dict[str, Any]:
    profiles = {
        profile.id: profile
        for profile in build_model_system_profiles(
            general_model=general_model,
            coding_model=coding_model,
            light_coding_model=light_coding_model,
        )
    }
    normalized_mode = str(mode or AUTO_MODE).strip().lower()
    if normalized_mode not in VALID_MODES:
        normalized_mode = AUTO_MODE
    normalized_pinned = str(pinned_system or "").strip().lower()
    if normalized_pinned not in VALID_SYSTEM_IDS or normalized_mode != MANUAL_MODE:
        normalized_pinned = ""
    pinned_profile = profiles.get(normalized_pinned)
    return {
        "active": True,
        "mode": normalized_mode,
        "pinned_system": normalized_pinned or None,
        "pinned_model": pinned_profile.model if pinned_profile is not None else None,
        "systems": [profile.payload() for profile in profiles.values()],
    }


class ModelSwitchboard:
    """Three-system model router with auto switching and manual pinning."""

    def __init__(self, config: AppConfig, *, state_path: Path) -> None:
        self.config = config
        self.state_path = state_path.resolve()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles = {
            profile.id: profile
            for profile in build_model_system_profiles(
                general_model=config.general_model,
                coding_model=config.coding_model,
                light_coding_model=config.light_coding_model,
            )
        }
        self._state = self._load_state()

    def _default_state(self) -> dict[str, str]:
        mode = AUTO_MODE if self.config.model_switch_default_mode not in VALID_MODES else self.config.model_switch_default_mode
        pinned = self.config.model_switch_pinned_system if self.config.model_switch_pinned_system in VALID_SYSTEM_IDS else ""
        if mode != MANUAL_MODE:
            pinned = ""
        return {"mode": mode, "pinned_system": pinned}

    def _load_state(self) -> dict[str, str]:
        state = self._default_state()
        if not self.state_path.exists():
            self._write_state(state)
            return state
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._write_state(state)
            return state
        mode = str(raw.get("mode", state["mode"])).strip().lower()
        pinned = str(raw.get("pinned_system", state["pinned_system"])).strip().lower()
        if mode not in VALID_MODES:
            mode = state["mode"]
        if pinned not in VALID_SYSTEM_IDS:
            pinned = ""
        if mode != MANUAL_MODE:
            pinned = ""
        loaded = {"mode": mode, "pinned_system": pinned}
        self._write_state(loaded)
        return loaded

    def _write_state(self, state: dict[str, str]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def set_mode(self, *, mode: str, pinned_system: str | None = None) -> dict[str, Any]:
        normalized_mode = str(mode or "").strip().lower()
        normalized_system = str(pinned_system or "").strip().lower()
        if normalized_mode not in VALID_MODES:
            raise ValueError("Model switch mode must be 'auto' or 'manual'.")
        if normalized_mode == MANUAL_MODE and normalized_system not in VALID_SYSTEM_IDS:
            raise ValueError("Manual mode requires one of: general, coding, light_coding.")
        next_state = {
            "mode": normalized_mode,
            "pinned_system": normalized_system if normalized_mode == MANUAL_MODE else "",
        }
        self._state = next_state
        self._write_state(next_state)
        return self.status_payload()

    def status_payload(self) -> dict[str, Any]:
        return build_model_router_payload(
            mode=self._state["mode"],
            pinned_system=self._state["pinned_system"],
            general_model=self.profiles[SYSTEM_GENERAL].model,
            coding_model=self.profiles[SYSTEM_CODING].model,
            light_coding_model=self.profiles[SYSTEM_LIGHT_CODING].model,
        )

    def choose(
        self,
        *,
        prompt: str,
        fast_mode: bool,
        mode: str,
        attachments: list[Attachment],
    ) -> ModelRouteDecision:
        if self._state["mode"] == MANUAL_MODE and self._state["pinned_system"] in self.profiles:
            profile = self.profiles[self._state["pinned_system"]]
            return ModelRouteDecision(
                system_id=profile.id,
                model=profile.model,
                label=profile.label,
                selection_mode=MANUAL_MODE,
                reason=f"Manually pinned to {profile.label}.",
            )

        lowered_mode = str(mode or "").strip().lower()
        has_image = any(attachment.is_image for attachment in attachments)
        build_score = _word_hits(prompt, _BUILD_TERMS)
        inspect_score = _word_hits(prompt, _INSPECT_TERMS)
        general_score = _word_hits(prompt, _GENERAL_TERMS)

        if has_image:
            profile = self.profiles[SYSTEM_GENERAL]
            return ModelRouteDecision(
                system_id=profile.id,
                model=profile.model,
                label=profile.label,
                selection_mode=AUTO_MODE,
                reason="Auto-selected general system because image attachments are present.",
            )
        if lowered_mode == "agent":
            profile = self.profiles[SYSTEM_CODING]
            return ModelRouteDecision(
                system_id=profile.id,
                model=profile.model,
                label=profile.label,
                selection_mode=AUTO_MODE,
                reason="Auto-selected coding system because agent mode needs heavier repo execution planning.",
            )
        if build_score > 0 and build_score >= max(inspect_score, general_score):
            profile = self.profiles[SYSTEM_CODING]
            return ModelRouteDecision(
                system_id=profile.id,
                model=profile.model,
                label=profile.label,
                selection_mode=AUTO_MODE,
                reason="Auto-selected coding system because the request looks like build/edit/execute work.",
            )
        if fast_mode or inspect_score > 0:
            profile = self.profiles[SYSTEM_LIGHT_CODING]
            return ModelRouteDecision(
                system_id=profile.id,
                model=profile.model,
                label=profile.label,
                selection_mode=AUTO_MODE,
                reason="Auto-selected light coding system for fast inspection and lighter code reasoning.",
            )
        profile = self.profiles[SYSTEM_GENERAL]
        return ModelRouteDecision(
            system_id=profile.id,
            model=profile.model,
            label=profile.label,
            selection_mode=AUTO_MODE,
            reason=(
                "Auto-selected general system for broader reasoning and operator-facing responses."
                if general_score >= 0
                else "Auto-selected general system."
            ),
        )
