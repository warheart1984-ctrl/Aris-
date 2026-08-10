"""Λ.3 CircuitBreaker State Machine - CLOSED/OPEN/HALF-OPEN with Operator-gated reset."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional
import time
import threading


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation, failures counted
    OPEN = "open"           # Failing, requests blocked
    HALF_OPEN = "half_open" # Testing recovery, limited requests


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 30.0
    half_open_max_calls: int = 3


@dataclass
class CircuitBreaker:
    """Circuit breaker with CLOSED/OPEN/HALF-OPEN states and Operator-gated reset."""
    
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _operator_override: bool = field(default=False, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_timeout_transition()
            return self._state

    def _check_timeout_transition(self) -> None:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute function through circuit breaker."""
        with self._lock:
            self._check_timeout_transition()
            
            if self._state == CircuitState.OPEN:
                if not self._operator_override:
                    raise CircuitOpenError(f"Circuit '{self.name}' is OPEN")
                # Operator override allows one call in OPEN state
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitOpenError(f"Circuit '{self.name}' HALF_OPEN call limit reached")
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN

    def force_open(self, operator_id: str) -> None:
        """Operator forces circuit open."""
        with self._lock:
            self._state = CircuitState.OPEN
            self._operator_override = False

    def force_closed(self, operator_id: str) -> None:
        """Operator forces circuit closed (reset)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._operator_override = False

    def allow_override(self, operator_id: str) -> None:
        """Operator grants one-time override for OPEN state."""
        with self._lock:
            self._operator_override = True

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_calls": self._half_open_calls,
                "last_failure_time": self._last_failure_time,
                "operator_override": self._operator_override,
            }


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is blocked."""
    pass