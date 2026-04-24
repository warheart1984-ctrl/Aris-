from __future__ import annotations

from typing import Any

from .runtime_law import LawPreflightResult, RuntimeLaw


class JarvisOperator:
    def __init__(self, runtime_law: RuntimeLaw) -> None:
        self.runtime_law = runtime_law

    def preflight(
        self,
        *,
        action: dict[str, Any],
        actor: str,
        route_name: str,
        repo_changed: bool,
        protected_target: bool,
    ) -> LawPreflightResult:
        return self.runtime_law.preflight_action(
            action,
            actor=actor,
            route_name=route_name,
            repo_changed=repo_changed,
            protected_target=protected_target,
        )
