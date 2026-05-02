from __future__ import annotations

import argparse
from pathlib import Path
import sys

import uvicorn

from evolving_ai.app.server import _build_service, create_app


def _status_lines(status: dict[str, object]) -> list[str]:
    kill_switch = status.get("kill_switch", {}) if isinstance(status.get("kill_switch"), dict) else {}
    mystic = status.get("mystic", {}) if isinstance(status.get("mystic"), dict) else {}
    mystic_reflection = (
        status.get("mystic_reflection", {}) if isinstance(status.get("mystic_reflection"), dict) else {}
    )
    shield = status.get("shield_of_truth", {}) if isinstance(status.get("shield_of_truth"), dict) else {}
    repo_logbook = status.get("repo_logbook", {}) if isinstance(status.get("repo_logbook"), dict) else {}
    forge = status.get("forge", {}) if isinstance(status.get("forge"), dict) else {}
    forge_eval = status.get("forge_eval", {}) if isinstance(status.get("forge_eval"), dict) else {}
    discard = status.get("hall_of_discard", {}) if isinstance(status.get("hall_of_discard"), dict) else {}
    shame = status.get("hall_of_shame", {}) if isinstance(status.get("hall_of_shame"), dict) else {}
    fame = status.get("hall_of_fame", {}) if isinstance(status.get("hall_of_fame"), dict) else {}
    doc_channel = status.get("doc_channel", {}) if isinstance(status.get("doc_channel"), dict) else {}
    model_router = status.get("model_router", {}) if isinstance(status.get("model_router"), dict) else {}
    execution_backend = (
        status.get("execution_backend", {}) if isinstance(status.get("execution_backend"), dict) else {}
    )
    shell_execution = (
        status.get("shell_execution", {}) if isinstance(status.get("shell_execution"), dict) else {}
    )
    blockers = list(status.get("startup_blockers", [])) if isinstance(status.get("startup_blockers"), list) else []
    model_systems = [
        f"{str(item.get('label', item.get('id', 'system'))).strip()}: {str(item.get('model', 'unknown')).strip()}"
        for item in list(model_router.get("systems", []))
        if isinstance(item, dict)
    ]
    return [
        f"ARIS startup target: {status.get('repo_target', Path.cwd())}",
        f"Law mode: {status.get('law_mode', 'unknown')}",
        f"1001 active: {status.get('meta_law_1001_active', False)}",
        (
            f"Doc channel: {doc_channel.get('namespace', 'unbound')}"
            if doc_channel.get("active")
            else "Doc channel: inactive"
        ),
        (
            f"Model router: {model_router.get('mode', 'unknown')}"
            + (
                f" ({str(model_router.get('pinned_system', '')).replace('_', ' ')})"
                if model_router.get("pinned_system")
                else ""
            )
        ),
        (
            "Model systems: " + " | ".join(model_systems)
            if model_systems
            else "Model systems: unavailable"
        ),
        f"Repo Logbook active: {repo_logbook.get('active', False)}",
        f"Shield of Truth active: {shield.get('active', False)}",
        f"Mystic sustainment: {'active' if mystic.get('active', False) else 'offline'}",
        (
            "Mystic Reflection: merged with Jarvis"
            if mystic_reflection.get("active", False) and mystic_reflection.get("merged_with_jarvis", False)
            else f"Mystic Reflection: {'active' if mystic_reflection.get('active', False) else 'offline'}"
        ),
        f"Forge connected: {forge.get('connected', False)}",
        f"Forge Eval connected: {forge_eval.get('connected', False)}",
        f"Hall of Discard active: {discard.get('active', False)}",
        f"Hall of Shame active: {shame.get('active', False)}",
        f"Hall of Fame active: {fame.get('active', False)}",
        (
            "Execution backend: "
            f"{execution_backend.get('active_backend', 'unknown')}"
            f" (requested: {execution_backend.get('requested_backend', 'unknown')})"
        ),
        (
            "Shell execution: disabled"
            if not shell_execution.get("enabled", False)
            else (
                "Shell execution: degraded"
                if shell_execution.get("degraded", False)
                else "Shell execution: ready"
            )
        ),
        (
            f"Execution detail: {shell_execution.get('detail', '')}"
            if shell_execution.get("detail")
            else "Execution detail: none"
        ),
        f"Kill switch mode: {kill_switch.get('mode', 'unknown')}",
        (
            "Startup blockers: none"
            if not blockers
            else "Startup blockers: " + " | ".join(str(item) for item in blockers)
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the ARIS governed service.")
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Print current ARIS startup state and exit with 0 only when healthy.",
    )
    parser.add_argument(
        "--reseal-integrity",
        action="store_true",
        help="Explicitly reseal protected-component integrity before startup.",
    )
    args = parser.parse_args()

    _build_service.cache_clear()
    service = _build_service()
    if args.reseal_integrity:
        try:
            service.aris.reset_kill_switch(
                reason="explicit CLI integrity reseal",
                actor="admin",
                reseal_integrity=True,
            )
        except Exception as exc:
            print(f"ARIS integrity reseal failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    status = service.aris_status_payload()
    print("ARIS")
    print("Advanced Repo Intelligence Service")
    for line in _status_lines(status):
        print(line)
    if args.healthcheck:
        raise SystemExit(0 if service.aris.health_payload().get("ok") else 1)
    if status.get("startup_blockers"):
        print("ARIS is starting in fail-closed lockdown so health, logs, and Hall of Discard remain inspectable.")
    uvicorn.run(
        create_app(),
        host=service.config.host,
        port=service.config.port,
        log_level="info",
    )
