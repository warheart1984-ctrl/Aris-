from __future__ import annotations

from pathlib import Path
from typing import Any

from evolving_ai.aris.runtime import ArisRuntime

from .profiles import DEFAULT_PROFILE_ID, resolve_profile


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class _ArisRuntimeProfileRuntime(ArisRuntime):
    PROFILE_ID = DEFAULT_PROFILE_ID
    LAW_MODE = "aris-1001-runtime-governed"
    ROUTE = ("Jarvis Blueprint", "Operator", "Governance Review", "Outcome")
    STRIPPED_COMPONENTS: tuple[str, ...] = ()
    RUNTIME_MODE_ACTIVE = False
    REPO_CHANGES_BLOCKED = False
    RISKY_PATHS_REQUIRE_MANUAL_UPGRADE = False

    def _profile(self):
        return resolve_profile(self.PROFILE_ID)

    def _runtime_mode_payload(self) -> dict[str, Any]:
        return {
            "active": self.RUNTIME_MODE_ACTIVE,
            "stripped_components": list(self.STRIPPED_COMPONENTS),
            "repo_changes_blocked": self.REPO_CHANGES_BLOCKED,
            "risky_paths_require_manual_upgrade": self.RISKY_PATHS_REQUIRE_MANUAL_UPGRADE,
            "route": list(self.ROUTE),
        }

    def _evolving_engine_payload(self) -> dict[str, Any]:
        return {
            "present": False,
            "active": False,
            "admitted": False,
            "reason": "The evolving engine is not admitted in this profile.",
        }

    def _admission_contract_payload(self, base: dict[str, Any]) -> dict[str, Any]:
        return dict(base)

    def _decorate_status_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def health_payload(self) -> dict[str, Any]:
        payload = super().health_payload()
        payload["system_name"] = self._profile().system_name
        payload["law_mode"] = self.LAW_MODE
        payload["forge_connected"] = self.forge is not None
        payload["forge_eval_connected"] = self.forge_eval is not None
        payload["runtime_mode_active"] = self.RUNTIME_MODE_ACTIVE
        payload["demo_mode_active"] = self.RUNTIME_MODE_ACTIVE
        payload["evolving_engine_active"] = bool(self._evolving_engine_payload().get("active", False))
        return payload

    def status_payload(self, *, include_recent: bool = True) -> dict[str, Any]:
        payload = super().status_payload(include_recent=include_recent)
        profile = self._profile()
        payload["system_name"] = profile.system_name
        payload["service_name"] = profile.service_name
        payload["law_mode"] = self.LAW_MODE
        payload["runtime_profile"] = profile.id
        mode_payload = self._runtime_mode_payload()
        payload["runtime_mode"] = mode_payload
        payload["demo_mode"] = mode_payload
        payload["evolving_engine"] = self._evolving_engine_payload()
        payload["admission_contract"] = self._admission_contract_payload(
            _dict(payload.get("admission_contract"))
        )
        return self._decorate_status_payload(payload)


class ArisV2Runtime(_ArisRuntimeProfileRuntime):
    """Desktop V2 profile with Forge and the extracted UL runtime admission active."""

    PROFILE_ID = "v2"
    LAW_MODE = "aris-1001-evolving-runtime"
    ROUTE = ("Jarvis Blueprint", "Operator", "Forge", "Forge Eval", "UL Runtime", "Outcome")

    def _evolving_engine_payload(self) -> dict[str, Any]:
        return {
            "present": True,
            "active": True,
            "admitted": True,
            "binding_layer": "Universal Adapter Protocol",
            "identity_source": "UL",
            "reason": "V2 admits the evolving engine through the extracted UL runtime while keeping authority proposal-bound under law.",
        }

    def _admission_contract_payload(self, base: dict[str, Any]) -> dict[str, Any]:
        payload = dict(base)
        payload.update(
            {
                "role": "Governed Adaptive Engine",
                "authority": "proposal_only",
                "admitted": True,
                "binding_layer": "Universal Adapter Protocol",
                "identity_source": "UL",
                "reason": "Forge, Forge Eval, and the evolving engine are admitted through the extracted UL runtime.",
            }
        )
        return payload

    def forge_repo_plan(
        self,
        *,
        goal: str,
        focus_paths: list[str] | None = None,
        operation_mode: str = "repo_manager",
    ) -> dict[str, Any]:
        payload = super().forge_repo_plan(
            goal=goal,
            focus_paths=focus_paths,
            operation_mode=operation_mode,
        )
        payload["runtime_profile"] = self.PROFILE_ID
        payload["evolving_engine"] = self._evolving_engine_payload()
        return payload


_RUNTIME_CLASSES = {
    "v2": ArisV2Runtime,
}


def runtime_class_for_profile(profile_id: str | None) -> type[ArisRuntime]:
    normalized = resolve_profile(profile_id).id
    return _RUNTIME_CLASSES[normalized]


def build_runtime_for_profile(
    *,
    profile_id: str | None,
    repo_root: Path,
    runtime_root: Path | None = None,
) -> ArisRuntime:
    runtime_class = runtime_class_for_profile(profile_id)
    return runtime_class(repo_root=repo_root, runtime_root=runtime_root)
