from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from typing import Any, Protocol

from .attachments import Attachment
from .config import AppConfig


class ChatProvider(Protocol):
    async def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        ...


class MockProvider:
    async def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        question = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"),
            "How can I help?",
        )
        tool_context = "\n".join(
            message["content"]
            for message in messages
            if message["role"] == "system" and "Tool context" in message["content"]
        )
        retrieval_context = "\n".join(
            message["content"]
            for message in messages
            if message["role"] == "system" and "Knowledge context" in message["content"]
        )
        parts = [
            "Running on the built-in mock brain right now.",
            "Point `FORGE_API_URL` at your own inference endpoint to switch to your API.",
            f"Mode: {mode}",
            f"Model route: {model}",
            f"Your request was: {question}",
        ]
        if attachments:
            parts.append(
                "Attachments:\n"
                + "\n".join(f"- {attachment.compact_preview()}" for attachment in attachments)
            )
        if tool_context:
            parts.append(tool_context.replace("Tool context:\n", ""))
        if retrieval_context:
            parts.append(retrieval_context.replace("Knowledge context:\n", ""))
        parts.append(
            "Fast mode is on." if fast_mode else "Quality mode is on with a wider context window."
        )
        reply = "\n\n".join(parts)
        for token in reply.split():
            await asyncio.sleep(0)
            yield token + " "


class OwnApiProvider:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        try:
            import httpx
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Own API provider requires httpx. Install the declared dependencies or use mock provider mode."
            ) from exc
        self._httpx = httpx
        self.client = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def stream_reply(
        self,
        *,
        messages: list[dict[str, str]],
        fast_mode: bool,
        mode: str,
        model: str,
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        url = self.config.vision_api_url if attachments and any(a.is_image for a in attachments) and self.config.vision_api_url else self.config.api_url
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "mode": mode,
            "temperature": 0.25 if fast_mode else 0.45,
            "max_tokens": self.config.max_response_tokens,
            "attachments": [
                {
                    "name": attachment.name,
                    "mime_type": attachment.mime_type,
                    "kind": attachment.kind,
                    "content": attachment.content,
                }
                for attachment in attachments
            ],
        }
        headers = {"Accept": "text/event-stream, application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        async with self.client.stream(
            "POST",
            url,
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/event-stream" in content_type:
                async for chunk in self._stream_sse(response):
                    yield chunk
                return

            raw_text = await response.aread()
            text = raw_text.decode("utf-8", errors="ignore").strip()
            if not text:
                return
            if text.startswith("{") or text.startswith("["):
                parsed = json.loads(text)
                chunk = self._extract_delta(parsed)
                if chunk:
                    yield chunk
                return
            for line in text.splitlines():
                parsed_chunk = self._parse_loose_line(line)
                if parsed_chunk:
                    yield parsed_chunk

    async def _stream_sse(self, response: Any) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            stripped = line.strip()
            if not stripped or stripped.startswith(":"):
                continue
            if stripped.startswith("data:"):
                stripped = stripped[5:].strip()
            if stripped == "[DONE]":
                break
            chunk = self._parse_loose_line(stripped)
            if chunk:
                yield chunk

    def _parse_loose_line(self, line: str) -> str | None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return line if line else None
        return self._extract_delta(payload)

    def _extract_delta(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("delta", "content", "text", "response", "message"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    nested = self._extract_delta(value)
                    if nested:
                        return nested
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                return self._extract_delta(choices[0])
        if isinstance(payload, list):
            for item in payload:
                chunk = self._extract_delta(item)
                if chunk:
                    return chunk
        return None


def build_provider(config: AppConfig) -> ChatProvider:
    if config.provider_mode == "mock" or not config.api_url:
        return MockProvider()
    return OwnApiProvider(config)
