from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .command_types import (
    AuthorizationResult,
    CommandReceipt,
    CommandRequest,
    CommandSource,
    CommandStatus,
    CommandAuthority,
    Intent,
    IntentCategory,
    RiskTier,
    VoiceAuthConfig,
    VoiceInput,
    AuthorityContext,
    create_command_request,
    create_intent,
    create_voice_input,
)


class InputSubstrate(ABC):
    @abstractmethod
    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        pass

    @abstractmethod
    def validate(self, raw_input: dict[str, Any]) -> bool:
        pass


class VoiceSubstrate(InputSubstrate):
    def __init__(self, auth_config: VoiceAuthConfig, speaker_verifier: Optional[Callable] = None):
        self.auth_config = auth_config
        self.speaker_verifier = speaker_verifier

    def validate(self, raw_input: dict[str, Any]) -> bool:
        return "utterance" in raw_input

    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        utterance = raw_input.get("utterance", "")
        confidence = raw_input.get("confidence", 1.0)
        audio_fingerprint = raw_input.get("audio_fingerprint")
        speaker_id = raw_input.get("speaker_id")
        speaker_verified = raw_input.get("speaker_verified", False)

        voice_input = create_voice_input(
            utterance=utterance,
            confidence=confidence,
            audio_fingerprint=audio_fingerprint,
            speaker_id=speaker_id,
            speaker_verified=speaker_verified,
        )

        intent = self._parse_intent(voice_input)
        authority = CommandAuthority.HUMAN if voice_input.speaker_verified else CommandAuthority.SYSTEM

        authority_context = None
        if voice_input.speaker_verified and speaker_id:
            authority_context = AuthorityContext(
                operator_id=speaker_id,
                operator_name=raw_input.get("speaker_name"),
                verified=True,
                confidence=confidence,
                privileges=raw_input.get("privileges", ["operator"]),
                source_interface=CommandSource.VOICE,
                verification_method="voiceprint",
                verification_timestamp=datetime.now(timezone.utc).isoformat(),
                session_binding=context.get("session_id"),
            )

        return create_command_request(
            source=CommandSource.VOICE,
            authority=authority,
            intent=intent,
            raw_input={
                "utterance": voice_input.utterance,
                "confidence": voice_input.confidence,
                "audio_fingerprint": voice_input.audio_fingerprint,
                "speaker_id": voice_input.speaker_id,
                "speaker_verified": voice_input.speaker_verified,
                "timestamp": voice_input.timestamp,
                "language": voice_input.language,
                "duration_ms": voice_input.duration_ms,
            },
            authority_context=authority_context,
            session_id=context.get("session_id"),
            speaker_id=voice_input.speaker_id,
            requires_governance=True,
        )

    def _parse_intent(self, voice_input: VoiceInput) -> Intent:
        text = voice_input.utterance.lower().strip()

        intent_map = {
            ("stop", "cancel", "abort", "halt", "kill"): (
                IntentCategory.EMERGENCY, "emergency_stop", {"action": "stop"}, True, "critical", RiskTier.DESTRUCTIVE
            ),
            ("pause", "wait", "hold"): (
                IntentCategory.CONTROL, "pause", {"action": "pause"}, False, "low", RiskTier.SENSITIVE
            ),
            ("resume", "continue", "proceed"): (
                IntentCategory.CONTROL, "resume", {"action": "resume"}, False, "low", RiskTier.SENSITIVE
            ),
            ("repeat", "say again", "what did you say"): (
                IntentCategory.QUERY, "repeat_last", {}, False, "low", RiskTier.SAFE
            ),
            ("status", "how are you", "health", "what's happening"): (
                IntentCategory.QUERY, "status", {}, False, "low", RiskTier.SAFE
            ),
            ("help", "what can you do", "commands"): (
                IntentCategory.QUERY, "help", {}, False, "low", RiskTier.SAFE
            ),
            ("approve", "yes", "ok", "accept", "confirm"): (
                IntentCategory.APPROVAL, "approve", {"decision": True}, True, "medium", RiskTier.DESTRUCTIVE
            ),
            ("reject", "no", "deny", "decline"): (
                IntentCategory.APPROVAL, "reject", {"decision": False}, True, "medium", RiskTier.DESTRUCTIVE
            ),
            ("run", "execute", "start", "do it"): (
                IntentCategory.EXECUTION, "run", {"action": "run"}, True, "medium", RiskTier.DESTRUCTIVE
            ),
            ("inspect", "show", "view", "look at", "examine"): (
                IntentCategory.NAVIGATION, "inspect", {}, False, "low", RiskTier.SAFE
            ),
        }

        for keywords, (category, name, params, confirm, risk, risk_tier) in intent_map.items():
            if any(kw in text for kw in keywords):
                if "switch" in text or "mode" in text or "brain" in text:
                    mode = self._extract_mode(text)
                    if mode:
                        return create_intent(
                            IntentCategory.CONFIGURATION,
                            "switch_mode",
                            parameters={"mode": mode},
                            requires_confirmation=True,
                            risk_level="medium",
                            risk_tier=RiskTier.SENSITIVE,
                        )

                return create_intent(
                    category, name, parameters=params, requires_confirmation=confirm, risk_level=risk, risk_tier=risk_tier
                )

        return create_intent(
            IntentCategory.QUERY,
            "unknown",
            parameters={"raw_text": text},
            confidence=voice_input.confidence * 0.5,
            risk_tier=RiskTier.SAFE,
        )

    def _extract_mode(self, text: str) -> Optional[str]:
        modes = ["chat", "build", "evaluate", "deep", "agent", "debug"]
        for mode in modes:
            if mode in text:
                return mode.capitalize()
        return None


class KeyboardSubstrate(InputSubstrate):
    def validate(self, raw_input: dict[str, Any]) -> bool:
        return "key" in raw_input or "action" in raw_input

    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        action = raw_input.get("action") or raw_input.get("key", "")
        
        risk_tier = RiskTier.SAFE
        if action in {"pause", "resume", "switch_mode"}:
            risk_tier = RiskTier.SENSITIVE
        elif action in {"approve", "reject", "emergency_stop", "run"}:
            risk_tier = RiskTier.DESTRUCTIVE
        
        intent = create_intent(
            IntentCategory.CONTROL,
            action,
            parameters=raw_input.get("parameters", {}),
            requires_confirmation=raw_input.get("confirm", False),
            risk_tier=risk_tier,
        )
        
        authority_context = AuthorityContext(
            operator_id=raw_input.get("operator_id"),
            operator_name=raw_input.get("operator_name"),
            verified=raw_input.get("verified", False),
            confidence=raw_input.get("confidence", 1.0),
            privileges=raw_input.get("privileges", ["operator"]),
            source_interface=CommandSource.KEYBOARD,
            verification_method=raw_input.get("verification_method", "keyboard"),
            verification_timestamp=datetime.now(timezone.utc).isoformat(),
            session_binding=context.get("session_id"),
        )
        
        return create_command_request(
            source=CommandSource.KEYBOARD,
            authority=CommandAuthority.HUMAN,
            intent=intent,
            raw_input=raw_input,
            authority_context=authority_context,
            session_id=context.get("session_id"),
        )


class MouseSubstrate(InputSubstrate):
    def validate(self, raw_input: dict[str, Any]) -> bool:
        return "click" in raw_input or "action" in raw_input

    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        action = raw_input.get("action", "click")
        
        risk_tier = RiskTier.SAFE
        if action in {"approve_click", "reject_click"}:
            risk_tier = RiskTier.DESTRUCTIVE
        
        intent = create_intent(
            IntentCategory.NAVIGATION,
            action,
            parameters=raw_input.get("parameters", {}),
            risk_tier=risk_tier,
        )
        
        authority_context = AuthorityContext(
            operator_id=raw_input.get("operator_id"),
            operator_name=raw_input.get("operator_name"),
            verified=raw_input.get("verified", False),
            confidence=raw_input.get("confidence", 1.0),
            privileges=raw_input.get("privileges", ["operator"]),
            source_interface=CommandSource.MOUSE,
            verification_method=raw_input.get("verification_method", "mouse"),
            verification_timestamp=datetime.now(timezone.utc).isoformat(),
            session_binding=context.get("session_id"),
        )
        
        return create_command_request(
            source=CommandSource.MOUSE,
            authority=CommandAuthority.HUMAN,
            intent=intent,
            raw_input=raw_input,
            authority_context=authority_context,
            session_id=context.get("session_id"),
        )


class APISubstrate(InputSubstrate):
    def validate(self, raw_input: dict[str, Any]) -> bool:
        return "endpoint" in raw_input or "method" in raw_input

    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        risk_level = raw_input.get("risk", "medium")
        risk_tier = RiskTier.SAFE
        if risk_level in {"high", "critical"}:
            risk_tier = RiskTier.DESTRUCTIVE
        elif risk_level == "medium":
            risk_tier = RiskTier.SENSITIVE
        
        intent = create_intent(
            IntentCategory.EXECUTION,
            raw_input.get("method", "api_call"),
            parameters=raw_input.get("params", {}),
            requires_confirmation=raw_input.get("confirm", False),
            risk_level=risk_level,
            risk_tier=risk_tier,
        )
        
        authority_context = AuthorityContext(
            operator_id=raw_input.get("operator_id"),
            operator_name=raw_input.get("operator_name"),
            verified=raw_input.get("verified", False),
            confidence=raw_input.get("confidence", 1.0),
            privileges=raw_input.get("privileges", ["api"]),
            source_interface=CommandSource.API,
            verification_method=raw_input.get("verification_method", "api_key"),
            verification_timestamp=datetime.now(timezone.utc).isoformat(),
            session_binding=context.get("session_id"),
            additional_factors={"api_key_present": "api_key" in raw_input},
        )
        
        return create_command_request(
            source=CommandSource.API,
            authority=CommandAuthority.AUTOMATED,
            intent=intent,
            raw_input=raw_input,
            authority_context=authority_context,
            session_id=context.get("session_id"),
        )


class AgentSubstrate(InputSubstrate):
    def validate(self, raw_input: dict[str, Any]) -> bool:
        return "agent_id" in raw_input

    def normalize(self, raw_input: dict[str, Any], context: dict[str, Any]) -> CommandRequest:
        risk_level = raw_input.get("risk", "high")
        risk_tier = RiskTier.DESTRUCTIVE if risk_level in {"high", "critical"} else RiskTier.SENSITIVE
        
        intent = create_intent(
            IntentCategory.EXECUTION,
            raw_input.get("action", "agent_task"),
            parameters=raw_input.get("parameters", {}),
            requires_confirmation=raw_input.get("confirm", True),
            risk_level=risk_level,
            risk_tier=risk_tier,
        )
        
        authority_context = AuthorityContext(
            operator_id=raw_input.get("agent_id"),
            operator_name=raw_input.get("agent_name"),
            verified=raw_input.get("verified", False),
            confidence=raw_input.get("confidence", 1.0),
            privileges=raw_input.get("privileges", ["agent"]),
            source_interface=CommandSource.AGENT,
            verification_method=raw_input.get("verification_method", "agent_token"),
            verification_timestamp=datetime.now(timezone.utc).isoformat(),
            session_binding=context.get("session_id"),
        )
        
        return create_command_request(
            source=CommandSource.AGENT,
            authority=CommandAuthority.AGENT,
            intent=intent,
            raw_input=raw_input,
            authority_context=authority_context,
            session_id=context.get("session_id"),
        )


class CommandNormalizer:
    def __init__(
        self,
        *,
        voice_auth: VoiceAuthConfig,
        speaker_verifier: Optional[Callable] = None,
        receipt_callback: Optional[Callable[[CommandReceipt], None]] = None,
    ):
        self.substrates: dict[CommandSource, InputSubstrate] = {
            CommandSource.VOICE: VoiceSubstrate(voice_auth, speaker_verifier),
            CommandSource.KEYBOARD: KeyboardSubstrate(),
            CommandSource.MOUSE: MouseSubstrate(),
            CommandSource.API: APISubstrate(),
            CommandSource.AGENT: AgentSubstrate(),
        }
        self.receipt_callback = receipt_callback
        self._lock = threading.Lock()

    def register_substrate(self, source: CommandSource, substrate: InputSubstrate) -> None:
        with self._lock:
            self.substrates[source] = substrate

    def normalize(
        self,
        source: CommandSource,
        raw_input: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> CommandRequest:
        substrate = self.substrates.get(source)
        if not substrate:
            raise ValueError(f"No substrate registered for source: {source}")

        if not substrate.validate(raw_input):
            raise ValueError(f"Invalid input for substrate {source}: {raw_input}")

        context = context or {}
        command = substrate.normalize(raw_input, context)

        receipt = CommandReceipt(
            command_id=command.id,
            run_id=command.run_id,
            source=command.source,
            authority=command.authority,
            intent=command.intent,
            authorization=AuthorizationResult(
                command_id=command.id,
                allowed=True,
                reason="Normalized successfully",
            ),
            status=CommandStatus.NORMALIZED,
        )

        if self.receipt_callback:
            try:
                self.receipt_callback(receipt)
            except Exception:
                pass

        return command


def create_default_normalizer(
    *,
    voice_auth: Optional[VoiceAuthConfig] = None,
    speaker_verifier: Optional[Callable] = None,
    receipt_callback: Optional[Callable[[CommandReceipt], None]] = None,
) -> CommandNormalizer:
    auth = voice_auth or VoiceAuthConfig()
    return CommandNormalizer(
        voice_auth=auth,
        speaker_verifier=speaker_verifier,
        receipt_callback=receipt_callback,
    )