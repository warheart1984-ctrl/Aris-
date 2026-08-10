from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


try:
    import numpy as np
except Exception:
    np = None


try:
    import speech_recognition as sr
except Exception:
    sr = None


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


@dataclass(frozen=True, slots=True)
class SpeakerProfile:
    speaker_id: str
    name: str
    embeddings: list[list[float]]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sample_count: int = 0
    is_authorized: bool = True


@dataclass(frozen=True, slots=True)
class VerificationResult:
    speaker_id: Optional[str]
    matched: bool
    confidence: float
    threshold: float
    method: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpeakerVerifier:
    def __init__(
        self,
        storage_path: Path,
        *,
        threshold: float = 0.85,
        method: str = "resemblyzer",
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
            if self.method == "resemblyzer" and VoiceEncoder is not None:
                self._encoder = VoiceEncoder()
            elif self.method == "speechbrain":
                pass
        return self._encoder

    def enroll(self, speaker_id: str, name: str, audio_samples: list[bytes]) -> SpeakerProfile:
        encoder = self._get_encoder()
        if encoder is None:
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
                )
            else:
                profile = SpeakerProfile(
                    speaker_id=speaker_id,
                    name=name,
                    embeddings=[avg_embedding],
                    sample_count=1,
                )
            self._profiles[speaker_id] = profile
            self._save_profiles()

        return profile

    def verify(self, audio_data: bytes) -> VerificationResult:
        encoder = self._get_encoder()
        if encoder is None:
            return VerificationResult(
                speaker_id=None,
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
            )

        if not self._profiles:
            return VerificationResult(
                speaker_id=None,
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
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
                matched=False,
                confidence=0.0,
                threshold=self.threshold,
                method=self.method,
            )

        best_match = None
        best_score = 0.0

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
                        best_match = speaker_id

        matched = best_score >= self.threshold
        return VerificationResult(
            speaker_id=best_match if matched else None,
            matched=matched,
            confidence=best_score,
            threshold=self.threshold,
            method=self.method,
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
                )
                self._save_profiles()
                return True
        return False

    def get_authorized_speakers(self) -> list[str]:
        with self._lock:
            return [sid for sid, p in self._profiles.items() if p.is_authorized]

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


class VoiceAuthManager:
    def __init__(
        self,
        data_root: Path,
        *,
        config: Optional["VoiceAuthConfig"] = None,
        on_enrollment_complete: Optional[Callable[[SpeakerProfile], None]] = None,
    ):
        from .command_types import VoiceAuthConfig
        self.data_root = data_root
        self.config = config or VoiceAuthConfig()
        self.on_enrollment_complete = on_enrollment_complete

        self.verifier = SpeakerVerifier(
            data_root / "voice_profiles.json",
            threshold=self.config.required_confidence,
            method=self.config.model,
        )
        self.fingerprinter = AudioFingerprinter()
        self._enrollment_active = False
        self._enrollment_speaker_id: Optional[str] = None
        self._enrollment_name: Optional[str] = None
        self._enrollment_samples: list[bytes] = []

    def start_enrollment(self, speaker_id: str, name: str) -> bool:
        if self._enrollment_active:
            return False
        self._enrollment_active = True
        self._enrollment_speaker_id = speaker_id
        self._enrollment_name = name
        self._enrollment_samples = []
        return True

    def add_enrollment_sample(self, audio_data: bytes) -> tuple[int, int]:
        if not self._enrollment_active:
            return (0, self.config.enrollment_samples_required)
        self._enrollment_samples.append(audio_data)
        return (len(self._enrollment_samples), self.config.enrollment_samples_required)

    def complete_enrollment(self) -> Optional[SpeakerProfile]:
        if not self._enrollment_active or not self._enrollment_speaker_id:
            return None

        try:
            profile = self.verifier.enroll(
                self._enrollment_speaker_id,
                self._enrollment_name or "Unknown",
                self._enrollment_samples,
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
            self._enrollment_samples = []

    def cancel_enrollment(self) -> None:
        self._enrollment_active = False
        self._enrollment_speaker_id = None
        self._enrollment_name = None
        self._enrollment_samples = []

    def verify_audio(self, audio_data: bytes) -> VerificationResult:
        if not self.config.enabled:
            return VerificationResult(
                speaker_id="unverified",
                matched=True,
                confidence=1.0,
                threshold=0.0,
                method="disabled",
            )
        return self.verifier.verify(audio_data)

    def is_authorized(self, speaker_id: Optional[str]) -> bool:
        if not self.config.enabled:
            return True
        if not speaker_id:
            return False
        return speaker_id in self.verifier.get_authorized_speakers()

    def get_authorized_speakers(self) -> list[str]:
        return self.verifier.get_authorized_speakers()

    def authorize_speaker(self, speaker_id: str, authorized: bool = True) -> bool:
        return self.verifier.authorize(speaker_id, authorized)

    def remove_speaker(self, speaker_id: str) -> bool:
        return self.verifier.remove_speaker(speaker_id)


def create_voice_auth_manager(
    data_root: Path,
    *,
    enabled: bool = True,
    required_confidence: float = 0.85,
    enrollment_samples: int = 3,
    model: str = "resemblyzer",
    on_enrollment_complete: Optional[Callable[[SpeakerProfile], None]] = None,
) -> VoiceAuthManager:
    from .command_types import VoiceAuthConfig
    config = VoiceAuthConfig(
        enabled=enabled,
        required_confidence=required_confidence,
        enrollment_samples_required=enrollment_samples,
        model=model,
    )
    return VoiceAuthManager(
        data_root,
        config=config,
        on_enrollment_complete=on_enrollment_complete,
    )