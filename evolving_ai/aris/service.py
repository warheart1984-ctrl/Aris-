from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from evolving_ai.app.memory import MemoryStore
from evolving_ai.app.execution import ExecutionResult
from evolving_ai.app.execution_backends import CommandExecutionResult
from evolving_ai.app.service import ChatService

from .cognitive_upgrade import ArisCognitiveUpgradeProvider
from .runtime import ArisRuntime, GovernanceDecision


def _merge_stderr(existing: str, message: str) -> str:
    current = str(existing or "").strip()
    extra = str(message or "").strip()
    if current and extra:
        return f"{current}\n{extra}"
    return current or extra


class GovernedExecutor:
    def __init__(self, inner: Any, runtime: ArisRuntime) -> None:
        self.inner = inner
        self.runtime = runtime

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _blocked_execution_result(
        self,
        *,
        session_id: str,
        decision: GovernanceDecision,
    ) -> ExecutionResult:
        files = self.inner.local_executor.workspace_manager.list_files(session_id)
        sandbox = {
            "backend": "aris",
            "blocked": True,
            "violations": [decision.reason],
            "aris": decision.payload(),
        }
        return ExecutionResult(
            session_id=session_id,
            returncode=126,
            stdout="",
            stderr=decision.reason,
            files=files,
            timed_out=False,
            sandbox=sandbox,
        )

    def _blocked_command_result(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        decision: GovernanceDecision,
    ) -> CommandExecutionResult:
        files = self.inner.local_executor.workspace_manager.list_files(session_id)
        sandbox = {
            "backend": "aris",
            "requested_backend": "aris",
            "blocked": True,
            "violations": [decision.reason],
            "aris": decision.payload(),
        }
        return CommandExecutionResult(
            session_id=session_id,
            command=list(command),
            cwd=str(cwd or ".").strip() or ".",
            returncode=126,
            stdout="",
            stderr=decision.reason,
            timed_out=False,
            files=files,
            sandbox=sandbox,
        )

    def execute(self, *, session_id: str, code: str) -> ExecutionResult:
        action = {
            "action_type": "python_execute",
            "session_id": session_id,
            "purpose": "Execute Python code in a governed ARIS workspace sandbox.",
            "target": session_id,
            "source": "api",
            "operator_decision": "approved",
            "code": code,
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        decision = self.runtime.review_action(action)
        if not decision.allowed:
            return self._blocked_execution_result(session_id=session_id, decision=decision)
        result = self.inner.execute(session_id=session_id, code=code)
        payload = {
            "session_id": result.session_id,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "files": result.files,
            "sandbox": dict(result.sandbox),
        }
        finalized = self.runtime.finalize_action(decision, result=payload)
        sandbox = dict(result.sandbox)
        sandbox["aris"] = finalized.payload()
        if finalized.verified:
            return ExecutionResult(
                session_id=result.session_id,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                files=result.files,
                timed_out=result.timed_out,
                sandbox=sandbox,
            )
        return ExecutionResult(
            session_id=result.session_id,
            returncode=126 if result.returncode == 0 else result.returncode,
            stdout=result.stdout,
            stderr=_merge_stderr(result.stderr, finalized.reason),
            files=result.files,
            timed_out=result.timed_out,
            sandbox=sandbox,
        )

    def execute_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float,
        allowed_commands: tuple[str, ...],
        max_command_tier: str | None = None,
        request_source: str = "api",
    ) -> CommandExecutionResult:
        action = {
            "action_type": "command_execute",
            "session_id": session_id,
            "purpose": f"Execute governed shell command: {' '.join(command)}",
            "target": str(cwd or ".").strip() or ".",
            "source": request_source,
            "operator_decision": "approved",
            "command": list(command),
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        decision = self.runtime.review_action(action)
        if not decision.allowed:
            return self._blocked_command_result(
                session_id=session_id,
                command=command,
                cwd=cwd,
                decision=decision,
            )
        result = self.inner.execute_command(
            session_id=session_id,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            allowed_commands=allowed_commands,
            max_command_tier=max_command_tier,
            request_source=request_source,
        )
        payload = {
            "session_id": result.session_id,
            "command": result.command,
            "cwd": result.cwd,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "files": result.files,
            "sandbox": dict(result.sandbox),
        }
        finalized = self.runtime.finalize_action(decision, result=payload)
        sandbox = dict(result.sandbox)
        sandbox["aris"] = finalized.payload()
        if finalized.verified:
            return CommandExecutionResult(
                session_id=result.session_id,
                command=result.command,
                cwd=result.cwd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=result.timed_out,
                files=result.files,
                sandbox=sandbox,
            )
        return CommandExecutionResult(
            session_id=result.session_id,
            command=result.command,
            cwd=result.cwd,
            returncode=126 if result.returncode == 0 else result.returncode,
            stdout=result.stdout,
            stderr=_merge_stderr(result.stderr, finalized.reason),
            timed_out=result.timed_out,
            files=result.files,
            sandbox=sandbox,
        )

    def stream_command(
        self,
        *,
        session_id: str,
        command: list[str],
        cwd: str | None,
        timeout_seconds: float,
        allowed_commands: tuple[str, ...],
        max_command_tier: str | None = None,
        request_source: str = "api",
    ):
        action = {
            "action_type": "command_execute",
            "session_id": session_id,
            "purpose": f"Execute governed shell command: {' '.join(command)}",
            "target": str(cwd or ".").strip() or ".",
            "source": request_source,
            "operator_decision": "approved",
            "command": list(command),
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        decision = self.runtime.review_action(action)
        start_payload = {
            "session_id": session_id,
            "command": list(command),
            "cwd": str(cwd or ".").strip() or ".",
            "requested_backend": "aris",
            "governance": decision.payload(),
        }
        yield {"event": "exec_start", "payload": start_payload}
        if not decision.allowed:
            blocked = self._blocked_command_result(
                session_id=session_id,
                command=command,
                cwd=cwd,
                decision=decision,
            )
            yield {
                "event": "exec_chunk",
                "payload": {"stream": "stderr", "content": f"{blocked.stderr}\n"},
            }
            yield {
                "event": "exec_done",
                "payload": {
                    "session_id": blocked.session_id,
                    "command": blocked.command,
                    "cwd": blocked.cwd,
                    "returncode": blocked.returncode,
                    "stdout": blocked.stdout,
                    "stderr": blocked.stderr,
                    "timed_out": blocked.timed_out,
                    "files": blocked.files,
                    "sandbox": blocked.sandbox,
                    "governance": decision.payload(),
                },
            }
            return

        for event in self.inner.stream_command(
            session_id=session_id,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            allowed_commands=allowed_commands,
            max_command_tier=max_command_tier,
            request_source=request_source,
        ):
            if event.get("event") != "exec_done":
                yield event
                continue
            payload = dict(event["payload"])
            finalized = self.runtime.finalize_action(decision, result=payload)
            sandbox = dict(payload.get("sandbox", {}))
            sandbox["aris"] = finalized.payload()
            payload["sandbox"] = sandbox
            payload["governance"] = finalized.payload()
            if not finalized.verified:
                payload["returncode"] = 126 if int(payload.get("returncode", 0)) == 0 else payload.get("returncode", 126)
                payload["stderr"] = _merge_stderr(str(payload.get("stderr", "")), finalized.reason)
            yield {"event": "exec_done", "payload": payload}


class ArisChatService(ChatService):
    def __init__(self, config) -> None:
        super().__init__(config)
        repo_root = Path(__file__).resolve().parents[2]
        runtime_root = self.config.workspaces_dir.parent / "aris"
        self.aris = ArisRuntime(repo_root=repo_root, runtime_root=runtime_root)
        self.memory = MemoryStore(self.aris.runtime_root / "memory.json")
        self.provider = ArisCognitiveUpgradeProvider(self.provider, self.aris.cognitive_upgrade)
        self.executor = GovernedExecutor(self.executor, self.aris)

    def config_payload(self) -> dict[str, object]:
        payload = super().config_payload()
        payload["aris"] = self.aris_status_payload()
        return payload

    def workspace_payload(self, session_id: str) -> dict[str, object]:
        payload = super().workspace_payload(session_id)
        payload["aris"] = self.aris_status_payload()
        return payload

    def aris_status_payload(self) -> dict[str, object]:
        payload = self.aris.status_payload()
        execution_backend = self.executor.status_payload()
        shell_enabled = bool(self.config.agent_allow_shell)
        docker_available = bool(execution_backend.get("docker_available", False))
        active_backend = str(execution_backend.get("active_backend", "unknown")).strip() or "unknown"
        requested_backend = (
            str(execution_backend.get("requested_backend", "unknown")).strip() or "unknown"
        )
        detail = str(execution_backend.get("docker_detail", "")).strip()
        payload["execution_backend"] = execution_backend
        payload["model_router"] = self.model_switchboard.status_payload()
        payload["shell_execution"] = {
            "enabled": shell_enabled,
            "requested_backend": requested_backend,
            "active_backend": active_backend,
            "docker_available": docker_available,
            "degraded": shell_enabled and requested_backend != "local" and not docker_available,
            "detail": detail,
        }
        return payload

    def aris_health_payload(self) -> dict[str, object]:
        health = self.aris.health_payload()
        status = self.aris_status_payload()
        health["model_router"] = status.get("model_router", {})
        health["execution_backend"] = status.get("execution_backend", {})
        health["shell_execution"] = status.get("shell_execution", {})
        health["degraded"] = bool(status.get("shell_execution", {}).get("degraded", False))
        return health

    def aris_activity_payload(self, *, limit: int = 25) -> dict[str, object]:
        return {"ok": True, "activity": self.aris.list_activity(limit=limit)}

    def aris_discards_payload(self, *, limit: int = 25) -> dict[str, object]:
        return {"ok": True, "entries": self.aris.list_discards(limit=limit)}

    def aris_shame_payload(self, *, limit: int = 25) -> dict[str, object]:
        return {"ok": True, "entries": self.aris.list_shames(limit=limit)}

    def aris_fame_payload(self, *, limit: int = 25) -> dict[str, object]:
        return {"ok": True, "entries": self.aris.list_fame(limit=limit)}

    def aris_kill_soft(self, *, reason: str) -> dict[str, object]:
        return {"ok": True, "kill_switch": self.aris.activate_soft_kill(reason=reason, actor="manual")}

    def aris_kill_hard(self, *, reason: str) -> dict[str, object]:
        return {"ok": True, "kill_switch": self.aris.activate_hard_kill(reason=reason, actor="manual")}

    def aris_kill_reset(self, *, reason: str, reseal_integrity: bool = False) -> dict[str, object]:
        return {
            "ok": True,
            "kill_switch": self.aris.reset_kill_switch(
                reason=reason,
                actor="admin",
                reseal_integrity=reseal_integrity,
            ),
        }

    def aris_forge_plan(self, *, goal: str, focus_paths: list[str] | None = None) -> dict[str, object]:
        return self.aris.forge_repo_plan(goal=goal, focus_paths=focus_paths or [])

    def aris_mystic_status(self, *, session_id: str | None) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        return self.aris.mystic_status_payload(session_id=normalized_session)

    def aris_mystic_tick(self, *, session_id: str | None) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        return self.aris.mystic_tick(session_id=normalized_session)

    def aris_mystic_break(self, *, session_id: str | None) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        return self.aris.mystic_record_break(session_id=normalized_session)

    def aris_mystic_acknowledge(self, *, session_id: str | None) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        return self.aris.mystic_acknowledge(session_id=normalized_session)

    def aris_mystic_mute(self, *, session_id: str | None, minutes: float) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        return self.aris.mystic_mute(session_id=normalized_session, minutes=minutes)

    def aris_mystic_read(
        self,
        *,
        session_id: str | None,
        input_text: str,
        source: str = "api",
    ) -> dict[str, object]:
        normalized_session = str(session_id or "scratchpad").strip() or "scratchpad"
        cleaned = " ".join(str(input_text or "").split()).strip()
        if not cleaned:
            return {
                "ok": False,
                "session_id": normalized_session,
                "error": "Mystic Reflection input is required.",
            }
        if self.aris.mystic_reflection is None:
            return {
                "ok": False,
                "session_id": normalized_session,
                "input": cleaned,
                "error": "Mystic Reflection is unavailable.",
                "mystic": self.aris.status_payload(include_recent=False).get("mystic", {}),
                "mystic_reflection": self.aris.status_payload(include_recent=False).get(
                    "mystic_reflection", {}
                ),
            }

        decision = self._review_governed_action(
            action_type="mystic_reflection",
            session_id=normalized_session,
            purpose="Run Mystic Reflection through Jarvis inheritance and ARIS governance.",
            target=normalized_session,
            source=source,
            operator_decision="recorded",
            code=cleaned,
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=normalized_session,
                target=normalized_session,
                decision=decision,
                extra={
                    "input": cleaned,
                    "tool": "mystic_reflection",
                },
            )

        tool_result = self.aris.mystic_reflection.read(
            cleaned,
            session_id=normalized_session,
            source=source,
        )
        finalized = self.aris.finalize_action(
            decision,
            result={
                "ok": True,
                "tool": tool_result["tool"],
                "status": tool_result["status"],
                "reading": tool_result["result"],
                "summary": tool_result["summary"],
            },
        )
        payload: dict[str, object] = {
            "ok": finalized.verified,
            "session_id": normalized_session,
            "input": cleaned,
            "tool_result": tool_result,
            "route": tool_result.get("route", []),
            "governance": finalized.payload(),
        }
        if finalized.hall_entry is not None and finalized.hall_name:
            payload["hall"] = {
                "name": finalized.hall_name,
                "entry": finalized.hall_entry,
            }
        if finalized.discard_entry is not None:
            payload["discard"] = finalized.discard_entry
        if not finalized.verified:
            payload["error"] = finalized.reason
        return payload

    def _governed_block_response(
        self,
        *,
        session_id: str,
        target: str,
        decision: GovernanceDecision,
        extra: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": False,
            "session_id": session_id,
            "path": target,
            "error": decision.reason,
            "files": self.workspace_manager.list_files(session_id),
            "governance": decision.payload(),
        }
        if decision.hall_entry is not None and decision.hall_name:
            payload["hall"] = {
                "name": decision.hall_name,
                "entry": decision.hall_entry,
            }
        if decision.discard_entry is not None:
            payload["discard"] = decision.discard_entry
        if decision.hall_name == "hall_of_shame" and decision.hall_entry is not None:
            payload["shame"] = decision.hall_entry
        if decision.hall_name == "hall_of_fame" and decision.hall_entry is not None:
            payload["fame"] = decision.hall_entry
        if extra:
            payload.update(extra)
        return payload

    def _safe_workspace_text_state(
        self,
        *,
        session_id: str,
        path: str,
    ) -> tuple[bool, str, str]:
        try:
            return self._read_workspace_text_state(session_id=session_id, path=path)
        except (IsADirectoryError, ValueError):
            normalized = str(path or "").strip()
            return False, "", normalized

    def _complete_observation_cycle(self, session_id: str) -> None:
        self.aris.runtime_law.clear_observation(session_id)

    def _mark_observation_result(
        self,
        *,
        session_id: str,
        result: dict[str, object],
    ) -> dict[str, object]:
        if bool(result.get("ok", False)):
            self._complete_observation_cycle(session_id)
        return result

    def read_workspace_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None = None,
    ) -> dict[str, object]:
        result = super().read_workspace_symbol(
            session_id=session_id,
            symbol=symbol,
            path=path,
        )
        return self._mark_observation_result(session_id=session_id, result=result)

    def read_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, object]:
        result = super().read_workspace_file(
            session_id=session_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
        )
        return self._mark_observation_result(session_id=session_id, result=result)

    def preview_workspace_patch(
        self,
        *,
        session_id: str,
        path: str,
        patch: str,
    ) -> dict[str, object]:
        result = super().preview_workspace_patch(
            session_id=session_id,
            path=path,
            patch=patch,
        )
        return self._mark_observation_result(session_id=session_id, result=result)

    def list_applied_workspace_changes(self, session_id: str) -> dict[str, object]:
        result = super().list_applied_workspace_changes(session_id)
        return self._mark_observation_result(session_id=session_id, result=result)

    def workspace_verification_payload(
        self,
        session_id: str,
        *,
        project_profile: dict[str, object] | None = None,
    ) -> dict[str, object]:
        result = super().workspace_verification_payload(
            session_id,
            project_profile=project_profile,
        )
        return self._mark_observation_result(session_id=session_id, result=result)

    def verify_workspace_change(
        self,
        *,
        session_id: str,
        change_id: str,
        preset_id: str | None = None,
        cwd: str | None = None,
    ) -> dict[str, object]:
        result = super().verify_workspace_change(
            session_id=session_id,
            change_id=change_id,
            preset_id=preset_id,
            cwd=cwd,
        )
        return self._mark_observation_result(session_id=session_id, result=result)

    def review_workspace(
        self,
        *,
        session_id: str,
        cwd: str | None = None,
    ) -> dict[str, object]:
        result = super().review_workspace(session_id=session_id, cwd=cwd)
        return self._mark_observation_result(session_id=session_id, result=result)

    def _finalize_governed_mutation(
        self,
        *,
        session_id: str,
        result: dict[str, object],
        decision: GovernanceDecision,
    ) -> dict[str, object]:
        finalized = self.aris.finalize_action(decision, result=result)
        result["governance"] = finalized.payload()
        if finalized.hall_entry is not None and finalized.hall_name:
            result["hall"] = {
                "name": finalized.hall_name,
                "entry": finalized.hall_entry,
            }
        if finalized.discard_entry is not None:
            result["discard"] = finalized.discard_entry
        if finalized.hall_name == "hall_of_shame" and finalized.hall_entry is not None:
            result["shame"] = finalized.hall_entry
        if finalized.hall_name == "hall_of_fame" and finalized.hall_entry is not None:
            result["fame"] = finalized.hall_entry
        if finalized.verified:
            return result

        containment = self._contain_unverified_mutation(session_id=session_id, result=result)
        result["ok"] = False
        result["error"] = finalized.reason
        if containment is not None:
            result["containment"] = containment
            if containment.get("files") is not None:
                result["files"] = containment["files"]
            if containment.get("applied_changes") is not None:
                result["applied_changes"] = containment["applied_changes"]
        return result

    def _finalize_governed_result(
        self,
        *,
        result: dict[str, object],
        decision: GovernanceDecision,
    ) -> dict[str, object]:
        finalized = self.aris.finalize_action(decision, result=result)
        result["governance"] = finalized.payload()
        if finalized.hall_entry is not None and finalized.hall_name:
            result["hall"] = {
                "name": finalized.hall_name,
                "entry": finalized.hall_entry,
            }
        if finalized.discard_entry is not None:
            result["discard"] = finalized.discard_entry
        if finalized.hall_name == "hall_of_shame" and finalized.hall_entry is not None:
            result["shame"] = finalized.hall_entry
        if finalized.hall_name == "hall_of_fame" and finalized.hall_entry is not None:
            result["fame"] = finalized.hall_entry
        if finalized.verified:
            return result
        result["ok"] = False
        result["error"] = finalized.reason
        return result

    def _review_governed_action(
        self,
        *,
        action_type: str,
        session_id: str,
        purpose: str,
        target: str,
        source: str = "api",
        operator_decision: str = "approved",
        patch: str = "",
        code: str = "",
        command: list[str] | None = None,
        flags: dict[str, object] | None = None,
    ) -> GovernanceDecision:
        action = {
            "action_type": action_type,
            "session_id": session_id,
            "purpose": purpose,
            "target": str(target or "").strip(),
            "source": source,
            "operator_decision": operator_decision,
            "patch": patch,
            "code": code,
            "command": list(command or []),
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        if flags:
            action.update(flags)
        return self.aris.review_action(action)

    def _pending_patch_target(
        self,
        *,
        session_id: str,
        patch_id: str,
    ) -> tuple[dict[str, object], str]:
        patch = self._lookup_pending_patch(session_id, patch_id) or {}
        target = str(patch.get("path", "")).strip() or patch_id
        return patch, target

    def _contain_unverified_mutation(
        self,
        *,
        session_id: str,
        result: dict[str, object],
    ) -> dict[str, object] | None:
        change = result.get("change")
        if not isinstance(change, dict):
            return None
        change_id = str(change.get("id", "")).strip()
        if not change_id:
            return None
        return self.change_history.rollback_change(
            session_id=session_id,
            change_id=change_id,
            source="aris_containment",
        )

    def edit_workspace_symbol(
        self,
        *,
        session_id: str,
        symbol: str,
        path: str | None,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        symbol_state = super().read_workspace_symbol(
            session_id=session_id,
            symbol=symbol,
            path=path,
        )
        resolved_path = str(
            ((symbol_state.get("symbol") or {}) if isinstance(symbol_state.get("symbol"), dict) else {}).get("path", "")
        ).strip() or str(path or "").strip()
        action = {
            "action_type": "symbol_edit",
            "session_id": session_id,
            "purpose": f"Edit symbol {symbol} in the governed ARIS workspace.",
            "target": resolved_path,
            "source": source,
            "operator_decision": "approved",
            "code": content,
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        decision = self.aris.review_action(action)
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=resolved_path,
                decision=decision,
                extra={"symbol": symbol},
            )
        result = super().edit_workspace_symbol(
            session_id=session_id,
            symbol=symbol,
            path=path,
            content=content,
            source=source,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def write_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        before_exists, before_content, relative = self._safe_workspace_text_state(
            session_id=session_id,
            path=path,
        )
        action = self.aris.action_for_file_change(
            action_type="file_write",
            session_id=session_id,
            purpose=f"Write workspace file {relative}.",
            path=relative,
            before=before_content if before_exists else "",
            after=content,
            source=source,
        )
        decision = self.aris.review_action(action)
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=relative,
                decision=decision,
            )
        result = super().write_workspace_file(
            session_id=session_id,
            path=path,
            content=content,
            source=source,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def replace_workspace_file(
        self,
        *,
        session_id: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        expected_occurrences: int | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        before_exists, before_content, relative = self._safe_workspace_text_state(
            session_id=session_id,
            path=path,
        )
        replacement_count = before_content.count(old_text)
        replacements = replacement_count if replace_all else 1
        after_content = before_content.replace(old_text, new_text, replacements)
        action = self.aris.action_for_file_change(
            action_type="file_replace",
            session_id=session_id,
            purpose=f"Replace text in workspace file {relative}.",
            path=relative,
            before=before_content if before_exists else "",
            after=after_content,
            source=source,
        )
        decision = self.aris.review_action(action)
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=relative,
                decision=decision,
            )
        result = super().replace_workspace_file(
            session_id=session_id,
            path=path,
            old_text=old_text,
            new_text=new_text,
            replace_all=replace_all,
            expected_occurrences=expected_occurrences,
            source=source,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def apply_workspace_text_patch(
        self,
        *,
        session_id: str,
        path: str,
        patch: str,
        expected_hash: str | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        target = str(path or "").strip()
        action = {
            "action_type": "text_patch_apply",
            "session_id": session_id,
            "purpose": f"Apply a direct text patch to workspace file {target}.",
            "target": target,
            "source": source,
            "operator_decision": "approved",
            "patch": patch,
            "authorized": True,
            "observed": True,
            "bounded": True,
        }
        decision = self.aris.review_action(action)
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
            )
        result = super().apply_workspace_text_patch(
            session_id=session_id,
            path=path,
            patch=patch,
            expected_hash=expected_hash,
            source=source,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def apply_workspace_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_apply",
            session_id=session_id,
            purpose=f"Apply a pending workspace patch to {target}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id},
            )
        result = super().apply_workspace_patch(session_id=session_id, patch_id=patch_id)
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def accept_workspace_patch_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_hunk_apply",
            session_id=session_id,
            purpose=f"Apply hunk {hunk_index} from pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id, "hunk_index": hunk_index},
            )
        result = super().accept_workspace_patch_hunk(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def accept_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_line_apply",
            session_id=session_id,
            purpose=f"Apply line {line_index} from hunk {hunk_index} in pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={
                    "patch_id": patch_id,
                    "hunk_index": hunk_index,
                    "line_index": line_index,
                },
            )
        result = super().accept_workspace_patch_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
        )
        return self._finalize_governed_mutation(
            session_id=session_id,
            result=result,
            decision=decision,
        )

    def create_workspace_snapshot(
        self,
        *,
        session_id: str,
        label: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        target = str(label or "snapshot").strip() or "snapshot"
        decision = self._review_governed_action(
            action_type="snapshot_create",
            session_id=session_id,
            purpose=f"Create workspace snapshot {target}.",
            target=target,
            source=source,
            operator_decision="recorded",
            code=json.dumps({"label": target}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"label": target},
            )
        result = super().create_workspace_snapshot(
            session_id=session_id,
            label=label,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def restore_workspace_snapshot(
        self,
        *,
        session_id: str,
        snapshot_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        target = str(snapshot_id or "").strip()
        decision = self._review_governed_action(
            action_type="snapshot_restore",
            session_id=session_id,
            purpose=f"Restore workspace snapshot {target}.",
            target=target,
            source=source,
            code=json.dumps({"snapshot_id": target}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"snapshot_id": snapshot_id},
            )
        result = super().restore_workspace_snapshot(
            session_id=session_id,
            snapshot_id=snapshot_id,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def resolve_workspace_task(
        self,
        *,
        session_id: str,
        task_id: str,
        approved: bool,
        note: str = "",
    ) -> dict[str, object]:
        task_payload = self.task_manager.get_task(session_id, task_id) or {}
        active_cwd = (
            str(task_payload.get("cwd", "")).strip()
            if isinstance(task_payload, dict)
            else ""
        ) or "."
        goal = (
            str(task_payload.get("goal", "")).strip()
            if isinstance(task_payload, dict)
            else ""
        )
        source = (
            str(task_payload.get("source", "")).strip()
            if isinstance(task_payload, dict)
            else ""
        ) or "task"
        target = task_id
        action_type = "task_approval" if approved else "task_rejection"
        decision = self._review_governed_action(
            action_type=action_type,
            session_id=session_id,
            purpose=(
                f"Approve workspace task {task_id} for goal {goal or 'unspecified goal'}."
                if approved
                else f"Reject workspace task {task_id} for redesign."
            ),
            target=target,
            source=source,
            operator_decision="approved" if approved else "rejected",
            code=json.dumps(
                {
                    "task_id": task_id,
                    "goal": goal,
                    "cwd": active_cwd,
                    "approved": approved,
                    "note": note.strip(),
                },
                sort_keys=True,
            ),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"task_id": task_id},
            )
        result = super().resolve_workspace_task(
            session_id=session_id,
            task_id=task_id,
            approved=approved,
            note=note,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def create_workspace_git_branch(
        self,
        *,
        session_id: str,
        name: str,
        cwd: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        target = str(name or "").strip()
        decision = self._review_governed_action(
            action_type="git_branch_create",
            session_id=session_id,
            purpose=f"Create workspace Git branch {target}.",
            target=target,
            source=source,
            operator_decision="recorded",
            code=json.dumps({"branch": target, "cwd": str(cwd or '.').strip() or "."}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"branch": target},
            )
        result = super().create_workspace_git_branch(
            session_id=session_id,
            name=name,
            cwd=cwd,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def import_workspace_upload(
        self,
        *,
        session_id: str,
        filename: str,
        payload: bytes,
        target_path: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        target = str(target_path or filename).strip() or filename
        descriptor = {
            "filename": filename,
            "target_path": str(target_path or "").strip(),
            "bytes": len(payload),
        }
        decision = self._review_governed_action(
            action_type="workspace_import_upload",
            session_id=session_id,
            purpose=f"Import uploaded workspace content into {target}.",
            target=target,
            source=source,
            code=json.dumps(descriptor, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"filename": filename},
            )
        result = super().import_workspace_upload(
            session_id=session_id,
            filename=filename,
            payload=payload,
            target_path=target_path,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def clone_workspace_repo(
        self,
        *,
        session_id: str,
        repo_url: str,
        branch: str | None = None,
        target_dir: str | None = None,
        source: str = "ui",
    ) -> dict[str, object]:
        target = str(target_dir or repo_url).strip() or repo_url
        descriptor = {
            "repo_url": repo_url,
            "branch": str(branch or "").strip(),
            "target_dir": str(target_dir or "").strip(),
        }
        decision = self._review_governed_action(
            action_type="workspace_repo_clone",
            session_id=session_id,
            purpose=f"Clone repository {repo_url} into workspace target {target}.",
            target=target,
            source=source,
            code=json.dumps(descriptor, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"repo_url": repo_url},
            )
        result = super().clone_workspace_repo(
            session_id=session_id,
            repo_url=repo_url,
            branch=branch,
            target_dir=target_dir,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def propose_workspace_write(
        self,
        *,
        session_id: str,
        path: str,
        content: str,
        source: str = "api",
    ) -> dict[str, object]:
        _, before_content, relative = self._safe_workspace_text_state(
            session_id=session_id,
            path=path,
        )
        patch = self.aris.action_for_file_change(
            action_type="patch_write_proposal",
            session_id=session_id,
            purpose=f"Propose a governed workspace write for {relative}.",
            path=relative,
            before=before_content,
            after=content,
            source=source,
            operator_decision="recorded",
        )["patch"]
        decision = self._review_governed_action(
            action_type="patch_write_proposal",
            session_id=session_id,
            purpose=f"Propose a governed workspace write for {relative}.",
            target=relative,
            source=source,
            operator_decision="recorded",
            patch=patch,
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=relative,
                decision=decision,
            )
        result = super().propose_workspace_write(
            session_id=session_id,
            path=path,
            content=content,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def propose_workspace_replace(
        self,
        *,
        session_id: str,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        expected_occurrences: int | None = None,
        source: str = "api",
    ) -> dict[str, object]:
        before_exists, before_content, relative = self._safe_workspace_text_state(
            session_id=session_id,
            path=path,
        )
        replacement_count = before_content.count(old_text)
        replacements = replacement_count if replace_all else 1
        after_content = before_content.replace(old_text, new_text, replacements)
        patch = self.aris.action_for_file_change(
            action_type="patch_replace_proposal",
            session_id=session_id,
            purpose=f"Propose a governed workspace replace for {relative}.",
            path=relative,
            before=before_content if before_exists else "",
            after=after_content,
            source=source,
            operator_decision="recorded",
        )["patch"]
        decision = self._review_governed_action(
            action_type="patch_replace_proposal",
            session_id=session_id,
            purpose=f"Propose a governed workspace replace for {relative}.",
            target=relative,
            source=source,
            operator_decision="recorded",
            patch=patch,
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=relative,
                decision=decision,
            )
        result = super().propose_workspace_replace(
            session_id=session_id,
            path=path,
            old_text=old_text,
            new_text=new_text,
            replace_all=replace_all,
            expected_occurrences=expected_occurrences,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def reject_workspace_patch_hunk(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_hunk_reject",
            session_id=session_id,
            purpose=f"Reject hunk {hunk_index} from pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            operator_decision="rejected",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id, "hunk_index": hunk_index},
            )
        result = super().reject_workspace_patch_hunk(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def edit_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        after_text: str,
    ) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_line_edit",
            session_id=session_id,
            purpose=f"Edit line {line_index} from hunk {hunk_index} in pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            operator_decision="recorded",
            code=json.dumps(
                {
                    "patch_id": patch_id,
                    "hunk_index": hunk_index,
                    "line_index": line_index,
                    "after_text": after_text,
                },
                sort_keys=True,
            ),
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id, "hunk_index": hunk_index, "line_index": line_index},
            )
        result = super().edit_workspace_patch_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
            after_text=after_text,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def reject_workspace_patch_line(
        self,
        *,
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_line_reject",
            session_id=session_id,
            purpose=f"Reject line {line_index} from hunk {hunk_index} in pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            operator_decision="rejected",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id, "hunk_index": hunk_index, "line_index": line_index},
            )
        result = super().reject_workspace_patch_line(
            session_id=session_id,
            patch_id=patch_id,
            hunk_index=hunk_index,
            line_index=line_index,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def reject_workspace_patch(self, *, session_id: str, patch_id: str) -> dict[str, object]:
        patch, target = self._pending_patch_target(session_id=session_id, patch_id=patch_id)
        decision = self._review_governed_action(
            action_type="patch_reject",
            session_id=session_id,
            purpose=f"Reject pending patch {patch_id}.",
            target=target,
            source=str(patch.get("source", "approval")).strip() or "approval",
            operator_decision="rejected",
            patch=str(patch.get("diff", "")),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"patch_id": patch_id},
            )
        result = super().reject_workspace_patch(session_id=session_id, patch_id=patch_id)
        return self._finalize_governed_result(result=result, decision=decision)

    def rollback_workspace_change(
        self,
        *,
        session_id: str,
        change_id: str,
        source: str = "ui",
    ) -> dict[str, object]:
        change = self.change_history.get_change(session_id, change_id)
        if isinstance(change, dict):
            target = str(change.get("path", "")).strip() or change_id
        else:
            target = str(getattr(change, "path", "") or "").strip() or change_id
        decision = self._review_governed_action(
            action_type="change_rollback",
            session_id=session_id,
            purpose=f"Rollback applied workspace change {change_id}.",
            target=target,
            source=source,
            code=json.dumps({"change_id": change_id, "target": target}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=target,
                decision=decision,
                extra={"change_id": change_id},
            )
        result = super().rollback_workspace_change(
            session_id=session_id,
            change_id=change_id,
            source=source,
        )
        return self._finalize_governed_result(result=result, decision=decision)

    def reset_sandbox(self, session_id: str) -> dict[str, object]:
        decision = self._review_governed_action(
            action_type="sandbox_reset",
            session_id=session_id,
            purpose=f"Reset governed execution sandbox for session {session_id}.",
            target=session_id,
            source="api",
            operator_decision="recorded",
            code=json.dumps({"session_id": session_id}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=session_id,
                decision=decision,
            )
        result = super().reset_sandbox(session_id)
        return self._finalize_governed_result(result=result, decision=decision)

    async def stream_workspace_task(
        self,
        *,
        session_id: str | None,
        goal: str,
        cwd: str | None,
        test_commands: list[str],
        fast_mode: bool,
        title: str | None = None,
    ) -> AsyncIterator[str]:
        task_goal = str(goal or "").strip()
        active_cwd = str(cwd or ".").strip() or "."
        session = self.sessions.get_or_create(session_id, title or task_goal or "Workspace task")
        decision = self._review_governed_action(
            action_type="task_run",
            session_id=session.id,
            purpose=f"Start governed workspace task for goal {task_goal or 'unspecified goal'}.",
            target=active_cwd,
            source="ui",
            operator_decision="approved",
            code=json.dumps(
                {
                    "goal": task_goal,
                    "cwd": active_cwd,
                    "test_commands": [command.strip() for command in test_commands if command.strip()],
                    "fast_mode": bool(fast_mode),
                },
                sort_keys=True,
            ),
        )
        if not decision.allowed:
            payload = self._governed_block_response(
                session_id=session.id,
                target=active_cwd,
                decision=decision,
                extra={"goal": task_goal},
            )
            yield self._sse_event(
                "meta",
                {
                    "session_id": session.id,
                    "mode": "task",
                    "governance": decision.payload(),
                    "blocked": True,
                },
            )
            yield self._sse_event(
                "agent_step",
                {
                    "step": 0,
                    "kind": "governance_block",
                    "content": decision.reason,
                    "governance": decision.payload(),
                },
            )
            yield self._sse_event("done", payload)
            return
        async for event in super().stream_workspace_task(
            session_id=session_id,
            goal=goal,
            cwd=cwd,
            test_commands=test_commands,
            fast_mode=fast_mode,
            title=title,
        ):
            yield event

    async def stream_approval_decision(
        self,
        *,
        session_id: str,
        approval_id: str,
        approved: bool,
    ) -> AsyncIterator[str]:
        session = self.sessions.get_or_create(session_id, "Approval follow-up")
        decision = self._review_governed_action(
            action_type="approval_resolution",
            session_id=session.id,
            purpose=(
                f"Approve pending agent approval {approval_id}."
                if approved
                else f"Reject pending agent approval {approval_id}."
            ),
            target=approval_id,
            source="approval",
            operator_decision="approved" if approved else "rejected",
            code=json.dumps({"approval_id": approval_id, "approved": approved}, sort_keys=True),
        )
        if not decision.allowed:
            payload = self._governed_block_response(
                session_id=session.id,
                target=approval_id,
                decision=decision,
                extra={"approval_id": approval_id},
            )
            yield self._sse_event(
                "meta",
                {
                    "session_id": session.id,
                    "mode": "agent_resume",
                    "approval_id": approval_id,
                    "approved": approved,
                    "governance": decision.payload(),
                    "blocked": True,
                },
            )
            yield self._sse_event(
                "agent_step",
                {
                    "step": 0,
                    "kind": "governance_block",
                    "content": decision.reason,
                    "governance": decision.payload(),
                },
            )
            yield self._sse_event("done", payload)
            return
        async for event in super().stream_approval_decision(
            session_id=session_id,
            approval_id=approval_id,
            approved=approved,
        ):
            yield event

    def cancel_agent_run(self, run_id: str) -> dict[str, object]:
        run = self.agent_runs.get_run(run_id) or {}
        session_id = str(run.get("session_id", "")).strip() or "system"
        decision = self._review_governed_action(
            action_type="run_cancel",
            session_id=session_id,
            purpose=f"Cancel agent run {run_id}.",
            target=run_id,
            source="ui",
            operator_decision="recorded",
            code=json.dumps({"run_id": run_id}, sort_keys=True),
        )
        if not decision.allowed:
            return self._governed_block_response(
                session_id=session_id,
                target=run_id,
                decision=decision,
                extra={"run_id": run_id},
            )
        result = super().cancel_agent_run(run_id)
        return self._finalize_governed_result(result=result, decision=decision)
