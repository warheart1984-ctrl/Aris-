"""CoGOS recovery mode: inspect, verify, and restore governed state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cogos_backup import import_backup, list_backups
from governance_invariant_engine import cogos_root
from manifest_signing import verify_core_manifests
from pattern_ledger import PatternLedger


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


class RecoveryMode:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or cogos_root()
        self.logs = self.root / "memory" / "logs"
        self.flag = self.root / "memory" / "operator" / "RECOVERY_MODE"
        self.proof = self.logs / "recovery_proof.json"

    def status(self) -> Dict[str, Any]:
        boot = _read_json(self.logs / "boot_report.json", {})
        pid1 = _read_json(self.logs / "pid1_proof.json", {})
        eval_report = _read_json(self.logs / "eval_report.json", {})
        return {
            "ok": True,
            "timestamp": utc_now(),
            "recovery_flag": self.flag.exists(),
            "boot_ok": bool(boot.get("ok")),
            "boot_stage": boot.get("stage"),
            "pid1_gate_ok": bool(pid1.get("pid1_gate_ok")),
            "eval_ok": eval_report.get("ok"),
            "release": _read_json(self.root / "config" / "release_manifest.json", {}).get("version"),
            "backups": list_backups()[:5],
            "snapshots": self.list_snapshots()[:5],
        }

    def verify(self) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        ledger = PatternLedger().verify_chain()
        signed = verify_core_manifests(self.root)
        checks.append({"name": "ledger", "ok": bool(ledger.get("ok")), "detail": ledger})
        checks.append({"name": "signed_manifests", "ok": bool(signed.get("ok")), "detail": signed})
        for rel in ("law/root_law.json", "law/governance_rules.json", "config/users.json"):
            path = self.root / rel
            checks.append({"name": rel, "ok": path.exists(), "detail": str(path)})
        report = {"ok": all(c["ok"] for c in checks), "timestamp": utc_now(), "checks": checks}
        self.write_proof("verify", report)
        return report

    def enable(self) -> Dict[str, Any]:
        self.flag.parent.mkdir(parents=True, exist_ok=True)
        self.flag.write_text(utc_now() + "\n", encoding="utf-8")
        out = {"ok": True, "recovery_flag": str(self.flag), "enabled": True}
        self.write_proof("enable", out)
        return out

    def disable(self) -> Dict[str, Any]:
        self.flag.unlink(missing_ok=True)
        out = {"ok": True, "recovery_flag": str(self.flag), "enabled": False}
        self.write_proof("disable", out)
        return out

    def list_snapshots(self) -> List[Dict[str, Any]]:
        snap_dir = self.root / "memory" / "snapshots"
        if not snap_dir.exists():
            return []
        out = []
        for path in sorted(snap_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_dir():
                continue
            manifest = _read_json(path / "manifest.json", {})
            out.append({"path": str(path), "label": manifest.get("label"), "ts": manifest.get("ts"), "files": len(manifest.get("files", []))})
        return out

    def apply_rollback(self, snapshot_path: str) -> Dict[str, Any]:
        from importlib import util

        update_path = self.root / "bin" / "cogos_update.py"
        spec = util.spec_from_file_location("cogos_update_recovery", update_path)
        if not spec or not spec.loader:
            out = {"ok": False, "error": "could not load cogos_update.py"}
        else:
            module = util.module_from_spec(spec)
            spec.loader.exec_module(module)
            out = module.apply_rollback(snapshot_path)
        self.write_proof("rollback", out)
        return out

    def restore_backup(self, bundle_path: str, *, profile_id: str = "operator") -> Dict[str, Any]:
        out = import_backup(bundle_path, profile_id=profile_id)
        self.write_proof("backup_restore", out)
        return out

    def reset_first_run(self) -> Dict[str, Any]:
        from first_run_wizard import FirstRunWizard

        out = FirstRunWizard().reset()
        self.write_proof("first_run_reset", out)
        return out

    def boot_recovery(self) -> Dict[str, Any]:
        report = {"ok": True, "mode": "recovery", "status": self.status(), "verify": self.verify()}
        self.write_proof("boot", report)
        return report

    def write_proof(self, action: str, detail: Dict[str, Any]) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        row = {"timestamp": utc_now(), "action": action, "detail": detail}
        self.proof.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        trace = self.root / "memory" / "traces" / "recovery_history.jsonl"
        trace.parent.mkdir(parents=True, exist_ok=True)
        with trace.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def recovery_requested() -> bool:
    root = cogos_root()
    if (root / "memory" / "operator" / "RECOVERY_MODE").exists():
        return True
    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8", errors="replace")
        return "cogos.recovery=1" in cmdline or "cogos_recovery=1" in cmdline
    except Exception:
        return False

