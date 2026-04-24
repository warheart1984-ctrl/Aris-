from __future__ import annotations

from typing import Any

from .law_decorators import law_wrapped
from .runtime_law import RuntimeLaw


class LawBoundForgeEvalClient:
    def __init__(self, inner: Any, runtime_law: RuntimeLaw) -> None:
        self.inner = inner
        self.runtime_law = runtime_law

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @law_wrapped(actor="forge_eval", route_name="forge_eval_client")
    def evaluate(self, request_payload: dict[str, Any]) -> tuple[Any, int]:
        payload = dict(request_payload or {})
        metadata = payload.setdefault("payload", {})
        if payload.get("mode") == "repo_patch":
            patch = str(metadata.get("patch") or "")
            config = metadata.get("config") or {}
            expected_files = list(config.get("expected_files") or [])
            if not patch or not expected_files or not str(payload.get("task_id") or "").strip():
                raise RuntimeError("Forge Eval requires task lineage, target scope, and diff presence.")
        return self.inner.evaluate(payload)
