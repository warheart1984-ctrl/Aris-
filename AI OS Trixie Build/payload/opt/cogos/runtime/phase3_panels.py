"""
phase3_panels.py — Operator cockpit: tiers, packages, backup, eval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from governance_invariant_engine import cogos_root


def tier_status(profile_id: str = "operator") -> Dict[str, Any]:
    from compute_tiers import ComputeTierEngine

    engine = ComputeTierEngine()
    tier = engine.resolve_tier(profile_id)
    tdef = engine.tier_def(tier)
    return {
        "active_tier": tier,
        "label": tdef.get("label", tier),
        "profile": profile_id,
        "capabilities_count": len(tdef.get("capabilities", [])),
        "denies_count": len(tdef.get("denies", [])),
        "all_tiers": engine.list_tiers(),
    }


def package_status() -> Dict[str, Any]:
    from cogos_pkg import list_packages

    pkgs = list_packages()
    return {
        "catalog_count": len(pkgs),
        "installed_count": sum(1 for p in pkgs if p.get("installed")),
        "packages": pkgs,
    }


def backup_status() -> Dict[str, Any]:
    from cogos_backup import list_backups

    backups = list_backups()
    return {"backup_count": len(backups), "latest": backups[0] if backups else None, "backups": backups[:5]}


def eval_status() -> Dict[str, Any]:
    path = cogos_root() / "memory" / "logs" / "eval_report.json"
    if not path.exists():
        return {"ok": None, "message": "run cogos_eval.py run"}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def release_status() -> Dict[str, Any]:
    path = cogos_root() / "config" / "release_manifest.json"
    if not path.exists():
        return {"version": "unknown"}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def automatic_status() -> Dict[str, Any]:
    from automatic_mode import AutomaticModeEngine

    return AutomaticModeEngine().status()


def phase3_status(profile_id: str = "operator") -> Dict[str, Any]:
    return {
        "tiers": tier_status(profile_id),
        "packages": package_status(),
        "backup": backup_status(),
        "eval": eval_status(),
        "release": release_status(),
        "automatic": automatic_status(),
    }
