"""Metrics - Constitutional metrics registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import threading


@dataclass
class MetricDefinition:
    """Constitutional metric definition."""
    name: str
    source_law: str  # Λ.1-Λ.7, Δ, Shield
    metric_type: str  # gauge, counter, histogram
    description: str
    tags: List[str] = field(default_factory=list)


class ConstitutionalMetricsRegistry:
    """Central registry for all Λ/Δ/Shield metrics."""
    
    def __init__(self):
        self._definitions: Dict[str, MetricDefinition] = {}
        self._values: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._register_core_metrics()

    def _register_core_metrics(self) -> None:
        """Register core constitutional metrics."""
        core_metrics = [
            MetricDefinition("determinism_checks_total", "Λ.1", "counter", "Total determinism checks"),
            MetricDefinition("determinism_violations", "Λ.1", "counter", "Determinism violations detected"),
            MetricDefinition("audit_records_emitted", "Λ.2", "counter", "Audit records emitted"),
            MetricDefinition("audit_chain_integrity", "Λ.2", "gauge", "Audit chain integrity (0/1)"),
            MetricDefinition("circuit_breaker_state", "Λ.3", "gauge", "Circuit breaker state (0=closed, 1=half-open, 2=open)"),
            MetricDefinition("identity_leaks_detected", "Λ.4", "counter", "Cross-identity leaks detected"),
            MetricDefinition("drift_score_behavioral", "Λ.5", "gauge", "Behavioral drift score"),
            MetricDefinition("drift_score_schema", "Λ.5", "gauge", "Schema drift score"),
            MetricDefinition("drift_score_identity", "Λ.5", "gauge", "Identity drift score"),
            MetricDefinition("drift_score_temporal", "Λ.5", "gauge", "Temporal drift score"),
            MetricDefinition("interrupt_requests", "Λ.6", "counter", "Interrupt requests received"),
            MetricDefinition("interrupt_ack_latency_ms", "Λ.6", "histogram", "Interrupt acknowledgment latency"),
            MetricDefinition("kill_switch_activations", "Λ.6", "counter", "Kill switch activations"),
            MetricDefinition("supremacy_validations", "Λ.7", "counter", "Supremacy validations performed"),
            MetricDefinition("supremacy_rejections", "Λ.7", "counter", "Supremacy rejections"),
            MetricDefinition("speech_chain_transitions", "SpeechChain", "counter", "Speech chain phase transitions"),
            MetricDefinition("cisiv_evaluations", "CISIV", "counter", "CISIV governance evaluations"),
            MetricDefinition("cisiv_blocked", "CISIV", "counter", "CISIV blocked evaluations"),
            MetricDefinition("stabilization_transitions", "Δ", "counter", "System state transitions"),
            MetricDefinition("convergence_epochs", "Δ", "counter", "Convergence epochs completed"),
            MetricDefinition("health_vector_system", "Δ", "gauge", "System health vector"),
            MetricDefinition("mutation_admissions", "MutationGate", "counter", "Mutation admissions"),
            MetricDefinition("hall_routing_discard", "HallRouter", "counter", "Hall of Discard entries"),
            MetricDefinition("hall_routing_shame", "HallRouter", "counter", "Hall of Shame entries"),
            MetricDefinition("hall_routing_fame", "HallRouter", "counter", "Hall of Fame entries"),
            MetricDefinition("override_reckoning_records", "OverrideReckoning", "counter", "Override records"),
            MetricDefinition("shield_verdicts_worthy", "Shield", "counter", "Worthy verdicts"),
            MetricDefinition("shield_verdicts_conditional", "Shield", "counter", "Conditional verdicts"),
            MetricDefinition("shield_verdicts_rejected", "Shield", "counter", "Rejected verdicts"),
            MetricDefinition("shield_verdicts_forbidden", "Shield", "counter", "Forbidden verdicts"),
        ]
        
        for metric in core_metrics:
            self._definitions[metric.name] = metric
            self._values[metric.name] = 0

    def register(self, definition: MetricDefinition) -> None:
        with self._lock:
            self._definitions[definition.name] = definition
            self._values[definition.name] = 0

    def increment(self, name: str, value: float = 1, tags: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            if name in self._values:
                self._values[name] += value

    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            if name in self._values:
                self._values[name] = value

    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            key = f"{name}_sum"
            if key not in self._values:
                self._values[key] = 0
                self._values[f"{name}_count"] = 0
            self._values[key] += value
            self._values[f"{name}_count"] += 1

    def get(self, name: str) -> Any:
        with self._lock:
            return self._values.get(name)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def get_definition(self, name: str) -> Optional[MetricDefinition]:
        with self._lock:
            return self._definitions.get(name)

    def list_definitions(self) -> List[MetricDefinition]:
        with self._lock:
            return list(self._definitions.values())

    def emit_standard_format(self) -> Dict[str, Any]:
        """Emit all metrics in standardized format."""
        with self._lock:
            return {
                "timestamp": time.time(),
                "metrics": {
                    name: {
                        "value": value,
                        "definition": self._definitions[name].__dict__ if name in self._definitions else None,
                    }
                    for name, value in self._values.items()
                }
            }