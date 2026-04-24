from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from functools import partial
import sys
from unittest.mock import AsyncMock, patch
import zipfile

from docx import Document
from fastapi.testclient import TestClient

from evolving_ai.app.attachments import Attachment
from evolving_ai.app.agent_runs import AgentRunStore
from evolving_ai.app.docker_workspace import DockerSessionContainerManager
from evolving_ai.app.execution import SandboxPolicy, WorkspaceManager
from evolving_ai.app.execution_backends import (
    CommandExecutionResult,
    DockerSandboxConfig,
    DockerSandboxExecutor,
    build_executor,
)
from evolving_ai.app.files import FileParser
from evolving_ai.app.knowledge import KnowledgeIndex
from evolving_ai.app.providers import ChatProvider, MockProvider, build_provider
from evolving_ai.app.tools import ToolRouter
from evolving_ai.app.server import _build_service, create_app

if os.name == "nt":
    tempfile.TemporaryDirectory = partial(  # type: ignore[assignment]
        tempfile.TemporaryDirectory,
        ignore_cleanup_errors=True,
    )


def _cleanup_temp_root(path: Path) -> None:
    if os.name != "nt" or not path.exists():
        return
    deadline = time.monotonic() + 5.0
    while path.exists():
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.25)


def _git_completed(
    arguments: list[str] | None = None,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments or ["git"], returncode, stdout, stderr)


class KnowledgeIndexTests(unittest.TestCase):
    def test_search_finds_relevant_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            knowledge_dir = root / "knowledge"
            knowledge_dir.mkdir()
            (knowledge_dir / "api.md").write_text(
                "ForgeChat supports retrieval, streaming, and prompt caching for your own APIs.",
                encoding="utf-8",
            )
            (knowledge_dir / "notes.md").write_text(
                "This file is about gardening and herbs.",
                encoding="utf-8",
            )
            index = KnowledgeIndex(knowledge_dir)
            index.refresh()

            hits = index.search("prompt caching for APIs", limit=2)

            self.assertTrue(hits)
            self.assertEqual(hits[0].source, "api.md")


class AiAppEndpointTests(unittest.TestCase):
    def test_mock_provider_build_does_not_require_httpx(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"FORGE_PROVIDER_MODE": "mock", "FORGE_API_URL": ""}, clear=False):
                with patch.dict(sys.modules, {"httpx": None}):
                    config = AppConfig.from_env(root)
                    provider = build_provider(config)

        self.assertIsInstance(provider, MockProvider)

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

    def test_chat_endpoint_streams_meta_and_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    add_response = client.post(
                        "/api/knowledge",
                        json={
                            "name": "product.md",
                            "content": "Our product helps teams answer questions with retrieval and caching.",
                        },
                    )
                    self.assertEqual(add_response.status_code, 200)

                    with client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "message": "My name is Riley. What does the product do and what time is it?",
                            "fast_mode": True,
                            "retrieval_k": 3,
                            "mode": "agent",
                            "attachments": [
                                {
                                    "name": "spec.md",
                                    "mime_type": "text/markdown",
                                    "kind": "text",
                                    "content": "The assistant should be fast, grounded, and support retrieval.",
                                }
                            ],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("event: meta", body)
                    self.assertIn("event: token", body)
                    self.assertIn("Current local time", body)
                    self.assertIn("spec.md", body)
                    self.assertIn('"mode": "agent"', body)

                    sessions_response = client.get("/api/sessions")
                    self.assertEqual(sessions_response.status_code, 200)
                    self.assertGreaterEqual(len(sessions_response.json()), 1)

                    memory_response = client.get("/api/memory")
                    self.assertEqual(memory_response.status_code, 200)
                    payload = memory_response.json()
                    self.assertTrue(payload["facts"])

                    execute_response = client.post(
                        "/api/execute",
                        json={"session_id": "scratchpad", "code": "print('hello from code')"},
                    )
                    self.assertEqual(execute_response.status_code, 200)
                    self.assertIn("hello from code", execute_response.json()["stdout"])
                    self.assertIn("sandbox", execute_response.json())
                    self.assertFalse(execute_response.json()["sandbox"]["policy"]["allow_network"])

                    parse_response = client.post(
                        "/api/attachments/parse",
                        files={
                            "file": ("sample.csv", b"name,score\nada,9\n", "text/csv"),
                        },
                    )
                    self.assertEqual(parse_response.status_code, 200)
                    parsed_payload = parse_response.json()
                    self.assertEqual(parsed_payload["attachment"]["kind"], "text")
                    self.assertIn("name | score", parsed_payload["attachment"]["content"])

                    doc = Document()
                    doc.add_paragraph("This is a docx note.")
                    doc_bytes_path = root / "sample.docx"
                    doc.save(doc_bytes_path)
                    parse_docx_response = client.post(
                        "/api/attachments/parse",
                        files={
                            "file": (
                                "sample.docx",
                                doc_bytes_path.read_bytes(),
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            ),
                        },
                    )
                    self.assertEqual(parse_docx_response.status_code, 200)
                    self.assertIn(
                        "docx note",
                        parse_docx_response.json()["attachment"]["content"].lower(),
                    )

                    sandbox_response = client.get("/api/sandbox")
                    self.assertEqual(sandbox_response.status_code, 200)
                    self.assertIn("active_backend", sandbox_response.json())

                    sandbox_session_response = client.get("/api/sandbox/scratchpad")
                    self.assertEqual(sandbox_session_response.status_code, 200)
                    self.assertIn("session", sandbox_session_response.json())

                    reset_response = client.post("/api/sandbox/scratchpad/reset")
                    self.assertEqual(reset_response.status_code, 200)
                    self.assertIn("removed", reset_response.json())

                    with client.stream(
                        "POST",
                        "/api/exec/stream",
                        json={"session_id": "scratchpad", "command": ["git", "status"]},
                    ) as response:
                        stream_body = "".join(response.iter_text())

                    self.assertIn("event: exec_start", stream_body)
                    self.assertIn("event: exec_chunk", stream_body)
                    self.assertIn("event: exec_done", stream_body)
                    self.assertIn("Docker backend", stream_body)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_executes_tool_loop(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Need to run code first",'
                        '"action":{"tool":"run_python","args":{"code":"print(2 + 2)"}}}'
                    )
                    return
                yield '{"thought":"Now I can answer","final":"The code result is 4."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "message": "Use the agent to calculate 2 + 2.",
                            "fast_mode": False,
                            "retrieval_k": 2,
                            "mode": "agent",
                            "attachments": [],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("event: agent_step", body)
                    self.assertIn("run_python", body)
                    self.assertIn("The code result is 4.", body)
                    self.assertEqual(provider.calls, 2)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_executes_run_command_tool_loop(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Need repository status first",'
                        '"action":{"tool":"run_command","args":{"command":["git","status"],"cwd":"."}}}'
                    )
                    return
                yield '{"thought":"Now I can answer","final":"Git status was checked successfully."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with patch.object(
                        service.executor,
                        "stream_command",
                        return_value=iter(
                            [
                                {
                                    "event": "exec_start",
                                    "payload": {
                                        "session_id": "scratchpad",
                                        "command": ["git", "status"],
                                        "cwd": "/workspace",
                                        "command_policy": {
                                            "tier": "read_only",
                                            "max_tier": "read_only",
                                            "source": "agent",
                                        },
                                    },
                                },
                                {
                                    "event": "exec_chunk",
                                    "payload": {
                                        "stream": "stdout",
                                        "content": "On branch main\n",
                                    },
                                },
                                {
                                    "event": "exec_done",
                                    "payload": {
                                        "session_id": "scratchpad",
                                        "command": ["git", "status"],
                                        "cwd": "/workspace",
                                        "returncode": 0,
                                        "stdout": "On branch main\n",
                                        "stderr": "",
                                        "timed_out": False,
                                        "files": ["README.md"],
                                        "sandbox": {
                                            "command_policy": {
                                                "tier": "read_only",
                                                "max_tier": "read_only",
                                                "source": "agent",
                                            },
                                            "violations": [],
                                        },
                                    },
                                },
                            ]
                        ),
                    ) as stream_command:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Use the agent to inspect the repository status.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                    self.assertIn("event: agent_step", body)
                    self.assertIn("run_command", body)
                    self.assertIn("command_chunk", body)
                    self.assertIn("On branch main", body)
                    self.assertIn("Git status was checked successfully.", body)
                    self.assertIn(
                        "Policy: tier=read_only, max=read_only, source=agent", body
                    )
                    self.assertEqual(provider.calls, 2)
                    stream_command.assert_called_once()
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_blocks_shell_when_permission_disabled(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Check git status first",'
                        '"action":{"tool":"run_command","args":{"command":["git","status"]}}}'
                    )
                    return
                yield '{"thought":"Now I can answer","final":"Shell access was blocked."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "docker"
                os.environ["FORGE_AGENT_ALLOW_SHELL"] = "false"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with patch.object(service.executor, "stream_command") as stream_command:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Try to inspect the repository with a shell command.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                    self.assertIn("run_command", body)
                    self.assertIn("Shell command execution is disabled for the agent.", body)
                    self.assertIn("Shell access was blocked.", body)
                    self.assertEqual(provider.calls, 2)
                    stream_command.assert_not_called()
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_can_read_and_edit_workspace_files(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Inspect the file first",'
                        '"action":{"tool":"read_file","args":{"path":"notes.txt"}}}'
                    )
                    return
                if self.calls == 2:
                    yield (
                        '{"thought":"Apply the targeted edit",'
                        '"action":{"tool":"replace_in_file","args":{"path":"notes.txt","old_text":"hello","new_text":"hello updated"}}}'
                    )
                    return
                if self.calls == 3:
                    yield (
                        '{"thought":"Verify the updated file",'
                        '"action":{"tool":"read_file","args":{"path":"notes.txt"}}}'
                    )
                    return
                yield (
                    '{"thought":"Now I can answer",'
                    '"final":"I updated notes.txt to hello updated."}'
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_ALLOW_FILESYSTEM_WRITE"] = "true"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                session_id = "editor"
                workspace = root / "workspaces" / session_id
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("hello\n", encoding="utf-8")

                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "session_id": session_id,
                            "message": "Read notes.txt and update hello to hello updated.",
                            "fast_mode": False,
                            "retrieval_k": 2,
                            "mode": "agent",
                            "attachments": [],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("read_file", body)
                    self.assertIn("replace_in_file", body)
                    self.assertIn("Replacements: 1", body)
                    self.assertIn("hello updated", body)
                    self.assertEqual(provider.calls, 4)
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "hello updated\n",
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_can_preview_and_apply_multi_hunk_patch(self) -> None:
        patch_text = (
            "@@ -1,2 +1,2 @@\n"
            "-alpha\n"
            "+alpha updated\n"
            " beta\n"
            "@@ -3,2 +3,2 @@\n"
            " gamma\n"
            "-delta\n"
            "+delta updated\n"
        )

        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Preview the diff first",'
                        '"action":{"tool":"preview_patch","args":{"path":"notes.txt","patch":'
                        + json.dumps(patch_text)
                        + "}}}"
                    )
                    return
                if self.calls == 2:
                    expected_hash = None
                    for message in reversed(messages):
                        content = message.get("content", "")
                        if not isinstance(content, str):
                            continue
                        match = re.search(r"Current hash: ([0-9a-f]{64})", content)
                        if match:
                            expected_hash = match.group(1)
                            break
                    args = {"path": "notes.txt", "patch": patch_text}
                    if expected_hash:
                        args["expected_hash"] = expected_hash
                    yield json.dumps(
                        {
                            "thought": "Apply the validated patch",
                            "action": {"tool": "apply_patch", "args": args},
                        }
                    )
                    return
                if self.calls == 3:
                    yield (
                        '{"thought":"Verify the patched file",'
                        '"action":{"tool":"read_file","args":{"path":"notes.txt"}}}'
                    )
                    return
                yield (
                    '{"thought":"Patch is in place",'
                    '"final":"I applied the multi-hunk patch to notes.txt."}'
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                session_id = "patch-editor"
                workspace = root / "workspaces" / session_id
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(
                    "alpha\nbeta\ngamma\ndelta\n",
                    encoding="utf-8",
                )

                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "session_id": session_id,
                            "message": "Preview and apply a multi-hunk patch to notes.txt.",
                            "fast_mode": False,
                            "retrieval_k": 2,
                            "mode": "agent",
                            "attachments": [],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                self.assertIn("preview_patch", body)
                self.assertIn("apply_patch", body)
                self.assertIn("Can apply: True", body)
                self.assertIn("I applied the multi-hunk patch to notes.txt.", body)
                self.assertEqual(provider.calls, 4)
                self.assertEqual(
                    (workspace / "notes.txt").read_text(encoding="utf-8"),
                    "alpha updated\nbeta\ngamma\ndelta updated\n",
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runtime_surfaces_command_approval_requirement(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                yield (
                    '{"thought":"Need to run a test command",'
                    '"action":{"tool":"run_command","args":{"command":["python","--version"],"cwd":"."}}}'
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_MAX_COMMAND_TIER"] = "read_only"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with patch.object(
                        service.executor,
                        "stream_command",
                        return_value=iter(
                            [
                                {
                                    "event": "exec_start",
                                    "payload": {
                                        "session_id": "scratchpad",
                                        "command": ["python", "--version"],
                                        "cwd": "/workspace",
                                        "command_policy": {
                                            "tier": "test",
                                            "max_tier": "read_only",
                                            "source": "agent",
                                            "executable": "python",
                                        },
                                    },
                                },
                                {
                                    "event": "exec_chunk",
                                    "payload": {
                                        "stream": "stderr",
                                        "content": (
                                            "Command tier `test` exceeds the allowed maximum "
                                            "`read_only` for agent execution.\n"
                                        ),
                                    },
                                },
                                {
                                    "event": "exec_done",
                                    "payload": {
                                        "session_id": "scratchpad",
                                        "command": ["python", "--version"],
                                        "cwd": "/workspace",
                                        "returncode": 126,
                                        "stdout": "",
                                        "stderr": (
                                            "Command tier `test` exceeds the allowed maximum "
                                            "`read_only` for agent execution."
                                        ),
                                        "timed_out": False,
                                        "files": [],
                                        "sandbox": {
                                            "blocked": True,
                                            "violations": [
                                                "Command tier `test` exceeds the allowed maximum "
                                                "`read_only` for agent execution."
                                            ],
                                            "command_policy": {
                                                "tier": "test",
                                                "max_tier": "read_only",
                                                "source": "agent",
                                                "executable": "python",
                                            },
                                        },
                                    },
                                },
                            ]
                        ),
                    ) as stream_command:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Inspect the repo and run a test command if needed.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                    session_id = client.get("/api/sessions").json()[0]["id"]
                    approvals = client.get(f"/api/agent/{session_id}/approvals").json()
                    self.assertIn("Approval required:", body)
                    self.assertIn("agent is capped at `read_only`", body)
                    self.assertIn(
                        "Open the Approvals panel to approve or reject this step",
                        body,
                    )
                    self.assertIn(
                        "Approve test command",
                        body,
                    )
                    self.assertEqual(provider.calls, 1)
                    stream_command.assert_called_once()
                    self.assertEqual(len(approvals["approvals"]), 1)
                    self.assertEqual(approvals["approvals"][0]["kind"], "command")
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_approval_endpoint_resumes_higher_tier_command(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0
                self.saw_resume_context = False

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Need to run a test command",'
                        '"action":{"tool":"run_command","args":{"command":["python","--version"],"cwd":"."}}}'
                    )
                    return
                self.saw_resume_context = any(
                    "User approved the higher-tier command request." in message.get("content", "")
                    for message in messages
                )
                yield '{"thought":"Continue after approval","final":"Approved command finished."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_MAX_COMMAND_TIER"] = "read_only"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with patch.object(
                        service.executor,
                        "stream_command",
                        side_effect=[
                            iter(
                                [
                                    {
                                        "event": "exec_start",
                                        "payload": {
                                            "command": ["python", "--version"],
                                            "cwd": "/workspace",
                                            "command_policy": {
                                                "tier": "test",
                                                "max_tier": "read_only",
                                                "source": "agent",
                                                "executable": "python",
                                            },
                                        },
                                    },
                                    {
                                        "event": "exec_chunk",
                                        "payload": {
                                            "stream": "stderr",
                                            "content": (
                                                "Command tier `test` exceeds the allowed maximum "
                                                "`read_only` for agent execution.\n"
                                            ),
                                        },
                                    },
                                    {
                                        "event": "exec_done",
                                        "payload": {
                                            "returncode": 126,
                                            "stdout": "",
                                            "stderr": (
                                                "Command tier `test` exceeds the allowed maximum "
                                                "`read_only` for agent execution."
                                            ),
                                            "timed_out": False,
                                            "files": [],
                                            "sandbox": {
                                                "blocked": True,
                                                "violations": [
                                                    "Command tier `test` exceeds the allowed maximum "
                                                    "`read_only` for agent execution."
                                                ],
                                                "command_policy": {
                                                    "tier": "test",
                                                    "max_tier": "read_only",
                                                    "source": "agent",
                                                    "executable": "python",
                                                },
                                            },
                                        },
                                    },
                                ]
                            ),
                            iter(
                                [
                                    {
                                        "event": "exec_start",
                                        "payload": {
                                            "command": ["python", "--version"],
                                            "cwd": "/workspace",
                                            "command_policy": {
                                                "tier": "test",
                                                "max_tier": "test",
                                                "source": "agent_approved",
                                                "executable": "python",
                                            },
                                        },
                                    },
                                    {
                                        "event": "exec_chunk",
                                        "payload": {
                                            "stream": "stdout",
                                            "content": "Python 3.11.9\n",
                                        },
                                    },
                                    {
                                        "event": "exec_done",
                                        "payload": {
                                            "returncode": 0,
                                            "stdout": "Python 3.11.9\n",
                                            "stderr": "",
                                            "timed_out": False,
                                            "files": [],
                                            "sandbox": {
                                                "command_policy": {
                                                    "tier": "test",
                                                    "max_tier": "test",
                                                    "source": "agent_approved",
                                                    "executable": "python",
                                                },
                                                "violations": [],
                                            },
                                        },
                                    },
                                ]
                            ),
                        ],
                    ) as stream_command:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Inspect the repo and run a test command if needed.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                        self.assertIn("Approval required:", body)
                        self.assertEqual(provider.calls, 1)

                        session_id = client.get("/api/sessions").json()[0]["id"]
                        approvals = client.get(f"/api/agent/{session_id}/approvals").json()
                        self.assertEqual(len(approvals["approvals"]), 1)
                        approval_id = approvals["approvals"][0]["id"]

                        with client.stream(
                            "POST",
                            f"/api/agent/{session_id}/approvals/{approval_id}/approve",
                        ) as response:
                            resume_body = "".join(response.iter_text())

                    self.assertIn("Approved command finished.", resume_body)
                    self.assertIn("Python 3.11.9", resume_body)
                    self.assertEqual(provider.calls, 2)
                    self.assertTrue(provider.saw_resume_context)
                    self.assertEqual(
                        client.get(f"/api/agent/{session_id}/approvals").json()["approvals"],
                        [],
                    )
                    self.assertEqual(stream_command.call_count, 2)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_patch_approval_resume_applies_patch_and_continues(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0
                self.saw_patch_resume = False
                self.saw_verification_pass = False

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Draft a file for review",'
                        '"action":{"tool":"propose_file_write","args":{"path":"notes.md","content":"hello from patch\\n"}}}'
                    )
                    return
                self.saw_patch_resume = any(
                    "User approved patch `notes.md`." in message.get("content", "")
                    for message in messages
                )
                self.saw_verification_pass = any(
                    "Automatic verification status: passed" in message.get("content", "")
                    for message in messages
                )
                yield '{"thought":"Continue after patch review","final":"Patch applied and work is ready."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            session_id = "patch-review"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_ALLOW_FILESYSTEM_WRITE"] = "true"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / session_id / "tests"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "test_dummy.py").write_text(
                    "def test_ok():\n    assert True\n",
                    encoding="utf-8",
                )
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with patch.object(
                    service.executor,
                    "execute_command",
                    side_effect=lambda **kwargs: CommandExecutionResult(
                        session_id=session_id,
                        command=[str(part) for part in kwargs.get("command", [])],
                        cwd=str(kwargs.get("cwd", ".") or "."),
                        returncode=0,
                        stdout="1 passed\n",
                        stderr="",
                        timed_out=False,
                        files=["notes.md", "tests/test_dummy.py"],
                        sandbox={"backend": "local"},
                    ),
                ) as mocked_execute:
                    with TestClient(app) as client:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "session_id": session_id,
                                "message": "Create a notes file, but wait for my review before applying it.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                        self.assertIn("Review patch for notes.md", body)
                        self.assertEqual(provider.calls, 1)

                        workspace_payload = client.get(f"/api/workspace/{session_id}").json()
                        self.assertEqual(len(workspace_payload["pending_patches"]), 1)
                        patch_id = workspace_payload["pending_patches"][0]["id"]

                        approvals = client.get(f"/api/agent/{session_id}/approvals").json()
                        self.assertTrue(
                            any(
                                approval["id"] == patch_id and approval["kind"] == "patch"
                                for approval in approvals["approvals"]
                            )
                        )

                        with client.stream(
                            "POST",
                            f"/api/agent/{session_id}/approvals/{patch_id}/approve",
                        ) as response:
                            resume_body = "".join(response.iter_text())

                        file_payload = client.get(
                            f"/api/workspace/{session_id}/file?path=notes.md"
                        ).json()
                        workspace_after = client.get(f"/api/workspace/{session_id}").json()
                        for _ in range(20):
                            if (
                                provider.calls >= 2
                                and not workspace_after["pending_patches"]
                                and workspace_after["applied_changes"]
                                and workspace_after["applied_changes"][0].get("verification")
                            ):
                                break
                            time.sleep(0.05)
                            workspace_after = client.get(
                                f"/api/workspace/{session_id}"
                            ).json()

                        self.assertIn("Patch applied and work is ready.", resume_body)
                        self.assertEqual(provider.calls, 2)
                        self.assertTrue(provider.saw_patch_resume)
                        self.assertTrue(provider.saw_verification_pass)
                        self.assertEqual(mocked_execute.call_count, 1)
                        self.assertTrue(file_payload["ok"])
                        self.assertEqual(file_payload["content"], "hello from patch")
                        self.assertEqual(workspace_after["pending_patches"], [])
                        self.assertEqual(
                            workspace_after["applied_changes"][0]["verification"]["status"],
                            "passed",
                        )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_patch_approval_resume_failed_verification_proposes_follow_up_patch(
        self,
    ) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0
                self.saw_verification_failure = False

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Draft a file for review",'
                        '"action":{"tool":"propose_file_write","args":{"path":"notes.md","content":"broken patch\\n"}}}'
                    )
                    return
                self.saw_verification_failure = any(
                    "Automatic verification status: failed" in message.get("content", "")
                    for message in messages
                )
                yield (
                    '{"thought":"Fix the failing verification",'
                    '"action":{"tool":"propose_file_write","args":{"path":"notes.md","content":"fixed patch\\n"}}}'
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            session_id = "patch-verify-fail"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_ALLOW_FILESYSTEM_WRITE"] = "true"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / session_id / "tests"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "test_dummy.py").write_text(
                    "def test_ok():\n    assert True\n",
                    encoding="utf-8",
                )
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with patch.object(
                    service.executor,
                    "execute_command",
                    side_effect=lambda **kwargs: CommandExecutionResult(
                        session_id=session_id,
                        command=[str(part) for part in kwargs.get("command", [])],
                        cwd=str(kwargs.get("cwd", ".") or "."),
                        returncode=1,
                        stdout="",
                        stderr="notes.md is still broken\n",
                        timed_out=False,
                        files=["notes.md", "tests/test_dummy.py"],
                        sandbox={"backend": "local"},
                    ),
                ) as mocked_execute:
                    with TestClient(app) as client:
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "session_id": session_id,
                                "message": "Create a notes file, but fix it if verification fails.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                        self.assertIn("Review patch for notes.md", body)
                        self.assertEqual(provider.calls, 1)
                        patch_id = client.get(f"/api/workspace/{session_id}").json()[
                            "pending_patches"
                        ][0]["id"]

                        with client.stream(
                            "POST",
                            f"/api/agent/{session_id}/approvals/{patch_id}/approve",
                        ) as response:
                            resume_body = "".join(response.iter_text())

                        workspace_after = client.get(f"/api/workspace/{session_id}").json()
                        for _ in range(20):
                            if (
                                provider.calls >= 2
                                and len(workspace_after["pending_patches"]) == 1
                                and workspace_after["applied_changes"]
                                and workspace_after["applied_changes"][0].get("verification")
                            ):
                                break
                            time.sleep(0.05)
                            workspace_after = client.get(
                                f"/api/workspace/{session_id}"
                            ).json()
                        self.assertEqual(provider.calls, 2)
                        self.assertTrue(provider.saw_verification_failure)
                        self.assertEqual(mocked_execute.call_count, 1)
                        self.assertIn("Review patch for notes.md", resume_body)
                        self.assertEqual(len(workspace_after["pending_patches"]), 1)
                        self.assertEqual(
                            workspace_after["applied_changes"][0]["verification"]["status"],
                            "failed",
                        )
                        self.assertEqual(
                            workspace_after["applied_changes"][0]["verification"]["results"][0]["stderr"],
                            "notes.md is still broken\n",
                        )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_command_approval_resume_survives_service_restart(self) -> None:
        class InitialProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                yield (
                    '{"thought":"Need to run a test command",'
                    '"action":{"tool":"run_command","args":{"command":["python","--version"],"cwd":"."}}}'
                )

        class ResumedProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0
                self.saw_resume_context = False

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                self.saw_resume_context = any(
                    "User approved the higher-tier command request." in message.get("content", "")
                    for message in messages
                )
                yield '{"thought":"Continue after restart","final":"Approved command resumed after restart."}'

        blocked_events = iter(
            [
                {
                    "event": "exec_start",
                    "payload": {
                        "command": ["python", "--version"],
                        "cwd": "/workspace",
                        "command_policy": {
                            "tier": "test",
                            "max_tier": "read_only",
                            "source": "agent",
                            "executable": "python",
                        },
                    },
                },
                {
                    "event": "exec_chunk",
                    "payload": {
                        "stream": "stderr",
                        "content": (
                            "Command tier `test` exceeds the allowed maximum "
                            "`read_only` for agent execution.\n"
                        ),
                    },
                },
                {
                    "event": "exec_done",
                    "payload": {
                        "returncode": 126,
                        "stdout": "",
                        "stderr": (
                            "Command tier `test` exceeds the allowed maximum "
                            "`read_only` for agent execution."
                        ),
                        "timed_out": False,
                        "files": [],
                        "sandbox": {
                            "blocked": True,
                            "violations": [
                                "Command tier `test` exceeds the allowed maximum "
                                "`read_only` for agent execution."
                            ],
                            "command_policy": {
                                "tier": "test",
                                "max_tier": "read_only",
                                "source": "agent",
                                "executable": "python",
                            },
                        },
                    },
                },
            ]
        )
        approved_events = iter(
            [
                {
                    "event": "exec_start",
                    "payload": {
                        "command": ["python", "--version"],
                        "cwd": "/workspace",
                        "command_policy": {
                            "tier": "test",
                            "max_tier": "test",
                            "source": "agent_approved",
                            "executable": "python",
                        },
                    },
                },
                {
                    "event": "exec_chunk",
                    "payload": {
                        "stream": "stdout",
                        "content": "Python 3.11.9\n",
                    },
                },
                {
                    "event": "exec_done",
                    "payload": {
                        "returncode": 0,
                        "stdout": "Python 3.11.9\n",
                        "stderr": "",
                        "timed_out": False,
                        "files": [],
                        "sandbox": {
                            "command_policy": {
                                "tier": "test",
                                "max_tier": "test",
                                "source": "agent_approved",
                                "executable": "python",
                            },
                            "violations": [],
                        },
                    },
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            approval_db_path = root / "approvals.db"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_MAX_COMMAND_TIER"] = "read_only"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_APPROVAL_DB_PATH"] = str(approval_db_path)
                _build_service.cache_clear()

                first_app = create_app()
                first_service = _build_service()
                first_provider = InitialProvider()
                first_service.provider = first_provider
                with TestClient(first_app) as first_client:
                    with patch.object(
                        first_service.executor,
                        "stream_command",
                        side_effect=[blocked_events],
                    ):
                        with first_client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Inspect the repo and run a test command if needed.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                    self.assertIn("Approval required:", body)
                    self.assertEqual(first_provider.calls, 1)
                    session_id = first_client.get("/api/sessions").json()[0]["id"]
                    approvals = first_client.get(f"/api/agent/{session_id}/approvals").json()
                    self.assertEqual(len(approvals["approvals"]), 1)
                    approval_id = approvals["approvals"][0]["id"]

                self.assertTrue(approval_db_path.exists())
                with closing(sqlite3.connect(approval_db_path)) as connection:
                    snapshot_rows = connection.execute(
                        "SELECT bucket, payload_json FROM approval_snapshot"
                    ).fetchall()
                    snapshot_payload = {
                        bucket: json.loads(payload_json)
                        for bucket, payload_json in snapshot_rows
                    }
                    self.assertEqual(len(snapshot_payload["command_approvals"]), 1)
                    self.assertEqual(
                        snapshot_payload["command_approvals"][0]["id"],
                        approval_id,
                    )
                    audit_actions = [
                        row[0]
                        for row in connection.execute(
                            """
                            SELECT action
                            FROM approval_audit_log
                            WHERE session_id = ?
                            ORDER BY id
                            """,
                            (session_id,),
                        ).fetchall()
                    ]
                self.assertEqual(audit_actions, ["requested"])

                _build_service.cache_clear()

                second_app = create_app()
                second_service = _build_service()
                second_provider = ResumedProvider()
                second_service.provider = second_provider
                with TestClient(second_app) as second_client:
                    approvals = second_client.get(f"/api/agent/{session_id}/approvals").json()
                    self.assertEqual(len(approvals["approvals"]), 1)
                    self.assertEqual(approvals["approvals"][0]["id"], approval_id)
                    self.assertTrue(approvals["approvals"][0]["resume_available"])

                    with patch.object(
                        second_service.executor,
                        "stream_command",
                        side_effect=[approved_events],
                    ) as resumed_stream_command:
                        with second_client.stream(
                            "POST",
                            f"/api/agent/{session_id}/approvals/{approval_id}/approve",
                        ) as response:
                            resume_body = "".join(response.iter_text())

                    self.assertIn("Approved command resumed after restart.", resume_body)
                    self.assertIn("Python 3.11.9", resume_body)
                    self.assertEqual(
                        second_client.get(f"/api/agent/{session_id}/approvals").json()["approvals"],
                        [],
                    )
                    audit_payload = second_client.get(
                        f"/api/agent/{session_id}/audit?limit=10"
                    ).json()
                    audit_actions = {entry["action"] for entry in audit_payload["entries"]}
                    self.assertTrue({"requested", "approved", "resumed"}.issubset(audit_actions))
                    self.assertEqual(resumed_stream_command.call_count, 1)

                self.assertEqual(second_provider.calls, 1)
                self.assertTrue(second_provider.saw_resume_context)
                self.assertTrue(approval_db_path.exists())
                with closing(sqlite3.connect(approval_db_path)) as connection:
                    remaining_snapshot_rows = connection.execute(
                        "SELECT COUNT(*) FROM approval_snapshot"
                    ).fetchone()[0]
                self.assertEqual(remaining_snapshot_rows, 0)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_patch_approval_resume_survives_service_restart(self) -> None:
        class InitialProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                yield (
                    '{"thought":"Draft a file for review",'
                    '"action":{"tool":"propose_file_write","args":{"path":"notes.md","content":"hello from patch\\n"}}}'
                )

        class ResumedProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0
                self.saw_patch_resume = False

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                self.saw_patch_resume = any(
                    "User approved patch `notes.md`." in message.get("content", "")
                    for message in messages
                )
                yield '{"thought":"Continue after restart","final":"Patch resumed after restart."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            approval_db_path = root / "approvals.db"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_ALLOW_FILESYSTEM_WRITE"] = "true"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_APPROVAL_DB_PATH"] = str(approval_db_path)
                _build_service.cache_clear()

                first_app = create_app()
                first_service = _build_service()
                first_provider = InitialProvider()
                first_service.provider = first_provider
                with TestClient(first_app) as first_client:
                    with first_client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "message": "Create a notes file, but wait for my review before applying it.",
                            "fast_mode": False,
                            "retrieval_k": 2,
                            "mode": "agent",
                            "attachments": [],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("Review patch for notes.md", body)
                    self.assertEqual(first_provider.calls, 1)
                    session_id = first_client.get("/api/sessions").json()[0]["id"]
                    workspace_payload = first_client.get(f"/api/workspace/{session_id}").json()
                    patch_id = workspace_payload["pending_patches"][0]["id"]

                self.assertTrue(approval_db_path.exists())
                with closing(sqlite3.connect(approval_db_path)) as connection:
                    snapshot_rows = connection.execute(
                        "SELECT bucket, payload_json FROM approval_snapshot"
                    ).fetchall()
                    snapshot_payload = {
                        bucket: json.loads(payload_json)
                        for bucket, payload_json in snapshot_rows
                    }
                    self.assertEqual(len(snapshot_payload["patch_resume_states"]), 1)
                    self.assertEqual(
                        snapshot_payload["patch_resume_states"][0]["patch_id"],
                        patch_id,
                    )
                    audit_actions = [
                        row[0]
                        for row in connection.execute(
                            """
                            SELECT action
                            FROM approval_audit_log
                            WHERE session_id = ?
                            ORDER BY id
                            """,
                            (session_id,),
                        ).fetchall()
                    ]
                self.assertEqual(audit_actions, ["requested"])

                _build_service.cache_clear()

                second_app = create_app()
                second_service = _build_service()
                second_provider = ResumedProvider()
                second_service.provider = second_provider
                with TestClient(second_app) as second_client:
                    approvals = second_client.get(f"/api/agent/{session_id}/approvals").json()
                    patch_approvals = [
                        approval
                        for approval in approvals["approvals"]
                        if approval["id"] == patch_id and approval["kind"] == "patch"
                    ]
                    self.assertEqual(len(patch_approvals), 1)
                    self.assertTrue(patch_approvals[0]["resume_available"])

                    with second_client.stream(
                        "POST",
                        f"/api/agent/{session_id}/approvals/{patch_id}/approve",
                    ) as response:
                        resume_body = "".join(response.iter_text())

                    file_payload = second_client.get(
                        f"/api/workspace/{session_id}/file?path=notes.md"
                    ).json()

                    self.assertIn("Patch resumed after restart.", resume_body)
                    self.assertTrue(file_payload["ok"])
                    self.assertEqual(file_payload["content"], "hello from patch")
                    self.assertEqual(
                        second_client.get(f"/api/agent/{session_id}/approvals").json()["approvals"],
                        [],
                    )
                    audit_payload = second_client.get(
                        f"/api/agent/{session_id}/audit?limit=10"
                    ).json()
                    audit_actions = {entry["action"] for entry in audit_payload["entries"]}
                    self.assertTrue({"requested", "approved", "resumed"}.issubset(audit_actions))

                self.assertEqual(second_provider.calls, 1)
                self.assertTrue(second_provider.saw_patch_resume)
                self.assertTrue(approval_db_path.exists())
                with closing(sqlite3.connect(approval_db_path)) as connection:
                    remaining_snapshot_rows = connection.execute(
                        "SELECT COUNT(*) FROM approval_snapshot"
                    ).fetchone()[0]
                self.assertEqual(remaining_snapshot_rows, 0)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_legacy_approval_json_is_migrated_into_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            legacy_state_path = root / "legacy-approvals.json"
            approval_db_path = root / "approvals.db"
            try:
                os.chdir(root)
                legacy_state_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "command_approvals": [
                                {
                                    "id": "legacy-command",
                                    "session_id": "legacy-session",
                                    "kind": "command",
                                    "title": "Approve test command",
                                    "summary": "`python --version` needs `test` access.",
                                    "created_at": "2026-03-31T10:00:00+00:00",
                                    "step": 1,
                                    "tool": "run_command",
                                    "source": "agent",
                                    "status": "pending",
                                    "resume_available": True,
                                    "details": {
                                        "command": ["python", "--version"],
                                        "command_text": "python --version",
                                        "cwd": ".",
                                        "requested_tier": "test",
                                    },
                                }
                            ],
                            "command_resume_states": [
                                {
                                    "approval_id": "legacy-command",
                                    "kind": "command",
                                    "session_id": "legacy-session",
                                    "blocked_step": 1,
                                    "next_step_index": 1,
                                    "created_at": "2026-03-31T10:00:00+00:00",
                                    "workspace_fingerprint": "",
                                    "fast_mode": False,
                                    "model": "mock-model",
                                    "attachments": [],
                                    "tool_messages": [],
                                    "agent_max_command_tier": "read_only",
                                    "agent_allowed_commands": ["git", "ls"],
                                    "allow_python": True,
                                    "allow_shell": True,
                                    "allow_filesystem_read": True,
                                    "allow_filesystem_write": True,
                                }
                            ],
                            "patch_resume_states": [],
                        }
                    ),
                    encoding="utf-8",
                )
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_APPROVAL_DB_PATH"] = str(approval_db_path)
                os.environ["FORGE_APPROVAL_STATE_PATH"] = str(legacy_state_path)
                _build_service.cache_clear()

                with TestClient(create_app()) as client:
                    approvals = client.get("/api/agent/legacy-session/approvals").json()

                self.assertEqual(len(approvals["approvals"]), 1)
                self.assertEqual(approvals["approvals"][0]["id"], "legacy-command")
                self.assertTrue(approval_db_path.exists())
                self.assertFalse(legacy_state_path.exists())
                with closing(sqlite3.connect(approval_db_path)) as connection:
                    snapshot_rows = connection.execute(
                        "SELECT bucket, payload_json FROM approval_snapshot"
                    ).fetchall()
                    snapshot_payload = {
                        bucket: json.loads(payload_json)
                        for bucket, payload_json in snapshot_rows
                    }
                self.assertEqual(len(snapshot_payload["command_approvals"]), 1)
                self.assertEqual(
                    snapshot_payload["command_approvals"][0]["id"],
                    "legacy-command",
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_runs_endpoint_replays_completed_run_history(self) -> None:
        class SequenceProvider(ChatProvider):
            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                yield '{"thought":"Wrap up quickly","final":"Persistent run complete."}'

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_AGENT_RUN_DB_PATH"] = str(root / "agent-runs.db")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                service.provider = SequenceProvider()
                with TestClient(app) as client:
                    with client.stream(
                        "POST",
                        "/api/chat",
                        json={
                            "message": "Finish this as a background run.",
                            "fast_mode": False,
                            "retrieval_k": 2,
                            "mode": "agent",
                            "attachments": [],
                        },
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("Persistent run complete.", body)
                    self.assertIn('"run_id"', body)
                    session_id = client.get("/api/sessions").json()[0]["id"]
                    runs_payload = client.get(f"/api/agent/{session_id}/runs").json()
                    self.assertEqual(len(runs_payload["runs"]), 1)
                    run_id = runs_payload["runs"][0]["id"]
                    self.assertEqual(runs_payload["runs"][0]["status"], "completed")
                    self.assertGreater(runs_payload["runs"][0]["last_event_id"], 0)

                    run_payload = client.get(f"/api/agent/runs/{run_id}").json()
                    self.assertTrue(run_payload["ok"])
                    self.assertEqual(
                        run_payload["run"]["final_message"],
                        "Persistent run complete.",
                    )

                    with client.stream(
                        "GET",
                        f"/api/agent/runs/{run_id}/stream",
                    ) as response:
                        replay_body = "".join(response.iter_text())

                    self.assertIn("event: meta", replay_body)
                    self.assertIn("Persistent run complete.", replay_body)
                    self.assertIn(run_id, replay_body)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_run_resume_updates_same_persistent_run(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Need to run a test command",'
                        '"action":{"tool":"run_command","args":{"command":["python","--version"],"cwd":"."}}}'
                    )
                    return
                yield '{"thought":"Continue after approval","final":"Run resumed on the same persistent job."}'

        blocked_events = iter(
            [
                {
                    "event": "exec_start",
                    "payload": {
                        "command": ["python", "--version"],
                        "cwd": "/workspace",
                        "command_policy": {
                            "tier": "test",
                            "max_tier": "read_only",
                            "source": "agent",
                            "executable": "python",
                        },
                    },
                },
                {
                    "event": "exec_chunk",
                    "payload": {
                        "stream": "stderr",
                        "content": (
                            "Command tier `test` exceeds the allowed maximum "
                            "`read_only` for agent execution.\n"
                        ),
                    },
                },
                {
                    "event": "exec_done",
                    "payload": {
                        "returncode": 126,
                        "stdout": "",
                        "stderr": (
                            "Command tier `test` exceeds the allowed maximum "
                            "`read_only` for agent execution."
                        ),
                        "timed_out": False,
                        "files": [],
                        "sandbox": {
                            "blocked": True,
                            "violations": [
                                "Command tier `test` exceeds the allowed maximum "
                                "`read_only` for agent execution."
                            ],
                            "command_policy": {
                                "tier": "test",
                                "max_tier": "read_only",
                                "source": "agent",
                                "executable": "python",
                            },
                        },
                    },
                },
            ]
        )
        approved_events = iter(
            [
                {
                    "event": "exec_start",
                    "payload": {
                        "command": ["python", "--version"],
                        "cwd": "/workspace",
                        "command_policy": {
                            "tier": "test",
                            "max_tier": "test",
                            "source": "agent_approved",
                            "executable": "python",
                        },
                    },
                },
                {
                    "event": "exec_chunk",
                    "payload": {
                        "stream": "stdout",
                        "content": "Python 3.11.9\n",
                    },
                },
                {
                    "event": "exec_done",
                    "payload": {
                        "returncode": 0,
                        "stdout": "Python 3.11.9\n",
                        "stderr": "",
                        "timed_out": False,
                        "files": [],
                        "sandbox": {
                            "command_policy": {
                                "tier": "test",
                                "max_tier": "test",
                                "source": "agent_approved",
                                "executable": "python",
                            },
                            "violations": [],
                        },
                    },
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_AGENT_MAX_COMMAND_TIER"] = "read_only"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_AGENT_RUN_DB_PATH"] = str(root / "agent-runs.db")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                with TestClient(app) as client:
                    with patch.object(
                        service.executor,
                        "stream_command",
                        side_effect=[blocked_events, approved_events],
                    ):
                        with client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "message": "Run a test command if needed.",
                                "fast_mode": False,
                                "retrieval_k": 2,
                                "mode": "agent",
                                "attachments": [],
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                        self.assertIn("Approval required:", body)
                        session_id = client.get("/api/sessions").json()[0]["id"]
                        approvals = client.get(f"/api/agent/{session_id}/approvals").json()
                        approval_id = approvals["approvals"][0]["id"]

                        runs_payload = client.get(f"/api/agent/{session_id}/runs").json()
                        self.assertEqual(len(runs_payload["runs"]), 1)
                        run_id = runs_payload["runs"][0]["id"]
                        self.assertEqual(runs_payload["runs"][0]["status"], "blocked")
                        self.assertEqual(
                            runs_payload["runs"][0]["blocked_on_approval_id"],
                            approval_id,
                        )

                        with client.stream(
                            "POST",
                            f"/api/agent/{session_id}/approvals/{approval_id}/approve",
                        ) as response:
                            resume_body = "".join(response.iter_text())

                    self.assertIn("Run resumed on the same persistent job.", resume_body)
                    self.assertIn(run_id, resume_body)
                    run_payload = client.get(f"/api/agent/runs/{run_id}").json()["run"]
                    self.assertEqual(run_payload["status"], "completed")
                    self.assertEqual(run_payload["blocked_on_approval_id"], "")
                    self.assertIn(
                        "Run resumed on the same persistent job.",
                        run_payload["final_message"],
                    )

                    with client.stream(
                        "GET",
                        f"/api/agent/runs/{run_id}/stream",
                    ) as response:
                        replay_body = "".join(response.iter_text())

                    self.assertIn("approval_required", replay_body)
                    self.assertIn("Run resumed on the same persistent job.", replay_body)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_agent_run_queue_claims_retries_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_db_path = root / "agent-runs.db"
            store = AgentRunStore(run_db_path)
            run = store.create_run(
                session_id="queue",
                kind="agent_chat",
                title="Queue run",
                mode="agent",
                user_message="queue this work",
                fast_mode=False,
                model="mock-model",
                request={"message": "queue this work"},
            )
            queued = store.enqueue_job(
                run_id=str(run["id"]),
                job_type="agent_chat",
                payload={"session_id": "queue", "message": "queue this work"},
                max_attempts=3,
            )

            self.assertIsNotNone(queued)
            self.assertEqual(queued["queue_status"], "queued")

            claimed = store.claim_next_job(worker_id="worker-a", lease_seconds=30)
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed["run_id"], run["id"])
            self.assertEqual(claimed["queue_status"], "leased")
            self.assertEqual(claimed["attempt_count"], 1)
            self.assertTrue(
                store.heartbeat_job(
                    run_id=str(run["id"]),
                    lease_token=str(claimed["lease_token"]),
                    lease_seconds=30,
                )
            )

            retried = store.release_job_for_retry(
                run_id=str(run["id"]),
                lease_token=str(claimed["lease_token"]),
                delay_seconds=0,
                error_text="retry me",
            )
            self.assertIsNotNone(retried)
            self.assertEqual(retried["queue_status"], "queued")
            self.assertEqual(retried["last_error"], "retry me")

            claimed_again = store.claim_next_job(worker_id="worker-b", lease_seconds=30)
            self.assertIsNotNone(claimed_again)
            self.assertEqual(claimed_again["attempt_count"], 2)

            completed = store.complete_job(
                run_id=str(run["id"]),
                lease_token=str(claimed_again["lease_token"]),
                queue_status="completed",
            )
            self.assertIsNotNone(completed)
            self.assertEqual(completed["queue_status"], "completed")
            self.assertTrue(completed["terminal"])
            self.assertIsNone(store.claim_next_job(worker_id="worker-c", lease_seconds=30))

    def test_leased_agent_runs_are_requeued_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            run_db_path = root / "agent-runs.db"
            try:
                os.chdir(root)
                store = AgentRunStore(run_db_path)
                run = store.create_run(
                    session_id="recover",
                    kind="agent_chat",
                    title="Recovery run",
                    mode="agent",
                    user_message="continue later",
                    fast_mode=False,
                    model="mock-model",
                    request={"message": "continue later"},
                )
                store.enqueue_job(
                    run_id=str(run["id"]),
                    job_type="agent_chat",
                    payload={"session_id": "recover", "message": "continue later"},
                    max_attempts=3,
                )
                claimed = store.claim_next_job(worker_id="startup-test", lease_seconds=30)
                self.assertIsNotNone(claimed)
                store.update_run(
                    str(run["id"]),
                    status="running",
                    started_at="2026-03-31T10:00:00+00:00",
                )

                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                os.environ["FORGE_AGENT_RUN_DB_PATH"] = str(run_db_path)
                os.environ["FORGE_AGENT_WORKER_ENABLED"] = "false"
                _build_service.cache_clear()

                with TestClient(create_app()) as client:
                    run_payload = client.get(f"/api/agent/runs/{run['id']}").json()

                self.assertTrue(run_payload["ok"])
                self.assertEqual(run_payload["run"]["status"], "queued")
                self.assertEqual(run_payload["run"]["error_text"], "")
                service = _build_service()
                queue_job = service.agent_runs.get_queue_job(str(run["id"]))
                self.assertIsNotNone(queue_job)
                self.assertEqual(queue_job["queue_status"], "queued")
                replay_events = service.agent_runs.list_events(run_id=str(run["id"]))
                self.assertTrue(
                    any(
                        event["event"] == "agent_step"
                        and event["payload"].get("kind") == "worker_recovered"
                        for event in replay_events
                    )
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_execute_endpoint_blocks_disallowed_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/execute",
                        json={"session_id": "secure", "code": "import socket\nprint('nope')"},
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["returncode"], 126)
                    self.assertIn("not allowed", payload["stderr"])
                    self.assertTrue(payload["sandbox"]["blocked"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_execute_endpoint_blocks_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/execute",
                        json={
                            "session_id": "secure",
                            "code": "with open('../escape.txt', 'w', encoding='utf-8') as handle:\n    handle.write('blocked')",
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertNotEqual(payload["returncode"], 0)
                    self.assertIn("outside the workspace", payload["stderr"])
                    self.assertFalse((root / "escape.txt").exists())
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_execute_endpoint_allows_safe_workspace_file_io(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/execute",
                        json={
                            "session_id": "safe-files",
                            "code": (
                                "from pathlib import Path\n"
                                "Path('note.txt').write_text('hello sandbox', encoding='utf-8')\n"
                                "print(Path('note.txt').read_text(encoding='utf-8'))"
                            ),
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["returncode"], 0)
                    self.assertIn("hello sandbox", payload["stdout"])
                    self.assertIn("note.txt", payload["files"])
                    self.assertFalse(payload["sandbox"]["blocked"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_exec_endpoint_requires_docker_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/exec",
                        json={"session_id": "scratchpad", "command": ["git", "status"]},
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["returncode"], 127)
                    self.assertIn("Docker backend", payload["stderr"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_exec_stream_endpoint_emits_sse_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    with client.stream(
                        "POST",
                        "/api/exec/stream",
                        json={"session_id": "scratchpad", "command": ["git", "status"]},
                    ) as response:
                        body = "".join(response.iter_text())

                    self.assertIn("event: exec_start", body)
                    self.assertIn("event: exec_chunk", body)
                    self.assertIn("event: exec_done", body)
                    self.assertIn("Docker backend", body)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_file_endpoints_read_write_and_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    write_response = client.put(
                        "/api/workspace/editor/file",
                        json={
                            "path": "notes/todo.txt",
                            "content": "alpha\nbeta\n",
                        },
                    )
                    self.assertEqual(write_response.status_code, 200)
                    write_payload = write_response.json()
                    self.assertTrue(write_payload["ok"])
                    self.assertTrue(write_payload["created"])
                    self.assertIn("notes/todo.txt", write_payload["files"])

                    read_response = client.get(
                        "/api/workspace/editor/file",
                        params={
                            "path": "notes/todo.txt",
                            "start_line": 2,
                            "end_line": 2,
                        },
                    )
                    self.assertEqual(read_response.status_code, 200)
                    read_payload = read_response.json()
                    self.assertTrue(read_payload["ok"])
                    self.assertEqual(read_payload["content"], "beta")
                    self.assertEqual(read_payload["start_line"], 2)
                    self.assertEqual(read_payload["end_line"], 2)

                    replace_response = client.post(
                        "/api/workspace/editor/file/replace",
                        json={
                            "path": "notes/todo.txt",
                            "old_text": "beta",
                            "new_text": "gamma",
                        },
                    )
                    self.assertEqual(replace_response.status_code, 200)
                    replace_payload = replace_response.json()
                    self.assertTrue(replace_payload["ok"])
                    self.assertEqual(replace_payload["replacements"], 1)

                    verify_response = client.get(
                        "/api/workspace/editor/file",
                        params={"path": "notes/todo.txt"},
                    )
                    self.assertEqual(verify_response.status_code, 200)
                    verify_payload = verify_response.json()
                    self.assertTrue(verify_payload["ok"])
                    self.assertIn("gamma", verify_payload["content"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_review_endpoint_and_pending_patch_apply_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/replace",
                        json={
                            "path": "notes.txt",
                            "old_text": "alpha",
                            "new_text": "beta",
                        },
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    propose_payload = propose_response.json()
                    self.assertTrue(propose_payload["ok"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "alpha\n",
                    )
                    patch_id = propose_payload["patch"]["id"]

                    review_response = client.get("/api/workspace/editor/review")
                    self.assertEqual(review_response.status_code, 200)
                    review_payload = review_response.json()
                    self.assertTrue(review_payload["ok"])
                    self.assertIn("Pending review", review_payload["summary"])
                    self.assertIn("notes.txt", review_payload["changed_files"])
                    self.assertEqual(len(review_payload["changed_entries"]), 1)
                    self.assertEqual(
                        review_payload["changed_entries"][0]["source"],
                        "pending_patch",
                    )
                    self.assertEqual(
                        review_payload["changed_entries"][0]["status"],
                        "P",
                    )
                    self.assertIn("-alpha", review_payload["diff"])
                    self.assertIn("+beta", review_payload["diff"])

                    apply_response = client.post(
                        f"/api/workspace/editor/patches/{patch_id}/apply"
                    )
                    self.assertEqual(apply_response.status_code, 200)
                    apply_payload = apply_response.json()
                    self.assertTrue(apply_payload["ok"])
                    self.assertEqual(apply_payload["change"]["path"], "notes.txt")
                    self.assertEqual(apply_payload["change"]["source"], "api")
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "beta\n",
                    )

                    write_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={
                            "path": "draft.txt",
                            "content": "pending\n",
                        },
                    )
                    self.assertEqual(write_response.status_code, 200)
                    reject_patch_id = write_response.json()["patch"]["id"]
                    reject_response = client.post(
                        f"/api/workspace/editor/patches/{reject_patch_id}/reject"
                    )
                    self.assertEqual(reject_response.status_code, 200)
                    reject_payload = reject_response.json()
                    self.assertTrue(reject_payload["ok"])
                    self.assertFalse((workspace / "draft.txt").exists())
                    self.assertEqual(len(reject_payload["pending_patches"]), 0)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_hunk_accept_updates_file_and_keeps_remaining_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            base_content = (
                "alpha\n"
                "beta\n"
                "charlie\n"
                "delta\n"
                "echo\n"
                "foxtrot\n"
                "golf\n"
                "hotel\n"
                "india\n"
                "juliet\n"
            )
            target_content = (
                "alpha updated\n"
                "beta\n"
                "charlie\n"
                "delta\n"
                "echo\n"
                "foxtrot\n"
                "golf\n"
                "hotel\n"
                "india\n"
                "juliet updated\n"
            )
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(base_content, encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={
                            "path": "notes.txt",
                            "content": target_content,
                        },
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    propose_payload = propose_response.json()
                    self.assertTrue(propose_payload["ok"])
                    self.assertEqual(propose_payload["patch"]["hunk_count"], 2)
                    patch_id = propose_payload["patch"]["id"]

                    accept_response = client.post(
                        f"/api/workspace/editor/patches/{patch_id}/hunks/0/accept"
                    )
                    self.assertEqual(accept_response.status_code, 200)
                    accept_payload = accept_response.json()
                    self.assertTrue(accept_payload["ok"])
                    self.assertTrue(accept_payload["accepted"])
                    self.assertEqual(accept_payload["change"]["operation"], "patch_hunk")
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        base_content.replace("alpha\n", "alpha updated\n", 1),
                    )
                    self.assertEqual(len(accept_payload["pending_patches"]), 1)
                    remaining_patch = accept_payload["pending_patches"][0]
                    self.assertEqual(remaining_patch["hunk_count"], 1)
                    self.assertIn("-juliet", remaining_patch["hunks"][0]["diff"])
                    self.assertIn("+juliet updated", remaining_patch["hunks"][0]["diff"])
                    self.assertNotIn("alpha updated", remaining_patch["diff"])

                    history_payload = client.get("/api/workspace/editor/changes").json()
                    self.assertEqual(len(history_payload["applied_changes"]), 1)
                    self.assertEqual(
                        history_payload["applied_changes"][0]["summary"],
                        "Accepted hunk 1 of 2 in notes.txt",
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_hunk_reject_keeps_workspace_and_trims_pending_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            base_content = (
                "alpha\n"
                "beta\n"
                "charlie\n"
                "delta\n"
                "echo\n"
                "foxtrot\n"
                "golf\n"
                "hotel\n"
                "india\n"
                "juliet\n"
            )
            target_content = (
                "alpha updated\n"
                "beta\n"
                "charlie\n"
                "delta\n"
                "echo\n"
                "foxtrot\n"
                "golf\n"
                "hotel\n"
                "india\n"
                "juliet updated\n"
            )
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(base_content, encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={
                            "path": "notes.txt",
                            "content": target_content,
                        },
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    propose_payload = propose_response.json()
                    self.assertTrue(propose_payload["ok"])
                    self.assertEqual(propose_payload["patch"]["hunk_count"], 2)
                    patch_id = propose_payload["patch"]["id"]

                    reject_response = client.post(
                        f"/api/workspace/editor/patches/{patch_id}/hunks/0/reject"
                    )
                    self.assertEqual(reject_response.status_code, 200)
                    reject_payload = reject_response.json()
                    self.assertTrue(reject_payload["ok"])
                    self.assertTrue(reject_payload["rejected"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        base_content,
                    )
                    self.assertEqual(len(reject_payload["pending_patches"]), 1)
                    remaining_patch = reject_payload["pending_patches"][0]
                    self.assertEqual(remaining_patch["hunk_count"], 1)
                    self.assertIn("-juliet", remaining_patch["hunks"][0]["diff"])
                    self.assertIn("+juliet updated", remaining_patch["hunks"][0]["diff"])
                    self.assertNotIn("alpha updated", remaining_patch["diff"])

                    history_payload = client.get("/api/workspace/editor/changes").json()
                    self.assertEqual(history_payload["applied_changes"], [])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_line_accept_updates_only_selected_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            base_content = "alpha\nbravo\ncharlie\n"
            target_content = "alpha updated\nbravo updated\ncharlie\n"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(base_content, encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={
                            "path": "notes.txt",
                            "content": target_content,
                        },
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    patch = propose_response.json()["patch"]
                    self.assertEqual(patch["hunk_count"], 1)
                    self.assertEqual(patch["hunks"][0]["line_count"], 2)

                    accept_response = client.post(
                        f"/api/workspace/editor/patches/{patch['id']}/hunks/0/lines/0/accept"
                    )
                    self.assertEqual(accept_response.status_code, 200)
                    accept_payload = accept_response.json()
                    self.assertTrue(accept_payload["ok"])
                    self.assertEqual(accept_payload["change"]["operation"], "patch_line")
                    self.assertEqual(
                        accept_payload["change"]["summary"],
                        "Accepted line 1 of 2 in hunk 1 of 1 in notes.txt",
                    )
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "alpha updated\nbravo\ncharlie\n",
                    )
                    self.assertEqual(len(accept_payload["pending_patches"]), 1)
                    remaining_patch = accept_payload["pending_patches"][0]
                    self.assertEqual(remaining_patch["hunk_count"], 1)
                    self.assertEqual(remaining_patch["hunks"][0]["line_count"], 1)
                    self.assertEqual(
                        remaining_patch["hunks"][0]["lines"][0]["after_text"],
                        "bravo updated",
                    )
                    self.assertEqual(
                        remaining_patch["hunks"][0]["lines"][0]["before_text"],
                        "bravo",
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_line_reject_keeps_other_lines_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            base_content = "alpha\nbravo\ncharlie\n"
            target_content = "alpha updated\nbravo updated\ncharlie\n"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(base_content, encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={
                            "path": "notes.txt",
                            "content": target_content,
                        },
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    patch = propose_response.json()["patch"]
                    self.assertEqual(patch["hunks"][0]["line_count"], 2)

                    reject_response = client.post(
                        f"/api/workspace/editor/patches/{patch['id']}/hunks/0/lines/0/reject"
                    )
                    self.assertEqual(reject_response.status_code, 200)
                    reject_payload = reject_response.json()
                    self.assertTrue(reject_payload["ok"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        base_content,
                    )
                    self.assertEqual(reject_payload["applied_changes"], [])
                    self.assertEqual(len(reject_payload["pending_patches"]), 1)
                    remaining_patch = reject_payload["pending_patches"][0]
                    self.assertEqual(remaining_patch["hunk_count"], 1)
                    self.assertEqual(remaining_patch["hunks"][0]["line_count"], 1)
                    self.assertEqual(
                        remaining_patch["hunks"][0]["lines"][0]["before_text"],
                        "bravo",
                    )
                    self.assertEqual(
                        remaining_patch["hunks"][0]["lines"][0]["after_text"],
                        "bravo updated",
                    )
                    self.assertNotIn("alpha updated", remaining_patch["diff"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_line_edit_updates_pending_patch_and_accept_uses_new_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            base_content = "alpha\nbravo\ncharlie\n"
            target_content = "alpha updated\nbravo\ncharlie\n"
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(base_content, encoding="utf-8")

                with TestClient(create_app()) as client:
                    propose_response = client.post(
                        "/api/workspace/editor/patches/write",
                        json={"path": "notes.txt", "content": target_content},
                    )
                    self.assertEqual(propose_response.status_code, 200)
                    patch = propose_response.json()["patch"]
                    self.assertEqual(patch["hunks"][0]["line_count"], 1)

                    edit_response = client.post(
                        f"/api/workspace/editor/patches/{patch['id']}/hunks/0/lines/0/edit",
                        json={"after_text": "alpha tuned"},
                    )
                    self.assertEqual(edit_response.status_code, 200)
                    edit_payload = edit_response.json()
                    self.assertTrue(edit_payload["ok"])
                    self.assertTrue(edit_payload["edited"])
                    self.assertEqual(
                        edit_payload["patch"]["hunks"][0]["lines"][0]["after_text"],
                        "alpha tuned",
                    )
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        base_content,
                    )

                    accept_response = client.post(
                        f"/api/workspace/editor/patches/{patch['id']}/hunks/0/lines/0/accept"
                    )
                    self.assertEqual(accept_response.status_code, 200)
                    accept_payload = accept_response.json()
                    self.assertTrue(accept_payload["ok"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "alpha tuned\nbravo\ncharlie\n",
                    )
                    self.assertEqual(accept_payload["pending_patches"], [])
                    self.assertEqual(
                        accept_payload["change"]["summary"],
                        "Accepted line 1 of 1 in hunk 1 of 1 in notes.txt",
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_change_history_lists_and_rolls_back_direct_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")

                with TestClient(create_app()) as client:
                    write_response = client.put(
                        "/api/workspace/editor/file",
                        json={"path": "notes.txt", "content": "beta\n"},
                    )
                    self.assertEqual(write_response.status_code, 200)
                    write_payload = write_response.json()
                    self.assertTrue(write_payload["ok"])
                    self.assertEqual(write_payload["change"]["operation"], "write")

                    history_response = client.get("/api/workspace/editor/changes")
                    self.assertEqual(history_response.status_code, 200)
                    history_payload = history_response.json()
                    self.assertEqual(len(history_payload["applied_changes"]), 1)
                    change = history_payload["applied_changes"][0]
                    self.assertEqual(change["path"], "notes.txt")
                    self.assertTrue(change["rollback_ready"])

                    rollback_response = client.post(
                        f"/api/workspace/editor/changes/{change['id']}/rollback"
                    )
                    self.assertEqual(rollback_response.status_code, 200)
                    rollback_payload = rollback_response.json()
                    self.assertTrue(rollback_payload["ok"])
                    self.assertTrue(rollback_payload["rolled_back"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "alpha\n",
                    )
                    self.assertEqual(rollback_payload["change"]["operation"], "rollback")
                    self.assertEqual(len(rollback_payload["applied_changes"]), 2)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_change_rollback_requires_latest_applied_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")

                with TestClient(create_app()) as client:
                    first_write = client.put(
                        "/api/workspace/editor/file",
                        json={"path": "notes.txt", "content": "beta\n"},
                    ).json()
                    observation = client.get("/api/workspace/editor/changes").json()
                    second_write = client.put(
                        "/api/workspace/editor/file",
                        json={"path": "notes.txt", "content": "gamma\n"},
                    ).json()
                    self.assertTrue(first_write["ok"])
                    self.assertTrue(observation["ok"])
                    self.assertTrue(second_write["ok"])
                    rollback_observation = client.get("/api/workspace/editor/changes").json()
                    self.assertTrue(rollback_observation["ok"])

                    stale_change_id = first_write["change"]["id"]
                    rollback_response = client.post(
                        f"/api/workspace/editor/changes/{stale_change_id}/rollback"
                    )
                    self.assertEqual(rollback_response.status_code, 200)
                    rollback_payload = rollback_response.json()
                    self.assertFalse(rollback_payload["ok"])
                    self.assertIn("changed again", rollback_payload["error"])
                    self.assertEqual(
                        (workspace / "notes.txt").read_text(encoding="utf-8"),
                        "gamma\n",
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_payload_exposes_verification_presets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "package.json").write_text(
                    json.dumps(
                        {
                            "name": "forge-demo",
                            "scripts": {
                                "test": "vitest run",
                                "lint": "eslint .",
                            },
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                with TestClient(create_app()) as client:
                    payload = client.get("/api/workspace/editor").json()
                    self.assertTrue(payload["verification"]["available"])
                    self.assertEqual(payload["verification"]["default_preset_id"], "full")
                    preset_ids = [
                        preset["id"] for preset in payload["verification"]["presets"]
                    ]
                    self.assertEqual(preset_ids, ["full", "tests", "lint"])
                    self.assertEqual(
                        payload["verification"]["presets"][0]["commands"],
                        ["npm test", "npm run lint"],
                    )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_change_verification_records_success_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                (workspace / "tests").mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")
                (workspace / "tests" / "test_dummy.py").write_text(
                    "def test_ok():\n    assert True\n",
                    encoding="utf-8",
                )

                service = _build_service()
                with patch.object(
                    service.executor,
                    "execute_command",
                    return_value=CommandExecutionResult(
                        session_id="editor",
                        command=["pytest", "-q"],
                        cwd=".",
                        returncode=0,
                        stdout="1 passed\n",
                        stderr="",
                        timed_out=False,
                        files=["notes.txt", "tests/test_dummy.py"],
                        sandbox={"backend": "docker"},
                    ),
                ) as mocked_execute:
                    with TestClient(create_app()) as client:
                        write_payload = client.put(
                            "/api/workspace/editor/file",
                            json={"path": "notes.txt", "content": "beta\n"},
                        ).json()
                        change_id = write_payload["change"]["id"]

                        verify_payload = client.post(
                            f"/api/workspace/editor/changes/{change_id}/verify",
                            json={"preset_id": "tests"},
                        ).json()

                        self.assertTrue(verify_payload["ok"])
                        self.assertTrue(verify_payload["verification"]["ok"])
                        self.assertEqual(verify_payload["verification"]["status"], "passed")
                        self.assertEqual(verify_payload["verification"]["label"], "Tests")
                        self.assertEqual(
                            verify_payload["change"]["verification"]["results"][0]["stdout"],
                            "1 passed\n",
                        )
                        self.assertEqual(
                            mocked_execute.call_args.kwargs["command"],
                            ["pytest", "-q"],
                        )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_change_verification_records_failure_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")
                (workspace / "package.json").write_text(
                    json.dumps(
                        {
                            "name": "forge-demo",
                            "scripts": {
                                "test": "vitest run",
                                "lint": "eslint .",
                            },
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                service = _build_service()
                with patch.object(
                    service.executor,
                    "execute_command",
                    side_effect=[
                        CommandExecutionResult(
                            session_id="editor",
                            command=["npm", "test"],
                            cwd=".",
                            returncode=0,
                            stdout="tests passed\n",
                            stderr="",
                            timed_out=False,
                            files=["notes.txt", "package.json"],
                            sandbox={"backend": "docker"},
                        ),
                        CommandExecutionResult(
                            session_id="editor",
                            command=["npm", "run", "lint"],
                            cwd=".",
                            returncode=1,
                            stdout="",
                            stderr="lint failed\n",
                            timed_out=False,
                            files=["notes.txt", "package.json"],
                            sandbox={"backend": "docker"},
                        ),
                    ],
                ):
                    with TestClient(create_app()) as client:
                        write_payload = client.put(
                            "/api/workspace/editor/file",
                            json={"path": "notes.txt", "content": "beta\n"},
                        ).json()
                        change_id = write_payload["change"]["id"]

                        verify_payload = client.post(
                            f"/api/workspace/editor/changes/{change_id}/verify",
                            json={"preset_id": "full"},
                        ).json()

                        self.assertTrue(verify_payload["ok"])
                        self.assertFalse(verify_payload["verification"]["ok"])
                        self.assertEqual(verify_payload["verification"]["status"], "failed")
                        self.assertIn("npm run lint", verify_payload["verification"]["summary"])
                        self.assertEqual(
                            verify_payload["change"]["verification"]["results"][1]["stderr"],
                            "lint failed\n",
                        )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_review_workspace_parses_git_status_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                service = _build_service()
                with patch.object(
                    service,
                    "execute_command",
                    side_effect=[
                        {
                            "returncode": 0,
                            "stdout": "M  src/app.py\n?? notes.md\n",
                            "stderr": "",
                            "timed_out": False,
                            "files": [],
                            "sandbox": {},
                        },
                        {
                            "returncode": 0,
                            "stdout": (
                                " src/app.py | 2 +-\n"
                                " notes.md   | 1 +\n"
                                " 2 files changed, 2 insertions(+), 1 deletion(-)\n"
                            ),
                            "stderr": "",
                            "timed_out": False,
                            "files": [],
                            "sandbox": {},
                        },
                        {
                            "returncode": 0,
                            "stdout": (
                                "diff --git a/src/app.py b/src/app.py\n"
                                "--- a/src/app.py\n"
                                "+++ b/src/app.py\n"
                            ),
                            "stderr": "",
                            "timed_out": False,
                            "files": [],
                            "sandbox": {},
                        },
                    ],
                ):
                    review = service.review_workspace(session_id="repo")

                self.assertTrue(review["ok"])
                self.assertEqual(review["changed_files"], ["notes.md", "src/app.py"])
                self.assertIn("2 files changed", review["diff_stat"])
                self.assertTrue(
                    any(
                        entry["source"] == "git"
                        and entry["status"] == "M"
                        and entry["path"] == "src/app.py"
                        for entry in review["changed_entries"]
                    )
                )
                self.assertTrue(
                    any(
                        entry["source"] == "git"
                        and entry["status"] == "??"
                        and entry["path"] == "notes.md"
                        for entry in review["changed_entries"]
                    )
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_preview_and_apply_multi_hunk_diff(self) -> None:
        patch_text = (
            "@@ -1,2 +1,2 @@\n"
            "-alpha\n"
            "+alpha updated\n"
            " beta\n"
            "@@ -3,2 +3,2 @@\n"
            " gamma\n"
            "-delta\n"
            "+delta updated\n"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text(
                    "alpha\nbeta\ngamma\ndelta\n",
                    encoding="utf-8",
                )

                with TestClient(create_app()) as client:
                    preview_response = client.post(
                        "/api/workspace/editor/patch/preview",
                        json={
                            "path": "notes.txt",
                            "patch": patch_text,
                        },
                    )
                    self.assertEqual(preview_response.status_code, 200)
                    preview_payload = preview_response.json()
                    self.assertTrue(preview_payload["ok"])
                    self.assertTrue(preview_payload["can_apply"])
                    self.assertEqual(preview_payload["hunk_count"], 2)
                    self.assertEqual(preview_payload["additions"], 2)
                    self.assertEqual(preview_payload["deletions"], 2)
                    self.assertIn("@@ -1,2 +1,2 @@", preview_payload["preview"])

                    apply_response = client.post(
                        "/api/workspace/editor/patch/apply",
                        json={
                            "path": "notes.txt",
                            "patch": patch_text,
                            "expected_hash": preview_payload["current_hash"],
                        },
                    )
                    self.assertEqual(apply_response.status_code, 200)
                    apply_payload = apply_response.json()
                    self.assertTrue(apply_payload["ok"])
                    self.assertEqual(apply_payload["hunk_count"], 2)
                    self.assertIn("notes.txt", apply_payload["files"])

                self.assertEqual(
                    (workspace / "notes.txt").read_text(encoding="utf-8"),
                    "alpha updated\nbeta\ngamma\ndelta updated\n",
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_patch_preview_reports_context_mismatch(self) -> None:
        patch_text = "@@ -1,1 +1,1 @@\n-wrong\n+right\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                workspace = root / "workspaces" / "editor"
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "notes.txt").write_text("alpha\n", encoding="utf-8")

                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/workspace/editor/patch/preview",
                        json={
                            "path": "notes.txt",
                            "patch": patch_text,
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertTrue(payload["ok"])
                    self.assertFalse(payload["can_apply"])
                    self.assertIn("does not match", " ".join(payload["issues"]))
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()

    def test_workspace_file_endpoint_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.put(
                        "/api/workspace/editor/file",
                        json={
                            "path": "../escape.txt",
                            "content": "blocked",
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertFalse(payload["ok"])
                    self.assertIn("inside the session workspace", payload["error"])
                    self.assertFalse((root / "escape.txt").exists())
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _build_service.cache_clear()


class ToolRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_mode_triggers_search_results(self) -> None:
        router = ToolRouter()
        with patch.object(
            router.navigator,
            "search",
            AsyncMock(
                return_value=[
                    type(
                        "SearchResultLike",
                        (),
                        {
                            "title": "Example",
                            "url": "https://example.com",
                            "snippet": "Example snippet",
                        },
                    )()
                ]
            ),
        ), patch.object(
            router.navigator,
            "fetch_page",
            AsyncMock(return_value="Example page body"),
        ):
            results = await router.run(
                "Tell me the latest on example topic",
                enable_remote_fetch=True,
                mode="deep",
            )

        names = [result.name for result in results]
        self.assertIn("web_search", names)
        self.assertIn("web_page", names)


class DockerSandboxTests(unittest.TestCase):
    def test_auto_backend_falls_back_to_local_when_docker_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="auto")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(False, "Docker daemon is offline."),
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                result = executor.execute(session_id="demo", code="print('hello')")

        self.assertEqual(result.returncode, 0)
        self.assertIn("hello", result.stdout)
        self.assertEqual(result.sandbox["backend"], "local")
        self.assertTrue(result.sandbox["fallback"]["used"])

    def test_docker_backend_reports_unavailable_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(False, "Docker daemon is offline."),
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                result = executor.execute(session_id="demo", code="print('hello')")

        self.assertEqual(result.returncode, 127)
        self.assertIn("offline", result.stderr.lower())
        self.assertEqual(result.sandbox["backend"], "docker")
        self.assertFalse(result.sandbox["fallback"]["used"])

    def test_docker_command_includes_isolation_flags(self) -> None:
        manager = WorkspaceManager(Path(tempfile.gettempdir()) / "forge-docker-test")
        config = DockerSandboxConfig(
            backend_preference="docker",
            image="python:3.11-alpine",
        )
        container_manager = DockerSessionContainerManager(manager, config)
        create_command = container_manager.build_create_command(
            session_id="demo",
            workspace=manager.workspace_for("demo"),
        )
        exec_command = container_manager.build_exec_command(
            session_id="demo",
            argv=["python", "-I", "-S", "-B", "/workspace/bootstrap.py"],
        )

        joined_create = " ".join(str(part) for part in create_command)
        joined_exec = " ".join(str(part) for part in exec_command)
        self.assertIn("docker run -d --name", joined_create)
        self.assertIn("--network none", joined_create)
        self.assertIn("--read-only", joined_create)
        self.assertIn("--cap-drop ALL", joined_create)
        self.assertIn("python:3.11-alpine", joined_create)
        self.assertIn("while true; do sleep 3600; done", joined_create)
        self.assertIn("docker exec --workdir /workspace", joined_exec)
        self.assertIn("bootstrap.py", joined_exec)

    def test_execute_command_blocks_disallowed_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(True, "Docker server is available."),
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                result = executor.execute_command(
                    session_id="demo",
                    command=["rm", "-rf", "/"],
                    cwd=".",
                    timeout_seconds=10,
                    allowed_commands=("python", "git"),
                )

        self.assertEqual(result.returncode, 126)
        self.assertIn("blocked", result.stderr.lower())

    def test_execute_command_blocks_git_branch_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(True, "Docker server is available."),
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                result = executor.execute_command(
                    session_id="demo",
                    command=["git", "branch"],
                    cwd=".",
                    timeout_seconds=10,
                    allowed_commands=("git",),
                    max_command_tier="read_only",
                    request_source="agent",
                )

        self.assertEqual(result.returncode, 126)
        self.assertIn("Git subcommand `branch` is not allowed.", result.stderr)
        self.assertEqual(result.sandbox["command_policy"]["tier"], "read_only")

    def test_execute_command_enforces_agent_command_tier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(True, "Docker server is available."),
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                result = executor.execute_command(
                    session_id="demo",
                    command=["python", "--version"],
                    cwd=".",
                    timeout_seconds=10,
                    allowed_commands=("python", "git"),
                    max_command_tier="read_only",
                    request_source="agent",
                )

        self.assertEqual(result.returncode, 126)
        self.assertIn("allowed maximum", result.stderr)
        self.assertEqual(result.sandbox["command_policy"]["tier"], "test")
        self.assertEqual(result.sandbox["command_policy"]["max_tier"], "read_only")
        self.assertEqual(result.sandbox["command_policy"]["source"], "agent")

    def test_status_payload_includes_session_container_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(True, "Docker server is available."),
            ), patch.object(
                DockerSandboxExecutor,
                "session_payload",
                return_value={
                    "session_id": "demo",
                    "container_name": "forge-demo",
                    "exists": True,
                    "running": True,
                    "status": "running",
                },
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                payload = executor.status_payload("demo")

        self.assertEqual(payload["active_backend"], "docker")
        self.assertEqual(payload["session"]["container_name"], "forge-demo")

    def test_reset_session_delegates_to_docker_manager(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = WorkspaceManager(Path(temp_dir))
            policy = SandboxPolicy(timeout_seconds=5)
            config = DockerSandboxConfig(backend_preference="docker")
            with patch.object(
                DockerSessionContainerManager,
                "_detect_availability",
                return_value=(True, "Docker server is available."),
            ), patch.object(
                DockerSandboxExecutor,
                "reset_session",
                return_value={"session_id": "demo", "removed": True},
            ):
                executor = build_executor(
                    workspace_manager=manager,
                    policy=policy,
                    docker_config=config,
                )
                payload = executor.reset_session("demo")

        self.assertTrue(payload["removed"])


class WorkspaceProjectAndTaskTests(unittest.TestCase):
    def test_workspace_import_upload_accepts_zip_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "importer"
                archive_path = root / "repo.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("src/app.py", "print('demo')\n")
                    archive.writestr("README.md", "# Demo\n")

                with TestClient(app) as client:
                    response = client.post(
                        f"/api/workspace/{session_id}/import/upload",
                        files={
                            "file": (
                                "repo.zip",
                                archive_path.read_bytes(),
                                "application/zip",
                            )
                        },
                        data={"target_path": "project"},
                    )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["import"]["kind"], "archive")
                    self.assertIn("project/src/app.py", payload["files"])
                    self.assertIn("project/README.md", payload["files"])

                    workspace_payload = client.get(f"/api/workspace/{session_id}").json()
                    self.assertEqual(len(workspace_payload["imports"]), 1)
                    self.assertEqual(workspace_payload["imports"][0]["kind"], "archive")
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_clone_records_import_and_hides_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()

                def fake_clone(
                    command: list[str],
                    *,
                    capture_output: bool,
                    text: bool,
                    encoding: str,
                    timeout: float,
                    creationflags: int,
                    cwd: Path | None = None,
                ) -> subprocess.CompletedProcess[str]:
                    if command and command[0] == "git" and "clone" in command:
                        target = Path(command[-1])
                        target.mkdir(parents=True, exist_ok=True)
                        (target / ".git").mkdir(parents=True, exist_ok=True)
                        (target / ".git" / "config").write_text("[core]\n", encoding="utf-8")
                        (target / "pkg").mkdir(parents=True, exist_ok=True)
                        (target / "pkg" / "main.py").write_text(
                            "print('demo')\n",
                            encoding="utf-8",
                        )
                        return subprocess.CompletedProcess(command, 0, "", "")
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch("evolving_ai.app.projects.subprocess.run", side_effect=fake_clone):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/workspace/cloner/import/clone",
                            json={
                                "repo_url": "https://github.com/example/demo.git",
                                "target_dir": "demo",
                            },
                        )

                        self.assertEqual(response.status_code, 200)
                        payload = response.json()
                        self.assertTrue(payload["ok"])
                        self.assertEqual(payload["import"]["kind"], "clone")
                        self.assertIn("demo/pkg/main.py", payload["files"])
                        self.assertFalse(
                            any(".git/" in item or item.startswith(".git") for item in payload["files"])
                        )

                        workspace_payload = client.get("/api/workspace/cloner").json()
                        self.assertEqual(len(workspace_payload["imports"]), 1)
                        self.assertEqual(workspace_payload["imports"][0]["kind"], "clone")
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_task_run_records_review_and_supports_approval(self) -> None:
        class SequenceProvider(ChatProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def stream_reply(
                self,
                *,
                messages: list[dict[str, str]],
                fast_mode: bool,
                mode: str,
                model: str,
                attachments: list[Attachment],
            ):
                self.calls += 1
                if self.calls == 1:
                    yield (
                        '{"thought":"Inspect the workspace first",'
                        '"action":{"tool":"review_workspace","args":{}}}'
                    )
                    return
                if self.calls == 2:
                    yield (
                        '{"thought":"Write the task output",'
                        '"action":{"tool":"write_file","args":{"path":"notes.txt","content":"task output\\n"}}}'
                    )
                    return
                if self.calls == 3:
                    yield (
                        '{"thought":"Run the requested tests",'
                        '"action":{"tool":"run_command","args":{"command":["pytest","-q"],"cwd":"."}}}'
                    )
                    return
                if self.calls == 4:
                    yield (
                        '{"thought":"Review the finished workspace",'
                        '"action":{"tool":"review_workspace","args":{}}}'
                    )
                    return
                yield (
                    '{"thought":"Task is ready",'
                    '"final":"I created notes.txt, ran pytest -q, and reviewed the workspace."}'
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                provider = SequenceProvider()
                service.provider = provider
                session_id = "tasker"
                workspace = root / "workspaces" / session_id
                (workspace / ".git").mkdir(parents=True, exist_ok=True)
                (workspace / "src").mkdir(parents=True, exist_ok=True)
                (workspace / "src" / "app.py").write_text(
                    "def run() -> str:\n    return 'ok'\n",
                    encoding="utf-8",
                )
                git_branch = {"name": "main"}

                def fake_run_git(
                    repo_root: Path, arguments: list[str]
                ) -> subprocess.CompletedProcess[str] | None:
                    if arguments == ["status", "--short"]:
                        return _git_completed(arguments, stdout="M  src/app.py\n")
                    if arguments == ["diff", "--stat"]:
                        return _git_completed(
                            arguments,
                            stdout=(
                                " src/app.py | 2 +-\n"
                                " 1 file changed, 1 insertion(+), 1 deletion(-)\n"
                            ),
                        )
                    if arguments == ["diff", "--no-ext-diff", "--unified=3"]:
                        return _git_completed(
                            arguments,
                            stdout=(
                                "diff --git a/src/app.py b/src/app.py\n"
                                "--- a/src/app.py\n"
                                "+++ b/src/app.py\n"
                                "@@ -1,2 +1,2 @@\n"
                                "-def run() -> str:\n"
                                "-    return 'old'\n"
                                "+def run() -> str:\n"
                                "+    return 'ok'\n"
                            ),
                        )
                    if arguments == ["rev-parse", "--abbrev-ref", "HEAD"]:
                        return _git_completed(arguments, stdout=f"{git_branch['name']}\n")
                    if arguments == ["rev-parse", "--short", "HEAD"]:
                        return _git_completed(arguments, stdout="abc1234\n")
                    if arguments == ["log", "--oneline", "-5"]:
                        return _git_completed(
                            arguments,
                            stdout="abc1234 Initial commit\n",
                        )
                    return _git_completed(arguments, returncode=1, stderr="unsupported git call")

                with TestClient(app) as client:
                    with patch.object(
                        service.executor,
                        "stream_command",
                        return_value=iter(
                            [
                                {
                                    "event": "exec_start",
                                    "payload": {
                                        "session_id": session_id,
                                        "command": ["pytest", "-q"],
                                        "cwd": "/workspace",
                                        "command_policy": {
                                            "tier": "test",
                                            "max_tier": "test",
                                            "source": "agent",
                                        },
                                    },
                                },
                                {
                                    "event": "exec_chunk",
                                    "payload": {
                                        "content": "1 passed\n",
                                        "stream": "stdout",
                                    },
                                },
                                {
                                    "event": "exec_done",
                                    "payload": {
                                        "session_id": session_id,
                                        "command": ["pytest", "-q"],
                                        "cwd": "/workspace",
                                        "returncode": 0,
                                        "stdout": "1 passed\n",
                                        "stderr": "",
                                        "timed_out": False,
                                        "files": ["notes.txt"],
                                        "sandbox": {
                                            "backend": "local",
                                            "blocked": False,
                                            "violations": [],
                                            "command_policy": {
                                                "tier": "test",
                                                "max_tier": "test",
                                                "source": "agent",
                                            },
                                        },
                                    },
                                },
                            ]
                        ),
                    ), patch.object(
                        service.project_manager,
                        "_run_git",
                        side_effect=fake_run_git,
                    ):
                        with client.stream(
                            "POST",
                            f"/api/workspace/{session_id}/tasks/run",
                            json={
                                "goal": "Create notes.txt and validate the result.",
                                "test_commands": ["pytest -q"],
                                "fast_mode": False,
                            },
                        ) as response:
                            body = "".join(response.iter_text())

                    self.assertIn("event: task_plan", body)
                    self.assertIn("event: task_result", body)
                    self.assertIn("pytest -q", body)
                    self.assertIn("review_workspace", body)
                    self.assertIn("branch_suggestion", body)
                    self.assertIn("commit_message", body)
                    self.assertIn(
                        "I created notes.txt, ran pytest -q, and reviewed the workspace.",
                        body,
                    )

                    task_payload = client.get(f"/api/workspace/{session_id}/tasks").json()
                    self.assertEqual(len(task_payload["tasks"]), 1)
                    task = task_payload["tasks"][0]
                    self.assertEqual(task["status"], "ready_for_approval")
                    self.assertEqual(task["phase"], "approve")
                    self.assertIn("Applied workspace edits", task["review_summary"])
                    self.assertEqual(task["plan"]["branch_suggestion"], "codex/create-notes-txt-and-validate-the")
                    self.assertEqual(
                        task["git_handoff"]["commit_message"]["subject"],
                        "feat: create notes txt and validate the",
                    )
                    self.assertEqual(
                        task["git_handoff"]["current_branch"],
                        "main",
                    )

                    approve_response = client.post(
                        f"/api/workspace/{session_id}/tasks/{task['id']}/approve",
                        json={"note": "ready"},
                    )
                    self.assertEqual(approve_response.status_code, 200)
                    approve_payload = approve_response.json()
                    approved_task = approve_payload["task"]
                    self.assertEqual(approved_task["status"], "approved")
                    self.assertEqual(
                        approve_payload["git_handoff"]["pull_request"]["title"],
                        "feat: create notes txt and validate the",
                    )
                    self.assertEqual(
                        (root / "workspaces" / session_id / "notes.txt").read_text(
                            encoding="utf-8"
                        ),
                        "task output\n",
                    )
                    self.assertEqual(provider.calls, 5)
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_task_plan_and_git_workflow_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                service = _build_service()
                session_id = "planner"
                workspace = root / "workspaces" / session_id
                (workspace / ".git").mkdir(parents=True, exist_ok=True)
                (workspace / "src").mkdir(parents=True, exist_ok=True)
                (workspace / "src" / "app.py").write_text(
                    "def run() -> str:\n    return 'v1'\n",
                    encoding="utf-8",
                )
                git_branch = {"name": "main"}

                def fake_run_git(
                    repo_root: Path, arguments: list[str]
                ) -> subprocess.CompletedProcess[str] | None:
                    if arguments == ["status", "--short"]:
                        return _git_completed(arguments, stdout="M  src/app.py\n")
                    if arguments == ["diff", "--stat"]:
                        return _git_completed(
                            arguments,
                            stdout=(
                                " src/app.py | 2 +-\n"
                                " 1 file changed, 1 insertion(+), 1 deletion(-)\n"
                            ),
                        )
                    if arguments == ["diff", "--no-ext-diff", "--unified=3"]:
                        return _git_completed(
                            arguments,
                            stdout=(
                                "diff --git a/src/app.py b/src/app.py\n"
                                "--- a/src/app.py\n"
                                "+++ b/src/app.py\n"
                                "@@ -1,2 +1,2 @@\n"
                                "-def run() -> str:\n"
                                "-    return 'v0'\n"
                                "+def run() -> str:\n"
                                "+    return 'v1'\n"
                            ),
                        )
                    if arguments == ["rev-parse", "--abbrev-ref", "HEAD"]:
                        return _git_completed(arguments, stdout=f"{git_branch['name']}\n")
                    if arguments == ["rev-parse", "--short", "HEAD"]:
                        return _git_completed(arguments, stdout="abc1234\n")
                    if arguments == ["log", "--oneline", "-5"]:
                        return _git_completed(
                            arguments,
                            stdout=(
                                "abc1234 Initial commit\n"
                                "9999999 Bootstrap workspace\n"
                            ),
                        )
                    if arguments[:2] == ["check-ref-format", "--branch"]:
                        return _git_completed(arguments, stdout=f"{arguments[-1]}\n")
                    if arguments[:2] == ["rev-parse", "--verify"]:
                        return _git_completed(arguments, returncode=1, stderr="missing branch")
                    if arguments[:2] == ["switch", "-c"]:
                        git_branch["name"] = arguments[-1]
                        return _git_completed(
                            arguments,
                            stdout=f"Switched to a new branch '{arguments[-1]}'\n",
                        )
                    return _git_completed(arguments, returncode=1, stderr="unsupported git call")

                with patch.object(
                    service.project_manager,
                    "_run_git",
                    side_effect=fake_run_git,
                ):
                    with TestClient(app) as client:
                        plan_payload = client.post(
                            f"/api/workspace/{session_id}/tasks/plan",
                            json={
                                "goal": "Fix app behavior and validate the repo state.",
                                "cwd": ".",
                                "test_commands": ["pytest -q"],
                            },
                        ).json()

                        self.assertTrue(plan_payload["ok"])
                        self.assertTrue(plan_payload["git"]["is_repo"])
                        self.assertEqual(
                            plan_payload["plan"]["branch_suggestion"],
                            "codex/fix-app-behavior-and-validate-the",
                        )
                        self.assertGreaterEqual(len(plan_payload["plan"]["steps"]), 5)

                        task = service.task_manager.start_task(
                            session_id=session_id,
                            goal="Fix app behavior and validate the repo state.",
                            cwd=".",
                            test_commands=["pytest -q"],
                            title="Fix app behavior",
                            source="test",
                            plan=plan_payload["plan"],
                        )
                        service.task_manager.update_task(
                            session_id=session_id,
                            task_id=task["id"],
                            phase="approve",
                            status="ready_for_approval",
                            summary="Task ready for approval.",
                            final_message="Updated src/app.py and checked the repo status.",
                            changed_files=["src/app.py"],
                        )

                        handoff_payload = client.post(
                            f"/api/workspace/{session_id}/git/handoff",
                            json={"task_id": task["id"], "cwd": "."},
                        ).json()
                        self.assertTrue(handoff_payload["ok"])
                        self.assertEqual(
                            handoff_payload["handoff"]["commit_message"]["subject"],
                            "fix: fix app behavior and validate the",
                        )
                        self.assertIn(
                            "pytest -q",
                            handoff_payload["handoff"]["pull_request"]["body"],
                        )

                        branch_payload = client.post(
                            f"/api/workspace/{session_id}/git/branch",
                            json={"name": "codex/fix-app-behavior-and-validate-the"},
                        ).json()
                        self.assertTrue(branch_payload["ok"])
                        self.assertEqual(branch_payload["branch"], "codex/fix-app-behavior-and-validate-the")
                        self.assertEqual(
                            branch_payload["git"]["branch"],
                            "codex/fix-app-behavior-and-validate-the",
                        )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_repo_map_endpoint_and_smart_task_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "repo-map"
                workspace = root / "workspaces" / session_id
                (workspace / "app").mkdir(parents=True, exist_ok=True)
                (workspace / "tests").mkdir(parents=True, exist_ok=True)
                (workspace / "app" / "__init__.py").write_text("", encoding="utf-8")
                (workspace / "app" / "helpers.py").write_text(
                    (
                        "def format_name(name: str) -> str:\n"
                        "    return name.strip().title()\n"
                    ),
                    encoding="utf-8",
                )
                (workspace / "app" / "main.py").write_text(
                    (
                        "from app.helpers import format_name\n\n"
                        "def run() -> str:\n"
                        "    return format_name('ada lovelace')\n"
                    ),
                    encoding="utf-8",
                )
                (workspace / "tests" / "test_helpers.py").write_text(
                    (
                        "from app.helpers import format_name\n\n"
                        "def test_format_name() -> None:\n"
                        "    assert format_name('ada') == 'Ada'\n"
                    ),
                    encoding="utf-8",
                )

                with TestClient(app) as client:
                    repo_map_payload = client.get(
                        f"/api/workspace/{session_id}/repo-map",
                        params={
                            "goal": "Fix the format_name helper bug and validate it.",
                            "cwd": ".",
                            "symbol": "format_name",
                        },
                    ).json()
                    plan_payload = client.post(
                        f"/api/workspace/{session_id}/tasks/plan",
                        json={
                            "goal": "Fix the format_name helper bug and validate it.",
                            "cwd": ".",
                        },
                    ).json()

                self.assertTrue(repo_map_payload["ok"])
                self.assertIn(
                    "app/helpers.py",
                    repo_map_payload["repo_map"]["focus_paths"],
                )
                self.assertIn(
                    "app/main.py",
                    repo_map_payload["repo_map"]["related_paths"],
                )
                self.assertIn(
                    "tests/test_helpers.py",
                    repo_map_payload["repo_map"]["likely_test_files"],
                )
                self.assertEqual(
                    repo_map_payload["repo_map"]["suggested_validation_commands"],
                    ["pytest -q tests/test_helpers.py"],
                )

                self.assertTrue(plan_payload["ok"])
                self.assertEqual(
                    plan_payload["plan"]["focus_paths"][0],
                    "app/helpers.py",
                )
                self.assertIn(
                    "tests/test_helpers.py",
                    plan_payload["plan"]["likely_test_files"],
                )
                self.assertEqual(
                    plan_payload["plan"]["suggested_test_commands"],
                    ["pytest -q tests/test_helpers.py"],
                )
                locate_step = next(
                    step
                    for step in plan_payload["plan"]["steps"]
                    if step["id"] == "locate-scope"
                )
                self.assertIn("inspect_repo_map", locate_step["tools"])
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_search_finds_files_text_and_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "searcher"
                workspace = root / "workspaces" / session_id
                (workspace / "src").mkdir(parents=True, exist_ok=True)
                (workspace / "web").mkdir(parents=True, exist_ok=True)
                (workspace / "src" / "main.py").write_text(
                    (
                        "class SearchDemo:\n"
                        "    pass\n\n"
                        "def locate_issue() -> str:\n"
                        "    return 'alpha needle'\n"
                    ),
                    encoding="utf-8",
                )
                (workspace / "web" / "app.ts").write_text(
                    "export function renderWidget() { return 'ok'; }\n",
                    encoding="utf-8",
                )
                (workspace / "README.md").write_text(
                    "Workspace search smoke test\n",
                    encoding="utf-8",
                )

                with TestClient(app) as client:
                    files_payload = client.get(
                        f"/api/workspace/{session_id}/search",
                        params={"query": "main.py", "mode": "files"},
                    ).json()
                    text_payload = client.get(
                        f"/api/workspace/{session_id}/search",
                        params={
                            "query": "alpha needle",
                            "mode": "text",
                            "path_prefix": "src",
                        },
                    ).json()
                    symbol_payload = client.get(
                        f"/api/workspace/{session_id}/search",
                        params={"query": "renderWidget", "mode": "symbols"},
                    ).json()

                self.assertTrue(files_payload["ok"])
                self.assertEqual(files_payload["mode"], "files")
                self.assertEqual(files_payload["results"][0]["path"], "src/main.py")

                self.assertTrue(text_payload["ok"])
                self.assertEqual(text_payload["mode"], "text")
                self.assertEqual(text_payload["results"][0]["path"], "src/main.py")
                self.assertEqual(text_payload["results"][0]["line"], 5)

                self.assertTrue(symbol_payload["ok"])
                self.assertEqual(symbol_payload["mode"], "symbols")
                self.assertEqual(symbol_payload["results"][0]["symbol"], "renderWidget")
                self.assertEqual(symbol_payload["results"][0]["path"], "web/app.ts")
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_symbol_tools_list_read_edit_and_find_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "symbols"
                workspace = root / "workspaces" / session_id / "src"
                workspace.mkdir(parents=True, exist_ok=True)
                target_file = workspace / "demo.py"
                target_file.write_text(
                    (
                        "class Greeter:\n"
                        "    def greet(self) -> str:\n"
                        "        return helper_name('Ada')\n\n"
                        "def helper_name(name: str) -> str:\n"
                        "    return f'Hello {name}'\n\n"
                        "def use_helper() -> str:\n"
                        "    return helper_name('Grace')\n"
                    ),
                    encoding="utf-8",
                )

                with TestClient(app) as client:
                    symbols_payload = client.get(
                        f"/api/workspace/{session_id}/symbols",
                        params={"query": "helper_name"},
                    ).json()
                    symbol_payload = client.get(
                        f"/api/workspace/{session_id}/symbol",
                        params={"symbol": "helper_name", "path": "src/demo.py"},
                    ).json()
                    references_payload = client.get(
                        f"/api/workspace/{session_id}/symbol/references",
                        params={"symbol": "helper_name"},
                    ).json()
                    edit_payload = client.put(
                        f"/api/workspace/{session_id}/symbol",
                        json={
                            "symbol": "helper_name",
                            "path": "src/demo.py",
                            "content": (
                                "def helper_name(name: str) -> str:\n"
                                "    return f'Hi {name}'"
                            ),
                        },
                    ).json()

                self.assertTrue(symbols_payload["ok"])
                self.assertGreaterEqual(symbols_payload["symbol_count"], 1)
                self.assertEqual(symbols_payload["symbols"][0]["name"], "helper_name")

                self.assertTrue(symbol_payload["ok"])
                self.assertEqual(symbol_payload["symbol"]["qualname"], "helper_name")
                self.assertIn("return f'Hello", symbol_payload["symbol"]["content"])

                self.assertTrue(references_payload["ok"])
                self.assertGreaterEqual(references_payload["result_count"], 2)

                self.assertTrue(edit_payload["ok"])
                self.assertEqual(edit_payload["symbol"]["qualname"], "helper_name")
                self.assertIn("Hi", target_file.read_text(encoding="utf-8"))
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_project_profile_detects_python_and_node_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "profiled"
                workspace = root / "workspaces" / session_id
                (workspace / "src").mkdir(parents=True, exist_ok=True)
                (workspace / "pyproject.toml").write_text(
                    (
                        "[project]\n"
                        "name = 'demo'\n"
                        "dependencies = ['fastapi', 'pytest', 'ruff']\n"
                    ),
                    encoding="utf-8",
                )
                (workspace / "uv.lock").write_text("# lock\n", encoding="utf-8")
                (workspace / "package.json").write_text(
                    json.dumps(
                        {
                            "name": "demo-web",
                            "scripts": {
                                "test": "vitest run",
                                "lint": "eslint .",
                                "dev": "vite",
                            },
                            "dependencies": {"react": "^18.0.0"},
                            "devDependencies": {
                                "eslint": "^9.0.0",
                                "vitest": "^2.0.0",
                            },
                            "main": "src/index.ts",
                        }
                    ),
                    encoding="utf-8",
                )
                (workspace / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
                (workspace / "src" / "main.py").write_text("print('demo')\n", encoding="utf-8")
                (workspace / "src" / "index.ts").write_text("export const app = 1;\n", encoding="utf-8")

                with TestClient(app) as client:
                    project_payload = client.get(
                        f"/api/workspace/{session_id}/project"
                    ).json()
                    workspace_payload = client.get(
                        f"/api/workspace/{session_id}"
                    ).json()

                project = project_payload["project"]
                self.assertTrue(project_payload["ok"])
                self.assertIn("python", project["languages"])
                self.assertIn("typescript", project["languages"])
                self.assertIn("uv", project["package_managers"])
                self.assertIn("pnpm", project["package_managers"])
                self.assertIn("pytest -q", project["test_commands"])
                self.assertIn("pnpm test", project["test_commands"])
                self.assertIn("ruff check .", project["lint_commands"])
                self.assertIn("pnpm run lint", project["lint_commands"])
                self.assertIn("src/main.py", project["entrypoints"])
                self.assertIn("src/index.ts", project["entrypoints"])
                self.assertEqual(
                    workspace_payload["project"]["package_managers"],
                    project["package_managers"],
                )
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()

    def test_workspace_snapshot_restore_recovers_repo_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_cwd = Path.cwd()
            original_env = dict(os.environ)
            try:
                os.chdir(root)
                os.environ["FORGE_PROVIDER_MODE"] = "mock"
                os.environ["FORGE_EXECUTION_BACKEND"] = "local"
                os.environ["FORGE_KNOWLEDGE_DIR"] = str(root / "knowledge")
                os.environ["FORGE_SESSIONS_PATH"] = str(root / "sessions.json")
                os.environ["FORGE_MEMORY_PATH"] = str(root / "memory.json")
                os.environ["FORGE_WORKSPACES_DIR"] = str(root / "workspaces")
                _build_service.cache_clear()
                app = create_app()
                session_id = "snapper"
                workspace = root / "workspaces" / session_id
                (workspace / "repo").mkdir(parents=True, exist_ok=True)
                (workspace / ".git").mkdir(parents=True, exist_ok=True)
                (workspace / "repo" / "app.py").write_text(
                    "print('before snapshot')\n",
                    encoding="utf-8",
                )
                (workspace / ".git" / "HEAD").write_text(
                    "ref: refs/heads/main\n",
                    encoding="utf-8",
                )
                (workspace / ".forge_exec_tasks.json").write_text(
                    json.dumps([{"id": "task-1", "status": "ready"}], indent=2),
                    encoding="utf-8",
                )

                with TestClient(app) as client:
                    create_payload = client.post(
                        f"/api/workspace/{session_id}/snapshots",
                        json={"label": "before edits"},
                    ).json()
                    self.assertTrue(create_payload["ok"])
                    snapshot_id = create_payload["snapshot"]["id"]

                    (workspace / "repo" / "app.py").write_text(
                        "print('after snapshot')\n",
                        encoding="utf-8",
                    )
                    (workspace / ".git" / "HEAD").write_text(
                        "ref: refs/heads/feature\n",
                        encoding="utf-8",
                    )
                    (workspace / ".forge_exec_tasks.json").write_text(
                        json.dumps([{"id": "task-2", "status": "changed"}], indent=2),
                        encoding="utf-8",
                    )

                    restore_payload = client.post(
                        f"/api/workspace/{session_id}/snapshots/{snapshot_id}/restore"
                    ).json()
                    workspace_payload = client.get(f"/api/workspace/{session_id}").json()

                self.assertTrue(restore_payload["ok"])
                self.assertEqual(
                    (workspace / "repo" / "app.py").read_text(encoding="utf-8"),
                    "print('before snapshot')\n",
                )
                self.assertEqual(
                    (workspace / ".git" / "HEAD").read_text(encoding="utf-8"),
                    "ref: refs/heads/main\n",
                )
                self.assertIn('"task-1"', (workspace / ".forge_exec_tasks.json").read_text(encoding="utf-8"))
                self.assertIn("repo/app.py", workspace_payload["files"])
                self.assertEqual(len(workspace_payload["snapshots"]), 1)
                self.assertEqual(workspace_payload["snapshots"][0]["label"], "before edits")
            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
                _cleanup_temp_root(root)
                _build_service.cache_clear()


if __name__ == "__main__":
    unittest.main()
