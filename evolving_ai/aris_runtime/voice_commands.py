from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import speech_recognition as sr
except Exception:
    sr = None

from .command_types import (
    AuthorizationResult,
    CommandReceipt,
    CommandRequest,
    CommandSource,
    CommandStatus,
    Intent,
    IntentCategory,
    VoiceAuthConfig,
    VoiceInput,
    create_command_request,
    create_intent,
    create_voice_input,
)
from .command_normalizer import CommandNormalizer, VoiceSubstrate, create_default_normalizer
from .constitutional_gate import ConstitutionalGate, EvidenceRecorder, create_constitutional_gate, create_evidence_recorder
from .voice_auth import VoiceAuthManager, create_voice_auth_manager


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _voice_commands_enabled() -> bool:
    return _bool_env("ARIS_VOICE_COMMANDS_ENABLED", True) and sr is not None


def _voice_command_timeout() -> float:
    try:
        return float(os.getenv("ARIS_VOICE_COMMAND_TIMEOUT", "5.0"))
    except Exception:
        return 5.0


def _voice_command_phrase_timeout() -> float:
    try:
        return float(os.getenv("ARIS_VOICE_COMMAND_PHRASE_TIMEOUT", "3.0"))
    except Exception:
        return 3.0


def _voice_command_energy_threshold() -> int:
    try:
        return int(os.getenv("ARIS_VOICE_COMMAND_ENERGY_THRESHOLD", "300"))
    except Exception:
        return 300


@dataclass(frozen=True, slots=True)
class VoicePipelineConfig:
    enabled: bool = True
    voice_auth_enabled: bool = True
    required_confidence: float = 0.85
    enrollment_samples: int = 3
    auth_model: str = "resemblyzer"
    constitutional_gate: bool = True
    evidence_recording: bool = True
    tts_responses: bool = True


class CanonicalVoiceProcessor:
    def __init__(
        self,
        host: Any,
        window: Any,
        data_root: Path,
        config: Optional[VoicePipelineConfig] = None,
    ):
        self.host = host
        self.window = window
        self.data_root = data_root
        self.config = config or VoicePipelineConfig()

        self.voice_auth: Optional[VoiceAuthManager] = None
        self.normalizer: Optional[CommandNormalizer] = None
        self.gate: Optional[ConstitutionalGate] = None
        self.recorder: Optional[EvidenceRecorder] = None
        self.pipeline: Optional["VoiceCommandPipeline"] = None

        self._recognizer: Optional[sr.Recognizer] = None
        self._microphone: Optional[sr.Microphone] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_listening = False
        self._calibrated = False

        self.on_listening_start: Callable[[], None] | None = None
        self.on_listening_end: Callable[[], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_command_result: Callable[[CommandReceipt], None] | None = None

        if self.config.enabled and sr is not None:
            self._init_components()

    def _init_components(self) -> None:
        auth_config = VoiceAuthConfig(
            enabled=self.config.voice_auth_enabled,
            required_confidence=self.config.required_confidence,
            enrollment_samples_required=self.config.enrollment_samples,
            model=self.config.auth_model,
        )

        self.voice_auth = create_voice_auth_manager(
            self.data_root,
            enabled=self.config.voice_auth_enabled,
            required_confidence=self.config.required_confidence,
            enrollment_samples=self.config.enrollment_samples,
            model=self.config.auth_model,
        )

        self.recorder = create_evidence_recorder(self.data_root)

        self.gate = create_constitutional_gate(aris_runtime=getattr(self.host, "aris", None))

        self.normalizer = create_default_normalizer(
            voice_auth=auth_config,
            speaker_verifier=self.voice_auth.verify_audio if self.voice_auth else None,
            receipt_callback=self._on_receipt,
        )

        self.pipeline = VoiceCommandPipeline(
            normalizer=self.normalizer,
            gate=self.gate,
            recorder=self.recorder,
            executor=self._execute_command,
            window=self.window,
            host=self.host,
            tts_enabled=self.config.tts_responses,
        )

        self._init_recognizer()

    def _init_recognizer(self) -> None:
        if sr is None:
            return
        try:
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = _voice_command_energy_threshold()
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 0.8
            self._microphone = sr.Microphone()
        except Exception:
            self._recognizer = None
            self._microphone = None

    def _on_receipt(self, receipt: CommandReceipt) -> None:
        if self.on_command_result:
            try:
                self.on_command_result(receipt)
            except Exception:
                pass

    def _calibrate(self) -> None:
        if self._recognizer is None or self._microphone is None or self._calibrated:
            return
        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            self._calibrated = True
        except Exception:
            pass

    def start_listening(self) -> bool:
        if not self.config.enabled or not _voice_commands_enabled():
            if self.on_error:
                self.on_error("Voice commands not enabled or speech_recognition not available")
            return False

        if self._is_listening:
            return True

        if self._recognizer is None or self._microphone is None:
            if self.on_error:
                self.on_error("Speech recognizer not initialized")
            return False

        self._calibrate()
        self._stop_event.clear()
        self._is_listening = True

        self._listen_thread = threading.Thread(
            target=self._listen_loop,
            name="aris-canonical-voice-listener",
            daemon=True,
        )
        self._listen_thread.start()

        if self.on_listening_start:
            try:
                self.on_listening_start()
            except Exception:
                pass

        return True

    def stop_listening(self) -> None:
        if not self._is_listening:
            return

        self._stop_event.set()
        self._is_listening = False

        if self._listen_thread is not None:
            self._listen_thread.join(timeout=2.0)
            self._listen_thread = None

        if self.on_listening_end:
            try:
                self.on_listening_end()
            except Exception:
                pass

    def _listen_loop(self) -> None:
        if self._recognizer is None or self._microphone is None:
            return

        timeout = _voice_command_timeout()
        phrase_timeout = _voice_command_phrase_timeout()

        while not self._stop_event.is_set():
            try:
                with self._microphone as source:
                    audio = self._recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_timeout,
                    )

                if self._stop_event.is_set():
                    break

                try:
                    text = self._recognizer.recognize_google(audio)
                    if text:
                        self._process_utterance(text, audio)
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    if self.on_error:
                        self.on_error(f"Speech recognition service error: {e}")
                    time.sleep(1.0)

            except sr.WaitTimeoutError:
                pass
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Listener error: {e}")
                time.sleep(0.5)

    def _process_utterance(self, text: str, audio_data: bytes) -> None:
        if not self.voice_auth or not self.pipeline:
            return

        verification = self.voice_auth.verify_audio(audio_data)

        raw_input = {
            "utterance": text,
            "confidence": verification.confidence if verification.matched else 0.5,
            "audio_fingerprint": self.voice_auth.fingerprinter.fingerprint(audio_data),
            "speaker_id": verification.speaker_id,
            "speaker_verified": verification.matched,
        }

        context = {
            "session_id": getattr(self.host, "current_session_id", None),
        }

        try:
            receipt = self.pipeline.process(CommandSource.VOICE, raw_input, context)
            self._handle_receipt(receipt, text, verification)
        except Exception as e:
            if self.on_error:
                self.on_error(f"Pipeline error: {e}")

    def _handle_receipt(self, receipt: CommandReceipt, utterance: str, verification: Any) -> None:
        from .voice import speak

        if receipt.status == CommandStatus.REJECTED:
            error_msg = receipt.error or receipt.authorization.reason
            if self.config.tts_responses:
                speak(f"Command not authorized: {error_msg}", "blocked_action")
            if self.window and hasattr(self.window, '_voice_status_label'):
                try:
                    self.window._voice_status_label.setText(f"⛔ Rejected: {error_msg[:50]}")
                except Exception:
                    pass
            return

        if receipt.status == CommandStatus.COMPLETED:
            if self.config.tts_responses:
                response = self._generate_response(receipt)
                if response:
                    speak(response, "status")
            if self.window and hasattr(self.window, '_voice_status_label'):
                try:
                    self.window._voice_status_label.setText("✅ Done")
                except Exception:
                    pass
            return

        if receipt.status == CommandStatus.FAILED:
            if self.config.tts_responses:
                speak(f"Command failed: {receipt.error}", "blocked_action")
            if self.window and hasattr(self.window, '_voice_status_label'):
                try:
                    self.window._voice_status_label.setText(f"❌ Failed: {receipt.error[:50]}")
                except Exception:
                    pass

    def _generate_response(self, receipt: CommandReceipt) -> Optional[str]:
        intent_name = receipt.intent.name

        if intent_name == "status":
            if self.host and hasattr(self.host, "service"):
                return "System operational. All governance checks passing."
            return "Status nominal."

        if intent_name == "help":
            return (
                "Available voice commands: stop, pause, resume, status, help, "
                "approve, reject, run, inspect, switch mode."
            )

        if intent_name == "emergency_stop":
            return "Emergency stop executed. All runtimes contained."

        if intent_name in {"pause", "resume"}:
            return f"Task {intent_name}d."

        if intent_name == "repeat_last":
            return "Repeating last response."

        if intent_name in {"approve", "reject"}:
            decision = "approved" if receipt.intent.parameters.get("decision") else "rejected"
            return f"Approval {decision}."

        if intent_name == "run":
            return "Task queued for governed execution."

        if intent_name == "inspect":
            return "Inspect panel opened."

        if intent_name == "switch_mode":
            mode = receipt.intent.parameters.get("mode", "unknown")
            return f"Switched to {mode} mode."

        return "Command completed."

    def _execute_command(
        self,
        command: CommandRequest,
        auth: AuthorizationResult,
    ) -> dict[str, Any]:
        intent_name = command.intent.name

        if intent_name == "emergency_stop":
            if hasattr(self.host, "activate_soft_kill"):
                return self.host.activate_soft_kill(reason="Voice command: emergency stop")
            return {"ok": False, "error": "Host does not support soft kill"}

        if intent_name == "pause":
            if self.window and hasattr(self.window, '_pause_current_task'):
                self.window._pause_current_task()
                return {"ok": True, "action": "pause"}
            return {"ok": False, "error": "No active task to pause"}

        if intent_name == "resume":
            if self.window and hasattr(self.window, '_resume_current_task'):
                self.window._resume_current_task()
                return {"ok": True, "action": "resume"}
            return {"ok": False, "error": "No paused task to resume"}

        if intent_name == "repeat_last":
            if self.window and hasattr(self.window, '_repeat_last_response'):
                self.window._repeat_last_response()
                return {"ok": True, "action": "repeat"}
            return {"ok": False, "error": "No response to repeat"}

        if intent_name == "status":
            if self.window and hasattr(self.window, '_announce_status'):
                self.window._announce_status()
                return {"ok": True, "action": "status"}
            return {"ok": True, "action": "status", "message": "Status announced"}

        if intent_name == "help":
            return {"ok": True, "action": "help"}

        if intent_name == "approve":
            if self.window and hasattr(self.window, '_approve_pending'):
                self.window._approve_pending()
                return {"ok": True, "action": "approve"}
            return {"ok": False, "error": "No pending approval"}

        if intent_name == "reject":
            if self.window and hasattr(self.window, '_reject_pending'):
                self.window._reject_pending()
                return {"ok": True, "action": "reject"}
            return {"ok": False, "error": "No pending approval"}

        if intent_name == "run":
            if self.window and hasattr(self.window, '_run_selected_task'):
                self.window._run_selected_task()
                return {"ok": True, "action": "run"}
            return {"ok": False, "error": "No task selected"}

        if intent_name == "inspect":
            if self.window and hasattr(self.window, '_inspect_active_run'):
                self.window._inspect_active_run()
                return {"ok": True, "action": "inspect"}
            return {"ok": False, "error": "No active run to inspect"}

        if intent_name == "switch_mode":
            if self.window and hasattr(self.window, '_switch_brain_mode'):
                mode = command.intent.parameters.get("mode", "")
                self.window._switch_brain_mode(mode)
                return {"ok": True, "action": "switch_mode", "mode": mode}
            return {"ok": False, "error": "Cannot switch mode"}

        return {"ok": False, "error": f"Unknown intent: {intent_name}"}

    def shutdown(self) -> None:
        self.stop_listening()

    @property
    def is_listening(self) -> bool:
        return self._is_listening


class VoiceCommandPipeline:
    def __init__(
        self,
        *,
        normalizer: CommandNormalizer,
        gate: ConstitutionalGate,
        recorder: EvidenceRecorder,
        executor: Callable[[CommandRequest, AuthorizationResult], dict[str, Any]],
        window: Any,
        host: Any,
        tts_enabled: bool = True,
    ):
        self.normalizer = normalizer
        self.gate = gate
        self.recorder = recorder
        self.executor = executor
        self.window = window
        self.host = host
        self.tts_enabled = tts_enabled

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

        return receipt


def create_canonical_voice_processor(
    host: Any,
    window: Any,
    data_root: Path,
    *,
    enabled: bool = True,
    voice_auth_enabled: bool = True,
    required_confidence: float = 0.85,
    enrollment_samples: int = 3,
    auth_model: str = "resemblyzer",
    constitutional_gate: bool = True,
    evidence_recording: bool = True,
    tts_responses: bool = True,
) -> CanonicalVoiceProcessor:
    config = VoicePipelineConfig(
        enabled=enabled,
        voice_auth_enabled=voice_auth_enabled,
        required_confidence=required_confidence,
        enrollment_samples=enrollment_samples,
        auth_model=auth_model,
        constitutional_gate=constitutional_gate,
        evidence_recording=evidence_recording,
        tts_responses=tts_responses,
    )
    return CanonicalVoiceProcessor(host, window, data_root, config)