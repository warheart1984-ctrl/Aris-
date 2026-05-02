from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from evolving_ai.aris import ArisChatService
from src.api import LawApiBridge

from .attachments import Attachment
from .config import AppConfig
from .service import ChatService


class AttachmentRequest(BaseModel):
    name: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    kind: str = Field(pattern="^(text|image)$")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1)
    fast_mode: bool | None = None
    retrieval_k: int | None = None
    mode: str = Field(default="chat")
    attachments: list[AttachmentRequest] = Field(default_factory=list)


class KnowledgeRequest(BaseModel):
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ExecuteRequest(BaseModel):
    session_id: str | None = None
    code: str = Field(min_length=1)


class ExecCommandRequest(BaseModel):
    session_id: str | None = None
    command: list[str] = Field(min_length=1)
    cwd: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class WorkspaceFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str = ""


class WorkspaceFileReplaceRequest(BaseModel):
    path: str = Field(min_length=1)
    old_text: str
    new_text: str
    replace_all: bool = False
    expected_occurrences: int | None = Field(default=None, ge=1)


class WorkspaceTextPatchRequest(BaseModel):
    path: str = Field(min_length=1)
    patch: str = Field(min_length=1)
    expected_hash: str | None = None


class WorkspaceRepoCloneRequest(BaseModel):
    repo_url: str = Field(min_length=1)
    branch: str | None = None
    target_dir: str | None = None


class WorkspaceSymbolEditRequest(BaseModel):
    symbol: str = Field(min_length=1)
    path: str | None = None
    content: str = Field(min_length=1)


class WorkspaceTaskRunRequest(BaseModel):
    goal: str = Field(min_length=1)
    title: str | None = None
    cwd: str | None = None
    test_commands: list[str] = Field(default_factory=list)
    fast_mode: bool = False


class WorkspaceTaskPlanRequest(BaseModel):
    goal: str = Field(min_length=1)
    title: str | None = None
    cwd: str | None = None
    test_commands: list[str] = Field(default_factory=list)


class WorkspaceTaskDecisionRequest(BaseModel):
    note: str = ""


class WorkspacePatchLineEditRequest(BaseModel):
    after_text: str = ""


class WorkspaceChangeVerifyRequest(BaseModel):
    preset_id: str | None = None
    cwd: str | None = None


class WorkspaceSnapshotCreateRequest(BaseModel):
    label: str | None = None


class WorkspaceGitBranchRequest(BaseModel):
    name: str = Field(min_length=1)
    cwd: str | None = None


class WorkspaceGitHandoffRequest(BaseModel):
    goal: str | None = None
    task_id: str | None = None
    cwd: str | None = None


class ArisKillRequest(BaseModel):
    reason: str = Field(min_length=1)


class ArisKillResetRequest(BaseModel):
    reason: str = Field(min_length=1)
    reseal_integrity: bool = False


class ArisForgePlanRequest(BaseModel):
    goal: str = Field(min_length=1)
    focus_paths: list[str] = Field(default_factory=list)


class ArisMysticReadRequest(BaseModel):
    input: str = Field(min_length=1)
    session_id: str | None = None


class ArisMysticSessionRequest(BaseModel):
    session_id: str | None = None


class ArisMysticMuteRequest(BaseModel):
    session_id: str | None = None
    minutes: float = Field(gt=0, le=240)


class ModelRouterUpdateRequest(BaseModel):
    mode: str = Field(pattern="^(auto|manual)$")
    pinned_system: str | None = Field(default=None, pattern="^(general|coding|light_coding)$")


@lru_cache(maxsize=1)
def _build_service() -> ChatService:
    root = Path.cwd()
    config = AppConfig.from_env(root)
    return ArisChatService(config)


def create_app(build_service: Callable[[], ChatService] | None = None) -> FastAPI:
    service_factory = build_service or _build_service
    service = service_factory()
    static_dir = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.start_background_workers()
        try:
            yield
        finally:
            service.stop_background_workers()

    app = FastAPI(title=service.config.app_name, lifespan=lifespan)
    law_bridge = LawApiBridge(service)

    @app.middleware("http")
    async def runtime_law_middleware(request, call_next):
        return await law_bridge.middleware(request, call_next)

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/health")
    async def health() -> JSONResponse:
        aris = service.aris_health_payload() if hasattr(service, "aris_health_payload") else {}
        return JSONResponse(
            {
                "ok": bool(aris.get("ok", True)),
                "provider_mode": service.config.provider_mode,
                "aris": aris,
            }
        )

    @app.get("/api/config")
    async def config_payload() -> JSONResponse:
        return JSONResponse(service.config_payload())

    @app.get("/api/model-router")
    async def model_router_payload() -> JSONResponse:
        return JSONResponse(service.model_router_payload())

    @app.post("/api/model-router")
    async def update_model_router(request: ModelRouterUpdateRequest) -> JSONResponse:
        return JSONResponse(
            service.set_model_router(
                mode=request.mode,
                pinned_system=request.pinned_system,
            )
        )

    @app.get("/api/aris/status")
    async def aris_status() -> JSONResponse:
        return JSONResponse(service.aris_status_payload())

    @app.get("/api/aris/activity")
    async def aris_activity(
        limit: int = Query(default=25, ge=1, le=200),
        session_id: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(service.aris_activity_payload(limit=limit, session_id=session_id))

    @app.get("/api/aris/discards")
    async def aris_discards(
        limit: int = Query(default=25, ge=1, le=200),
    ) -> JSONResponse:
        return JSONResponse(service.aris_discards_payload(limit=limit))

    @app.get("/api/aris/shame")
    async def aris_shame(
        limit: int = Query(default=25, ge=1, le=200),
    ) -> JSONResponse:
        return JSONResponse(service.aris_shame_payload(limit=limit))

    @app.get("/api/aris/fame")
    async def aris_fame(
        limit: int = Query(default=25, ge=1, le=200),
    ) -> JSONResponse:
        return JSONResponse(service.aris_fame_payload(limit=limit))

    @app.get("/api/aris/truth")
    async def aris_truth(
        session_id: str | None = Query(default=None),
        activity_limit: int = Query(default=25, ge=1, le=200),
        hall_limit: int = Query(default=25, ge=1, le=200),
    ) -> JSONResponse:
        return JSONResponse(
            service.aris_truth_payload(
                session_id=session_id,
                activity_limit=activity_limit,
                hall_limit=hall_limit,
            )
        )

    @app.post("/api/aris/kill/soft")
    async def aris_kill_soft(request: ArisKillRequest) -> JSONResponse:
        return JSONResponse(service.aris_kill_soft(reason=request.reason))

    @app.post("/api/aris/kill/hard")
    async def aris_kill_hard(request: ArisKillRequest) -> JSONResponse:
        return JSONResponse(service.aris_kill_hard(reason=request.reason))

    @app.post("/api/aris/kill/reset")
    async def aris_kill_reset(request: ArisKillResetRequest) -> JSONResponse:
        return JSONResponse(
            service.aris_kill_reset(
                reason=request.reason,
                reseal_integrity=request.reseal_integrity,
            )
        )

    @app.post("/api/aris/forge/plan")
    async def aris_forge_plan(request: ArisForgePlanRequest) -> JSONResponse:
        return JSONResponse(
            service.aris_forge_plan(
                goal=request.goal,
                focus_paths=request.focus_paths,
            )
        )

    @app.post("/api/aris/mystic-read")
    async def aris_mystic_read(request: ArisMysticReadRequest) -> JSONResponse:
        return JSONResponse(
            service.aris_mystic_read(
                session_id=request.session_id,
                input_text=request.input,
            )
        )

    @app.get("/api/aris/mystic/status")
    async def aris_mystic_status(session_id: str | None = Query(default=None)) -> JSONResponse:
        return JSONResponse(service.aris_mystic_status(session_id=session_id))

    @app.post("/api/aris/mystic/tick")
    async def aris_mystic_tick(request: ArisMysticSessionRequest) -> JSONResponse:
        return JSONResponse(service.aris_mystic_tick(session_id=request.session_id))

    @app.post("/api/aris/mystic/break")
    async def aris_mystic_break(request: ArisMysticSessionRequest) -> JSONResponse:
        return JSONResponse(service.aris_mystic_break(session_id=request.session_id))

    @app.post("/api/aris/mystic/acknowledge")
    async def aris_mystic_acknowledge(request: ArisMysticSessionRequest) -> JSONResponse:
        return JSONResponse(service.aris_mystic_acknowledge(session_id=request.session_id))

    @app.post("/api/aris/mystic/mute")
    async def aris_mystic_mute(request: ArisMysticMuteRequest) -> JSONResponse:
        return JSONResponse(
            service.aris_mystic_mute(
                session_id=request.session_id,
                minutes=request.minutes,
            )
        )

    @app.get("/api/memory")
    async def memory_payload() -> JSONResponse:
        return JSONResponse(service.memory_payload())

    @app.get("/api/search")
    async def search_preview(query: str = Query(min_length=1)) -> JSONResponse:
        tool_results = await service.tools.run(
            query,
            enable_remote_fetch=service.config.enable_remote_fetch,
            mode="deep",
        )
        return JSONResponse([asdict(result) for result in tool_results])

    @app.get("/api/sessions")
    async def sessions() -> JSONResponse:
        return JSONResponse(service.list_sessions())

    @app.get("/api/knowledge")
    async def knowledge() -> JSONResponse:
        return JSONResponse(service.list_knowledge())

    @app.post("/api/knowledge")
    async def add_knowledge(request: KnowledgeRequest) -> JSONResponse:
        service.add_knowledge(request.name, request.content)
        return JSONResponse({"ok": True, "sources": service.list_knowledge()})

    @app.post("/api/attachments/parse")
    async def parse_attachment(file: UploadFile = File(...)) -> JSONResponse:
        payload = await file.read()
        parsed = service.parse_attachment(
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            payload=payload,
        )
        return JSONResponse(parsed)

    @app.post("/api/execute")
    async def execute(request: ExecuteRequest) -> JSONResponse:
        session_id = request.session_id or "scratchpad"
        return JSONResponse(service.execute_code(session_id=session_id, code=request.code))

    @app.post("/api/exec")
    async def execute_command(request: ExecCommandRequest) -> JSONResponse:
        session_id = request.session_id or "scratchpad"
        return JSONResponse(
            service.execute_command(
                session_id=session_id,
                command=request.command,
                cwd=request.cwd,
                timeout_seconds=request.timeout_seconds,
            )
        )

    @app.post("/api/exec/stream")
    async def stream_command(request: ExecCommandRequest) -> StreamingResponse:
        stream = service.stream_command(
            session_id=request.session_id,
            command=request.command,
            cwd=request.cwd,
            timeout_seconds=request.timeout_seconds,
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.get("/api/sandbox")
    async def sandbox_overview() -> JSONResponse:
        return JSONResponse(service.sandbox_payload())

    @app.get("/api/sandbox/{session_id}")
    async def sandbox_session(session_id: str) -> JSONResponse:
        return JSONResponse(service.sandbox_payload(session_id))

    @app.post("/api/sandbox/{session_id}/reset")
    async def sandbox_reset(session_id: str) -> JSONResponse:
        return JSONResponse(service.reset_sandbox(session_id))

    @app.get("/api/workspace/{session_id}")
    async def workspace(session_id: str) -> JSONResponse:
        return JSONResponse(service.workspace_payload(session_id))

    @app.get("/api/workspace/{session_id}/project")
    async def workspace_project(session_id: str) -> JSONResponse:
        return JSONResponse(service.inspect_workspace_project(session_id))

    @app.get("/api/workspace/{session_id}/repo-map")
    async def workspace_repo_map(
        session_id: str,
        goal: str | None = Query(default=None),
        cwd: str | None = Query(default=None),
        path: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1),
    ) -> JSONResponse:
        return JSONResponse(
            service.inspect_workspace_repo_map(
                session_id,
                goal=goal,
                cwd=cwd,
                focus_path=path,
                symbol=symbol,
                limit=limit,
            )
        )

    @app.get("/api/workspace/{session_id}/git")
    async def workspace_git(
        session_id: str,
        cwd: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(service.inspect_workspace_git(session_id, cwd=cwd))

    @app.post("/api/workspace/{session_id}/git/branch")
    async def create_workspace_git_branch(
        session_id: str,
        request: WorkspaceGitBranchRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.create_workspace_git_branch(
                session_id=session_id,
                name=request.name,
                cwd=request.cwd,
            )
        )

    @app.post("/api/workspace/{session_id}/git/handoff")
    async def prepare_workspace_git_handoff(
        session_id: str,
        request: WorkspaceGitHandoffRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.prepare_workspace_git_handoff(
                session_id=session_id,
                goal=request.goal,
                task_id=request.task_id,
                cwd=request.cwd,
            )
        )

    @app.get("/api/workspace/{session_id}/search")
    async def workspace_search(
        session_id: str,
        query: str = Query(min_length=1),
        mode: str = Query(default="text"),
        limit: int | None = Query(default=None, ge=1),
        path_prefix: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(
            service.search_workspace(
                session_id=session_id,
                query=query,
                mode=mode,
                limit=limit,
                path_prefix=path_prefix,
            )
        )

    @app.get("/api/workspace/{session_id}/symbols")
    async def workspace_symbols(
        session_id: str,
        query: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1),
        path_prefix: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(
            service.list_workspace_symbols(
                session_id=session_id,
                query=query,
                limit=limit,
                path_prefix=path_prefix,
            )
        )

    @app.get("/api/workspace/{session_id}/symbol")
    async def workspace_symbol(
        session_id: str,
        symbol: str = Query(min_length=1),
        path: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(
            service.read_workspace_symbol(
                session_id=session_id,
                symbol=symbol,
                path=path,
            )
        )

    @app.get("/api/workspace/{session_id}/symbol/references")
    async def workspace_symbol_references(
        session_id: str,
        symbol: str = Query(min_length=1),
        limit: int | None = Query(default=None, ge=1),
        path_prefix: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(
            service.find_workspace_references(
                session_id=session_id,
                symbol=symbol,
                limit=limit,
                path_prefix=path_prefix,
            )
        )

    @app.put("/api/workspace/{session_id}/symbol")
    async def edit_workspace_symbol(
        session_id: str,
        request: WorkspaceSymbolEditRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.edit_workspace_symbol(
                session_id=session_id,
                symbol=request.symbol,
                path=request.path,
                content=request.content,
            )
        )

    @app.get("/api/workspace/{session_id}/snapshots")
    async def workspace_snapshots(session_id: str) -> JSONResponse:
        return JSONResponse(service.list_workspace_snapshots(session_id))

    @app.post("/api/workspace/{session_id}/snapshots")
    async def create_workspace_snapshot(
        session_id: str,
        request: WorkspaceSnapshotCreateRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.create_workspace_snapshot(
                session_id=session_id,
                label=request.label,
            )
        )

    @app.post("/api/workspace/{session_id}/snapshots/{snapshot_id}/restore")
    async def restore_workspace_snapshot(
        session_id: str,
        snapshot_id: str,
    ) -> JSONResponse:
        return JSONResponse(
            service.restore_workspace_snapshot(
                session_id=session_id,
                snapshot_id=snapshot_id,
            )
        )

    @app.post("/api/workspace/{session_id}/import/upload")
    async def upload_workspace_import(
        session_id: str,
        file: UploadFile = File(...),
        target_path: str | None = Form(default=None),
    ) -> JSONResponse:
        payload = await file.read()
        return JSONResponse(
            service.import_workspace_upload(
                session_id=session_id,
                filename=file.filename or "upload.bin",
                payload=payload,
                target_path=target_path,
            )
        )

    @app.post("/api/workspace/{session_id}/import/clone")
    async def clone_workspace_repo(
        session_id: str,
        request: WorkspaceRepoCloneRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.clone_workspace_repo(
                session_id=session_id,
                repo_url=request.repo_url,
                branch=request.branch,
                target_dir=request.target_dir,
            )
        )

    @app.get("/api/workspace/{session_id}/file")
    async def workspace_file(
        session_id: str,
        path: str = Query(min_length=1),
        start_line: int | None = Query(default=None, ge=1),
        end_line: int | None = Query(default=None, ge=1),
    ) -> JSONResponse:
        return JSONResponse(
            service.read_workspace_file(
                session_id=session_id,
                path=path,
                start_line=start_line,
                end_line=end_line,
            )
        )

    @app.put("/api/workspace/{session_id}/file")
    async def write_workspace_file(
        session_id: str,
        request: WorkspaceFileWriteRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.write_workspace_file(
                session_id=session_id,
                path=request.path,
                content=request.content,
            )
        )

    @app.post("/api/workspace/{session_id}/file/replace")
    async def replace_workspace_file(
        session_id: str,
        request: WorkspaceFileReplaceRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.replace_workspace_file(
                session_id=session_id,
                path=request.path,
                old_text=request.old_text,
                new_text=request.new_text,
                replace_all=request.replace_all,
                expected_occurrences=request.expected_occurrences,
            )
        )

    @app.post("/api/workspace/{session_id}/patch/preview")
    async def preview_workspace_patch(
        session_id: str,
        request: WorkspaceTextPatchRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.preview_workspace_patch(
                session_id=session_id,
                path=request.path,
                patch=request.patch,
            )
        )

    @app.post("/api/workspace/{session_id}/patch/apply")
    async def apply_workspace_text_patch(
        session_id: str,
        request: WorkspaceTextPatchRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.apply_workspace_text_patch(
                session_id=session_id,
                path=request.path,
                patch=request.patch,
                expected_hash=request.expected_hash,
            )
        )

    @app.get("/api/workspace/{session_id}/patches")
    async def workspace_patches(session_id: str) -> JSONResponse:
        return JSONResponse(service.list_pending_workspace_patches(session_id))

    @app.get("/api/workspace/{session_id}/changes")
    async def workspace_changes(session_id: str) -> JSONResponse:
        return JSONResponse(service.list_applied_workspace_changes(session_id))

    @app.get("/api/workspace/{session_id}/verification")
    async def workspace_verification(session_id: str) -> JSONResponse:
        return JSONResponse(service.workspace_verification_payload(session_id))

    @app.get("/api/workspace/{session_id}/review")
    async def workspace_review(
        session_id: str,
        cwd: str | None = Query(default=None),
    ) -> JSONResponse:
        return JSONResponse(service.review_workspace(session_id=session_id, cwd=cwd))

    @app.get("/api/workspace/{session_id}/tasks")
    async def workspace_tasks(session_id: str) -> JSONResponse:
        return JSONResponse(service.list_workspace_tasks(session_id))

    @app.post("/api/workspace/{session_id}/tasks/plan")
    async def plan_workspace_task(
        session_id: str,
        request: WorkspaceTaskPlanRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.plan_workspace_task(
                session_id=session_id,
                goal=request.goal,
                cwd=request.cwd,
                test_commands=request.test_commands,
                title=request.title,
            )
        )

    @app.post("/api/workspace/{session_id}/tasks/run")
    async def run_workspace_task(
        session_id: str,
        request: WorkspaceTaskRunRequest,
    ) -> StreamingResponse:
        stream = service.stream_workspace_task(
            session_id=session_id,
            goal=request.goal,
            cwd=request.cwd,
            test_commands=request.test_commands,
            fast_mode=request.fast_mode,
            title=request.title,
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.post("/api/workspace/{session_id}/tasks/{task_id}/approve")
    async def approve_workspace_task(
        session_id: str,
        task_id: str,
        request: WorkspaceTaskDecisionRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.resolve_workspace_task(
                session_id=session_id,
                task_id=task_id,
                approved=True,
                note=request.note,
            )
        )

    @app.post("/api/workspace/{session_id}/tasks/{task_id}/reject")
    async def reject_workspace_task(
        session_id: str,
        task_id: str,
        request: WorkspaceTaskDecisionRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.resolve_workspace_task(
                session_id=session_id,
                task_id=task_id,
                approved=False,
                note=request.note,
            )
        )

    @app.post("/api/workspace/{session_id}/patches/write")
    async def propose_workspace_file_write(
        session_id: str,
        request: WorkspaceFileWriteRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.propose_workspace_write(
                session_id=session_id,
                path=request.path,
                content=request.content,
            )
        )

    @app.post("/api/workspace/{session_id}/patches/replace")
    async def propose_workspace_file_replace(
        session_id: str,
        request: WorkspaceFileReplaceRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.propose_workspace_replace(
                session_id=session_id,
                path=request.path,
                old_text=request.old_text,
                new_text=request.new_text,
                replace_all=request.replace_all,
                expected_occurrences=request.expected_occurrences,
            )
        )

    @app.post("/api/workspace/{session_id}/patches/{patch_id}/apply")
    async def apply_workspace_patch(session_id: str, patch_id: str) -> JSONResponse:
        return JSONResponse(
            service.apply_workspace_patch(session_id=session_id, patch_id=patch_id)
        )

    @app.post("/api/workspace/{session_id}/patches/{patch_id}/hunks/{hunk_index}/accept")
    async def accept_workspace_patch_hunk(
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> JSONResponse:
        return JSONResponse(
            service.accept_workspace_patch_hunk(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=hunk_index,
            )
        )

    @app.post("/api/workspace/{session_id}/patches/{patch_id}/hunks/{hunk_index}/reject")
    async def reject_workspace_patch_hunk(
        session_id: str,
        patch_id: str,
        hunk_index: int,
    ) -> JSONResponse:
        return JSONResponse(
            service.reject_workspace_patch_hunk(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=hunk_index,
            )
        )

    @app.post(
        "/api/workspace/{session_id}/patches/{patch_id}/hunks/{hunk_index}/lines/{line_index}/accept"
    )
    async def accept_workspace_patch_line(
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> JSONResponse:
        return JSONResponse(
            service.accept_workspace_patch_line(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=hunk_index,
                line_index=line_index,
            )
        )

    @app.post(
        "/api/workspace/{session_id}/patches/{patch_id}/hunks/{hunk_index}/lines/{line_index}/edit"
    )
    async def edit_workspace_patch_line(
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
        request: WorkspacePatchLineEditRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.edit_workspace_patch_line(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=hunk_index,
                line_index=line_index,
                after_text=request.after_text,
            )
        )

    @app.post(
        "/api/workspace/{session_id}/patches/{patch_id}/hunks/{hunk_index}/lines/{line_index}/reject"
    )
    async def reject_workspace_patch_line(
        session_id: str,
        patch_id: str,
        hunk_index: int,
        line_index: int,
    ) -> JSONResponse:
        return JSONResponse(
            service.reject_workspace_patch_line(
                session_id=session_id,
                patch_id=patch_id,
                hunk_index=hunk_index,
                line_index=line_index,
            )
        )

    @app.post("/api/workspace/{session_id}/patches/{patch_id}/reject")
    async def reject_workspace_patch(session_id: str, patch_id: str) -> JSONResponse:
        return JSONResponse(
            service.reject_workspace_patch(session_id=session_id, patch_id=patch_id)
        )

    @app.post("/api/workspace/{session_id}/changes/{change_id}/rollback")
    async def rollback_workspace_change(session_id: str, change_id: str) -> JSONResponse:
        return JSONResponse(
            service.rollback_workspace_change(
                session_id=session_id,
                change_id=change_id,
            )
        )

    @app.post("/api/workspace/{session_id}/changes/{change_id}/verify")
    async def verify_workspace_change(
        session_id: str,
        change_id: str,
        request: WorkspaceChangeVerifyRequest,
    ) -> JSONResponse:
        return JSONResponse(
            service.verify_workspace_change(
                session_id=session_id,
                change_id=change_id,
                preset_id=request.preset_id,
                cwd=request.cwd,
            )
        )

    @app.get("/api/agent/{session_id}/approvals")
    async def agent_approvals(session_id: str) -> JSONResponse:
        return JSONResponse(service.list_pending_approvals(session_id))

    @app.get("/api/agent/{session_id}/runs")
    async def agent_runs(
        session_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse:
        return JSONResponse(service.list_agent_runs(session_id, limit=limit))

    @app.get("/api/agent/runs/{run_id}")
    async def agent_run(run_id: str) -> JSONResponse:
        return JSONResponse(service.get_agent_run(run_id))

    @app.get("/api/agent/runs/{run_id}/stream")
    async def stream_agent_run(
        run_id: str,
        after_event_id: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        return StreamingResponse(
            service.stream_agent_run(run_id=run_id, after_event_id=after_event_id),
            media_type="text/event-stream",
        )

    @app.post("/api/agent/runs/{run_id}/cancel")
    async def cancel_agent_run(run_id: str) -> JSONResponse:
        return JSONResponse(service.cancel_agent_run(run_id))

    @app.get("/api/agent/{session_id}/audit")
    async def agent_approval_audit(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> JSONResponse:
        return JSONResponse(service.list_approval_audit(session_id, limit=limit))

    @app.post("/api/agent/{session_id}/approvals/{approval_id}/approve")
    async def approve_agent_approval(
        session_id: str,
        approval_id: str,
    ) -> StreamingResponse:
        stream = service.stream_approval_decision(
            session_id=session_id,
            approval_id=approval_id,
            approved=True,
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.post("/api/agent/{session_id}/approvals/{approval_id}/reject")
    async def reject_agent_approval(
        session_id: str,
        approval_id: str,
    ) -> StreamingResponse:
        stream = service.stream_approval_decision(
            session_id=session_id,
            approval_id=approval_id,
            approved=False,
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> StreamingResponse:
        stream = service.stream_chat(
            session_id=request.session_id,
            user_message=request.message,
            fast_mode=request.fast_mode
            if request.fast_mode is not None
            else service.config.fast_mode_default,
            retrieval_k=request.retrieval_k or service.config.retrieval_k,
            mode=request.mode,
            attachments=[
                Attachment(**attachment_request.model_dump())
                for attachment_request in request.attachments
            ],
        )
        return StreamingResponse(stream, media_type="text/event-stream")

    return app


def main() -> None:
    service = _build_service()
    uvicorn.run(
        create_app(build_service=_build_service),
        host=service.config.host,
        port=service.config.port,
        log_level="info",
    )
