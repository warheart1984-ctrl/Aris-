"""
phase1_panels.py — Operator Dashboard, Governance Timeline, LawPulse data layer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from governance_invariant_engine import cogos_root
from user_profiles import UserProfileManager


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _read_jsonl(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def _pid_running(path: Path) -> bool:
    try:
        pid = path.read_text(encoding="utf-8").strip()
        return bool(pid) and Path(f"/proc/{pid}").exists()
    except OSError:
        return False


def operator_dashboard() -> Dict[str, Any]:
    root = cogos_root()
    run = Path("/run")
    profiles = UserProfileManager()
    paused = (root / "memory" / "operator" / "PAUSED").exists()
    return {
        "daemon_running": _pid_running(run / "cogos-daemon.pid"),
        "hal_running": _pid_running(run / "cogos-hal.pid"),
        "dashboard_running": _pid_running(run / "cogos-dashboard.pid"),
        "paused": paused,
        "active_profile": profiles.active_id,
        "profiles": profiles.list_profiles(),
        "mode_hint": profiles.get_active().mode_default,
        "boot_report_ok": _read_json(root / "memory" / "logs" / "boot_report.json", {}).get("ok"),
        "pid1_ok": _read_json(root / "memory" / "logs" / "pid1_proof.json", {}).get("pid1_gate_ok"),
        "commands_pending": len(_read_jsonl(root / "memory" / "operator" / "command_queue.jsonl", 20)),
    }


def governance_timeline() -> Dict[str, Any]:
    root = cogos_root()
    events: List[Dict[str, Any]] = []

    for path, kind in (
        (root / "memory" / "patterns" / "gre_audit.jsonl", "gre_audit"),
        (root / "memory" / "operator" / "profile_switches.jsonl", "profile_switch"),
        (root / "memory" / "traces" / "law_decisions.jsonl", "law_decision"),
        (root / "memory" / "traces" / "update_history.jsonl", "update"),
        (root / "memory" / "logs" / "boot_report.json", "boot"),
    ):
        if path.suffix == ".json":
            data = _read_json(path, {})
            if data:
                events.append({"kind": kind, "ts": data.get("timestamp"), "summary": str(data.get("stage", data.get("ok")))})
        else:
            for row in _read_jsonl(path, 30):
                events.append({"kind": kind, "ts": row.get("ts") or row.get("timestamp"), "summary": _summarize(row)})

    events.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)
    return {"events": events[:40]}


def _summarize(row: Dict[str, Any]) -> str:
    if "module_id" in row:
        return f"{row.get('module_id')} passed={row.get('passed', row.get('payload', {}).get('passed'))}"
    if "profile" in row:
        return f"profile → {row.get('profile')}"
    if "action" in row:
        return str(row.get("action"))
    return json.dumps(row, default=str)[:120]


def law_pulse() -> Dict[str, Any]:
    root = cogos_root()
    corridor = _read_json(root / "memory" / "logs" / "determinism_corridor.json", {})
    hal = _read_json(root / "memory" / "logs" / "hal_snapshot.json", {})
    ledger_verify = {}
    try:
        from pattern_ledger import PatternLedger

        ledger_verify = PatternLedger().verify_chain()
    except Exception as exc:
        ledger_verify = {"ok": False, "error": str(exc)}

    root_law = _read_json(root / "law" / "root_law.json", {})
    net_rows = _read_jsonl(root / "memory" / "traces" / "net_gre.jsonl", 5)
    drift_composite = 0.0
    gre_rows = _read_jsonl(root / "memory" / "patterns" / "gre_audit.jsonl", 3)
    if gre_rows:
        drift_composite = float(gre_rows[-1].get("payload", {}).get("drift_composite", 0))

    pulse = {
        "law_version": root_law.get("version", "?"),
        "law_name": root_law.get("name", "?"),
        "ledger_health": ledger_verify,
        "drift_composite": drift_composite,
        "determinism_corridor": corridor,
        "hal_disks": len(hal.get("disks", [])),
        "hal_net_ifaces": len(hal.get("net_interfaces", [])),
        "mesh_status": "single-node",
        "net_gre_recent": net_rows,
        "loadavg": _read_proc_loadavg(),
    }
    try:
        from device_storage_manager import DeviceStorageManager

        storage = DeviceStorageManager().inventory()
        pulse["device_storage"] = {
            "ok": storage.get("ok"),
            "devices": len(storage.get("devices", [])),
            "warnings": storage.get("warnings", []),
            "payload_used_percent": storage.get("storage", {}).get("payload", {}).get("used_percent"),
            "plans": storage.get("storage", {}).get("plans", 0),
        }
    except Exception as exc:
        pulse["device_storage"] = {"ok": False, "error": str(exc)}
    try:
        from phase2_panels import creative_status, mesh_status, network_visibility

        pulse["creative"] = creative_status()
        pulse["mesh"] = mesh_status()
        pulse["network_visibility"] = network_visibility()
        pulse["mesh_status"] = mesh_status().get("mesh_name", "single-node")
    except Exception:
        pass
    return pulse


def _read_proc_loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text(encoding="utf-8").strip()
    except OSError:
        return "n/a"


def phase1_status() -> Dict[str, Any]:
    return {
        "operator_dashboard": operator_dashboard(),
        "governance_timeline": governance_timeline(),
        "law_pulse": law_pulse(),
    }


def enqueue_operator_command(action: str, **kwargs: Any) -> Dict[str, Any]:
    root = cogos_root()
    queue = root / "memory" / "operator" / "command_queue.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    import time

    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action, **kwargs}
    with queue.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    if action == "pause":
        (root / "memory" / "operator" / "PAUSED").touch()
    elif action == "resume":
        paused = root / "memory" / "operator" / "PAUSED"
        if paused.exists():
            paused.unlink()
    elif action == "switch_profile":
        pid = kwargs.get("profile_id", "operator")
        UserProfileManager().set_active(str(pid))
        os.environ["COGOS_PROFILE"] = str(pid)

    return {"ok": True, "queued": row}
