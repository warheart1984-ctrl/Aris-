from __future__ import annotations

from pathlib import Path
from typing import Any

from evolving_ai.aris.runtime import ArisRuntime

from .profiles import DEFAULT_PROFILE_ID, resolve_profile


DEMO_STRIPPED_COMPONENTS = (
    "forge",
    "forge_eval",
    "evolving_engine",
)

V1_STRIPPED_COMPONENTS = ("evolving_engine",)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class _ArisDemoProfileRuntime(ArisRuntime):
    PROFILE_ID = DEFAULT_PROFILE_ID
    LAW_MODE = "aris-1001-demo-governed"
    ROUTE = ("Jarvis Blueprint", "Operator", "Governance Review", "Outcome")
    STRIPPED_COMPONENTS: tuple[str, ...] = ()
    DEMO_MODE_ACTIVE = False
    REPO_CHANGES_BLOCKED = False
    RISKY_PATHS_REQUIRE_MANUAL_UPGRADE = False

    def _profile(self):
        return resolve_profile(self.PROFILE_ID)

    def _demo_mode_payload(self) -> dict[str, Any]:
        return {
            "active": self.DEMO_MODE_ACTIVE,
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
        payload["demo_mode_active"] = self.DEMO_MODE_ACTIVE
        payload["evolving_engine_active"] = bool(self._evolving_engine_payload().get("active", False))
        return payload

    def status_payload(self, *, include_recent: bool = True) -> dict[str, Any]:
        payload = super().status_payload(include_recent=include_recent)
        profile = self._profile()
        payload["system_name"] = profile.system_name
        payload["service_name"] = profile.service_name
        payload["law_mode"] = self.LAW_MODE
        payload["runtime_profile"] = profile.id
        payload["demo_mode"] = self._demo_mode_payload()
        payload["evolving_engine"] = self._evolving_engine_payload()
        payload["admission_contract"] = self._admission_contract_payload(
            _dict(payload.get("admission_contract"))
        )
        return self._decorate_status_payload(payload)


class ArisDemoRuntime(_ArisDemoProfileRuntime):
    """A demo-safe copy of ARIS with Forge and the evolving engine stripped out."""

    PROFILE_ID = "demo"
    LAW_MODE = "aris-1001-demo-governed"
    ROUTE = ("Jarvis Blueprint", "Operator", "Governance Review", "Outcome")
    STRIPPED_COMPONENTS = DEMO_STRIPPED_COMPONENTS
    DEMO_MODE_ACTIVE = True
    REPO_CHANGES_BLOCKED = True
    RISKY_PATHS_REQUIRE_MANUAL_UPGRADE = True

    def __init__(self, *, repo_root: Path, runtime_root: Path | None = None) -> None:
        super().__init__(repo_root=repo_root, runtime_root=runtime_root)
        self.forge = None
        self.forge_eval = None
        self._startup = self._refresh_startup_state(lockdown_on_failure=True)

    def _collect_startup_blockers(self, *, integrity: dict[str, Any]) -> list[str]:
        blockers = super()._collect_startup_blockers(integrity=integrity)
        ignored_prefixes = (
            "Forge is unavailable.",
            "Forge Eval is unavailable.",
        )
        return [
            blocker
            for blocker in blockers
            if not any(blocker.startswith(prefix) for prefix in ignored_prefixes)
        ]

    def _evolving_engine_payload(self) -> dict[str, Any]:
        return {
            "present": False,
            "active": False,
            "admitted": False,
            "reason": "ARIS Demo is stripped of the evolving engine and its adaptive proposal authority.",
        }

    def _admission_contract_payload(self, base: dict[str, Any]) -> dict[str, Any]:
        del base
        return {
            "component": "evolving-ai",
            "role": "removed_in_demo",
            "authority": "none",
            "admitted": False,
            "reason": "The demo copy excludes the evolving engine and all Forge-driven proposal paths.",
        }

    def _decorate_status_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["forge"] = {
            "connected": False,
            "provider_configured": False,
            "health": {
                "status": "stripped",
                "service": "forge",
                "reason": "Forge is intentionally stripped from ARIS Demo.",
            },
        }
        payload["forge_eval"] = {
            "connected": False,
            "health": {
                "status": "stripped",
                "service": "forge_eval",
                "reason": "Forge Eval is intentionally stripped from ARIS Demo.",
            },
        }
        return payload

    def forge_repo_plan(
        self,
        *,
        goal: str,
        focus_paths: list[str] | None = None,
        operation_mode: str = "repo_manager",
    ) -> dict[str, Any]:
        del goal, focus_paths, operation_mode
        return {
            "ok": False,
            "error": "Forge is stripped from ARIS Demo, so governed repo planning is unavailable in this profile.",
            "demo_mode": {
                "active": True,
                "stripped_components": list(DEMO_STRIPPED_COMPONENTS),
            },
            "route": [
                {"stage": "Jarvis Blueprint", "status": "ready"},
                {"stage": "Operator", "status": "approved"},
                {"stage": "Governance Review", "status": "demo_limited"},
                {"stage": "Outcome", "status": "blocked"},
            ],
        }


class ArisDemoV1Runtime(_ArisDemoProfileRuntime):
    """Desktop demo profile with Forge and Forge Eval available but no evolving engine."""

    PROFILE_ID = "v1"
    LAW_MODE = "aris-1001-forge-governed"
    ROUTE = ("Jarvis Blueprint", "Operator", "Forge", "Forge Eval", "Outcome")
    STRIPPED_COMPONENTS = V1_STRIPPED_COMPONENTS

    def _evolving_engine_payload(self) -> dict[str, Any]:
        return {
            "present": False,
            "active": False,
            "admitted": False,
            "reason": "V1 keeps Forge and Forge Eval active while the evolving engine remains outside the admitted runtime.",
        }

    def _admission_contract_payload(self, base: dict[str, Any]) -> dict[str, Any]:
        payload = dict(base)
        payload.update(
            {
                "role": "Governed Repo Orchestrator",
                "authority": "proposal_only",
                "admitted": True,
                "evolving_engine_active": False,
                "reason": "Forge and Forge Eval are admitted for governed repo work. The evolving engine remains disabled in V1.",
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


class ArisDemoV2Runtime(_ArisDemoProfileRuntime):
    """Desktop demo profile with Forge and the extracted UL runtime admission active."""

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
    "demo": ArisDemoRuntime,
    "v1": ArisDemoV1Runtime,
    "v2": ArisDemoV2Runtime,
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
