from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .adapter_protocol import HostDeclaration
from .constants_runtime import (
    DISPOSITION_DEGRADED,
    DISPOSITION_REJECTED,
    DISPOSITION_VALID,
    MUTATION_ACTION_TYPES,
    POST_VERIFICATION_COOLDOWN_SECONDS,
    PROTECTED_IDENTITIES,
)
from .law_context_builder import LawContextBuilder, RuntimeLawContext
from .ul_runtime import ULRuntimeSubstrate


@dataclass(frozen=True, slots=True)
class OverrideReckoningRecord:
    kind: str
    severity: str
    structural_cost: int
    reason: str
    repeated_count: int
    foundational: bool
    recovery_actions: tuple[str, ...]
    quarantine: bool
    block: bool
    created_at: str

    def payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "structural_cost": self.structural_cost,
            "reason": self.reason,
            "repeated_count": self.repeated_count,
            "foundational": self.foundational,
            "recovery_actions": list(self.recovery_actions),
            "quarantine": self.quarantine,
            "block": self.block,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class LawPreflightResult:
    allowed: bool
    disposition: str
    reason: str
    context: RuntimeLawContext
    derived_flags: dict[str, Any]
    override: OverrideReckoningRecord | None = None
    mutation_admission: dict[str, Any] | None = None
    cisiv: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "disposition": self.disposition,
            "reason": self.reason,
            "context": self.context.payload(),
            "derived_flags": dict(self.derived_flags),
            "override": self.override.payload() if self.override else None,
            "mutation_admission": dict(self.mutation_admission or {}),
            "cisiv": dict(self.cisiv or {}),
        }


class OverrideReckoning:
    def __init__(self, ledger: LawLedger) -> None:
        self.ledger = ledger
        self._counts: dict[str, int] = {}

    def record(
        self,
        *,
        kind: str,
        context: RuntimeLawContext,
        reason: str,
        foundational: bool = False,
    ) -> OverrideReckoningRecord:
        key = f"{kind}:{context.claimed_identity}:{context.route_name}:{context.requested_scope}"
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        cost = 10 + (count - 1) * 5 + (20 if foundational else 0)
        severity = "critical" if foundational or count >= 3 else "high" if count == 2 else "elevated"
        record = OverrideReckoningRecord(
            kind=kind,
            severity=severity,
            structural_cost=cost,
            reason=reason,
            repeated_count=count,
            foundational=foundational,
            recovery_actions=(
                "review_required",
                "lineage_required",
                "verification_required",
                "integrity_recheck",
            ),
            quarantine=foundational,
            block=True,
            created_at=datetime.now(UTC).isoformat(),
        )
        self.ledger.record(
            "override_reckoning",
            {
                "context": context.payload(),
                "record": record.payload(),
            },
            require_success=True,
        )
        return record


class RuntimeLaw:
    def __init__(self, *, repo_root: Path, runtime_root: Path, system_name: str = "ARIS") -> None:
        self.repo_root = repo_root
        self.runtime_root = runtime_root
        self.system_name = system_name
        self.observation_windows: dict[str, str] = {}
        self.substrate = ULRuntimeSubstrate(
            runtime_root=runtime_root,
            observation_blocked=self.is_observation_blocked,
        )
        self.ledger = self.substrate.ledger
        self.bootstrap = self.substrate.bootstrap
        self.host_attestation = self.substrate.host_attestation
        self.identity_registry = self.substrate.identity_registry
        self.identity_verifier = self.substrate.identity_verifier
        self.context_builder = self.substrate.context_builder
        self.foundation_store = self.substrate.foundation_store
        self.cisiv = self.substrate.cisiv
        self.reckoning = OverrideReckoning(self.ledger)
        self.mutation_gate = self.substrate.mutation_gate
        self.mutation_broker = self.substrate.mutation_broker
        self.verification_engine = self.substrate.verification_engine
        self.bootstrap_state = self.bootstrap.load()

    def default_host(self, *, session_id: str, actor: str) -> Any:
        host_name = "aris-runtime" if self.system_name.lower().startswith("aris") else "aais-runtime"
        if actor == "api":
            host_name = "aris-api" if self.system_name.lower().startswith("aris") else "aais-api"
        return self.host_attestation.build_internal_host(
            name=host_name,
            version="1.0",
            capabilities=(
                "api",
                "governance",
                "mutation",
                "verification",
                "lineage",
                "identity_preservation",
            ),
            session_binding=session_id,
        )

    def _normalize_capabilities(self, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            raw = [item for item in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            raw = list(value)
        else:
            raw = []
        return self.host_attestation.protocol.normalize_capabilities(raw)

    def resolve_host_declaration(self, action: dict[str, Any], *, actor: str) -> HostDeclaration:
        session_id = str(action.get("session_id") or "system").strip() or "system"
        actor_name = str(actor or "").strip()
        claimed_identity = str(action.get("claimed_identity") or "").strip()
        host_payload = action.get("host")
        host_material_present = any(
            (
                action.get("host_name"),
                action.get("host_version"),
                action.get("host_capabilities"),
                action.get("legitimacy_token"),
                isinstance(host_payload, HostDeclaration),
                isinstance(host_payload, dict) and any(host_payload.values()),
            )
        )
        if isinstance(host_payload, HostDeclaration):
            return host_payload
        if host_material_present:
            payload = host_payload if isinstance(host_payload, dict) else None
            return HostDeclaration(
                name=str((payload or {}).get("name") or action.get("host_name") or "").strip(),
                version=str((payload or {}).get("version") or action.get("host_version") or "").strip(),
                capabilities=self._normalize_capabilities(
                    (payload or {}).get("capabilities", action.get("host_capabilities"))
                ),
                legitimacy_token=str(
                    (payload or {}).get("legitimacy_token", action.get("legitimacy_token") or "")
                ).strip(),
                session_binding=str((payload or {}).get("session_binding") or session_id).strip() or session_id,
                host_class=str((payload or {}).get("host_class") or action.get("host_class") or "external").strip()
                or "external",
            )
        return self.default_host(session_id=session_id, actor=actor_name)

    def is_observation_blocked(self, session_id: str) -> bool:
        value = self.observation_windows.get(str(session_id or "").strip())
        if not value:
            return False
        try:
            blocked_until = datetime.fromisoformat(value)
        except ValueError:
            return False
        return datetime.now(UTC) < blocked_until

    def begin_observation(self, session_id: str) -> None:
        blocked_until = datetime.now(UTC) + timedelta(seconds=POST_VERIFICATION_COOLDOWN_SECONDS)
        self.observation_windows[str(session_id or "").strip()] = blocked_until.isoformat()
        self.ledger.record(
            "observation_mode",
            {
                "session_id": str(session_id or "").strip(),
                "blocked_until": blocked_until.isoformat(),
            },
            require_success=True,
        )

    def clear_observation(self, session_id: str) -> None:
        self.observation_windows.pop(str(session_id or "").strip(), None)

    def record_sensitive_entry(self, *, actor: str, route_name: str) -> None:
        self.ledger.record(
            "sensitive_entry",
            {"actor": actor, "route_name": route_name},
            require_success=True,
        )

    def _boundary_ok(self, context: RuntimeLawContext) -> bool:
        return context.requested_scope in context.allowed_scopes

    def _derived_flags(
        self,
        *,
        context: RuntimeLawContext,
        boundary_ok: bool,
        flagged: bool,
        override: OverrideReckoningRecord | None,
    ) -> dict[str, Any]:
        return {
            "authorized": context.identity_verified and context.host_attested,
            "observed": True,
            "bounded": boundary_ok,
            "uncertain": False,
            "unsafe": bool(context.protected_target),
            "failed": False,
            "flagged": flagged,
            "unverified": False,
            "unauthorized": not (context.identity_verified and context.host_attested),
            "unbounded": not boundary_ok,
            "unobservable": False,
            "out_of_contract": not boundary_ok,
            "bypass_requested": bool(override and override.kind == "law_bypass_attempt"),
            "authority_expansion": bool(override and override.kind == "authority_expansion"),
            "lineage": context.lineage,
            "law_context": context.payload(),
            "law_context_bound": True,
            "verification_present": False,
            "identity_source": context.identity_source,
            "adapter_binding_ok": context.adapter_binding_ok,
            "host_capabilities": list(context.host_capabilities),
        }

    def preflight_action(
        self,
        action: dict[str, Any],
        *,
        actor: str,
        route_name: str,
        repo_changed: bool = False,
        protected_target: bool = False,
    ) -> LawPreflightResult:
        host_declaration = self.resolve_host_declaration(action, actor=actor)
        context = self.context_builder.build_action_context(
            action,
            actor=actor,
            route_name=route_name,
            host=host_declaration,
            repo_changed=repo_changed,
            protected_target=protected_target,
        )
        cisiv = self.cisiv.evaluate(context=context, action=action, phase="preflight")
        if not self.bootstrap_state.ok:
            return LawPreflightResult(
                allowed=False,
                disposition=DISPOSITION_DEGRADED,
                reason=self.bootstrap_state.reason,
                context=context,
                derived_flags=self._derived_flags(
                    context=context,
                    boundary_ok=False,
                    flagged=True,
                    override=None,
                ),
                cisiv=cisiv.payload(),
            )
        self.bootstrap_state = self.bootstrap.load()
        if not self.bootstrap_state.ok:
            return LawPreflightResult(
                allowed=False,
                disposition=DISPOSITION_DEGRADED,
                reason=self.bootstrap_state.reason,
                context=context,
                derived_flags=self._derived_flags(
                    context=context,
                    boundary_ok=False,
                    flagged=True,
                    override=None,
                ),
                cisiv=cisiv.payload(),
            )
        boundary_ok = self._boundary_ok(context)
        override: OverrideReckoningRecord | None = None
        reason = "Runtime law preflight passed."
        allowed = True
        disposition = DISPOSITION_VALID
        if context.code_present and not context.state_present:
            override = self.reckoning.record(
                kind="speech_state_failure",
                context=context,
                reason="Code (1000) cannot arise without valid state (0001).",
                foundational=context.protected_target,
            )
            allowed = False
            disposition = DISPOSITION_REJECTED
            reason = "Code (1000) cannot arise without valid state (0001)."
        elif context.caller_claims:
            foundational = any(
                field in {"verification_present", "1001_pass", "verified", "law_verified"}
                for field in context.caller_claims
            )
            if "claimed_identity" in context.caller_claims:
                override_reason = "Caller attempted to spoof protected identity."
                reason = "Identity claims must be derived internally."
            elif foundational:
                override_reason = "Caller attempted to supply verification-controlled facts."
                reason = "Verification claims must come from the law spine."
            else:
                override_reason = "Caller attempted to supply law-controlled facts."
                reason = "Caller-controlled law fields were rejected."
            override = self.reckoning.record(
                kind="law_bypass_attempt",
                context=context,
                reason=override_reason,
                foundational=foundational,
            )
            allowed = False
            disposition = DISPOSITION_REJECTED
        elif not context.identity_verified or not context.host_attested:
            failure_reason = (
                context.adapter_binding_reason
                if (not context.adapter_binding_ok or not context.host_attested)
                else "Identity or host legitimacy failed."
            )
            override = self.reckoning.record(
                kind="identity_or_host_failure",
                context=context,
                reason=failure_reason,
                foundational=False,
            )
            allowed = False
            disposition = DISPOSITION_REJECTED
            reason = failure_reason
        elif not boundary_ok:
            override = self.reckoning.record(
                kind="authority_expansion",
                context=context,
                reason="Requested scope exceeded allowed scope.",
                foundational=context.protected_target,
            )
            allowed = False
            disposition = DISPOSITION_DEGRADED if not context.protected_target else DISPOSITION_REJECTED
            reason = "Requested scope exceeded lawful authority."
        mutation_admission = None
        if allowed and context.action_type in MUTATION_ACTION_TYPES:
            admission = self.mutation_broker.admit(context=context, action=action)
            mutation_admission = admission.payload()
            if not admission.allowed:
                override = self.reckoning.record(
                    kind="mutation_gate_bypass",
                    context=context,
                    reason=admission.reason,
                    foundational=context.protected_target,
                )
                allowed = False
                disposition = DISPOSITION_REJECTED
                reason = admission.reason
        derived = self._derived_flags(
            context=context,
            boundary_ok=boundary_ok,
            flagged=not allowed,
            override=override,
        )
        ledger_result = self.ledger.record(
            "preflight",
            {
                "context": context.payload(),
                "allowed": allowed,
                "disposition": disposition,
                "reason": reason,
                "override": override.payload() if override else None,
                "mutation_admission": mutation_admission,
                "cisiv": cisiv.payload(),
            },
            require_success=False,
        )
        if not ledger_result.get("recorded", False):
            allowed = False
            disposition = DISPOSITION_REJECTED
            reason = "Sensitive action could not be recorded in the law ledger."
        return LawPreflightResult(
            allowed=allowed,
            disposition=disposition,
            reason=reason,
            context=context,
            derived_flags=derived,
            override=override,
            mutation_admission=mutation_admission,
            cisiv=cisiv.payload(),
        )

    def post_execute(
        self,
        *,
        context: RuntimeLawContext,
        result: dict[str, Any],
        repo_changed: bool,
        payload_ok: bool,
    ) -> dict[str, Any]:
        report = self.verification_engine.verify(
            context=context,
            result=result,
            repo_changed=repo_changed,
            payload_ok=payload_ok,
        )
        override = None
        if report.false_verification:
            override = self.reckoning.record(
                kind="false_verification",
                context=context,
                reason="Verification was claimed by payload instead of the verification engine.",
                foundational=repo_changed,
            )
        if report.passed and context.action_type in MUTATION_ACTION_TYPES:
            self.begin_observation(context.session_id)
        cisiv = self.cisiv.evaluate(
            context=context,
            action=result,
            phase="post_execute",
            verification_passed=report.passed,
        )
        return {
            "report": report.payload(),
            "override": override.payload() if override else None,
            "cisiv": cisiv.payload(),
        }

    def status_payload(self) -> dict[str, Any]:
        return {
            "bootstrap": self.bootstrap_state.payload(),
            "ledger_path": str(self.ledger.path),
            "primitive_inventory": self.substrate.primitive_inventory().payload(),
            "substrate": self.substrate.status_payload(),
        }
