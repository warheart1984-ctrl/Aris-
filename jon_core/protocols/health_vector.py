"""HealthVectorEngine - Dimensional health computation with thresholds and trend detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import threading
from collections import deque


class HealthTrend(Enum):
    """Health trend classification."""
    IMPROVING = "improving"
    STABLE = "stable"
    GRADUAL_DECLINE = "gradual_decline"
    OSCILLATION = "oscillation"
    SUDDEN_DROP = "sudden_drop"
    PLATEAU = "plateau"


class HealthThreshold(Enum):
    """Health threshold levels."""
    CRITICAL = "critical"      # 0.0 - 0.3
    DEGRADED = "degraded"      # 0.3 - 0.5
    CAUTION = "caution"        # 0.5 - 0.7
    NOMINAL = "nominal"        # 0.7 - 0.9
    OPTIMAL = "optimal"        # 0.9 - 1.0


@dataclass
class DimensionalHealth:
    """Health score for a dimension."""
    module: float = 1.0
    lane: float = 1.0
    agent: float = 1.0
    timestamp: float = field(default_factory=time.time)

    def get_contributions(self) -> Dict[str, float]:
        return {"module": self.module, "lane": self.lane, "agent": self.agent}


@dataclass
class SystemHealth:
    """System health vector."""
    overall: float
    dimensional: DimensionalHealth
    threshold: HealthThreshold
    trend: HealthTrend
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "dimensional": self.dimensional.get_contributions(),
            "threshold": self.threshold.value,
            "trend": self.trend.value,
            "timestamp": self.timestamp,
        }


class HealthContributor:
    """Protocol for health contributors."""
    
    def get_dimensional_health(self) -> Dict[str, float]:
        raise NotImplementedError
    
    def get_drift_scores(self) -> Dict[str, float]:
        raise NotImplementedError
    
    def get_contract_compliance_percentage(self) -> float:
        raise NotImplementedError


class HealthVectorEngine:
    """HealthVector engine with min-formula, thresholds, hysteresis, and trend detection."""
    
    # Weights for min-formula: System_Health = min(w_m×Module_avg, w_l×Lane_min, w_a×Agent_min)
    DEFAULT_WEIGHTS = {
        "module": 1.0,
        "lane": 1.0,
        "agent": 1.0,
    }
    
    THRESHOLDS = {
        HealthThreshold.CRITICAL: (0.0, 0.3),
        HealthThreshold.DEGRADED: (0.3, 0.5),
        HealthThreshold.CAUTION: (0.5, 0.7),
        HealthThreshold.NOMINAL: (0.7, 0.9),
        HealthThreshold.OPTIMAL: (0.9, 1.0),
    }
    
    HYSTERESIS_CYCLES = 3

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        computation_cycle_seconds: float = 1.0,
        history_hours: int = 24,
    ):
        self._weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._cycle = computation_cycle_seconds
        self._history_size = int(history_hours * 3600 / computation_cycle_seconds)
        
        self._contributors: Dict[str, HealthContributor] = {}
        self._history: deque = deque(maxlen=self._history_size)
        self._threshold_state = HealthThreshold.NOMINAL
        self._hysteresis_counter = 0
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[SystemHealth], None]] = []

    def register_contributor(self, name: str, contributor: HealthContributor) -> None:
        with self._lock:
            self._contributors[name] = contributor

    def unregister_contributor(self, name: str) -> bool:
        with self._lock:
            return self._contributors.pop(name, None) is not None

    def register_callback(self, callback: Callable[[SystemHealth], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._computation_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _computation_loop(self) -> None:
        while self._running:
            health = self._compute_health()
            self._history.append(health)
            
            # Check threshold transitions with hysteresis
            new_threshold = self._classify_threshold(health.overall)
            if new_threshold != self._threshold_state:
                self._hysteresis_counter += 1
                if self._hysteresis_counter >= self.HYSTERESIS_CYCLES:
                    self._threshold_state = new_threshold
                    self._hysteresis_counter = 0
            else:
                self._hysteresis_counter = 0
            
            # Detect trend
            health.trend = self._detect_trend()
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(health)
                except Exception:
                    pass
            
            time.sleep(self._cycle)

    def _compute_health(self) -> SystemHealth:
        with self._lock:
            if not self._contributors:
                return SystemHealth(
                    overall=1.0,
                    dimensional=DimensionalHealth(),
                    threshold=HealthThreshold.OPTIMAL,
                    trend=HealthTrend.STABLE,
                )
            
            # Collect dimensional health from all contributors
            module_scores = []
            lane_scores = []
            agent_scores = []
            
            for contributor in self._contributors.values():
                dims = contributor.get_dimensional_health()
                module_scores.append(dims.get("module", 1.0))
                lane_scores.append(dims.get("lane", 1.0))
                agent_scores.append(dims.get("agent", 1.0))
            
            module_avg = sum(module_scores) / len(module_scores) if module_scores else 1.0
            lane_min = min(lane_scores) if lane_scores else 1.0
            agent_min = min(agent_scores) if agent_scores else 1.0
            
            # Min-formula: System_Health = min(w_m×Module_avg, w_l×Lane_min, w_a×Agent_min)
            overall = min(
                self._weights["module"] * module_avg,
                self._weights["lane"] * lane_min,
                self._weights["agent"] * agent_min,
            )
            overall = max(0.0, min(1.0, overall))
            
            dimensional = DimensionalHealth(
                module=module_avg,
                lane=lane_min,
                agent=agent_min,
            )
            
            return SystemHealth(
                overall=overall,
                dimensional=dimensional,
                threshold=self._threshold_state,
                trend=HealthTrend.STABLE,  # Will be updated by trend detection
            )

    def _classify_threshold(self, score: float) -> HealthThreshold:
        for threshold, (low, high) in self.THRESHOLDS.items():
            if low <= score < high:
                return threshold
        return HealthThreshold.OPTIMAL if score >= 0.9 else HealthThreshold.CRITICAL

    def _detect_trend(self) -> HealthTrend:
        if len(self._history) < 10:
            return HealthTrend.STABLE
        
        recent = [h.overall for h in list(self._history)[-10:]]
        
        # Simple trend detection
        diffs = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
        avg_diff = sum(diffs) / len(diffs)
        
        if avg_diff > 0.02:
            return HealthTrend.IMPROVING
        elif avg_diff < -0.02:
            # Check for sudden drop
            min_diff = min(diffs)
            if min_diff < -0.15:
                return HealthTrend.SUDDEN_DROP
            # Check for oscillation
            sign_changes = sum(1 for i in range(len(diffs)-1) if diffs[i] * diffs[i+1] < 0)
            if sign_changes >= 3:
                return HealthTrend.OSCILLATION
            return HealthTrend.GRADUAL_DECLINE
        else:
            return HealthTrend.STABLE

    def get_system_health(self) -> SystemHealth:
        with self._lock:
            if self._history:
                return self._history[-1]
            return self._compute_health()

    def get_history(self) -> List[SystemHealth]:
        with self._lock:
            return list(self._history)

    def get_trend(self) -> HealthTrend:
        with self._lock:
            if self._history:
                return self._history[-1].trend
            return HealthTrend.STABLE