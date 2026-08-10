from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .command_types import (
    AuthorizationResult,
    CommandReceipt,
    CommandRequest,
    CommandSource,
    CommandStatus,
    Intent,
    IntentCategory,
    RiskTier,
    AuthorityContext,
)


@dataclass(frozen=True, slots=True)
class PolicyRule:
    id: str
    name: str
    description: str
    intent_categories: list[IntentCategory]
    intent_names: list[str]
    source_allowlist: list[CommandSource]
    authority_allowlist: list[str]
    risk_tiers: list[RiskTier] = field(default_factory=lambda: [RiskTier.SAFE, RiskTier.SENSITIVE, RiskTier.DESTRUCTIVE])
    requires_confirmation: bool = False
    requires_approval: bool = False
    requires_strong_auth: bool = False
    max_risk_level: str = "high"
    constraints: dict[str, Any] = field(default_factory=dict)


DEFAULT_POLICIES = [
    PolicyRule(
        id="emergency_stop",
        name="Emergency Stop",
        description="Allow emergency stop from any authorized source",
        intent_categories=[IntentCategory.EMERGENCY],
        intent_names=["emergency_stop"],
        source_allowlist=[
            CommandSource.VOICE,
            CommandSource.KEYBOARD,
            CommandSource.MOUSE,
            CommandSource.API,
        ],
        authority_allowlist=["human", "system"],
        risk_tiers=[RiskTier.DESTRUCTIVE],
        requires_confirmation=True,
        requires_strong_auth=True,
        max_risk_level="critical",
    ),
    PolicyRule(
        id="safe_voice_commands",
        name="Safe Voice Commands",
        description="Allow safe voice commands from verified speaker (status, help, repeat)",
        intent_categories=[IntentCategory.QUERY],
        intent_names=["status", "help", "repeat_last"],
        source_allowlist=[CommandSource.VOICE],
        authority_allowlist=["human"],
        risk_tiers=[RiskTier.SAFE],
        requires_confirmation=False,
        requires_strong_auth=False,
        max_risk_level="low",
    ),
    PolicyRule(
        id="sensitive_voice_commands",
        name="Sensitive Voice Commands",
        description="Allow sensitive voice commands with operator confirmation (pause, resume, switch_mode)",
        intent_categories=[IntentCategory.CONTROL, IntentCategory.CONFIGURATION],
        intent_names=["pause", "resume", "switch_mode"],
        source_allowlist=[CommandSource.VOICE],
        authority_allowlist=["human"],
        risk_tiers=[RiskTier.SENSITIVE],
        requires_confirmation=True,
        requires_strong_auth=False,
        max_risk_level="medium",
    ),
    PolicyRule(
        id="approval_gate",
        name="Approval Gate",
        description="Require operator approval for approval decisions",
        intent_categories=[IntentCategory.APPROVAL],
        intent_names=["approve", "reject"],
        source_allowlist=[CommandSource.VOICE, CommandSource.KEYBOARD, CommandSource.MOUSE],
        authority_allowlist=["human"],
        risk_tiers=[RiskTier.DESTRUCTIVE],
        requires_confirmation=True,
        requires_approval=True,
        requires_strong_auth=True,
        max_risk_level="high",
    ),
    PolicyRule(
        id="execution_gate",
        name="Execution Gate",
        description="Require governance review for execution commands",
        intent_categories=[IntentCategory.EXECUTION],
        intent_names=["run", "execute"],
        source_allowlist=[CommandSource.VOICE, CommandSource.KEYBOARD, CommandSource.API],
        authority_allowlist=["human", "agent"],
        risk_tiers=[RiskTier.DESTRUCTIVE],
        requires_confirmation=True,
        requires_strong_auth=True,
        max_risk_level="high",
    ),
    PolicyRule(
        id="navigation_voice",
        name="Navigation Voice Commands",
        description="Allow navigation commands from verified speaker (inspect, show, view)",
        intent_categories=[IntentCategory.NAVIGATION],
        intent_names=["inspect", "show", "view"],
        source_allowlist=[CommandSource.VOICE],
        authority_allowlist=["human"],
        risk_tiers=[RiskTier.SAFE],
        requires_confirmation=False,
        requires_strong_auth=False,
        max_risk_level="low",
    ),
]


class ConstitutionalGate:
    def __init__(
        self,
        *,
        policies: Optional[list[PolicyRule]] = None,
        aris_runtime: Any = None,
    ):
        self.policies = policies or DEFAULT_POLICIES
        self.aris_runtime = aris_runtime
        self._lock = threading.Lock()

    def evaluate(self, command: CommandRequest) -> AuthorizationResult:
        matching_policies = self._find_matching_policies(command)

        if not matching_policies:
            return AuthorizationResult(
                command_id=command.id,
                allowed=False,
                reason="No matching policy found - command rejected by default",
                policy_refs=[],
            )

        for policy in matching_policies:
            result = self._evaluate_policy(command, policy)
            if not result.allowed:
                return result

        return AuthorizationResult(
            command_id=command.id,
            allowed=True,
            reason="Authorized by constitutional gate",
            policy_refs=[p.id for p in matching_policies],
            required_approvals=[],
            constraints={},
        )

    def _find_matching_policies(self, command: CommandRequest) -> list[PolicyRule]:
        matches = []
        for policy in self.policies:
            if command.intent.category in policy.intent_categories:
                if not policy.intent_names or command.intent.name in policy.intent_names:
                    if command.source in policy.source_allowlist:
                        if command.authority.value in policy.authority_allowlist:
                            if command.intent.risk_tier in policy.risk_tiers:
                                matches.append(policy)
        return matches

    def _evaluate_policy(self, command: CommandRequest, policy: PolicyRule) -> AuthorizationResult:
        if command.intent.risk_level == "critical" and policy.max_risk_level != "critical":
            return AuthorizationResult(
                command_id=command.id,
                allowed=False,
                reason=f"Risk level {command.intent.risk_level} exceeds policy maximum",
                policy_refs=[policy.id],
            )

        if policy.requires_confirmation and not command.intent.requires_confirmation:
            return AuthorizationResult(
                command_id=command.id,
                allowed=False,
                reason=f"Policy {policy.id} requires explicit confirmation",
                policy_refs=[policy.id],
                required_approvals=["operator_confirmation"],
            )

        if policy.requires_approval:
            return AuthorizationResult(
                command_id=command.id,
                allowed=False,
                reason=f"Policy {policy.id} requires operator approval",
                policy_refs=[policy.id],
                required_approvals=["operator_approval"],
            )

        if policy.requires_strong_auth:
            if not command.authority_context or not command.authority_context.verified:
                return AuthorizationResult(
                    command_id=command.id,
                    allowed=False,
                    reason=f"Policy {policy.id} requires strong authentication (verified operator)",
                    policy_refs=[policy.id],
                    required_approvals=["strong_authentication"],
                )
            
            if command.intent.risk_tier == RiskTier.DESTRUCTIVE:
                required_privileges = ["operator", "admin"]
                has_privilege = any(p in command.authority_context.privileges for p in required_privileges)
                if not has_privilege:
                    return AuthorizationResult(
                        command_id=command.id,
                        allowed=False,
                        reason=f"Policy {policy.id} requires operator/admin privileges for destructive action",
                        policy_refs=[policy.id],
                        required_approvals=["privilege_escalation"],
                    )

        if self.aris_runtime and hasattr(self.aris_runtime, "review_action"):
            try:
                review_result = self.aris_runtime.review_action(
                    action_type=command.intent.name,
                    payload=command.intent.parameters,
                    source=command.source.value,
                )
                if not review_result.get("allowed", True):
                    return AuthorizationResult(
                        command_id=command.id,
                        allowed=False,
                        reason=review_result.get("reason", "ARIS governance rejected"),
                        policy_refs=[policy.id, "aris_governance"],
                    )
            except Exception:
                pass

        return AuthorizationResult(
            command_id=command.id,
            allowed=True,
            reason=f"Policy {policy.id} satisfied",
            policy_refs=[policy.id],
        )

    def add_policy(self, policy: PolicyRule) -> None:
        with self._lock:
            self.policies.append(policy)

    def remove_policy(self, policy_id: str) -> bool:
        with self._lock:
            for i, p in enumerate(self.policies):
                if p.id == policy_id:
                    self.policies.pop(i)
                    return True
        return False


class EvidenceRecorder:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.evidence_dir = data_root / "command_evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.evidence_dir / "index.jsonl"
        self._lock = threading.Lock()

    def record_command(self, command: CommandRequest) -> str:
        evidence = command.to_evidence()
        evidence["phase"] = "normalized"
        evidence["recorded_at"] = datetime.now(timezone.utc).isoformat()
        evidence_id = f"cmd_{command.id[:8]}_{int(time.time() * 1000)}"

        evidence_file = self.evidence_dir / f"{evidence_id}.json"
        with evidence_file.open("w") as f:
            json.dump(evidence, f, indent=2)

        with self._lock:
            with self.index_path.open("a") as f:
                f.write(json.dumps({"evidence_id": evidence_id, "command_id": command.id, "phase": "normalized"}) + "\n")

        return evidence_id

    def record_authorization(self, command_id: str, auth: AuthorizationResult) -> str:
        evidence = {
            "command_id": command_id,
            "phase": "authorized" if auth.allowed else "rejected",
            "authorization": {
                "allowed": auth.allowed,
                "reason": auth.reason,
                "policy_refs": auth.policy_refs,
                "required_approvals": auth.required_approvals,
                "constraints": auth.constraints,
            },
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        evidence_id = f"auth_{command_id[:8]}_{int(time.time() * 1000)}"

        evidence_file = self.evidence_dir / f"{evidence_id}.json"
        with evidence_file.open("w") as f:
            json.dump(evidence, f, indent=2)

        with self._lock:
            with self.index_path.open("a") as f:
                f.write(json.dumps({"evidence_id": evidence_id, "command_id": command_id, "phase": "authorized"}) + "\n")

        return evidence_id

    def record_execution(self, receipt: CommandReceipt) -> str:
        evidence = {
            "command_id": receipt.command_id,
            "run_id": receipt.run_id,
            "phase": "executed",
            "status": receipt.status.value,
            "execution_result": receipt.execution_result,
            "error": receipt.error,
            "started_at": receipt.started_at,
            "completed_at": receipt.completed_at,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        evidence_id = f"exec_{receipt.command_id[:8]}_{int(time.time() * 1000)}"

        evidence_file = self.evidence_dir / f"{evidence_id}.json"
        with evidence_file.open("w") as f:
            json.dump(evidence, f, indent=2)

        with self._lock:
            with self.index_path.open("a") as f:
                f.write(json.dumps({"evidence_id": evidence_id, "command_id": receipt.command_id, "phase": "executed"}) + "\n")

        return evidence_id

    def get_command_evidence(self, command_id: str) -> list[dict[str, Any]]:
        results = []
        if not self.index_path.exists():
            return results

        with self.index_path.open("r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("command_id") == command_id:
                        evidence_file = self.evidence_dir / f"{entry['evidence_id']}.json"
                        if evidence_file.exists():
                            with evidence_file.open("r") as ef:
                                results.append(json.load(ef))
                except Exception:
                    continue
        return results


class CommandPipeline:
    def __init__(
        self,
        *,
        normalizer: "CommandNormalizer",
        gate: ConstitutionalGate,
        recorder: EvidenceRecorder,
        executor: Callable[[CommandRequest, AuthorizationResult], dict[str, Any]],
        receipt_callback: Optional[Callable[[CommandReceipt], None]] = None,
    ):
        from .command_normalizer import CommandNormalizer
        self.normalizer = normalizer
        self.gate = gate
        self.recorder = recorder
        self.executor = executor
        self.receipt_callback = receipt_callback

    def process(
        self,
        source: CommandSource,
        raw_input: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> CommandReceipt:
        command = self.normalizer.normalize(source, raw_input, context or {})

        self.recorder.record_command(command)

        auth = self.gate.evaluate(command)
        self.recorder.record_authorization(command.id, auth)

        receipt = CommandReceipt(
            command_id=command.id,
            run_id=command.run_id,
            source=command.source,
            authority=command.authority,
            intent=command.intent,
            authorization=auth,
            status=CommandStatus.AUTHORIZED if auth.allowed else CommandStatus.REJECTED,
        )

        if not auth.allowed:
            if self.receipt_callback:
                self.receipt_callback(receipt)
            self.recorder.record_execution(receipt)
            return receipt

        receipt = receipt.mark_executing()

        try:
            result = self.executor(command, auth)
            receipt = receipt.mark_completed(result, evidence_ref="")
            evidence_id = self.recorder.record_execution(receipt)
            receipt = CommandReceipt(
                command_id=receipt.command_id,
                run_id=receipt.run_id,
                source=receipt.source,
                authority=receipt.authority,
                intent=receipt.intent,
                authorization=receipt.authorization,
                execution_result=receipt.execution_result,
                evidence_ref=evidence_id,
                started_at=receipt.started_at,
                completed_at=receipt.completed_at,
                status=receipt.status,
                error=receipt.error,
            )
        except Exception as e:
            receipt = receipt.mark_failed(str(e))
            self.recorder.record_execution(receipt)

        if self.receipt_callback:
            try:
                self.receipt_callback(receipt)
            except Exception:
                pass

        return receipt


def create_constitutional_gate(aris_runtime: Any = None) -> ConstitutionalGate:
    return ConstitutionalGate(aris_runtime=aris_runtime)


def create_evidence_recorder(data_root: Path) -> EvidenceRecorder:
    return EvidenceRecorder(data_root)