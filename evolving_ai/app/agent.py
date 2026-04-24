from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentAction:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentDecision:
    thought: str
    action: AgentAction | None = None
    final: str | None = None


@dataclass(frozen=True, slots=True)
class AgentToolPermissions:
    allow_python: bool
    allow_shell: bool
    allow_filesystem_read: bool
    allow_filesystem_write: bool

    def payload(self) -> dict[str, bool]:
        return {
            "python": self.allow_python,
            "shell": self.allow_shell,
            "filesystem_read": self.allow_filesystem_read,
            "filesystem_write": self.allow_filesystem_write,
        }

    def allows(self, tool: str) -> bool:
        if tool == "run_python":
            return self.allow_python
        if tool == "run_command":
            return self.allow_shell
        if tool in {
            "list_workspace",
            "search_workspace",
            "find_symbol",
            "list_symbols",
            "read_symbol",
            "find_references",
            "inspect_repo_map",
            "inspect_project",
            "inspect_git",
            "prepare_handoff",
            "list_snapshots",
            "list_pending_patches",
            "read_file",
            "preview_patch",
            "review_workspace",
        }:
            return self.allow_filesystem_read
        if tool in {
            "write_file",
            "replace_in_file",
            "apply_patch",
            "edit_symbol",
            "snapshot_workspace",
            "create_branch",
            "propose_file_write",
            "propose_replace_in_file",
            "save_knowledge",
        }:
            return self.allow_filesystem_write
        return True

    def denial_reason(self, tool: str) -> str | None:
        if self.allows(tool):
            return None
        if tool == "run_python":
            return "Python execution is disabled for the agent."
        if tool == "run_command":
            return "Shell command execution is disabled for the agent."
        if tool in {
            "list_workspace",
            "search_workspace",
            "find_symbol",
            "list_symbols",
            "read_symbol",
            "find_references",
            "inspect_repo_map",
            "inspect_project",
            "inspect_git",
            "prepare_handoff",
            "list_snapshots",
            "list_pending_patches",
            "read_file",
            "preview_patch",
            "review_workspace",
        }:
            return "Filesystem read access is disabled for the agent."
        if tool in {
            "write_file",
            "replace_in_file",
            "apply_patch",
            "edit_symbol",
            "snapshot_workspace",
            "create_branch",
            "propose_file_write",
            "propose_replace_in_file",
            "save_knowledge",
        }:
            return "Filesystem write access is disabled for the agent."
        return f"Tool `{tool}` is disabled for the agent."


def build_agent_system_prompt(
    *,
    allow_remote_fetch: bool,
    agent_max_command_tier: str,
    allowed_commands: tuple[str, ...],
    permissions: AgentToolPermissions,
) -> str:
    command_hint = ", ".join(allowed_commands) if allowed_commands else "none"
    tool_lines: list[str] = ['- search_knowledge: {"query": string, "limit": integer optional}']
    disabled: list[str] = []
    if allow_remote_fetch:
        tool_lines.extend(
            [
                '- search_web: {"query": string, "limit": integer optional}',
                '- fetch_url: {"url": string}',
            ]
        )
    else:
        disabled.append("remote web fetch")
    if permissions.allow_filesystem_read:
        tool_lines.extend(
            [
                '- read_file: {"path": string, "start_line": integer optional, "end_line": integer optional}',
                '- search_workspace: {"query": string, "mode": "files" | "text" optional, "limit": integer optional, "path_prefix": string optional}',
                '- find_symbol: {"query": string, "limit": integer optional, "path_prefix": string optional}',
                '- list_symbols: {"query": string optional, "limit": integer optional, "path_prefix": string optional}',
                '- read_symbol: {"symbol": string, "path": string optional}',
                '- find_references: {"symbol": string, "limit": integer optional, "path_prefix": string optional}',
                '- inspect_repo_map: {"goal": string optional, "cwd": string optional, "path": string optional, "symbol": string optional, "limit": integer optional}',
                "- inspect_project: {}",
                '- inspect_git: {"cwd": string optional}',
                '- prepare_handoff: {"goal": string optional, "task_id": string optional, "cwd": string optional}',
                '- preview_patch: {"path": string, "patch": string}',
                "- list_workspace: {}",
                "- list_snapshots: {}",
                "- list_pending_patches: {}",
                "- review_workspace: {}",
            ]
        )
    else:
        disabled.append("filesystem reads")
    if permissions.allow_filesystem_write:
        tool_lines.extend(
            [
                '- write_file: {"path": string, "content": string}',
                '- replace_in_file: {"path": string, "old_text": string, "new_text": string, "replace_all": boolean optional, "expected_occurrences": integer optional}',
                '- apply_patch: {"path": string, "patch": string, "expected_hash": string optional}',
                '- edit_symbol: {"symbol": string, "path": string optional, "content": string}',
                '- snapshot_workspace: {"label": string optional}',
                '- create_branch: {"name": string, "cwd": string optional}',
                '- propose_file_write: {"path": string, "content": string}',
                '- propose_replace_in_file: {"path": string, "old_text": string, "new_text": string, "replace_all": boolean optional, "expected_occurrences": integer optional}',
                '- save_knowledge: {"name": string, "content": string}',
            ]
        )
    else:
        disabled.append("filesystem writes")
    if permissions.allow_python:
        tool_lines.append('- run_python: {"code": string}')
    else:
        disabled.append("python execution")
    if permissions.allow_shell:
        tool_lines.append('- run_command: {"command": string[] or string, "cwd": string optional}')
    else:
        disabled.append("shell commands")
    tool_lines.append('- remember: {"text": string}')

    prompt = [
        "You are ForgeChat Agent. Work step by step.",
        "When you need a tool, respond ONLY with JSON matching this schema:",
        '{"thought":"short reason","action":{"tool":"tool_name","args":{"key":"value"}}}',
        "When you are ready to answer the user, respond ONLY with JSON matching this schema:",
        '{"thought":"short reason","final":"final answer for the user"}',
        "Available tools:",
        *tool_lines,
        "Rules:",
        "- Use only one tool per turn.",
        "- Prefer the shortest effective tool path.",
        "- Start repo tasks with `inspect_project` when you need to understand the stack, test runner, or entrypoints.",
        "- Use `inspect_git` when repo state, branch context, or changed files matter to the task.",
        "- Use `inspect_repo_map` before broader edits when you need likely owner files, related modules, or likely tests.",
        "- Use `search_workspace` or `find_symbol` before broad file reads when you need to locate code in a larger repo.",
        "- Use `list_symbols`, `read_symbol`, and `find_references` when you can work at the function or class level instead of raw file text.",
        "- Use `read_file` before editing unless you already know the exact target text.",
        "- Prefer `edit_symbol` for focused function or class replacements when the target symbol is clear.",
        "- Use `replace_in_file` for simple targeted edits and `write_file` only when replacing the full file intentionally.",
        "- Use `preview_patch` before `apply_patch` for non-trivial or multi-hunk diffs.",
        "- When `preview_patch` returns a current hash, pass it back as `expected_hash` in `apply_patch` for validation.",
        "- Use `propose_file_write` or `propose_replace_in_file` when you want the user to review a change before applying it.",
        "- Use `snapshot_workspace` before risky multi-file changes when you may need a clean rollback point.",
        "- Use `prepare_handoff` near the end of repo tasks so your final answer can include branch, commit, validation, and PR-ready notes.",
        "- Use `create_branch` only after you understand the repo state and have a clear task-scoped branch name.",
        "- Workspace file paths must stay inside the session workspace.",
    ]
    if permissions.allow_shell:
        prompt.extend(
            [
                f"- `run_command` is limited to the `{agent_max_command_tier}` policy tier.",
                f"- Agent-accessible executables right now are: {command_hint}.",
                "- Treat `run_command` as a workspace inspection tool first.",
                "- Use `run_python` for small snippets; use `run_command` for repo checks like `git status`, `git diff`, `ls`, or `cat`.",
                "- If a tool result says approval is required, stop escalating and ask the user before retrying a higher-tier command.",
            ]
        )
    if permissions.allow_filesystem_read:
        prompt.extend(
            [
                "- Use `review_workspace` after proposing changes so you can summarize changed files and diffs clearly.",
                "- For repo tasks, prefer this loop: inspect -> read file -> propose patch -> review -> request approval for tests or installs when needed -> summarize.",
                "- After an approved patch resumes with automatic verification results, use failing checks to plan the next patch automatically instead of stopping early.",
                "- Only stop after patch approval if verification passed or you truly need fresh user input.",
            ]
        )
    if disabled:
        prompt.append(f"- Disabled capabilities: {', '.join(disabled)}.")
    prompt.extend(
        [
            "- After receiving a tool result, either use another tool or finish.",
            "- Never wrap the JSON in markdown fences.",
        ]
    )
    return "\n".join(prompt)


def parse_agent_decision(text: str) -> AgentDecision | None:
    candidate = _extract_json_object(text)
    if candidate is None:
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    thought = str(payload.get("thought", "")).strip()
    final = payload.get("final")
    action_payload = payload.get("action")
    action: AgentAction | None = None
    if isinstance(action_payload, dict):
        tool = str(action_payload.get("tool", "")).strip()
        args = action_payload.get("args", {})
        if tool and isinstance(args, dict):
            action = AgentAction(tool=tool, args=args)
    if isinstance(final, str) and final.strip():
        return AgentDecision(thought=thought, final=final.strip())
    if action is not None:
        return AgentDecision(thought=thought, action=action)
    return None


def _extract_json_object(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
