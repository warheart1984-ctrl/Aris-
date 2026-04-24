from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str
    host: str
    port: int
    provider_mode: str
    api_url: str
    vision_api_url: str
    api_key: str
    model: str
    fast_model: str
    quality_model: str
    vision_model: str
    general_model: str
    coding_model: str
    light_coding_model: str
    model_switch_default_mode: str
    model_switch_pinned_system: str
    timeout_seconds: float
    cache_size: int
    max_context_messages: int
    max_response_tokens: int
    retrieval_k: int
    knowledge_dir: Path
    sessions_path: Path
    memory_path: Path
    agent_run_db_path: Path
    approval_db_path: Path
    legacy_approval_state_path: Path
    agent_worker_enabled: bool
    agent_worker_concurrency: int
    agent_worker_poll_seconds: float
    agent_worker_lease_seconds: float
    agent_worker_heartbeat_seconds: float
    agent_worker_max_attempts: int
    agent_worker_retry_delay_seconds: float
    workspaces_dir: Path
    execution_timeout_seconds: float
    execution_max_code_chars: int
    execution_max_output_chars: int
    execution_max_files: int
    execution_max_file_bytes: int
    execution_backend: str
    docker_image: str
    docker_memory: str
    docker_cpus: str
    docker_pids_limit: int
    docker_workdir: str
    docker_tmpfs_size: str
    docker_network_disabled: bool
    docker_read_only_root: bool
    docker_no_new_privileges: bool
    docker_user: str
    command_timeout_seconds: float
    allowed_exec_commands: tuple[str, ...]
    agent_max_command_tier: str
    agent_allow_python: bool
    agent_allow_shell: bool
    agent_allow_filesystem_read: bool
    agent_allow_filesystem_write: bool
    repo_upload_max_bytes: int
    repo_archive_max_entries: int
    repo_max_total_bytes: int
    repo_clone_timeout_seconds: float
    repo_allowed_clone_hosts: tuple[str, ...]
    workspace_search_max_results: int
    workspace_search_max_excerpt_chars: int
    workspace_snapshot_max_entries: int
    workspace_snapshot_max_total_bytes: int
    workspace_snapshot_max_snapshots: int
    fast_mode_default: bool
    enable_remote_fetch: bool

    @classmethod
    def from_env(cls, root: Path) -> "AppConfig":
        data_dir = root / ".forge_chat"
        knowledge_dir = Path(
            os.getenv("FORGE_KNOWLEDGE_DIR", str(data_dir / "knowledge"))
        )
        sessions_path = Path(
            os.getenv("FORGE_SESSIONS_PATH", str(data_dir / "sessions.json"))
        )
        memory_path = Path(
            os.getenv("FORGE_MEMORY_PATH", str(data_dir / "memory.json"))
        )
        agent_run_db_path = Path(
            os.getenv("FORGE_AGENT_RUN_DB_PATH", str(data_dir / "agent-runs.db"))
        )
        approval_db_path = Path(
            os.getenv("FORGE_APPROVAL_DB_PATH", str(data_dir / "approvals.db"))
        )
        legacy_approval_state_path = Path(
            os.getenv("FORGE_APPROVAL_STATE_PATH", str(data_dir / "approvals.json"))
        )
        workspaces_dir = Path(
            os.getenv("FORGE_WORKSPACES_DIR", str(data_dir / "workspaces"))
        )
        return cls(
            app_name=os.getenv("FORGE_APP_NAME", "ARIS"),
            host=os.getenv("FORGE_HOST", "127.0.0.1"),
            port=int(os.getenv("FORGE_PORT", "8080")),
            provider_mode=os.getenv("FORGE_PROVIDER_MODE", "mock").lower(),
            api_url=os.getenv("FORGE_API_URL", "").strip(),
            vision_api_url=os.getenv("FORGE_VISION_API_URL", "").strip(),
            api_key=os.getenv("FORGE_API_KEY", "").strip(),
            model=os.getenv("FORGE_MODEL", "your-local-model"),
            fast_model=os.getenv("FORGE_FAST_MODEL", os.getenv("FORGE_MODEL", "your-local-model-fast")),
            quality_model=os.getenv("FORGE_QUALITY_MODEL", os.getenv("FORGE_MODEL", "your-local-model")),
            vision_model=os.getenv("FORGE_VISION_MODEL", os.getenv("FORGE_MODEL", "your-vision-model")),
            general_model=os.getenv(
                "GENERAL_MODEL",
                os.getenv("FORGE_GENERAL_MODEL", os.getenv("FORGE_VISION_MODEL", "gemma3:12b")),
            ).strip(),
            coding_model=os.getenv(
                "CODING_MODEL",
                os.getenv("FORGE_CODING_MODEL", os.getenv("FORGE_QUALITY_MODEL", "devstral")),
            ).strip(),
            light_coding_model=os.getenv(
                "LIGHT_CODING_MODEL",
                os.getenv("FORGE_LIGHT_CODING_MODEL", os.getenv("FORGE_FAST_MODEL", "qwen2.5-coder:7b")),
            ).strip(),
            model_switch_default_mode=os.getenv("FORGE_MODEL_SWITCH_MODE", "auto").strip().lower(),
            model_switch_pinned_system=os.getenv("FORGE_MODEL_SWITCH_PINNED_SYSTEM", "").strip().lower(),
            timeout_seconds=float(os.getenv("FORGE_TIMEOUT_SECONDS", "40")),
            cache_size=int(os.getenv("FORGE_CACHE_SIZE", "64")),
            max_context_messages=int(os.getenv("FORGE_MAX_CONTEXT_MESSAGES", "10")),
            max_response_tokens=int(os.getenv("FORGE_MAX_RESPONSE_TOKENS", "900")),
            retrieval_k=int(os.getenv("FORGE_RETRIEVAL_K", "4")),
            knowledge_dir=knowledge_dir,
            sessions_path=sessions_path,
            memory_path=memory_path,
            agent_run_db_path=agent_run_db_path,
            approval_db_path=approval_db_path,
            legacy_approval_state_path=legacy_approval_state_path,
            agent_worker_enabled=os.getenv("FORGE_AGENT_WORKER_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"},
            agent_worker_concurrency=max(
                1,
                int(os.getenv("FORGE_AGENT_WORKER_CONCURRENCY", "1")),
            ),
            agent_worker_poll_seconds=max(
                0.05,
                float(os.getenv("FORGE_AGENT_WORKER_POLL_SECONDS", "0.1")),
            ),
            agent_worker_lease_seconds=max(
                5.0,
                float(os.getenv("FORGE_AGENT_WORKER_LEASE_SECONDS", "30")),
            ),
            agent_worker_heartbeat_seconds=max(
                1.0,
                float(os.getenv("FORGE_AGENT_WORKER_HEARTBEAT_SECONDS", "5")),
            ),
            agent_worker_max_attempts=max(
                1,
                int(os.getenv("FORGE_AGENT_WORKER_MAX_ATTEMPTS", "3")),
            ),
            agent_worker_retry_delay_seconds=max(
                0.25,
                float(os.getenv("FORGE_AGENT_WORKER_RETRY_DELAY_SECONDS", "2")),
            ),
            workspaces_dir=workspaces_dir,
            execution_timeout_seconds=float(
                os.getenv("FORGE_EXECUTION_TIMEOUT_SECONDS", "15")
            ),
            execution_max_code_chars=int(
                os.getenv("FORGE_EXECUTION_MAX_CODE_CHARS", "12000")
            ),
            execution_max_output_chars=int(
                os.getenv("FORGE_EXECUTION_MAX_OUTPUT_CHARS", "16000")
            ),
            execution_max_files=int(os.getenv("FORGE_EXECUTION_MAX_FILES", "2048")),
            execution_max_file_bytes=int(
                os.getenv("FORGE_EXECUTION_MAX_FILE_BYTES", "1048576")
            ),
            execution_backend=os.getenv("FORGE_EXECUTION_BACKEND", "auto").lower(),
            docker_image=os.getenv("FORGE_DOCKER_IMAGE", "python:3.11-alpine"),
            docker_memory=os.getenv("FORGE_DOCKER_MEMORY", "256m"),
            docker_cpus=os.getenv("FORGE_DOCKER_CPUS", "1.0"),
            docker_pids_limit=int(os.getenv("FORGE_DOCKER_PIDS_LIMIT", "64")),
            docker_workdir=os.getenv("FORGE_DOCKER_WORKDIR", "/workspace"),
            docker_tmpfs_size=os.getenv("FORGE_DOCKER_TMPFS_SIZE", "64m"),
            docker_network_disabled=os.getenv(
                "FORGE_DOCKER_NETWORK_DISABLED", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            docker_read_only_root=os.getenv(
                "FORGE_DOCKER_READ_ONLY_ROOT", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            docker_no_new_privileges=os.getenv(
                "FORGE_DOCKER_NO_NEW_PRIVILEGES", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            docker_user=os.getenv("FORGE_DOCKER_USER", "").strip(),
            command_timeout_seconds=float(
                os.getenv("FORGE_COMMAND_TIMEOUT_SECONDS", "60")
            ),
            allowed_exec_commands=tuple(
                item.strip()
                for item in os.getenv(
                    "FORGE_ALLOWED_COMMANDS",
                    "python,python3,pytest,pip,pip3,uv,git,ls,pwd,cat,head,tail,find,grep,wc,echo",
                ).split(",")
                if item.strip()
            ),
            agent_max_command_tier=os.getenv(
                "FORGE_AGENT_MAX_COMMAND_TIER", "read_only"
            ).strip().lower(),
            agent_allow_python=os.getenv("FORGE_AGENT_ALLOW_PYTHON", "true").lower()
            in {"1", "true", "yes", "on"},
            agent_allow_shell=os.getenv("FORGE_AGENT_ALLOW_SHELL", "true").lower()
            in {"1", "true", "yes", "on"},
            agent_allow_filesystem_read=os.getenv(
                "FORGE_AGENT_ALLOW_FILESYSTEM_READ", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            agent_allow_filesystem_write=os.getenv(
                "FORGE_AGENT_ALLOW_FILESYSTEM_WRITE", "true"
            ).lower()
            in {"1", "true", "yes", "on"},
            repo_upload_max_bytes=int(
                os.getenv("FORGE_REPO_UPLOAD_MAX_BYTES", "12000000")
            ),
            repo_archive_max_entries=int(
                os.getenv("FORGE_REPO_ARCHIVE_MAX_ENTRIES", "2048")
            ),
            repo_max_total_bytes=int(
                os.getenv("FORGE_REPO_MAX_TOTAL_BYTES", "48000000")
            ),
            repo_clone_timeout_seconds=float(
                os.getenv("FORGE_REPO_CLONE_TIMEOUT_SECONDS", "180")
            ),
            repo_allowed_clone_hosts=tuple(
                item.strip().lower()
                for item in os.getenv(
                    "FORGE_REPO_ALLOWED_CLONE_HOSTS",
                    "github.com,gitlab.com,bitbucket.org",
                ).split(",")
                if item.strip()
            ),
            workspace_search_max_results=int(
                os.getenv("FORGE_WORKSPACE_SEARCH_MAX_RESULTS", "25")
            ),
            workspace_search_max_excerpt_chars=int(
                os.getenv("FORGE_WORKSPACE_SEARCH_MAX_EXCERPT_CHARS", "220")
            ),
            workspace_snapshot_max_entries=int(
                os.getenv("FORGE_WORKSPACE_SNAPSHOT_MAX_ENTRIES", "4096")
            ),
            workspace_snapshot_max_total_bytes=int(
                os.getenv("FORGE_WORKSPACE_SNAPSHOT_MAX_TOTAL_BYTES", "64000000")
            ),
            workspace_snapshot_max_snapshots=int(
                os.getenv("FORGE_WORKSPACE_SNAPSHOT_MAX_SNAPSHOTS", "20")
            ),
            fast_mode_default=os.getenv("FORGE_FAST_MODE_DEFAULT", "true").lower()
            in {"1", "true", "yes", "on"},
            enable_remote_fetch=os.getenv("FORGE_ENABLE_REMOTE_FETCH", "true").lower()
            in {"1", "true", "yes", "on"},
        )
