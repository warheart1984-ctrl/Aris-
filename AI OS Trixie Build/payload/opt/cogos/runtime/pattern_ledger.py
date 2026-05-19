"""
pattern_ledger.py — Hash-chained audit trail from GRE AuditChain (Phase 0)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from governance_invariant_engine import AuditRecord, cogos_root


@dataclass
class LedgerEntry:
    seq: int
    trace_id: str
    module_id: str
    passed: bool
    record_hash: str
    prev_hash: str
    payload: Dict[str, Any]


class PatternLedger:
    MAX_ENTRIES = 500

    def __init__(self, path: Optional[Path] = None) -> None:
        root = cogos_root()
        base = path or (root / "memory" / "patterns" / "gre_audit.jsonl")
        self.path = Path(base)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._seq = 0
        self._prev_hash = "GENESIS"
        self._load_tail()

    def _load_tail(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            return
        if not lines:
            return
        last = json.loads(lines[-1])
        self._seq = int(last.get("seq", 0))
        self._prev_hash = str(last.get("record_hash", "GENESIS"))

    def _hash_entry(self, payload: Dict[str, Any], prev_hash: str) -> str:
        blob = json.dumps({"prev": prev_hash, "payload": payload}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def append_audit(self, record: AuditRecord) -> LedgerEntry:
        with self._AppendLock(self):
            self._load_tail()
            self._seq += 1
            payload = {
                "trace_id": record.trace_id,
                "module_id": record.module_id,
                "lane_id": record.lane_id,
                "subject": record.subject,
                "passed": record.passed,
                "checkpoint": record.checkpoint.value if hasattr(record.checkpoint, "value") else str(record.checkpoint),
                "input_hash": record.input_hash,
                "output_hash": record.output_hash,
                "violations": record.violations,
                "drift_composite": record.drift_composite,
                "timestamp": record.timestamp,
                "stages_completed": record.stages_completed,
            }
            record_hash = self._hash_entry(payload, self._prev_hash)
            entry = LedgerEntry(
                seq=self._seq,
                trace_id=record.trace_id,
                module_id=record.module_id,
                passed=record.passed,
                record_hash=record_hash,
                prev_hash=self._prev_hash,
                payload=payload,
            )
            self._prev_hash = record_hash
            line = json.dumps(asdict(entry), sort_keys=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._rotate_if_needed()
            return entry

    def ingest_gre_chain(self, audit_chain: List[AuditRecord]) -> int:
        count = 0
        for record in audit_chain:
            self.append_audit(record)
            count += 1
        return count

    def list_entries(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        out: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def verify_chain(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"ok": True, "entries": 0}
        prev = "GENESIS"
        entries = 0
        for line in self.path.read_text(encoding="utf-8").strip().splitlines():
            row = json.loads(line)
            expected_prev = row.get("prev_hash")
            if expected_prev != prev:
                return {"ok": False, "entries": entries, "reason": "prev_hash mismatch"}
            payload = row.get("payload", {})
            recomputed = self._hash_entry(payload, prev)
            if recomputed != row.get("record_hash"):
                return {"ok": False, "entries": entries, "reason": "record_hash mismatch"}
            prev = row["record_hash"]
            entries += 1
        return {"ok": True, "entries": entries}

    def _rotate_if_needed(self) -> None:
        if not self.path.exists():
            return
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) <= self.MAX_ENTRIES:
            return
        keep = lines[-self.MAX_ENTRIES :]
        rotated = self.path.with_suffix(".jsonl.rotated")
        try:
            if self.path.exists():
                self.path.replace(rotated)
        except OSError:
            pass
        self.path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    class _AppendLock:
        def __init__(self_outer, outer: "PatternLedger") -> None:
            self_outer.outer = outer
            self_outer.fd: Optional[int] = None

        def __enter__(self_outer):
            deadline = time.time() + 10
            while True:
                try:
                    self_outer.fd = os.open(
                        self_outer.outer.lock_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    )
                    os.write(self_outer.fd, str(os.getpid()).encode("ascii"))
                    return self_outer
                except FileExistsError:
                    if time.time() > deadline:
                        try:
                            self_outer.outer.lock_path.unlink()
                        except OSError:
                            pass
                    time.sleep(0.05)

        def __exit__(self_outer, exc_type, exc, tb) -> None:
            if self_outer.fd is not None:
                try:
                    os.close(self_outer.fd)
                except OSError:
                    pass
            try:
                self_outer.outer.lock_path.unlink()
            except OSError:
                pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pattern ledger query")
    parser.add_argument("command", choices=["list", "verify"], nargs="?", default="list")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    ledger = PatternLedger()
    if args.command == "verify":
        print(json.dumps(ledger.verify_chain(), indent=2))
    else:
        print(json.dumps(ledger.list_entries(args.limit), indent=2))


if __name__ == "__main__":
    main()
