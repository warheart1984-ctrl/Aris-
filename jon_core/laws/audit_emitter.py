"""Λ.2 AuditEmitter Interface - Tamper-evident audit chain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional
from datetime import datetime, timezone
import hashlib
import json


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Single audit record in the chain."""
    index: int
    timestamp: str
    module: str
    event_type: str
    payload: dict[str, Any]
    previous_hash: str
    record_hash: str

    @classmethod
    def create(cls, index: int, module: str, event_type: str, payload: dict[str, Any], previous_hash: str) -> "AuditRecord":
        """Create a new audit record with computed hash."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        content = f"{index}:{timestamp}:{module}:{event_type}:{json.dumps(payload, sort_keys=True)}:{previous_hash}"
        record_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(
            index=index,
            timestamp=timestamp,
            module=module,
            event_type=event_type,
            payload=payload,
            previous_hash=previous_hash,
            record_hash=record_hash,
        )

    def verify(self) -> bool:
        """Verify this record's hash integrity."""
        content = f"{self.index}:{self.timestamp}:{self.module}:{self.event_type}:{json.dumps(self.payload, sort_keys=True)}:{self.previous_hash}"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return self.record_hash == expected


class AuditEmitter(ABC):
    """Protocol for tamper-evident audit emission."""

    @abstractmethod
    def emit_record(self, module: str, event_type: str, payload: dict[str, Any]) -> AuditRecord:
        """Emit a new audit record."""
        ...

    @abstractmethod
    def query_by_module(self, module: str) -> List[AuditRecord]:
        """Query records by module name."""
        ...

    @abstractmethod
    def query_by_time_range(self, start: datetime, end: datetime) -> List[AuditRecord]:
        """Query records by time range."""
        ...

    @abstractmethod
    def verify_chain_integrity(self) -> tuple[bool, list[str]]:
        """Verify entire chain integrity. Returns (valid, errors)."""
        ...


class AppendOnlyAuditEmitter(AuditEmitter):
    """Reference implementation with content-addressed hash chaining."""

    def __init__(self):
        self._records: List[AuditRecord] = []
        self._genesis_hash = "0" * 64

    def emit_record(self, module: str, event_type: str, payload: dict[str, Any]) -> AuditRecord:
        previous_hash = self._records[-1].record_hash if self._records else self._genesis_hash
        record = AuditRecord.create(
            index=len(self._records),
            module=module,
            event_type=event_type,
            payload=payload,
            previous_hash=previous_hash,
        )
        self._records.append(record)
        return record

    def query_by_module(self, module: str) -> List[AuditRecord]:
        return [r for r in self._records if r.module == module]

    def query_by_time_range(self, start: datetime, end: datetime) -> List[AuditRecord]:
        # Ensure timezone-aware datetimes for comparison
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        
        return [
            r for r in self._records 
            if start <= datetime.fromisoformat(r.timestamp.replace("Z", "+00:00")) <= end
        ]

    def verify_chain_integrity(self) -> tuple[bool, list[str]]:
        errors = []
        expected_previous = self._genesis_hash

        for i, record in enumerate(self._records):
            if record.previous_hash != expected_previous:
                errors.append(f"Record {i}: previous_hash mismatch (expected {expected_previous[:16]}..., got {record.previous_hash[:16]}...)")
            if not record.verify():
                errors.append(f"Record {i}: record_hash verification failed")
            expected_previous = record.record_hash

        return len(errors) == 0, errors

    def get_all_records(self) -> List[AuditRecord]:
        return list(self._records)

    def get_latest_hash(self) -> str:
        return self._records[-1].record_hash if self._records else self._genesis_hash