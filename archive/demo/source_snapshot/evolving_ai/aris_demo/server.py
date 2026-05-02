from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from evolving_ai.app.config import AppConfig
from evolving_ai.app.server import create_app as create_base_app

from .service import ArisDemoChatService


@lru_cache(maxsize=1)
def _build_service() -> ArisDemoChatService:
    root = Path.cwd()
    config = AppConfig.from_env(root)
    return ArisDemoChatService(config)


def create_app() -> FastAPI:
    return create_base_app(build_service=_build_service)


def main() -> None:
    service = _build_service()
    uvicorn.run(
        create_app(),
        host=service.config.host,
        port=service.config.port,
        log_level="info",
    )