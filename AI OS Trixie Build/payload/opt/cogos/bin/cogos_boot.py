#!/usr/bin/env python3
"""Project Infi / ARIS governed boot harness.

Verifies staged payload, boots Phase 0 cognitive runtime (GRE + Nova), and
emits a governed boot report. Fails closed when required files are missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any


ROOT = pathlib.Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"

REQUIRED = [
    ROOT / "law" / "root_law.json",
    ROOT / "law" / "boot_law.json",
    ROOT / "law" / "governance_rules.json",
    ROOT / "law" / "law_manifest.json",
    ROOT / "config" / "runtime.json",
    ROOT / "config" / "module_manifest.json",
    ROOT / "runtime" / "aais_unified.py",
    ROOT / "runtime" / "aris_runtime.py",
    ROOT / "runtime" / "ul_core.py",
    ROOT / "runtime" / "forge_eval.py",
    ROOT / "runtime" / "governance_invariant_engine.py",
    ROOT / "runtime" / "cogos_runtime.py",
    ROOT / "runtime" / "nova_layer.py",
    ROOT / "runtime" / "pattern_ledger.py",
    ROOT / "runtime" / "adapter_cycle_context.py",
    ROOT / "config" / "users.json",
    ROOT / "config" / "update_channel.json",
    ROOT / "runtime" / "user_profiles.py",
    ROOT / "runtime" / "determinism_corridor.py",
    ROOT / "runtime" / "hal_service.py",
    ROOT / "runtime" / "net_gre.py",
    ROOT / "runtime" / "phase1_panels.py",
    ROOT / "config" / "mesh.json",
    ROOT / "runtime" / "mesh_identity.py",
    ROOT / "runtime" / "reasoning_exchange.py",
    ROOT / "runtime" / "creative_modules.py",
    ROOT / "runtime" / "creative_substrate.py",
    ROOT / "runtime" / "phase2_panels.py",
    ROOT / "config" / "compute_tiers.json",
    ROOT / "config" / "package_catalog.json",
    ROOT / "config" / "release_manifest.json",
    ROOT / "runtime" / "compute_tiers.py",
    ROOT / "runtime" / "cogos_pkg.py",
    ROOT / "runtime" / "cogos_backup.py",
    ROOT / "runtime" / "eval_harness.py",
    ROOT / "runtime" / "phase3_panels.py",
    ROOT / "runtime" / "operator_cockpit.py",
    ROOT / "runtime" / "automatic_mode.py",
    ROOT / "bin" / "cogos_auto.py",
    ROOT / "runtime" / "manifest_signing.py",
    ROOT / "runtime" / "recovery_mode.py",
    ROOT / "bin" / "cogos_recovery.py",
    ROOT / "config" / "trust_keys.json",
    ROOT / "config" / "release_manifest.json.sig",
    ROOT / "config" / "package_catalog.json.sig",
    ROOT / "config" / "update_channel.json.sig",
]


def _ensure_runtime_path() -> None:
    for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def boot_cognitive_runtime() -> dict[str, Any]:
    _ensure_runtime_path()
    try:
        from cogos_runtime import CognitiveRuntime

        runtime = CognitiveRuntime()
        ok = runtime.boot()
        status = runtime.status()
        return {
            "ok": ok,
            "cognitive_boot": ok,
            "mode": status.get("mode"),
            "ledger_verify": status.get("ledger_verify"),
            "gre_audit_len": status.get("gre_audit_len"),
        }
    except Exception as exc:
        return {"ok": False, "cognitive_boot": False, "error": str(exc)}


def verify_payload() -> dict[str, Any]:
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        return {"ok": False, "stage": "payload", "missing": missing}

    files = []
    for path in REQUIRED:
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    root_law = load_json(ROOT / "law" / "root_law.json")
    boot_law = load_json(ROOT / "law" / "boot_law.json")
    governance = load_json(ROOT / "law" / "governance_rules.json")
    law_manifest = load_json(ROOT / "law" / "law_manifest.json")
    manifest = load_json(ROOT / "config" / "module_manifest.json")

    cognitive = boot_cognitive_runtime()
    phase1 = run_phase1_boot_hooks()
    phase3 = run_phase3_boot_hooks()

    ok = bool(cognitive.get("cognitive_boot")) and bool(phase1.get("ok", True)) and bool(phase3.get("ok", True))

    return {
        "ok": ok,
        "stage": "governed_ready" if ok else "cognitive_boot_failed",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root_law": root_law.get("name"),
        "boot_sequence": boot_law.get("sequence", []),
        "governance_mode": governance.get("mode"),
        "law_manifest": law_manifest.get("mode"),
        "modules": manifest.get("modules", []),
        "cognitive_runtime": cognitive,
        "phase1": phase1,
        "phase3": phase3,
        "files": files,
    }


def run_phase3_boot_hooks() -> dict[str, Any]:
    _ensure_runtime_path()
    out: dict[str, Any] = {"ok": True}
    try:
        from compute_tiers import ComputeTierEngine

        out["compute_tier"] = ComputeTierEngine().resolve_tier(
            __import__("user_profiles", fromlist=["UserProfileManager"]).UserProfileManager().active_id
        )
    except Exception as exc:
        out["tier_error"] = str(exc)
    try:
        from eval_harness import run_eval_suite

        out["eval"] = run_eval_suite()
        if not out["eval"].get("ok"):
            out["ok"] = False
    except Exception as exc:
        out["eval_error"] = str(exc)
        out["ok"] = False
    try:
        from phase3_panels import release_status

        out["release"] = release_status()
    except Exception as exc:
        out["release_error"] = str(exc)
    return out


def run_phase1_boot_hooks() -> dict[str, Any]:
    _ensure_runtime_path()
    out: dict[str, Any] = {"ok": True}
    try:
        from hal_service import write_hal_snapshot

        path = write_hal_snapshot()
        out["hal_snapshot"] = str(path)
    except Exception as exc:
        out["hal_error"] = str(exc)
        out["ok"] = False
    try:
        from determinism_corridor import run_boot_verification

        out["determinism_corridor"] = run_boot_verification()
        if not out["determinism_corridor"].get("ok"):
            out["ok"] = False
    except Exception as exc:
        out["determinism_error"] = str(exc)
        out["ok"] = False
    try:
        from user_profiles import UserProfileManager

        out["active_profile"] = UserProfileManager().active_id
    except Exception as exc:
        out["profile_error"] = str(exc)
    try:
        from mesh_identity import MeshIdentityStore

        out["mesh_identity"] = MeshIdentityStore().export_exchange_bundle()
    except Exception as exc:
        out["mesh_error"] = str(exc)
    try:
        from phase2_panels import phase2_status

        out["phase2"] = phase2_status()
    except Exception as exc:
        out["phase2_error"] = str(exc)
    return out


def write_report(report: dict[str, Any]) -> None:
    out_dir = ROOT / "memory" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "boot_report.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boot", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    report = verify_payload()
    write_report(report)

    if args.smoke:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
