from __future__ import annotations

import argparse
from pathlib import Path
import sys

import uvicorn

from .server import _build_service, create_app


def _status_lines(status: dict[str, object]) -> list[str]:
    kill_switch = status.get("kill_switch", {}) if isinstance(status.get("kill_switch"), dict) else {}
    mystic = status.get("mystic", {}) if isinstance(status.get("mystic"), dict) else {}
    mystic_reflection = (
        status.get("mystic_reflection", {}) if isinstance(status.get("mystic_reflection"), dict) else {}
    )
    shield = status.get("shield_of_truth", {}) if isinstance(status.get("shield_of_truth"), dict) else {}
    repo_logbook = status.get("repo_logbook", {}) if isinstance(status.get("repo_logbook"), dict) else {}
    runtime_mode = (
        status.get("runtime_mode", {})
        if isinstance(status.get("runtime_mode"), dict)
        else status.get("demo_mode", {})
        if isinstance(status.get("demo_mode"), dict)
        else {}
    )
    evolving_engine = (
        status.get("evolving_engine", {}) if isinstance(status.get("evolving_engine"), dict) else {}
    )
    blockers = list(status.get("startup_blockers", [])) if isinstance(status.get("startup_blockers"), list) else []
    return [
        f"ARIS V2 startup target: {status.get('repo_target', Path.cwd())}",
        f"Law mode: {status.get('law_mode', 'unknown')}",
        f"1001 active: {status.get('meta_law_1001_active', False)}",
        f"Repo Logbook active: {repo_logbook.get('active', False)}",
        f"Shield of Truth active: {shield.get('active', False)}",
        f"Mystic sustainment: {'active' if mystic.get('active', False) else 'offline'}",
        (
            "Mystic Reflection: merged with Jarvis"
            if mystic_reflection.get("active", False) and mystic_reflection.get("merged_with_jarvis", False)
            else f"Mystic Reflection: {'active' if mystic_reflection.get('active', False) else 'offline'}"
        ),
        f"Profile mode active: {runtime_mode.get('active', False)}",
        f"Evolving engine admitted: {evolving_engine.get('active', False)}",
        "Runtime route: " + " -> ".join(str(item) for item in runtime_mode.get("route", [])),
        f"Kill switch mode: {kill_switch.get('mode', 'unknown')}",
        (
            "Startup blockers: none"
            if not blockers
            else "Startup blockers: " + " | ".join(str(item) for item in blockers)
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the ARIS V2 governed service.")
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Print current ARIS V2 startup state and exit with 0 only when healthy.",
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
            print(f"ARIS V2 integrity reseal failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    status = service.aris_status_payload()
    print("ARIS V2")
    print("Advanced Repo Intelligence Service V2")
    for line in _status_lines(status):
        print(line)
    if args.healthcheck:
        raise SystemExit(0 if service.aris_health_payload().get("ok") else 1)
    if status.get("startup_blockers"):
        print("ARIS V2 is starting in fail-closed lockdown so health, logs, and hall state remain inspectable.")
    uvicorn.run(
        create_app(),
        host=service.config.host,
        port=service.config.port,
        log_level="info",
    )
