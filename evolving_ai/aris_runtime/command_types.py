from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class CommandSource(str, Enum):
    VOICE = "voice"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    API = "api"
    MCP = "mcp"
    AGENT = "agent"
    SCHEDULED = "scheduled"
    SYSTEM = "system"


class CommandAuthority(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"
    AUTOMATED = "automated"


class IntentCategory(str, Enum):
    CONTROL = "control"
    NAVIGATION = "navigation"
    QUERY = "query"
    APPROVAL = "approval"
    EXECUTION = "execution"
    CONFIGURATION = "configuration"
    EMERGENCY = "emergency"


class RiskTier(str, Enum):
    SAFE = "safe"          # Voice alone sufficient (status, help, repeat)
    SENSITIVE = "sensitive"  # Voice + operator confirmation (pause, resume, switch_mode)
    DESTRUCTIVE = "destructive"  # Voice + strong auth + governance (approve, reject, emergency_stop, run)


class CommandStatus(str, Enum):
    RECEIVED = "received"
    NORMALIZED = "normalized"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AuthorityContext:
    operator_id: Optional[str] = None
    operator_name: Optional[str] = None
    verified: bool = False
    confidence: float = 0.0
    privileges: list[str] = field(default_factory=list)
    source_interface: CommandSource = CommandSource.VOICE
    verification_method: str = "voiceprint"
    verification_timestamp: Optional[str] = None
    additional_factors: dict[str, Any] = field(default_factory=dict)
    session_binding: Optional[str] = None


@dataclass(frozen=True, slots=True)
class VoiceInput:
    utterance: str
    audio_fingerprint: Optional[str] = None
    confidence: float = 0.0
    language: str = "en-US"
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    speaker_id: Optional[str] = None
    speaker_verified: bool = False


@dataclass(frozen=True, slots=True)
class Intent:
    category: IntentCategory
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    requires_confirmation: bool = False
    risk_level: str = "low"
    risk_tier: RiskTier = RiskTier.SAFE
    source_substrate: CommandSource = CommandSource.VOICE


@dataclass(frozen=True, slots=True)
class CommandRequest:
    source: CommandSource
    authority: CommandAuthority
    intent: Intent
    raw_input: dict[str, Any]
    authority_context: Optional[AuthorityContext] = None
    id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    speaker_id: Optional[str] = None
    session_id: Optional[str] = None
    requires_governance: bool = True
    status: CommandStatus = CommandStatus.RECEIVED

    def to_evidence(self) -> dict[str, Any]:
        evidence = {
            "command_id": self.id,
            "run_id": self.run_id,
            "source": self.source.value,
            "authority": self.authority.value,
            "intent": self.intent.name,
            "intent_category": self.intent.category.value,
            "risk_tier": self.intent.risk_tier.value,
            "parameters": self.intent.parameters,
            "raw_input": self.raw_input,
            "timestamp": self.timestamp,
            "speaker_id": self.speaker_id,
            "session_id": self.session_id,
            "requires_governance": self.requires_governance,
            "status": self.status.value,
        }
        if self.authority_context:
            evidence["authority_context"] = {
                "operator_id": self.authority_context.operator_id,
                "operator_name": self.authority_context.operator_name,
                "verified": self.authority_context.verified,
                "confidence": self.authority_context.confidence,
                "privileges": self.authority_context.privileges,
                "source_interface": self.authority_context.source_interface.value,
                "verification_method": self.authority_context.verification_method,
                "verification_timestamp": self.authority_context.verification_timestamp,
                "additional_factors": self.authority_context.additional_factors,
                "session_binding": self.authority_context.session_binding,
            }
        return evidence


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    command_id: str
    allowed: bool
    reason: str
    policy_refs: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: str
    run_id: str
    source: CommandSource
    authority: CommandAuthority
    intent: Intent
    authorization: AuthorizationResult
    execution_result: Optional[dict[str, Any]] = None
    evidence_ref: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    status: CommandStatus = CommandStatus.NORMALIZED
    error: Optional[str] = None

    def mark_executing(self) -> "CommandReceipt":
        return CommandReceipt(
            command_id=self.command_id,
            run_id=self.run_id,
            source=self.source,
            authority=self.authority,
            intent=self.intent,
            authorization=self.authorization,
            execution_result=self.execution_result,
            evidence_ref=self.evidence_ref,
            started_at=self.started_at,
            completed_at=None,
            status=CommandStatus.EXECUTING,
            error=self.error,
        )

    def mark_completed(self, result: dict[str, Any], evidence_ref: str) -> "CommandReceipt":
        return CommandReceipt(
            command_id=self.command_id,
            run_id=self.run_id,
            source=self.source,
            authority=self.authority,
            intent=self.intent,
            authorization=self.authorization,
            execution_result=result,
            evidence_ref=evidence_ref,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            status=CommandStatus.COMPLETED,
            error=None,
        )

    def mark_failed(self, error: str) -> "CommandReceipt":
        return CommandReceipt(
            command_id=self.command_id,
            run_id=self.run_id,
            source=self.source,
            authority=self.authority,
            intent=self.intent,
            authorization=self.authorization,
            execution_result=self.execution_result,
            evidence_ref=self.evidence_ref,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            status=CommandStatus.FAILED,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class VoiceAuthConfig:
    enabled: bool = True
    authorized_speaker_ids: list[str] = field(default_factory=list)
    required_confidence: float = 0.85
    enrollment_samples_required: int = 3
    model: str = "resemblyzer"  # or "speechbrain", "custom"


def create_voice_input(
    utterance: str,
    *,
    confidence: float = 1.0,
    audio_fingerprint: Optional[str] = None,
    speaker_id: Optional[str] = None,
    speaker_verified: bool = False,
) -> VoiceInput:
    return VoiceInput(
        utterance=utterance,
        confidence=confidence,
        audio_fingerprint=audio_fingerprint,
        speaker_id=speaker_id,
        speaker_verified=speaker_verified,
    )


def create_intent(
    category: IntentCategory,
    name: str,
    *,
    parameters: Optional[dict[str, Any]] = None,
    confidence: float = 1.0,
    requires_confirmation: bool = False,
    risk_level: str = "low",
    risk_tier: RiskTier = RiskTier.SAFE,
    source_substrate: CommandSource = CommandSource.VOICE,
) -> Intent:
    return Intent(
        category=category,
        name=name,
        parameters=parameters or {},
        confidence=confidence,
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        risk_tier=risk_tier,
        source_substrate=source_substrate,
    )


def create_command_request(
    source: CommandSource,
    authority: CommandAuthority,
    intent: Intent,
    raw_input: dict[str, Any],
    *,
    session_id: Optional[str] = None,
    speaker_id: Optional[str] = None,
    authority_context: Optional[AuthorityContext] = None,
    requires_governance: bool = True,
) -> CommandRequest:
    return CommandRequest(
        source=source,
        authority=authority,
        intent=intent,
        raw_input=raw_input,
        authority_context=authority_context,
        session_id=session_id,
        speaker_id=speaker_id,
        requires_governance=requires_governance,
    )