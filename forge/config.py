"""Configuration for the isolated Forge contractor service."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_MODEL = "claude-3-7-sonnet-20250219"
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"


@dataclass(slots=True)
class ForgeConfig:
    """Runtime settings for the Forge contractor service."""

    host: str
    port: int
    storage_root: Path
    model: str
    api_key: str
    api_url: str
    anthropic_version: str
    timeout_ms: int
    max_retries: int
    max_tokens: int
    default_output_chars: int
    trace_enabled: bool

    @property
    def provider_configured(self) -> bool:
        return bool(self.api_key.strip())


def load_forge_config() -> ForgeConfig:
    """Load Forge settings from the local environment."""

    storage_root = Path(
        os.getenv("FORGE_STORAGE")
        or (Path.cwd() / ".runtime" / "forge")
    ).expanduser().resolve()

    return ForgeConfig(
        host=os.getenv("FORGE_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=max(1, int(os.getenv("FORGE_PORT", "6060"))),
        storage_root=storage_root,
        model=(
            os.getenv("FORGE_MODEL", "").strip()
            or os.getenv("AAIS_CLAUDE_MODEL", "").strip()
            or DEFAULT_MODEL
        ),
        api_key=(
            os.getenv("CLAUDE_API_KEY", "").strip()
            or os.getenv("ANTHROPIC_API_KEY", "").strip()
        ),
        api_url=os.getenv("CLAUDE_API_URL", "").strip() or DEFAULT_API_URL,
        anthropic_version=(
            os.getenv("FORGE_ANTHROPIC_VERSION", "").strip()
            or DEFAULT_ANTHROPIC_VERSION
        ),
        timeout_ms=max(1000, int(os.getenv("FORGE_TIMEOUT_MS", "25000"))),
        max_retries=max(0, int(os.getenv("FORGE_MAX_RETRIES", "2"))),
        max_tokens=max(256, int(os.getenv("FORGE_MAX_TOKENS", "2000"))),
        default_output_chars=max(1000, int(os.getenv("FORGE_DEFAULT_OUTPUT_CHARS", "20000"))),
        trace_enabled=os.getenv("FORGE_TRACE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
    )
