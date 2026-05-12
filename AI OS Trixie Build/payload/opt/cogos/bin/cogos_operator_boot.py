#!/usr/bin/env python3
"""Fast operator boot surface for CoGOS v10."""

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Any


ROOT = pathlib.Path("/opt/cogos")
RUN = pathlib.Path("/run")
BOOT_PROFILE = ROOT / "config" / "boot_profile.json"
BOOT_REPORT = ROOT / "memory" / "logs" / "boot_report.json"
DASHBOARD_PID = RUN / "cogos-dashboard.pid"
DAEMON_PID = RUN / "cogos-daemon.pid"
DAEMON_STATE = RUN / "cogos-daemon.json"


def read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def pid_running(path: pathlib.Path) -> bool:
    try:
        pid = path.read_text(encoding="utf-8").strip()
        if not pid:
            return False
        subprocess.run(["kill", "-0", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def line(label: str, value: Any) -> None:
    print(f"{label:22} {value}")


def main() -> int:
    profile = read_json(BOOT_PROFILE, {})
    boot_report = read_json(BOOT_REPORT, {})
    daemon_state = read_json(DAEMON_STATE, {})
    daemon_running = pid_running(DAEMON_PID)
    dashboard_running = pid_running(DASHBOARD_PID)

    print("Project Infi / CoGOS v10 Fast Operator Boot")
    print("=" * 46)
    line("profile", profile.get("profile", "unknown"))
    line("message", profile.get("operator_message", ""))
    line("boot verification", "ok" if boot_report.get("ok") else "pending")
    line("daemon", "running" if daemon_running else "not running")
    line("daemon status", daemon_state.get("status", "unknown"))
    line("dashboard", "running at http://localhost:8080" if dashboard_running else "deferred")
    print()
    print("Next commands")
    print("  cogos-proof                 full governed proof summary")
    print("  cogos-perf                  fast performance/status view")
    print("  cogos-module run trace_analyzer")
    print("  cogos-traits prove")
    print("  cogos-patterns ingest")
    print("  cogos-patterns prove")
    print("  cogos-dashboard-start       start dashboard on demand")
    print("  cogos-dashboard-stop        stop dashboard when laggy")
    print("  cogos-desktop-hint          show desktop recovery hints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
