from __future__ import annotations

from abc import ABC, abstractmethod
import platform
import shutil
import subprocess


class VoiceAdapter(ABC):
    @abstractmethod
    def speak(self, message: str) -> None:
        raise NotImplementedError


class NullVoiceAdapter(VoiceAdapter):
    def speak(self, message: str) -> None:
        return


class OSVoiceAdapter(VoiceAdapter):
    def speak(self, message: str) -> None:
        system = platform.system()
        if system == "Windows":
            self._speak_windows(message)
            return
        if system == "Darwin":
            subprocess.run(["say", message], check=False)
            return
        if system == "Linux":
            if shutil.which("spd-say"):
                subprocess.run(["spd-say", message], check=False)
                return
            raise RuntimeError("No supported Linux speech engine found.")
        raise RuntimeError(f"Unsupported platform for voice output: {system}")

    def _speak_windows(self, message: str) -> None:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f'$s.Speak("{message.replace(chr(34), chr(39))}")'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
        )
