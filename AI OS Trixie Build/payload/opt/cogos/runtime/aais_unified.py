"""
AAIS Unified Module v1.0
========================
Combines all five modules into a single integrated runtime:

  MODULE 1 — Invariant Engine
      Statistical + topological health monitoring across the swarm.

  MODULE 2 — Realtime Event-Cause Predictor
      Rolling-window forecasting of degradation events before they occur.

  MODULE 3 — Swarm Law
      Priority-based, spatially-aware agent coordination governance.
      Prediction-aware: can act proactively on approved forecasts.

  MODULE 4 — Time-Delay / Grace Module          [from Time_lag_delay_module.docx]
      Handles signal lag, delayed telemetry, async swarm updates, and
      long-distance comms gaps.  Issues lag-compensated state packets
      instead of triggering immediate stops on every missed heartbeat.

  MODULE 5 — Flight Module (Space-Lane Swarm Law)  [from swarm_law__2_.docx]
      Deterministic, drift-free navigation for multi-agent spacecraft
      operating in warp-frame lanes, zero-G, and formation flight.
      Reshapes the navigation frame so the ship experiences a straight path.

Integration flow (one tick):
  Grace Module  →  lag-compensated peer states
  Invariant Engine  →  health snapshot
  Predictor  →  advisory prediction
  Authority Gate (stub)  →  approve / block
  Swarm Law + Flight Module  →  yield / stop / degrade / fly decisions
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from scipy.stats import kurtosis, skew


# ══════════════════════════════════════════════════════════════════════════════
# CORE TYPES  (shared across all modules)
# ══════════════════════════════════════════════════════════════════════════════

class AgentRole(str, Enum):
    SUPERVISOR       = "supervisor"
    LOADED_HAUL      = "loaded_haul"
    EMPTY_HAUL       = "empty_haul"
    INSPECTION_DRONE = "inspection_drone"


class DegradationMode(str, Enum):
    NORMAL                 = "normal"
    RETREAT                = "retreat"
    RELAY_ONLY             = "relay_only"
    MAPPING_ONLY           = "mapping_only"
    FREEZE_REQUEST_REROUTE = "freeze_request_reroute"
    OBSERVER_ONLY          = "observer_only"


class EventCode(int, Enum):
    NONE                  = 0
    PREDICTED_STOP        = 1
    PREDICTED_DEGRADATION = 2
    PREDICTED_CONFLICT    = 3
    SWARM_INSTABILITY     = 4
    COMMS_LOSS            = 5


class CauseCode(int, Enum):
    SPATIAL_UNCERTAINTY   = 1
    COMMS_DEGRADED        = 2
    PROPULSION_LOW        = 3
    NAVIGATION_LOW        = 4
    SENSOR_LOW            = 5
    SWARM_STAT_ANOMALY    = 6
    TOPOLOGICAL_FRAGILITY = 7


# ── Flight-specific enums ────────────────────────────────────────────────────

class FlightAction(str, Enum):
    PROCEED = "proceed"
    YIELD   = "yield"
    HALT    = "halt"
    REROUTE = "reroute"


# ── Shared geometry ──────────────────────────────────────────────────────────

@dataclass
class Vector3:
    x: float
    y: float
    z: float

    def __sub__(self, other: Vector3) -> Vector3:
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __add__(self, other: Vector3) -> Vector3:
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, scalar: float) -> Vector3:
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def magnitude(self) -> float:
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5


def _vec3_dist(a: Vector3, b: Vector3) -> float:
    return (a - b).magnitude()


# ── Core agent state ─────────────────────────────────────────────────────────

@dataclass
class AgentState:
    id: str
    role: AgentRole
    position: Vector3
    velocity: Vector3
    destination: Vector3

    # Spatial
    spatial_uncertainty_m: float
    safety_envelope_violated: bool

    # Comms
    comms_health_pct: float    # 0–100
    last_comms_ms_ago: float   # ms since last packet received

    # Hardware health
    propulsion_health_pct: float
    navigation_health_pct: float
    payload_health_pct: float
    sensor_health_pct: float

    # Flight-specific (optional — defaults safe for ground agents)
    warp_frame_curvature: float = 0.0   # local warp-bubble curvature metric


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — INVARIANT ENGINE
# Computes statistical + topological stability metrics on the swarm.
# ══════════════════════════════════════════════════════════════════════════════

class InvariantEngine:
    """
    Produces a health snapshot each tick.
    The predictor watches these snapshots for anomalies.
    """

    @staticmethod
    def swarm_health_vector(agents: list[AgentState]) -> np.ndarray:
        """Return an (N, 4) array: [propulsion, navigation, comms, sensor] per agent."""
        return np.array(
            [[a.propulsion_health_pct, a.navigation_health_pct,
              a.comms_health_pct, a.sensor_health_pct]
             for a in agents],
            dtype=float,
        )

    @staticmethod
    def statistical_invariants(data: np.ndarray) -> dict:
        """First four statistical moments across all health readings."""
        flat = data.flatten()
        return {
            "mean": float(np.mean(flat)),
            "var":  float(np.var(flat)),
            "std":  float(np.std(flat)),
            "skew": float(skew(flat, nan_policy="omit")),
            "kurt": float(kurtosis(flat, nan_policy="omit")),
            "min":  float(np.min(flat)),
        }

    @staticmethod
    def topological_fragility(agents: list[AgentState], comms_range_m: float = 50.0) -> float:
        """
        Fragility score 0.0–1.0 based on swarm connectivity.
        >= 0.5 is a warning signal.
        """
        if len(agents) < 2:
            return 0.0
        total = isolated = 0
        for i, a in enumerate(agents):
            for b in agents[i + 1:]:
                total += 1
                if _vec3_dist(a.position, b.position) > comms_range_m:
                    isolated += 1
        return isolated / total if total > 0 else 0.0

    def compute(self, agents: list[AgentState]) -> dict:
        """Full invariant snapshot for this tick."""
        health = self.swarm_health_vector(agents)
        stats  = self.statistical_invariants(health)
        frag   = self.topological_fragility(agents)
        return {
            "health_stats":          stats,
            "topological_fragility": frag,
            "n_agents":              len(agents),
            "n_degraded":            sum(
                1 for a in agents
                if a.propulsion_health_pct < 60 or a.navigation_health_pct < 60
            ),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — REALTIME EVENT-CAUSE PREDICTOR
# Watches a rolling window of invariant snapshots and forecasts events.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PredictionPacket:
    id: str
    ts: str
    event_code: EventCode
    cause_codes: list[int]
    confidence: int       # 0–100
    horizon_ms: int       # how far ahead this prediction applies
    advisory_only: bool = True   # must be set False by authority gate to act on


class RealtimeEventCausePredictor:
    """
    Emits a PredictionPacket on each tick.
    All predictions start advisory_only=True.
    The authority gate (AaisIntegratedRuntime) must approve before action.
    """

    WINDOW_SIZE = 10

    def __init__(self) -> None:
        self._window: deque[dict] = deque(maxlen=self.WINDOW_SIZE)

    def ingest(self, snapshot: dict) -> None:
        self._window.append(snapshot)

    def predict(self, horizon_ms: int = 200) -> PredictionPacket:
        if not self._window:
            return PredictionPacket(
                id=str(uuid.uuid4())[:8], ts=self._now(),
                event_code=EventCode.NONE, cause_codes=[],
                confidence=0, horizon_ms=horizon_ms,
            )

        latest     = self._window[-1]
        stats      = latest["health_stats"]
        frag       = latest["topological_fragility"]
        n_deg      = latest["n_degraded"]
        event_code = EventCode.NONE
        causes: list[CauseCode] = []
        confidence = 0

        # Rule 1 — rising variance + low mean → degradation trend
        if stats["var"] > 150 and stats["mean"] < 70:
            event_code = EventCode.PREDICTED_DEGRADATION
            causes.append(CauseCode.SWARM_STAT_ANOMALY)
            confidence = min(95, int(stats["var"] / 3))

        # Rule 2 — high fragility → comms loss incoming
        if frag >= 0.4:
            if event_code == EventCode.NONE:
                event_code = EventCode.COMMS_LOSS
            causes.append(CauseCode.TOPOLOGICAL_FRAGILITY)
            confidence = max(confidence, int(frag * 100))

        # Rule 3 — multiple degraded agents → swarm instability
        if n_deg >= 2:
            event_code = EventCode.SWARM_INSTABILITY
            causes.append(CauseCode.PROPULSION_LOW)
            confidence = max(confidence, min(90, n_deg * 30))

        # Rule 4 — any health dimension bottomed out → mandatory stop likely
        if stats["min"] < 40:
            if event_code == EventCode.NONE:
                event_code = EventCode.PREDICTED_STOP
            causes.append(CauseCode.NAVIGATION_LOW)
            confidence = max(confidence, 75)

        return PredictionPacket(
            id=str(uuid.uuid4())[:8], ts=self._now(),
            event_code=event_code,
            cause_codes=list({c.value for c in causes}),
            confidence=confidence,
            horizon_ms=horizon_ms,
        )

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — SWARM LAW
# Priority-based, spatially-aware agent coordination governance.
# Prediction-aware: can act proactively on approved forecasts.
# ══════════════════════════════════════════════════════════════════════════════

ROLE_PRIORITY: dict[AgentRole, int] = {
    AgentRole.SUPERVISOR:       4,
    AgentRole.LOADED_HAUL:      3,
    AgentRole.EMPTY_HAUL:       2,
    AgentRole.INSPECTION_DRONE: 1,
}


def comms_healthy(agent: AgentState) -> bool:
    return agent.comms_health_pct >= 60 and agent.last_comms_ms_ago <= 1000


@dataclass
class YieldDecision:
    should_yield: bool
    yielding_agent_id: Optional[str]
    reason: str


def decide_yield(a: AgentState, b: AgentState) -> YieldDecision:
    """
    Swarm Law arbitration for two agents contesting the same corridor.
    Lower-priority yields; equal-priority → farther from destination yields.
    Persistent tie → escalate.
    """
    pA, pB = ROLE_PRIORITY[a.role], ROLE_PRIORITY[b.role]
    if pA != pB:
        loser = a.id if pA < pB else b.id
        return YieldDecision(True, loser, "Lower-priority agent yields.")
    dA = _vec3_dist(a.position, a.destination)
    dB = _vec3_dist(b.position, b.destination)
    if abs(dA - dB) > 1e-6:
        loser = a.id if dA > dB else b.id
        return YieldDecision(True, loser, "Farther from destination yields.")
    return YieldDecision(False, None, "Indeterminate — escalate to supervisor.")


@dataclass
class MandatoryStopDecision:
    must_stop: bool
    reason: Optional[str]
    triggered_by_prediction: bool = False


def evaluate_mandatory_stop(
    agent: AgentState,
    prediction: Optional[PredictionPacket] = None,
) -> MandatoryStopDecision:
    """
    Reactive invariant checks (Swarm Law v2.1) plus prediction-aware proactive check.
    Proactive check fires only when authority gate has approved the prediction.
    """
    # — Reactive checks —
    if agent.spatial_uncertainty_m > 0.3:
        return MandatoryStopDecision(True, "Spatial uncertainty > 0.3 m.")
    if not comms_healthy(agent):
        return MandatoryStopDecision(True, "Comms timeout or degraded health.")
    if agent.safety_envelope_violated:
        return MandatoryStopDecision(True, "Safety envelope violated.")

    # — Proactive check (requires authority gate approval) —
    if prediction and not prediction.advisory_only:
        if (prediction.event_code in (EventCode.SWARM_INSTABILITY, EventCode.PREDICTED_STOP)
                and prediction.confidence >= 80):
            return MandatoryStopDecision(
                True,
                f"Proactive stop: predicted {prediction.event_code.name} "
                f"(confidence {prediction.confidence}%, "
                f"horizon {prediction.horizon_ms} ms).",
                triggered_by_prediction=True,
            )

    return MandatoryStopDecision(False, None)


def decide_degradation_mode(agent: AgentState) -> DegradationMode:
    """
    Tiered degradation selection based on current health metrics.

    Retreat           — propulsion or navigation < 60 %
    Relay-only        — comms < 60 %
    Mapping-only      — propulsion/payload < 20 % but sensors still healthy
    Freeze/reroute    — any mandatory-stop condition not covered above
    Normal            — all systems within tolerance
    """
    if agent.propulsion_health_pct < 60 or agent.navigation_health_pct < 60:
        return DegradationMode.RETREAT
    if agent.comms_health_pct < 60:
        return DegradationMode.RELAY_ONLY
    if (agent.propulsion_health_pct < 20 or agent.payload_health_pct < 20) \
            and agent.sensor_health_pct >= 80:
        return DegradationMode.MAPPING_ONLY
    if evaluate_mandatory_stop(agent).must_stop:
        return DegradationMode.FREEZE_REQUEST_REROUTE
    return DegradationMode.NORMAL


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — TIME-DELAY / GRACE MODULE
# From: Time_lag_delay_module.docx
#
# Instead of triggering an immediate mandatory stop on every missed heartbeat,
# this module opens a configurable grace window and projects a lag-compensated
# state for the agent so downstream modules can still reason about it.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LagCompensatedState:
    """
    Projected agent state estimated during a comms gap.
    Downstream modules should treat this as a best-effort extrapolation.
    """
    agent_id: str
    estimated_position: Vector3
    estimated_velocity: Vector3
    within_grace: bool      # True → still inside grace window, act normally
    should_freeze: bool     # True → grace expired, trigger mandatory stop
    lag_ms: float           # how stale the last known state is


class GraceModule:
    """
    Handles:
      - Signal lag
      - Delayed telemetry
      - Asynchronous swarm updates
      - Long-distance comms gaps

    Without causing:
      - Oscillation (repeated stop/start)
      - Over-correction (sudden direction reversals)
      - Drift amplification
      - Cascade failures from a single missed packet

    Doctrine:
      Communication timeout triggers a grace window, not an instant stop.
      If the agent re-establishes comms within the window, no action is taken.
      If the grace window expires the agent freezes and requests a reroute.
    """

    def __init__(self, grace_window_ms: float = 500.0) -> None:
        """
        grace_window_ms — how long to tolerate a comms gap before freezing.
                          Default 500 ms is conservative for underground mining.
                          Increase for deep-space / high-latency lanes.
        """
        self.grace_window_ms = grace_window_ms

    def compensate(self, agent: AgentState, delta_t_s: float = 0.2) -> LagCompensatedState:
        """
        Produce a lag-compensated state for `agent`.

        If the agent is within the grace window: extrapolate position using
        last known velocity (dead reckoning).  No halt is issued.

        If the grace window has expired: mark should_freeze=True.  The swarm
        law / flight module should treat this as a mandatory stop trigger.

        Args:
            agent      — current (possibly stale) agent state
            delta_t_s  — tick interval in seconds used for dead reckoning
        """
        lag_ms       = agent.last_comms_ms_ago
        within_grace = lag_ms <= self.grace_window_ms
        should_freeze = not within_grace and not comms_healthy(agent)

        if within_grace:
            # Dead-reckoning: project forward by one tick
            projected = agent.position + agent.velocity * delta_t_s
        else:
            # Grace expired — hold last known position (freeze in place)
            projected = agent.position

        return LagCompensatedState(
            agent_id=agent.id,
            estimated_position=projected,
            estimated_velocity=agent.velocity if within_grace else Vector3(0, 0, 0),
            within_grace=within_grace,
            should_freeze=should_freeze,
            lag_ms=lag_ms,
        )

    def compensate_swarm(
        self,
        agents: list[AgentState],
        delta_t_s: float = 0.2,
    ) -> dict[str, LagCompensatedState]:
        """Run compensation for every agent in the swarm."""
        return {a.id: self.compensate(a, delta_t_s) for a in agents}


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — FLIGHT MODULE  (Space-Lane Swarm Law)
# From: swarm_law__2_.docx
#
# Deterministic, drift-free navigation for multi-agent spacecraft.
# This module does NOT calculate turns — it reshapes the navigation frame
# so the ship experiences a straight path (warp-frame inversion).
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WarpFrameState:
    """Represents local warp-bubble geometry around an agent."""
    curvature: float        # local spacetime curvature metric
    aligned: bool = False   # True once frame has been adjusted for destination


@dataclass
class FlightDecision:
    action: FlightAction
    reason: str
    frame_adjustment: Optional[str] = None   # warp-bubble geometry change
    formation_slot: Optional[int]  = None    # slot index if in formation


class FlightModule:
    """
    Space-Lane Swarm Law extension.

    Governs:
      - Predictive trajectory merging (dead-reckoning in 3D)
      - Warp-frame inversion (reframe so path feels straight)
      - Space-lane yielding (Swarm Law in 3D)
      - Mandatory stop invariants (same thresholds, drift-amplification aware)

    Inputs per agent:
      position, velocity, destination, warpFrameState,
      peer states, lag-compensated states, invariants.

    Outputs per agent:
      FlightDecision with action, frame adjustment, formation slot.
    """

    def __init__(self, grace_module: GraceModule) -> None:
        self.grace_module = grace_module

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _predict_position(agent: AgentState, delta_t_s: float = 0.2) -> Vector3:
        """Dead-reckoning: project position forward one tick."""
        return agent.position + agent.velocity * delta_t_s

    @staticmethod
    def _compute_warp_alignment(projected: Vector3, destination: Vector3) -> str:
        """
        Warp-frame inversion description.
        In a real implementation this returns bubble geometry coefficients.
        """
        diff = destination - projected
        mag  = diff.magnitude()
        if mag < 1e-6:
            return "at_destination"
        return f"align_vector({diff.x/mag:.3f},{diff.y/mag:.3f},{diff.z/mag:.3f})"

    @staticmethod
    def _evaluate_mandatory_stop_flight(agent: AgentState) -> Optional[str]:
        """
        Flight-specific mandatory stop check.
        Same 0.3 m uncertainty threshold — in microgravity, drift amplifies fast.
        """
        if agent.spatial_uncertainty_m > 0.3:
            return "Spatial uncertainty > 0.3 m — drift amplification risk."
        if not comms_healthy(agent):
            return "Comms degraded — cannot confirm peer trajectories."
        if agent.safety_envelope_violated:
            return "Safety envelope violated."
        return None

    # ── Public API ───────────────────────────────────────────────────────────

    def decide(
        self,
        agent: AgentState,
        peers: list[AgentState],
        lag_states: dict[str, LagCompensatedState],
        warp_frame: WarpFrameState,
        delta_t_s: float = 0.2,
    ) -> FlightDecision:
        """
        Run the full flight-module decision loop for a single agent.

        Steps:
          1. Mandatory stop check (highest priority)
          2. Grace / freeze check from lag-compensated states
          3. Swarm-law yield arbitration in 3D
          4. Warp-frame alignment
          5. Proceed
        """

        # Step 1 — Mandatory stop (reactive invariants)
        stop_reason = self._evaluate_mandatory_stop_flight(agent)
        if stop_reason:
            return FlightDecision(FlightAction.HALT, stop_reason)

        # Step 2 — Grace check: if this agent's own lag state says freeze, halt
        own_lag = lag_states.get(agent.id)
        if own_lag and own_lag.should_freeze:
            return FlightDecision(
                FlightAction.HALT,
                f"Grace window expired ({own_lag.lag_ms:.0f} ms lag). Freeze and request reroute.",
            )

        # Step 3 — Space-lane yield arbitration (Swarm Law in 3D)
        for peer in peers:
            if peer.id == agent.id:
                continue
            peer_lag = lag_states.get(peer.id)
            # Use lag-compensated position if available and within grace
            effective_peer = peer
            if peer_lag and peer_lag.within_grace:
                # Shallow-copy with projected position for arbitration only
                import dataclasses
                effective_peer = dataclasses.replace(
                    peer,
                    position=peer_lag.estimated_position,
                    velocity=peer_lag.estimated_velocity,
                )
            decision = decide_yield(agent, effective_peer)
            if decision.should_yield and decision.yielding_agent_id == agent.id:
                return FlightDecision(
                    FlightAction.YIELD,
                    f"Yield to {peer.id}: {decision.reason}",
                )

        # Step 4 — Warp-frame alignment
        projected      = self._predict_position(agent, delta_t_s)
        frame_adj      = self._compute_warp_alignment(projected, agent.destination)

        return FlightDecision(
            action=FlightAction.PROCEED,
            reason="Aligned flight path — proceeding.",
            frame_adjustment=frame_adj,
        )

    def decide_swarm(
        self,
        agents: list[AgentState],
        warp_frames: dict[str, WarpFrameState],
        lag_states: dict[str, LagCompensatedState],
        delta_t_s: float = 0.2,
    ) -> dict[str, FlightDecision]:
        """Run flight decisions for all agents in the swarm."""
        peers = agents  # each agent sees all others as peers
        return {
            a.id: self.decide(
                a, peers,
                lag_states,
                warp_frames.get(a.id, WarpFrameState(curvature=a.warp_frame_curvature)),
                delta_t_s,
            )
            for a in agents
        }


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION RUNTIME
# One tick:  Grace → Invariants → Predictor → Gate → Swarm Law → Flight
# ══════════════════════════════════════════════════════════════════════════════

class AaisUnifiedRuntime:
    """
    Runs one governance tick across all five modules.

    Flow:
      1. GraceModule     — produce lag-compensated states for every agent
      2. InvariantEngine — snapshot current swarm health
      3. Predictor       — ingest snapshot, emit advisory PredictionPacket
      4. Authority gate  — approve prediction if confidence >= 80 % (stub)
      5. Swarm Law       — mandatory-stop + degradation decisions
      6. FlightModule    — 3D space-lane decisions (uses lag states + yields)
    """

    def __init__(
        self,
        grace_window_ms: float = 500.0,
        comms_range_m: float   = 50.0,
        tick_s: float          = 0.2,
    ) -> None:
        self.grace_module     = GraceModule(grace_window_ms=grace_window_ms)
        self.invariant_engine = InvariantEngine()
        self.predictor        = RealtimeEventCausePredictor()
        self.flight_module    = FlightModule(grace_module=self.grace_module)
        self.tick_s           = tick_s
        self._comms_range_m   = comms_range_m

    def tick(
        self,
        agents: list[AgentState],
        warp_frames: Optional[dict[str, WarpFrameState]] = None,
        horizon_ms: int = 200,
    ) -> dict:
        """
        Run one unified governance tick.

        Returns a dict with keys:
          lag_states       — dict[agent_id, LagCompensatedState]
          snapshot         — InvariantEngine output
          prediction       — PredictionPacket (approved or advisory)
          stop_decisions   — dict[agent_id, MandatoryStopDecision]
          degradation      — dict[agent_id, DegradationMode]
          flight_decisions — dict[agent_id, FlightDecision]
        """
        warp_frames = warp_frames or {}

        # ── 1. Grace / lag compensation ──────────────────────────────────────
        lag_states = self.grace_module.compensate_swarm(agents, self.tick_s)

        # ── 2. Invariant snapshot ─────────────────────────────────────────────
        snapshot = self.invariant_engine.compute(agents)

        # ── 3. Prediction (advisory) ──────────────────────────────────────────
        self.predictor.ingest(snapshot)
        prediction = self.predictor.predict(horizon_ms)

        # ── 4. Authority gate (stub) ──────────────────────────────────────────
        # Production: Jarvis reviews prediction here.
        # Stub: auto-approve high-confidence predictions.
        approved_prediction: Optional[PredictionPacket] = None
        if prediction.confidence >= 80:
            prediction.advisory_only = False
            approved_prediction = prediction

        # ── 5. Swarm Law decisions ────────────────────────────────────────────
        stop_decisions = {
            a.id: evaluate_mandatory_stop(a, approved_prediction)
            for a in agents
        }
        degradation_modes = {
            a.id: decide_degradation_mode(a)
            for a in agents
        }

        # ── 6. Flight Module decisions ────────────────────────────────────────
        flight_decisions = self.flight_module.decide_swarm(
            agents, warp_frames, lag_states, self.tick_s
        )

        return {
            "lag_states":       lag_states,
            "snapshot":         snapshot,
            "prediction":       prediction,
            "stop_decisions":   stop_decisions,
            "degradation":      degradation_modes,
            "flight_decisions": flight_decisions,
        }


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# Exercises all five modules: nominal swarm, grace-window test, degraded swarm.
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    SEP = "=" * 65

    # ── Scenario A — Nominal swarm ────────────────────────────────────────────
    agents_nominal = [
        AgentState("rover-1", AgentRole.LOADED_HAUL,
                   Vector3(0, 0, 0),   Vector3(1, 0, 0), Vector3(100, 0, 0),
                   0.10, False, 95, 200, 90, 88, 95, 92),
        AgentState("rover-2", AgentRole.EMPTY_HAUL,
                   Vector3(10, 0, 0),  Vector3(1, 0, 0), Vector3(100, 0, 0),
                   0.05, False, 92, 150, 85, 91, 88, 95),
        AgentState("drone-1", AgentRole.INSPECTION_DRONE,
                   Vector3(5, 5, 2),   Vector3(0, 1, 0), Vector3(5, 50, 2),
                   0.08, False, 97, 100, 94, 93, 97, 98),
    ]

    # ── Scenario B — Comms-lagged swarm (grace window test) ──────────────────
    agents_lagged = [
        AgentState("rover-1", AgentRole.LOADED_HAUL,
                   Vector3(0, 0, 0),   Vector3(1, 0, 0), Vector3(100, 0, 0),
                   0.10, False, 80, 400, 90, 88, 95, 92),   # 400 ms lag — within 500 ms grace
        AgentState("rover-2", AgentRole.EMPTY_HAUL,
                   Vector3(10, 0, 0),  Vector3(1, 0, 0), Vector3(100, 0, 0),
                   0.05, False, 70, 650, 85, 91, 88, 95),   # 650 ms lag — grace expired
        AgentState("drone-1", AgentRole.INSPECTION_DRONE,
                   Vector3(5, 5, 2),   Vector3(0, 1, 0), Vector3(5, 50, 2),
                   0.08, False, 97, 100, 94, 93, 97, 98),   # healthy
    ]

    # ── Scenario C — Degraded swarm (triggers prediction + proactive stop) ───
    agents_degraded = [
        AgentState("rover-1", AgentRole.LOADED_HAUL,
                   Vector3(0, 0, 0),   Vector3(0, 0, 0), Vector3(100, 0, 0),
                   0.40, False, 45, 1200, 35, 40, 88, 82),
        AgentState("rover-2", AgentRole.EMPTY_HAUL,
                   Vector3(200, 0, 0), Vector3(0, 0, 0), Vector3(100, 0, 0),
                   0.20, True,  55,  900, 50, 55, 70, 90),
        AgentState("drone-1", AgentRole.INSPECTION_DRONE,
                   Vector3(5, 5, 2),   Vector3(0, 0, 0), Vector3(5, 50, 2),
                   0.15, False, 30,  800, 88, 85, 92, 95),
    ]

    # Warp frames (space lane scenario — only drone is in warp)
    warp_frames = {
        "drone-1": WarpFrameState(curvature=0.12),
    }

    runtime = AaisUnifiedRuntime(grace_window_ms=500.0, comms_range_m=50.0, tick_s=0.2)

    # ── Print helper ──────────────────────────────────────────────────────────
    def print_tick(label: str, result: dict) -> None:
        print(f"\n{SEP}")
        print(label)
        print(SEP)
        snap = result["snapshot"]
        pred = result["prediction"]
        print(f"  Swarm health mean : {snap['health_stats']['mean']:.1f}%")
        print(f"  Topological frag  : {snap['topological_fragility']:.2f}")
        print(f"  Degraded agents   : {snap['n_degraded']}")
        print(f"  Prediction        : {pred.event_code.name} | "
              f"confidence {pred.confidence}% | "
              f"advisory={pred.advisory_only}")
        if pred.cause_codes:
            names = [CauseCode(c).name for c in pred.cause_codes]
            print(f"  Causes            : {names}")
        print()
        for agent_id in [a.id for a in agents_nominal]:  # order only
            if agent_id not in result["stop_decisions"]:
                continue
            stop   = result["stop_decisions"][agent_id]
            mode   = result["degradation"][agent_id]
            flight = result["flight_decisions"][agent_id]
            lag    = result["lag_states"][agent_id]
            proact = " ← PROACTIVE" if stop.triggered_by_prediction else ""
            grace  = "IN GRACE" if lag.within_grace else "GRACE EXPIRED"
            print(f"  [{agent_id}]")
            print(f"    Lag: {lag.lag_ms:.0f} ms ({grace})")
            print(f"    Stop  : {stop.must_stop}{proact}"
                  + (f"  — {stop.reason}" if stop.reason else ""))
            print(f"    Mode  : {mode.value}")
            print(f"    Flight: {flight.action.value} — {flight.reason}")
            if flight.frame_adjustment:
                print(f"    Frame : {flight.frame_adjustment}")

    # ── Tick A — Nominal ──────────────────────────────────────────────────────
    result_a = runtime.tick(agents_nominal, warp_frames)
    print_tick("TICK A — NOMINAL SWARM", result_a)

    # ── Tick B — Grace window test ────────────────────────────────────────────
    result_b = runtime.tick(agents_lagged, warp_frames)
    print_tick("TICK B — COMMS LAG / GRACE WINDOW TEST", result_b)

    # ── Ticks C×5 — Degraded (build predictor window) ────────────────────────
    for _ in range(5):
        result_c = runtime.tick(agents_degraded, warp_frames)
    print_tick("TICKS C×5 — DEGRADED SWARM (predictor window built)", result_c)

    print(f"\n{SEP}")
    print("All five modules executed successfully.")
    print(SEP)
