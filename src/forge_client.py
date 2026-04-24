from __future__ import annotations

from typing import Any

from .law_decorators import law_wrapped
from .runtime_law import RuntimeLaw


class LawBoundForgeClient:
    def __init__(self, inner: Any, runtime_law: RuntimeLaw) -> None:
        self.inner = inner
        self.runtime_law = runtime_law

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @law_wrapped(actor="forge", route_name="forge_client")
    def handle_contractor_request(self, request_payload: dict[str, Any]) -> tuple[Any, int, str | None]:
        payload = dict(request_payload or {})
        context = payload.setdefault("context", {})
        context.setdefault("law_disposition", "bounded")
        context.setdefault("lineage", payload.get("task_id", "forge-task"))
        if context.get("change_intent") in {"mutation", "write", "apply"}:
            raise RuntimeError("Forge mutation-capable contracts require mutation broker admission.")
        return self.inner.handle_contractor_request(payload)
