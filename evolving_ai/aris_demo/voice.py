from __future__ import annotations

from functools import partial
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

import requests


_DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
_DEFAULT_MODEL = "eleven_flash_v2_5"
_FALLBACK_MODEL = "eleven_multilingual_v2"
_OUTPUT_FORMAT = "mp3_44100_128"
_PLAYBACK_LOCK = threading.Lock()
_ACTIVE_PLAYERS: list[tuple[Any, Any, Path]] = []


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _voice_enabled() -> bool:
    return _bool_env("ARIS_VOICE_ENABLED", True)


def _voice_provider() -> str:
    return str(os.getenv("ARIS_VOICE_PROVIDER", "elevenlabs")).strip().lower() or "elevenlabs"


def _voice_model() -> str:
    value = str(os.getenv("ARIS_VOICE_MODEL", _DEFAULT_MODEL)).strip()
    return value or _DEFAULT_MODEL


def _voice_id() -> str:
    value = str(os.getenv("ARIS_VOICE_ID", _DEFAULT_VOICE_ID)).strip()
    return value or _DEFAULT_VOICE_ID


def _short_phrase(text: str, event_type: str) -> str:
    phrases = {
        "system_ready": "ARIS is ready.",
        "brain_switch": "Switching active brain.",
        "shipping_complete": "Packaging complete. Artifacts verified.",
        "upgrade_accepted": "Upgrade accepted.",
        "upgrade_rejected": "Upgrade rejected. Stability not preserved.",
        "blocked_action": "Action blocked. Law violation detected.",
    }
    if event_type in phrases:
        return phrases[event_type]
    compact = " ".join(str(text or "").split())
    if len(compact) <= 96:
        return compact
    return compact[:93].rstrip() + "..."


def _cleanup_player(player: Any, audio_output: Any, audio_path: Path) -> None:
    with _PLAYBACK_LOCK:
        for index, item in enumerate(list(_ACTIVE_PLAYERS)):
            if item[0] is player:
                _ACTIVE_PLAYERS.pop(index)
                break
    try:
        player.deleteLater()
    except Exception:
        pass
    try:
        audio_output.deleteLater()
    except Exception:
        pass
    try:
        audio_path.unlink(missing_ok=True)
    except Exception:
        pass


def _play_with_qt(audio_bytes: bytes) -> bool:
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import QApplication
    except Exception:
        return False

    app = QApplication.instance()
    if app is None:
        return False

    with tempfile.NamedTemporaryFile(prefix="aris-voice-", suffix=".mp3", delete=False) as handle:
        handle.write(audio_bytes)
        temp_file = Path(handle.name).resolve()
    audio_output = QAudioOutput()
    player = QMediaPlayer()
    player.setAudioOutput(audio_output)
    audio_output.setVolume(0.85)

    def handle_status(_status: Any) -> None:
        if player.playbackState() == QMediaPlayer.StoppedState:
            _cleanup_player(player, audio_output, temp_file)

    player.mediaStatusChanged.connect(handle_status)
    player.playbackStateChanged.connect(lambda _state: handle_status(_state))
    with _PLAYBACK_LOCK:
        _ACTIVE_PLAYERS.append((player, audio_output, temp_file))
    player.setSource(QUrl.fromLocalFile(str(temp_file)))
    player.play()
    return True


def _try_elevenlabs(text: str) -> bool:
    api_key = str(os.getenv("ELEVENLABS_API_KEY", "")).strip()
    if not api_key:
        return False
    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{_voice_id()}",
            params={"output_format": _OUTPUT_FORMAT},
            headers={
                "xi-api-key": api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": _voice_model() or _DEFAULT_MODEL,
            },
            timeout=12,
        )
        if response.status_code >= 400 and _voice_model() == _DEFAULT_MODEL:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{_voice_id()}",
                params={"output_format": _OUTPUT_FORMAT},
                headers={
                    "xi-api-key": api_key,
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": _FALLBACK_MODEL,
                },
                timeout=12,
            )
        response.raise_for_status()
        return _play_with_qt(response.content)
    except Exception:
        return False


def _try_pyttsx3(text: str) -> bool:
    try:
        import pyttsx3
    except Exception:
        return False
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        return False


def _speak_worker(text: str, event_type: str) -> None:
    phrase = _short_phrase(text, event_type)
    if not phrase:
        return
    provider = _voice_provider()
    if provider == "pyttsx3":
        _try_pyttsx3(phrase)
        return
    if _try_elevenlabs(phrase):
        return
    _try_pyttsx3(phrase)


def speak(text: str, event_type: str = "system") -> None:
    if not _voice_enabled():
        return
    phrase = _short_phrase(text, event_type)
    if not phrase:
        return
    worker = threading.Thread(
        target=partial(_speak_worker, phrase, event_type),
        name=f"aris-voice-{event_type}",
        daemon=True,
    )
    worker.start()
