"""Flask entrypoint for the isolated ForgeEval evaluator service."""

from __future__ import annotations

from flask import Flask, jsonify, request

from forge_eval.service import ForgeEvalService


app = Flask(__name__)
forge_eval_service = ForgeEvalService()


@app.get("/health")
def health():
    """Basic runtime health for the separate ForgeEval service."""

    return jsonify(forge_eval_service.health().model_dump())


@app.post("/evaluate")
def evaluate():
    """Run one evaluator request."""

    payload = request.get_json(silent=True) or {}
    result, status_code = forge_eval_service.evaluate(payload)
    response = jsonify(result.model_dump(exclude_none=True))
    response.status_code = status_code
    return response
