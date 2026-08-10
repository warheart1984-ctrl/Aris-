"""LawLedger - Append-only JSONL with event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import time
import threading
import hashlib


class LawLedgerEventType(Enum):
    """LawLedger event types."""
    PREFLIGHT = "preflight"
    POST_VERIFICATION = "post_verification"
    MUTATION_GATE = "mutation_gate"
    MUTATION_ADMISSION = "mutation_admission"
    OVERRIDE_RECKONING = "override_reckoning"
    OBSERVATION_MODE = "observation_mode"
    SENSITIVE_ENTRY = "sensitive_entry"


@dataclass
class LawLedgerRecord:
    """Single ledger record."""
    event_type: LawLedgerEventType
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    record_hash: str = ""
    previous_hash: str = ""

    def compute_hash(self) -> str:
        content = f"{self.event_type.value}:{json.dumps(self.payload, sort_keys=True)}:{self.timestamp}:{self.previous_hash}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, previous_hash: str) -> "LawLedgerRecord":
        """Create sealed record with hash chain."""
        return LawLedgerRecord(
            event_type=self.event_type,
            payload=self.payload,
            timestamp=self.timestamp,
            previous_hash=previous_hash,
            record_hash="",  # Will be computed
        )


class LawLedger:
    """Append-only JSONL ledger with hash chain."""
    
    def __init__(self):
        self._records: List[LawLedgerRecord] = []
        self._genesis_hash = "0" * 64
        self._lock = threading.RLock()

    def record(self, event_type: LawLedgerEventType, payload: Dict[str, Any], require_success: bool = True) -> LawLedgerRecord:
        """Record event to ledger."""
        with self._lock:
            previous_hash = self._records[-1].record_hash if self._records else self._genesis_hash
            
            record = LawLedgerRecord(
                event_type=event_type,
                payload=payload,
                previous_hash=previous_hash,
            )
            record.record_hash = record.compute_hash()
            
            self._records.append(record)
            
            if require_success:
                # Verify immediately
                if not self._verify_record(record):
                    raise ValueError("Ledger record verification failed")
            
            return record

    def _verify_record(self, record: LawLedgerRecord) -> bool:
        return record.record_hash == record.compute_hash()

    def query_by_type(self, event_type: LawLedgerEventType) -> List[LawLedgerRecord]:
        with self._lock:
            return [r for r in self._records if r.event_type == event_type]

    def query_by_time_range(self, start: float, end: float) -> List[LawLedgerRecord]:
        with self._lock:
            return [r for r in self._records if start <= r.timestamp <= end]

    def query_by_module(self, module: str) -> List[LawLedgerRecord]:
        with self._lock:
            return [r for r in self._records if r.payload.get("module") == module]

    def verify_chain_integrity(self) -> Tuple[bool, List[str]]:
        with self._lock:
            errors = []
            expected_previous = self._genesis_hash
            
            for i, record in enumerate(self._records):
                if record.previous_hash != expected_previous:
                    errors.append(f"Record {i}: previous_hash mismatch")
                if not self._verify_record(record):
                    errors.append(f"Record {i}: hash verification failed")
                expected_previous = record.record_hash
            
            return len(errors) == 0, errors

    def get_all_records(self) -> List[LawLedgerRecord]:
        with self._lock:
            return list(self._records)

    def get_latest_hash(self) -> str:
        with self._lock:
            return self._records[-1].record_hash if self._records else self._genesis_hash

    def export_jsonl(self) -> str:
        with self._lock:
            lines = []
            for record in self._records:
                lines.append(json.dumps({
                    "event_type": record.event_type.value,
                    "payload": record.payload,
                    "timestamp": record.timestamp,
                    "record_hash": record.record_hash,
                    "previous_hash": record.previous_hash,
                }))
            return "\n".join(lines)