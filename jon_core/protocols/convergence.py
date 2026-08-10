"""ConvergenceOrchestrator - Epoch timer, monotonic HealthVector check, governed FIFO action queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import time
import threading
import uuid


@dataclass
class ConvergenceAction:
    """Single convergence action."""
    action_id: str
    scope: str
    action_type: str
    payload: Dict[str, Any]
    reversibility: str  # "full", "partial", "none"
    estimated_duration: float  # seconds
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ConvergencePlan:
    """Convergence plan for an epoch."""
    plan_id: str
    affected_scopes: List[str]
    proposed_actions: List[ConvergenceAction]
    epoch_duration: float
    reversibility_assessment: str  # "full", "partial", "none"
    operator_approvals: Dict[str, bool] = field(default_factory=dict)
    health_trajectory: List[float] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class ConvergenceActionQueue:
    """Governed FIFO per scope; sequential execution; cross-scope requires Cascade Guard."""
    
    def __init__(self):
        self._queues: Dict[str, List[ConvergenceAction]] = {}
        self._lock = threading.RLock()
        self._executing: Dict[str, ConvergenceAction] = {}
        self._completed: List[ConvergenceAction] = []

    def enqueue(self, scope: str, action: ConvergenceAction) -> None:
        with self._lock:
            if scope not in self._queues:
                self._queues[scope] = []
            self._queues[scope].append(action)

    def dequeue(self, scope: str) -> Optional[ConvergenceAction]:
        with self._lock:
            if scope not in self._queues or not self._queues[scope]:
                return None
            action = self._queues[scope].pop(0)
            self._executing[scope] = action
            return action

    def complete(self, scope: str, action: ConvergenceAction) -> None:
        with self._lock:
            if scope in self._executing and self._executing[scope].action_id == action.action_id:
                del self._executing[scope]
                self._completed.append(action)

    def get_queue(self, scope: str) -> List[ConvergenceAction]:
        with self._lock:
            return list(self._queues.get(scope, []))

    def get_executing(self, scope: str) -> Optional[ConvergenceAction]:
        with self._lock:
            return self._executing.get(scope)

    def is_empty(self, scope: str) -> bool:
        with self._lock:
            return len(self._queues.get(scope, [])) == 0

    def clear_scope(self, scope: str) -> None:
        with self._lock:
            self._queues.pop(scope, None)
            self._executing.pop(scope, None)


class ConvergenceOrchestrator:
    """Orchestrates convergence with epoch timer enforcement and monotonic progress sampling."""
    
    def __init__(self, health_vector_engine: Optional["HealthVectorEngine"] = None):
        self._hve = health_vector_engine
        self._action_queue = ConvergenceActionQueue()
        self._current_plan: Optional[ConvergencePlan] = None
        self._lock = threading.RLock()
        self._epoch_timer: Optional[threading.Timer] = None
        self._progress_sampler: Optional[threading.Timer] = None
        self._callbacks: List[Callable[[ConvergencePlan, str], None]] = []

    def register_callback(self, callback: Callable[[ConvergencePlan, str], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def create_plan(
        self,
        affected_scopes: List[str],
        proposed_actions: List[ConvergenceAction],
        epoch_duration: float,
        reversibility_assessment: str,
    ) -> ConvergencePlan:
        with self._lock:
            plan = ConvergencePlan(
                plan_id=str(uuid.uuid4())[:8],
                affected_scopes=affected_scopes,
                proposed_actions=proposed_actions,
                epoch_duration=epoch_duration,
                reversibility_assessment=reversibility_assessment,
            )
            
            # Enqueue actions per scope
            for action in proposed_actions:
                self._action_queue.enqueue(action.scope, action)
            
            self._current_plan = plan
            return plan

    def start_epoch(self) -> bool:
        """Start epoch timer and progress sampling."""
        with self._lock:
            if self._current_plan is None:
                return False
            
            plan = self._current_plan
            plan.started_at = time.time()
            
            # Start epoch timer
            self._epoch_timer = threading.Timer(
                plan.epoch_duration,
                self._epoch_timeout,
            )
            self._epoch_timer.daemon = True
            self._epoch_timer.start()
            
            # Start progress sampling (every 10% of epoch)
            sample_interval = plan.epoch_duration / 10.0
            self._start_sampling(sample_interval)
            
            self._notify(plan, "epoch_started")
            return True

    def _start_sampling(self, interval: float) -> None:
        def sample():
            with self._lock:
                if self._current_plan is None:
                    return
                plan = self._current_plan
                
                # Sample health if HVE available
                if self._hve:
                    health = self._hve.get_system_health()
                    plan.health_trajectory.append(health)
                
                # Check for monotonic regression
                if len(plan.health_trajectory) >= 3:
                    recent = plan.health_trajectory[-3:]
                    if recent[2] < recent[1] < recent[0]:
                        # Monotonic regression detected
                        self._notify(plan, "health_regression")
                
                # Reschedule
                self._progress_sampler = threading.Timer(interval, sample)
                self._progress_sampler.daemon = True
                self._progress_sampler.start()
        
        self._progress_sampler = threading.Timer(interval, sample)
        self._progress_sampler.daemon = True
        self._progress_sampler.start()

    def _epoch_timeout(self) -> None:
        with self._lock:
            if self._current_plan:
                plan = self._current_plan
                plan.completed_at = time.time()
                self._notify(plan, "epoch_timeout")
                self._finalize_plan()

    def _finalize_plan(self) -> None:
        if self._epoch_timer:
            self._epoch_timer.cancel()
        if self._progress_sampler:
            self._progress_sampler.cancel()
        self._current_plan = None

    def _notify(self, plan: ConvergencePlan, event: str) -> None:
        for callback in self._callbacks:
            try:
                callback(plan, event)
            except Exception:
                pass

    def get_current_plan(self) -> Optional[ConvergencePlan]:
        with self._lock:
            return self._current_plan

    def get_action_queue(self) -> ConvergenceActionQueue:
        return self._action_queue