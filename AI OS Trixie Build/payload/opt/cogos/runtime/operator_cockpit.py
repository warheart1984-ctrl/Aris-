"""
operator_cockpit.py — Unified Phase 0–3 operator status API.
"""

from __future__ import annotations

from typing import Any, Dict

from phase1_panels import phase1_status
from phase2_panels import phase2_status
from phase3_panels import phase3_status
from user_profiles import UserProfileManager
from device_storage_manager import DeviceStorageManager


def full_cockpit() -> Dict[str, Any]:
    profile = UserProfileManager().active_id
    return {
        "profile": profile,
        "phase1": phase1_status(),
        "phase2": phase2_status(),
        "phase3": phase3_status(profile),
        "device_storage": DeviceStorageManager().inventory(),
    }


def cockpit_summary_lines() -> list[str]:
    c = full_cockpit()
    p3 = c["phase3"]
    lines = [
        f"Profile: {c['profile']} | Tier: {p3['tiers']['active_tier']} ({p3['tiers']['label']})",
        f"Release: {p3['release'].get('version', '?')} | Eval: {p3['eval'].get('passed', '?')}/{p3['eval'].get('total', '?')}",
        f"Packages: {p3['packages']['installed_count']}/{p3['packages']['catalog_count']} installed",
        f"Backups: {p3['backup']['backup_count']} bundles",
        f"Creative artifacts: {c['phase2']['creative'].get('artifacts_total', 0)}",
        f"Mesh: {c['phase2']['mesh'].get('mesh_name', '?')} | peers trusted: {c['phase2']['mesh'].get('trusted_peers', 0)}",
    ]
    op = c["phase1"]["operator_dashboard"]
    lines.append(
        f"Daemon: {'RUN' if op.get('daemon_running') else 'STOP'} | "
        f"PID1: {'OK' if op.get('pid1_ok') else 'FAIL'} | "
        f"Ledger: {'OK' if c['phase1']['law_pulse'].get('ledger_health', {}).get('ok') else 'FAIL'}"
    )
    ds = c.get("device_storage", {})
    lines.append(
        f"Storage: {len(ds.get('devices', []))} devices | "
        f"warnings: {len(ds.get('warnings', []))} | plans: {ds.get('storage', {}).get('plans', 0)}"
    )
    return lines
