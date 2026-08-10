"""Λ.5 DriftMonitor - 4-dimension drift scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import time
import threading
from collections import deque


class DriftDimension(Enum):
    BEHAVIORAL = "behavioral"
    SCHEMA = "schema"
    IDENTITY = "identity"
    TEMPORAL = "temporal"


@dataclass(frozen=True, slots=True)
class DriftScore:
    """Drift score across dimensions."""
    behavioral: float = 0.0
    schema: float = 0.0
    identity: float = 0.0
    temporal: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def overall(self) -> float:
        """Composite drift score (max of dimensions)."""
        return max(self.behavioral, self.schema, self.identity, self.temporal)

    def to_dict(self) -> Dict[str, float]:
        return {
            "behavioral": self.behavioral,
            "schema": self.schema,
            "identity": self.identity,
            "temporal": self.temporal,
            "overall": self.overall,
            "timestamp": self.timestamp,
        }


@dataclass
class DriftMonitor:
    """Monitors 4-dimension drift and publishes DriftScore events."""
    
    module_name: str
    history_size: int = 1000
    _behavioral_baseline: Dict[str, Any] = field(default_factory=dict, init=False)
    _schema_baseline: Dict[str, Any] = field(default_factory=dict, init=False)
    _identity_baseline: Dict[str, Any] = field(default_factory=dict, init=False)
    _temporal_baseline: float = field(default=0.0, init=False)
    _history: deque = field(default_factory=lambda: deque(maxlen=1000), init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _callbacks: List[Callable[[DriftScore], None]] = field(default_factory=list, init=False)

    def __post_init__(self):
        self._temporal_baseline = time.time()

    def set_behavioral_baseline(self, baseline: Dict[str, Any]) -> None:
        with self._lock:
            self._behavioral_baseline = baseline.copy()

    def set_schema_baseline(self, baseline: Dict[str, Any]) -> None:
        with self._lock:
            self._schema_baseline = baseline.copy()

    def set_identity_baseline(self, baseline: Dict[str, Any]) -> None:
        with self._lock:
            self._identity_baseline = baseline.copy()

    def record_observation(
        self,
        behavioral: Optional[Dict[str, Any]] = None,
        schema: Optional[Dict[str, Any]] = None,
        identity: Optional[Dict[str, Any]] = None,
    ) -> DriftScore:
        """Record observation and compute drift score."""
        with self._lock:
            now = time.time()
            
            # Behavioral drift: compare current behavior to baseline
            behavioral_score = 0.0
            if behavioral and self._behavioral_baseline:
                behavioral_score = self._compute_dict_distance(behavioral, self._behavioral_baseline)
            
            # Schema drift: compare schema to baseline
            schema_score = 0.0
            if schema and self._schema_baseline:
                schema_score = self._compute_dict_distance(schema, self._schema_baseline)
            
            # Identity drift: compare identity to baseline
            identity_score = 0.0
            if identity and self._identity_baseline:
                identity_score = self._compute_dict_distance(identity, self._identity_baseline)
            
            # Temporal drift: time since baseline
            temporal_score = min(1.0, (now - self._temporal_baseline) / 86400.0)  # Normalize to 24hr
            
            score = DriftScore(
                behavioral=behavioral_score,
                schema=schema_score,
                identity=identity_score,
                temporal=temporal_score,
                timestamp=now,
            )
            
            self._history.append(score)
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(score)
                except Exception:
                    pass
            
            return score

    def _compute_dict_distance(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> float:
        """Compute normalized distance between two dicts."""
        all_keys = set(current.keys()) | set(baseline.keys())
        if not all_keys:
            return 0.0
        
        differences = 0
        for key in all_keys:
            cv = current.get(key)
            bv = baseline.get(key)
            if cv != bv:
                differences += 1
        
        return differences / len(all_keys)

    def get_current_score(self) -> DriftScore:
        with self._lock:
            return self._history[-1] if self._history else DriftScore()

    def get_history(self) -> List[DriftScore]:
        with self._lock:
            return list(self._history)

    def register_callback(self, callback: Callable[[DriftScore], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def get_trend(self, window: int = 10) -> Dict[str, float]:
        """Get drift trend over recent window."""
        with self._lock:
            if len(self._history) < 2:
                return {"behavioral": 0.0, "schema": 0.0, "identity": 0.0, "temporal": 0.0}
            
            recent = list(self._history)[-window:]
            if len(recent) < 2:
                return {"behavioral": 0.0, "schema": 0.0, "identity": 0.0, "temporal": 0.0}
            
            first = recent[0]
            last = recent[-1]
            
            return {
                "behavioral": last.behavioral - first.behavioral,
                "schema": last.schema - first.schema,
                "identity": last.identity - first.identity,
                "temporal": last.temporal - first.temporal,
            }