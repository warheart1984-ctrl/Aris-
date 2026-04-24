from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class LawApiBridge:
    def __init__(self, service) -> None:
        self.service = service
        self.runtime_law = getattr(getattr(service, "aris", None), "runtime_law", None)

    async def middleware(self, request: Request, call_next):
        if self.runtime_law is None:
            return await call_next(request)
        host_capabilities = request.headers.get("x-aris-host-capabilities", "")
        action = {
            "action_id": request.headers.get("x-request-id", ""),
            "action_type": f"http:{request.method.lower()}",
            "purpose": f"Handle HTTP request for {request.url.path}.",
            "target": request.url.path,
            "session_id": request.query_params.get("session_id", "http"),
            "source": "api",
            "lineage": request.headers.get("x-aris-lineage", ""),
            "claimed_identity": request.headers.get("x-aris-identity", ""),
            "legitimacy_token": request.headers.get("x-aris-legitimacy-token", ""),
            "host_name": request.headers.get("x-aris-host-name", ""),
            "host_version": request.headers.get("x-aris-host-version", ""),
            "host_capabilities": [item.strip() for item in host_capabilities.split(",") if item.strip()],
            "host_class": request.headers.get("x-aris-host-class", "external"),
            "verified": request.headers.get("x-aris-verified", ""),
        }
        preflight = self.runtime_law.preflight_action(
            action,
            actor="api",
            route_name=request.url.path,
            repo_changed=request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"},
            protected_target=False,
        )
        request.state.law_context = preflight.context.payload()
        if not preflight.allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": preflight.reason,
                    "law": preflight.payload(),
                },
            )
        response = await call_next(request)
        self.runtime_law.ledger.record(
            "api_response",
            {
                "path": request.url.path,
                "status_code": response.status_code,
                "context": preflight.context.payload(),
            },
            require_success=True,
        )
        return response
