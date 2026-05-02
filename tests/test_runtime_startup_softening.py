from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch

from evolving_ai.app.config import AppConfig
from evolving_ai.app.files import FileParser
from evolving_ai.app.providers import MockProvider, build_provider
from evolving_ai.app.tools import ToolRouter
from evolving_ai.app.web import WebNavigator


class RuntimeStartupSofteningTests(unittest.TestCase):
    def test_file_parser_html_falls_back_when_bs4_is_unavailable(self) -> None:
        parser = FileParser()

        with patch.dict(sys.modules, {"bs4": None}):
            parsed = parser.parse(
                filename="sample.html",
                mime_type="text/html",
                payload=b"<html><body><script>bad()</script><p>Hello <b>world</b></p></body></html>",
            )

        self.assertEqual(parsed.attachment.kind, "text")
        self.assertIn("Hello world", parsed.attachment.content)
        self.assertNotIn("bad()", parsed.attachment.content)

    def test_mock_provider_build_does_not_require_httpx(self) -> None:
        root = Path.cwd() / ".runtime" / "demo-startup-softening" / uuid.uuid4().hex[:10]
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        with patch.dict(os.environ, {"FORGE_PROVIDER_MODE": "mock", "FORGE_API_URL": ""}, clear=False):
            with patch.dict(sys.modules, {"httpx": None}):
                config = AppConfig.from_env(root)
                provider = build_provider(config)

        self.assertIsInstance(provider, MockProvider)

    def test_web_navigator_search_returns_empty_without_httpx(self) -> None:
        navigator = WebNavigator()

        with patch.dict(sys.modules, {"httpx": None}):
            results = asyncio.run(navigator.search("law spine", limit=3))

        self.assertEqual(results, [])

    def test_tool_router_url_fetch_reports_unavailable_without_httpx(self) -> None:
        router = ToolRouter()

        with patch.dict(sys.modules, {"httpx": None}):
            results = asyncio.run(
                router.run(
                    "check https://example.com",
                    enable_remote_fetch=True,
                    mode="chat",
                )
            )

        self.assertTrue(results)
        self.assertEqual(results[0].name, "url_fetch_unavailable")


if __name__ == "__main__":
    unittest.main()
