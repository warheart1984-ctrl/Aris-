from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


try:
    import numpy as np
except Exception:
    np = None


try:
    from resemblyzer import VoiceEncoder, preprocess_wav
except Exception:
    VoiceEncoder = None
    preprocess_wav = None


try:
    import torch
    import torchaudio
except Exception:
    torch = None
    torchaudio = None


class SpeakerVerificationMethod(str, Enum):
    RESEMBLYZER = "resemblyzer"
    SPEECHBRAIN = "speechbrain"
    CUSTOM = "custom"
    DISABLED = "disabled"


class SpeakerStatus(str, Enum):
    ENROLLED = "enrolled"
    VERIFIED = "verified"
    UNKNOWN = "unknown"
    SPOOFED = "spoofed"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class SpeakerProfile:
    speaker_id: str
    name: str
    embeddings: list[list[float]]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sample_count: int = 0
    is_authorized: bool = True
    privileges: list[str] = field(default_factory=lambda: ["operator"])
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    speaker_id: Optional[str]
    name: Optional[str]
    matched: bool
    confidence: float
    threshold: float
    method: SpeakerVerificationMethod
    status: SpeakerStatus
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    audio_fingerprint: Optional[str] = None
    spoof_indicators: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VoiceIdentity:
    speaker_id: Optional[str]
    name: Optional[str]
    verified: bool
    confidence: float
    status: SpeakerStatus
    privileges: list[str]
    verification_result: VerificationResult
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpeakerVerifier:
    def __init__(
        self,
        storage_path: Path,
        *,
        threshold: float = 0.85,
        method: SpeakerVerificationMethod = SpeakerVerificationMethod.RESEMBLYZER,
    ):
        self.storage_path = storage_path
        self.threshold = threshold
        self.method = method
        self._lock = threading.Lock()
        self._encoder = None
        self._profiles: dict[str, SpeakerProfile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r") as f:
                data = json.load(f)
            for speaker_id, profile_data in data.items():
                self._profiles[speaker_id] = SpeakerProfile(**profile_data)
        except Exception:
            pass

    def _save_profiles(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: p.__dict__ for sid, p in self._profiles.items()}
        with self.storage_path.open("w") as f:
            json.dump(data, f, indent=2)

    def _get_encoder(self):
        if self._encoder is None:
            if self.method == SpeakerVerificationMethod.RESEMBLYZER and VoiceEncoder is not None:
                self._encoder = VoiceEncoder()
            elif self.method == SpeakerVerificationMethod.SPEECHBRAIN:
                pass
        return self._encoder

    def enroll(
        self,
        speaker_id: str,
        name: str,
        audio_samples: list[bytes],
        privileges: Optional[list[str]] = None,
    ) -> SpeakerProfile:
        encoder = self._get_encoder()
        if encoder is None and self.method != SpeakerVerificationMethod.DISABLED:
            raise RuntimeError(f"Voice encoder not available for method: {self.method}")

        embeddings = []
        for sample in audio_samples:
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(sample)
                    tmp_path = tmp.name
                wav = preprocess_wav(tmp_path)
                emb = encoder.embed_utterance(wav)
                embeddings.append(emb.tolist())
                os.unlink(tmp_path)
            except Exception:
                continue

        if not embeddings:
            raise ValueError("No valid embeddings extracted from samples")

        avg_embedding = np.mean(embeddings, axis=0).tolist() if np else embeddings[0]

        with self._lock:
            existing = self._profiles.get(speaker_id)
            if existing:
                all_embeddings = existing.embeddings + [avg_embedding]
                profile = SpeakerProfile(
                    speaker_id=speaker_id,
                    name=name,
                    embeddings=all_embeddings,
                    created_at=existing.created_at,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    sample_count=existing.sample_count + 1,
                    is_authorized=existing.is_authorized,
                    privileges=existing.privileges,
                    metadata=existing.metadata,
                )
            else:
                profile = SpeakerProfile(
                    speaker_id=speaker_id,
                    name=name,
                    embeddings=[avg_embedding],
                    sample_count=1,
                    privileges=privileges or ["operator"],
                )
            self._profiles[speaker_id] = profile
            self._save_profiles()

        return profile

    def verify(self, audio_data: bytes) -> VerificationResult:
        encoder = self._get_encoder()
        fingerprint = hashlib.sha256(audio_data).hexdigest()[:16]

        if encoder is None or self.method == SpeakerVerificationMethod.DISABLED:
            return VerificationResult(
                speaker_id=None,
                name=None,
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
                status=SpeakerStatus.UNKNOWN,
                audio_fingerprint=fingerprint,
            )

        if not self._profiles:
            return VerificationResult(
                speaker_id=None,
                name=None,
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
                status=SpeakerStatus.UNKNOWN,
                audio_fingerprint=fingerprint,
            )

        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name
            wav = preprocess_wav(tmp_path)
            test_emb = encoder.embed_utterance(wav)
            os.unlink(tmp_path)
        except Exception:
            return VerificationResult(
                speaker_id=None,
                name=None,
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
                status=SpeakerStatus.UNKNOWN,
                audio_fingerprint=fingerprint,
            )

        best_match = None
        best_score = 0.0
        spoof_indicators = []

        with self._lock:
            for speaker_id, profile in self._profiles.items():
                if not profile.is_authorized:
                    continue
                for emb in profile.embeddings:
                    if np is not None:
                        score = float(np.dot(test_emb, emb) / (np.linalg.norm(test_emb) * np.linalg.norm(emb)))
                    else:
                        score = sum(a * b for a, b in zip(test_emb, emb)) / (
                            sum(a * a for a in test_emb) ** 0.5 * sum(b * b for b in emb) ** 0.5
                        )
                    if score > best_score:
                        best_score = score
                        best_match = (speaker_id, profile.name, profile.privileges)

        matched = best_score >= self.threshold
        status = SpeakerStatus.VERIFIED if matched else SpeakerStatus.UNKNOWN

        if matched:
            speaker_id, name, privileges = best_match
        else:
            speaker_id, name, privileges = None, None, []

        return VerificationResult(
            speaker_id=speaker_id,
            name=name,
            matched=matched,
            confidence=best_score,
            threshold=self.threshold,
            method=self.method,
            status=status,
            audio_fingerprint=fingerprint,
            spoof_indicators=spoof_indicators,
        )

    def authorize(self, speaker_id: str, authorized: bool = True) -> bool:
        with self._lock:
            if speaker_id in self._profiles:
                profile = self._profiles[speaker_id]
                self._profiles[speaker_id] = SpeakerProfile(
                    speaker_id=profile.speaker_id,
                    name=profile.name,
                    embeddings=profile.embeddings,
                    created_at=profile.created_at,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    sample_count=profile.sample_count,
                    is_authorized=authorized,
                    privileges=profile.privileges,
                    metadata=profile.metadata,
                )
                self._save_profiles()
                return True
        return False

    def set_privileges(self, speaker_id: str, privileges: list[str]) -> bool:
        with self._lock:
            if speaker_id in self._profiles:
                profile = self._profiles[speaker_id]
                self._profiles[speaker_id] = SpeakerProfile(
                    speaker_id=profile.speaker_id,
                    name=profile.name,
                    embeddings=profile.embeddings,
                    created_at=profile.created_at,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    sample_count=profile.sample_count,
                    is_authorized=profile.is_authorized,
                    privileges=privileges,
                    metadata=profile.metadata,
                )
                self._save_profiles()
                return True
        return False

    def get_authorized_speakers(self) -> list[str]:
        with self._lock:
            return [sid for sid, p in self._profiles.items() if p.is_authorized]

    def get_speaker_privileges(self, speaker_id: str) -> list[str]:
        with self._lock:
            if speaker_id in self._profiles:
                return self._profiles[speaker_id].privileges
        return []

    def remove_speaker(self, speaker_id: str) -> bool:
        with self._lock:
            if speaker_id in self._profiles:
                del self._profiles[speaker_id]
                self._save_profiles()
                return True
        return False


class AudioFingerprinter:
    @staticmethod
    def fingerprint(audio_data: bytes) -> str:
        return hashlib.sha256(audio_data).hexdigest()[:16]

    @staticmethod
    def fingerprint_from_file(filepath: Path) -> str:
        with filepath.open("rb") as f:
            return AudioFingerprinter.fingerprint(f.read())


class VoiceIdentityProvider:
    def __init__(
        self,
        data_root: Path,
        *,
        method: SpeakerVerificationMethod = SpeakerVerificationMethod.RESEMBLYZER,
        threshold: float = 0.85,
        on_enrollment_complete: Optional[Callable[[SpeakerProfile], None]] = None,
    ):
        self.data_root = data_root
        self.method = method
        self.threshold = threshold
        self.on_enrollment_complete = on_enrollment_complete

        self.verifier = SpeakerVerifier(
            data_root / "voice_profiles.json",
            threshold=threshold,
            method=method,
        )
        self.fingerprinter = AudioFingerprinter()
        self._enrollment_active = False
        self._enrollment_speaker_id: Optional[str] = None
        self._enrollment_name: Optional[str] = None
        self._enrollment_privileges: list[str] = ["operator"]
        self._enrollment_samples: list[bytes] = []

    def start_enrollment(self, speaker_id: str, name: str, privileges: Optional[list[str]] = None) -> bool:
        if self._enrollment_active:
            return False
        self._enrollment_active = True
        self._enrollment_speaker_id = speaker_id
        self._enrollment_name = name
        self._enrollment_privileges = privileges or ["operator"]
        self._enrollment_samples = []
        return True

    def add_enrollment_sample(self, audio_data: bytes) -> tuple[int, int]:
        if not self._enrollment_active:
            return (0, 3)
        self._enrollment_samples.append(audio_data)
        return (len(self._enrollment_samples), 3)

    def complete_enrollment(self) -> Optional[SpeakerProfile]:
        if not self._enrollment_active or not self._enrollment_speaker_id:
            return None

        try:
            profile = self.verifier.enroll(
                self._enrollment_speaker_id,
                self._enrollment_name or "Unknown",
                self._enrollment_samples,
                privileges=self._enrollment_privileges,
            )
            if self.on_enrollment_complete:
                try:
                    self.on_enrollment_complete(profile)
                except Exception:
                    pass
            return profile
        except Exception:
            return None
        finally:
            self._enrollment_active = False
            self._enrollment_speaker_id = None
            self._enrollment_name = None
            self._enrollment_privileges = ["operator"]
            self._enrollment_samples = []

    def cancel_enrollment(self) -> None:
        self._enrollment_active = False
        self._enrollment_speaker_id = None
        self._enrollment_name = None
        self._enrollment_privileges = ["operator"]
        self._enrollment_samples = []

    def verify_audio(self, audio_data: bytes) -> VerificationResult:
        if self.method == SpeakerVerificationMethod.DISABLED:
            return VerificationResult(
                speaker_id="unverified",
                name="Unverified",
                matched=True,
                confidence=1.0,
                threshold=0.0,
                method=self.method,
                status=SpeakerStatus.UNKNOWN,
            )
        return self.verifier.verify(audio_data)

    def create_voice_identity(self, audio_data: bytes) -> VoiceIdentity:
        result = self.verify_audio(audio_data)
        return VoiceIdentity(
            speaker_id=result.speaker_id,
            name=result.name,
            verified=result.matched,
            confidence=result.confidence,
            status=result.status,
            privileges=self.verifier.get_speaker_privileges(result.speaker_id) if result.speaker_id else [],
            verification_result=result,
        )

    def is_authorized(self, speaker_id: Optional[str]) -> bool:
        if self.method == SpeakerVerificationMethod.DISABLED:
            return True
        if not speaker_id:
            return False
        return speaker_id in self.verifier.get_authorized_speakers()

    def get_authorized_speakers(self) -> list[str]:
        return self.verifier.get_authorized_speakers()

    def get_speaker_privileges(self, speaker_id: str) -> list[str]:
        return self.verifier.get_speaker_privileges(speaker_id)

    def authorize_speaker(self, speaker_id: str, authorized: bool = True) -> bool:
        return self.verifier.authorize(speaker_id, authorized)

    def set_speaker_privileges(self, speaker_id: str, privileges: list[str]) -> bool:
        return self.verifier.set_privileges(speaker_id, privileges)

    def remove_speaker(self, speaker_id: str) -> bool:
        return self.verifier.remove_speaker(speaker_id)


def create_voice_identity_provider(
    data_root: Path,
    *,
    method: SpeakerVerificationMethod = SpeakerVerificationMethod.RESEMBLYZER,
    threshold: float = 0.85,
    on_enrollment_complete: Optional[Callable[[SpeakerProfile], None]] = None,
) -> VoiceIdentityProvider:
    return VoiceIdentityProvider(
        data_root,
        method=method,
        threshold=threshold,
        on_enrollment_complete=on_enrollment_complete,
    )