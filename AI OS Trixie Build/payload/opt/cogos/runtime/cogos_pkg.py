"""
cogos_pkg.py — Governed package shim over curated catalog (Phase 3).
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from compute_tiers import ComputeTierEngine
from governance_invariant_engine import cogos_root
from manifest_signing import verify_manifest_file


def _catalog() -> Dict[str, Any]:
    path = cogos_root() / "config" / "package_catalog.json"
    verification = verify_manifest_file(path)
    if not verification.get("ok"):
        raise RuntimeError(f"package catalog signature verification failed: {verification.get('error')}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_catalog() -> Dict[str, Any]:
    return verify_manifest_file(cogos_root() / "config" / "package_catalog.json")


def list_packages() -> List[Dict[str, Any]]:
    installed = _installed_index()
    out = []
    for pkg in _catalog().get("packages", []):
        pid = pkg["id"]
        out.append({
            **pkg,
            "installed": pid in installed,
            "install_record": installed.get(pid),
        })
    return out


def _installed_index() -> Dict[str, Any]:
    path = cogos_root() / "memory" / "packages" / "installed.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _save_installed(index: Dict[str, Any]) -> None:
    path = cogos_root() / "memory" / "packages" / "installed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def _log(action: str, detail: Dict[str, Any]) -> None:
    log = cogos_root() / "memory" / "traces" / "package_history.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action, **detail}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def install(package_id: str, *, profile_id: str = "operator") -> Dict[str, Any]:
    tiers = ComputeTierEngine()
    check = tiers.check("pkg.install", profile_id=profile_id)
    if not check.allowed:
        tiers.log_denial(check, context={"action": "install", "package": package_id})
        return {"ok": False, "error": check.reason, "tier": check.tier}

    pkg = next((p for p in _catalog().get("packages", []) if p["id"] == package_id), None)
    if not pkg:
        return {"ok": False, "error": f"unknown package: {package_id}"}

    req = pkg.get("required_tier", "standard")
    tier = tiers.resolve_tier(profile_id)
    order = ["base", "standard", "elevated", "developer"]
    if order.index(tier) < order.index(req) if req in order and tier in order else 0:
        return {"ok": False, "error": f"tier {tier} insufficient for package (requires {req})"}

    root = cogos_root()
    slot = root / "memory" / "packages" / "installed" / package_id
    slot.mkdir(parents=True, exist_ok=True)

    if pkg.get("install_type") == "memory_slot":
        target = Path(pkg.get("memory_path", str(slot)))
        target.mkdir(parents=True, exist_ok=True)
        (target / ".installed").write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
    elif pkg.get("module_path"):
        src = Path(pkg["module_path"])
        if src.exists():
            dest = slot / "module"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            return {"ok": False, "error": f"module path missing: {pkg['module_path']}"}
    elif pkg.get("artifact"):
        art = Path(pkg["artifact"])
        if art.exists():
            shutil.copy2(art, slot / art.name)
        else:
            return {"ok": False, "error": f"artifact missing: {pkg['artifact']}"}

    record = {
        "package_id": package_id,
        "version": pkg.get("version"),
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tier": tier,
        "slot": str(slot),
        "capabilities": pkg.get("capabilities", []),
    }
    idx = _installed_index()
    idx[package_id] = record
    _save_installed(idx)
    _log("install", record)
    return {"ok": True, "package": package_id, "record": record}


def remove(package_id: str, *, profile_id: str = "operator") -> Dict[str, Any]:
    tiers = ComputeTierEngine()
    check = tiers.check("pkg.remove", profile_id=profile_id)
    if not check.allowed:
        return {"ok": False, "error": check.reason}

    idx = _installed_index()
    if package_id not in idx:
        return {"ok": False, "error": "not installed"}

    slot = cogos_root() / "memory" / "packages" / "installed" / package_id
    if slot.exists():
        shutil.rmtree(slot, ignore_errors=True)
    del idx[package_id]
    _save_installed(idx)
    _log("remove", {"package_id": package_id})
    return {"ok": True, "package_id": package_id}
