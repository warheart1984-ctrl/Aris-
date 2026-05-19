"""
determinism_corridor.py — Versioned replay verification for GRE / ledger audit chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from governance_invariant_engine import cogos_root


CORRIDOR_VERSION = "1.0.0"


def _hash_payload(payload: Dict[str, Any], prev: str) -> str:
    blob = json.dumps({"prev": prev, "payload": payload}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def verify_pattern_ledger(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "entries": 0, "version": CORRIDOR_VERSION, "reason": "empty"}
    prev = "GENESIS"
    entries = 0
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        row = json.loads(line)
        if row.get("prev_hash") != prev:
            return {"ok": False, "entries": entries, "reason": "prev_hash mismatch"}
        recomputed = _hash_payload(row.get("payload", {}), prev)
        if recomputed != row.get("record_hash"):
            return {"ok": False, "entries": entries, "reason": "record_hash mismatch"}
        prev = row["record_hash"]
        entries += 1
    return {"ok": True, "entries": entries, "version": CORRIDOR_VERSION}


def verify_gre_audit_chain(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replay GRE audit records — input_hash must be stable for same input_data."""
    seen: Dict[str, str] = {}
    for rec in records:
        tid = rec.get("trace_id", "")
        ih = rec.get("input_hash", "")
        if tid in seen and seen[tid] != ih:
            return {"ok": False, "reason": f"trace {tid} input_hash drift"}
        seen[tid] = ih
    return {"ok": True, "records": len(records), "version": CORRIDOR_VERSION}


def run_boot_verification() -> Dict[str, Any]:
    root = cogos_root()
    ledger_path = root / "memory" / "patterns" / "gre_audit.jsonl"
    boot_report = root / "memory" / "logs" / "boot_report.json"
    results: Dict[str, Any] = {
        "corridor_version": CORRIDOR_VERSION,
        "ledger": verify_pattern_ledger(ledger_path),
    }
    if boot_report.exists():
        try:
            br = json.loads(boot_report.read_text(encoding="utf-8-sig"))
            cognitive = br.get("cognitive_runtime", {})
            results["cognitive_boot"] = cognitive.get("cognitive_boot", False)
        except (OSError, json.JSONDecodeError):
            results["cognitive_boot"] = False
    results["ok"] = bool(results["ledger"].get("ok")) and results.get("cognitive_boot", True)
    out_path = root / "memory" / "logs" / "determinism_corridor.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-boot", action="store_true")
    parser.add_argument("--verify-ledger", action="store_true")
    args = parser.parse_args()
    if args.verify_ledger or args.verify_boot:
        result = run_boot_verification()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
