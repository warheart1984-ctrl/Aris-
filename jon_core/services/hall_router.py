"""HallRouter (Discard/Shame/Fame) - Fingerprint-based routing with re-entry blocking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json
import time


class HallType(Enum):
    """Hall of Discard/Shame/Fame."""
    DISCARD = "discard"
    SHAME = "shame"
    FAME = "fame"


@dataclass(frozen=True, slots=True)
class HallEntry:
    """Immutable hall entry."""
    fingerprint: str
    hall_type: HallType
    lineage_key: str
    action_type: str
    purpose: str
    target: str
    patch: Optional[str] = None
    command: Optional[str] = None
    code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    re_evaluation_of: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    sealed: bool = False

    @classmethod
    def create(cls, hall_type: HallType, action: Dict[str, Any], lineage_key: str) -> "HallEntry":
        """Create hall entry from action."""
        # Compute fingerprint from action_type+purpose+target+patch+command+code+metadata
        fingerprint_parts = [
            action.get("type", ""),
            action.get("purpose", ""),
            action.get("target", ""),
            action.get("patch", ""),
            action.get("command", ""),
            action.get("code", ""),
            json.dumps(action.get("metadata", {}), sort_keys=True),
        ]
        fingerprint = hashlib.sha256(":".join(fingerprint_parts).encode("utf-8")).hexdigest()
        
        return cls(
            fingerprint=fingerprint,
            hall_type=hall_type,
            lineage_key=lineage_key,
            action_type=action.get("type", ""),
            purpose=action.get("purpose", ""),
            target=action.get("target", ""),
            patch=action.get("patch"),
            command=action.get("command"),
            code=action.get("code"),
            metadata=action.get("metadata", {}),
        )


class HallRouter:
    """Routes mutations to Discard/Shame/Fame with fingerprint-based re-entry blocking."""
    
    def __init__(self):
        self._discard: Dict[str, HallEntry] = {}
        self._shame: Dict[str, HallEntry] = {}
        self._fame: Dict[str, HallEntry] = {}
        self._lineage_index: Dict[str, List[HallEntry]] = {}

    def discard(self, action: Dict[str, Any], lineage_key: str, re_evaluation_of: Optional[str] = None) -> HallEntry:
        """Route to Hall of Discard."""
        entry = HallEntry.create(HallType.DISCARD, action, lineage_key)
        if re_evaluation_of:
            entry = HallEntry(
                fingerprint=entry.fingerprint,
                hall_type=entry.hall_type,
                lineage_key=entry.lineage_key,
                action_type=entry.action_type,
                purpose=entry.purpose,
                target=entry.target,
                patch=entry.patch,
                command=entry.command,
                code=entry.code,
                metadata=entry.metadata,
                re_evaluation_of=re_evaluation_of,
                timestamp=entry.timestamp,
            )
        self._discard[entry.fingerprint] = entry
        self._index_lineage(entry)
        return entry

    def shame(self, action: Dict[str, Any], lineage_key: str, re_evaluation_of: Optional[str] = None) -> HallEntry:
        """Route to Hall of Shame."""
        entry = HallEntry.create(HallType.SHAME, action, lineage_key)
        if re_evaluation_of:
            entry = HallEntry(
                fingerprint=entry.fingerprint,
                hall_type=entry.hall_type,
                lineage_key=entry.lineage_key,
                action_type=entry.action_type,
                purpose=entry.purpose,
                target=entry.target,
                patch=entry.patch,
                command=entry.command,
                code=entry.code,
                metadata=entry.metadata,
                re_evaluation_of=re_evaluation_of,
                timestamp=entry.timestamp,
            )
        self._shame[entry.fingerprint] = entry
        self._index_lineage(entry)
        return entry

    def fame(self, action: Dict[str, Any], lineage_key: str, re_evaluation_of: Optional[str] = None) -> HallEntry:
        """Route to Hall of Fame."""
        entry = HallEntry.create(HallType.FAME, action, lineage_key)
        if re_evaluation_of:
            entry = HallEntry(
                fingerprint=entry.fingerprint,
                hall_type=entry.hall_type,
                lineage_key=entry.lineage_key,
                action_type=entry.action_type,
                purpose=entry.purpose,
                target=entry.target,
                patch=entry.patch,
                command=entry.command,
                code=entry.code,
                metadata=entry.metadata,
                re_evaluation_of=re_evaluation_of,
                timestamp=entry.timestamp,
            )
        self._fame[entry.fingerprint] = entry
        self._index_lineage(entry)
        return entry

    def _index_lineage(self, entry: HallEntry) -> None:
        if entry.lineage_key not in self._lineage_index:
            self._lineage_index[entry.lineage_key] = []
        self._lineage_index[entry.lineage_key].append(entry)

    def find_reentry_blocker(self, fingerprint: str) -> Optional[HallEntry]:
        """Check if fingerprint is blocked from re-entry."""
        if fingerprint in self._discard:
            return self._discard[fingerprint]
        if fingerprint in self._shame:
            return self._shame[fingerprint]
        if fingerprint in self._fame:
            return self._fame[fingerprint]
        return None

    def find_latest_lineage_entry(self, lineage_key: str) -> Optional[HallEntry]:
        """Find latest entry for a lineage key."""
        entries = self._lineage_index.get(lineage_key, [])
        if not entries:
            return None
        return max(entries, key=lambda e: e.timestamp)

    def is_blocked(self, action: Dict[str, Any]) -> Optional[HallEntry]:
        """Check if action is blocked by any hall."""
        fingerprint_parts = [
            action.get("type", ""),
            action.get("purpose", ""),
            action.get("target", ""),
            action.get("patch", ""),
            action.get("command", ""),
            action.get("code", ""),
            json.dumps(action.get("metadata", {}), sort_keys=True),
        ]
        fingerprint = hashlib.sha256(":".join(fingerprint_parts).encode("utf-8")).hexdigest()
        return self.find_reentry_blocker(fingerprint)

    def get_discard(self) -> List[HallEntry]:
        return list(self._discard.values())

    def get_shame(self) -> List[HallEntry]:
        return list(self._shame.values())

    def get_fame(self) -> List[HallEntry]:
        return list(self._fame.values())

    def seal_epoch(self, epoch_id: str) -> None:
        """Seal all entries for an epoch (tamper-evident)."""
        for entry in self._discard.values():
            if not entry.sealed:
                # In practice, would add epoch seal hash
                pass
        for entry in self._shame.values():
            if not entry.sealed:
                pass
        for entry in self._fame.values():
            if not entry.sealed:
                pass