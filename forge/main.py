"""Flask entrypoint for the isolated Forge contractor service."""

from __future__ import annotations

from flask import Flask, jsonify, request

from forge.service import ForgeService


app = Flask(__name__)
forge_service = ForgeService()


@app.get("/health")
def health():
    """Basic runtime health for the separate Forge service."""

    return jsonify(forge_service.health().model_dump())


@app.get("/forge/health")
def forge_health():
    """Explicit Forge-scoped health alias."""

    return jsonify(forge_service.health().model_dump())


@app.post("/contractor")
def contractor():
    """Run one bounded contractor task against task-local code context."""

    payload = request.get_json(silent=True) or {}
    result, status_code, trace_id = forge_service.handle_contractor_request(payload)
    response = jsonify(result.model_dump(exclude_none=True))
    response.status_code = status_code
    if trace_id:
        response.headers["X-Forge-Trace-Id"] = trace_id
    return response
