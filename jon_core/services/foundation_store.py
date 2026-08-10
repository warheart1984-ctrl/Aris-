"""FoundationStore - Protected immutable entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import threading


@dataclass
class FoundationEntry:
    """Protected foundation entry."""
    id: str
    content: Any
    locked: bool = False
    created_at: float = field(default_factory=lambda: __import__('time').time())
    locked_at: Optional[float] = None


class FoundationStore:
    """Protected entries (UL_ROOT_LAW_ID, ARIS_HANDBOOK_ID, ARIS_DOC_CHANNEL_ID)."""
    
    PROTECTED_IDS = {
        "UL_ROOT_LAW_LOCKED",
        "ARIS_HANDBOOK_LOCKED", 
        "ARIS_DOC_CHANNEL_LOCKED",
    }

    def __init__(self):
        self._entries: Dict[str, FoundationEntry] = {}
        self._lock = threading.RLock()

    def set(self, id: str, content: Any) -> bool:
        """Set entry content. Fails if locked."""
        with self._lock:
            if id in self._entries and self._entries[id].locked:
                return False
            
            entry = FoundationEntry(id=id, content=content)
            self._entries[id] = entry
            return True

    def get(self, id: str) -> Optional[Any]:
        """Get entry content."""
        with self._lock:
            entry = self._entries.get(id)
            return entry.content if entry else None

    def lock(self, id: str) -> bool:
        """Lock entry (irreversible)."""
        with self._lock:
            entry = self._entries.get(id)
            if entry is None:
                return False
            if entry.locked:
                return True
            
            import time
            entry.locked = True
            entry.locked_at = time.time()
            return True

    def is_locked(self, id: str) -> bool:
        with self._lock:
            entry = self._entries.get(id)
            return entry.locked if entry else False

    def is_protected(self, id: str) -> bool:
        return id in self.PROTECTED_IDS

    def list_entries(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                id: {
                    "locked": entry.locked,
                    "created_at": entry.created_at,
                    "locked_at": entry.locked_at,
                }
                for id, entry in self._entries.items()
            }