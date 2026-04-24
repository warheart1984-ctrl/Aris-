from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import uuid


TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "cancelled", "interrupted"}
INTERRUPTIBLE_RUN_STATUSES = {"queued", "running"}
QUEUE_READY_STATUSES = {"queued", "leased"}
QUEUE_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class AgentRunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    fast_mode INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    final_message TEXT NOT NULL DEFAULT '',
                    error_text TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    blocked_on_approval_id TEXT NOT NULL DEFAULT '',
                    blocked_on_kind TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_queue (
                    run_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    queue_status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_token TEXT NOT NULL DEFAULT '',
                    lease_expires_at TEXT NOT NULL DEFAULT '',
                    heartbeat_at TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS agent_runs_session_idx
                ON agent_runs(session_id, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS agent_run_events_run_idx
                ON agent_run_events(run_id, id ASC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS agent_run_queue_claim_idx
                ON agent_run_queue(queue_status, available_at, lease_expires_at, created_at)
                """
            )

    def interrupt_inflight_runs(self) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE agent_runs
                SET
                    status = 'interrupted',
                    error_text = CASE
                        WHEN TRIM(error_text) = '' THEN 'Run interrupted by service restart.'
                        ELSE error_text
                    END,
                    updated_at = ?,
                    completed_at = CASE
                        WHEN TRIM(completed_at) = '' THEN ?
                        ELSE completed_at
                    END
                WHERE status IN ({",".join("?" for _ in INTERRUPTIBLE_RUN_STATUSES)})
                """,
                (now, now, *sorted(INTERRUPTIBLE_RUN_STATUSES)),
            )
            return int(cursor.rowcount or 0)

    def create_run(
        self,
        *,
        session_id: str,
        kind: str,
        title: str,
        mode: str,
        user_message: str,
        fast_mode: bool,
        model: str,
        request: dict[str, object],
    ) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        run_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs(
                    id,
                    session_id,
                    kind,
                    title,
                    mode,
                    status,
                    user_message,
                    fast_mode,
                    model,
                    request_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    kind,
                    title,
                    mode,
                    user_message,
                    1 if fast_mode else 0,
                    model,
                    json.dumps(request, separators=(",", ":"), ensure_ascii=True),
                    now,
                    now,
                ),
            )
        return self.get_run(run_id) or {}

    def append_event(
        self,
        *,
        run_id: str,
        event_name: str,
        payload: dict[str, object],
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO agent_run_events(run_id, event_name, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_name,
                    json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE agent_runs
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, run_id),
            )
            return int(cursor.lastrowid or 0)

    def update_run(self, run_id: str, **fields: object) -> dict[str, object] | None:
        allowed = {
            "status",
            "final_message",
            "error_text",
            "cancel_requested",
            "blocked_on_approval_id",
            "blocked_on_kind",
            "started_at",
            "completed_at",
            "updated_at",
        }
        assignments: list[str] = []
        values: list[object] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            assignments.append(f"{key} = ?")
            values.append(value)
        if not assignments:
            return self.get_run(run_id)
        if "updated_at" not in fields:
            assignments.append("updated_at = ?")
            values.append(datetime.now(UTC).isoformat())
        values.append(run_id)
        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE agent_runs
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                values,
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            event_row = connection.execute(
                """
                SELECT id
                FROM agent_run_events
                WHERE run_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return self._row_to_run(row, last_event_id=int(event_row["id"]) if event_row else 0)

    def list_runs(self, *, session_id: str, limit: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM agent_runs
                WHERE session_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        runs: list[dict[str, object]] = []
        for row in rows:
            run = self.get_run(str(row["id"]))
            if run is not None:
                runs.append(run)
        return runs

    def list_events(
        self,
        *,
        run_id: str,
        after_id: int = 0,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_name, payload_json, created_at
                FROM agent_run_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (run_id, after_id, limit),
            ).fetchall()
        events: list[dict[str, object]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            events.append(
                {
                    "id": int(row["id"]),
                    "event": str(row["event_name"]),
                    "payload": payload,
                    "created_at": str(row["created_at"]),
                }
            )
        return events

    def get_queue_job(self, run_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_run_queue WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._row_to_queue_job(row) if row is not None else None

    def enqueue_job(
        self,
        *,
        run_id: str,
        job_type: str,
        payload: dict[str, object],
        max_attempts: int,
        delay_seconds: float = 0.0,
    ) -> dict[str, object] | None:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        available_at = (now_dt + timedelta(seconds=max(0.0, float(delay_seconds)))).isoformat()
        bounded_attempts = max(1, int(max_attempts))
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_run_queue(
                    run_id,
                    job_type,
                    payload_json,
                    queue_status,
                    attempt_count,
                    max_attempts,
                    available_at,
                    lease_owner,
                    lease_token,
                    lease_expires_at,
                    heartbeat_at,
                    last_error,
                    created_at,
                    updated_at,
                    completed_at
                )
                VALUES (?, ?, ?, 'queued', 0, ?, ?, '', '', '', '', '', ?, ?, '')
                ON CONFLICT(run_id) DO UPDATE SET
                    job_type = excluded.job_type,
                    payload_json = excluded.payload_json,
                    queue_status = 'queued',
                    attempt_count = 0,
                    max_attempts = excluded.max_attempts,
                    available_at = excluded.available_at,
                    lease_owner = '',
                    lease_token = '',
                    lease_expires_at = '',
                    heartbeat_at = '',
                    last_error = '',
                    updated_at = excluded.updated_at,
                    completed_at = ''
                """,
                (
                    run_id,
                    job_type,
                    payload_json,
                    bounded_attempts,
                    available_at,
                    now,
                    now,
                ),
            )
        return self.get_queue_job(run_id)

    def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> dict[str, object] | None:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        lease_expires_at = (now_dt + timedelta(seconds=max(1.0, float(lease_seconds)))).isoformat()
        lease_token = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM agent_run_queue
                WHERE
                    (queue_status = 'queued' AND available_at <= ?)
                    OR
                    (queue_status = 'leased' AND TRIM(lease_expires_at) <> '' AND lease_expires_at <= ?)
                ORDER BY available_at ASC, created_at ASC
                LIMIT 1
                """,
                (now, now),
            ).fetchone()
            if row is None:
                return None
            run_id = str(row["run_id"])
            cursor = connection.execute(
                """
                UPDATE agent_run_queue
                SET
                    queue_status = 'leased',
                    attempt_count = attempt_count + 1,
                    lease_owner = ?,
                    lease_token = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    updated_at = ?,
                    last_error = ''
                WHERE run_id = ?
                  AND (
                    (queue_status = 'queued' AND available_at <= ?)
                    OR
                    (queue_status = 'leased' AND TRIM(lease_expires_at) <> '' AND lease_expires_at <= ?)
                  )
                """,
                (
                    worker_id,
                    lease_token,
                    lease_expires_at,
                    now,
                    now,
                    run_id,
                    now,
                    now,
                ),
            )
            if int(cursor.rowcount or 0) != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM agent_run_queue WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._row_to_queue_job(claimed) if claimed is not None else None

    def heartbeat_job(
        self,
        *,
        run_id: str,
        lease_token: str,
        lease_seconds: float,
    ) -> bool:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        lease_expires_at = (now_dt + timedelta(seconds=max(1.0, float(lease_seconds)))).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_run_queue
                SET
                    heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE run_id = ?
                  AND lease_token = ?
                  AND queue_status = 'leased'
                """,
                (now, lease_expires_at, now, run_id, lease_token),
            )
            return int(cursor.rowcount or 0) == 1

    def complete_job(
        self,
        *,
        run_id: str,
        lease_token: str,
        queue_status: str = "completed",
        error_text: str = "",
    ) -> dict[str, object] | None:
        status = str(queue_status).strip().lower()
        if status not in QUEUE_TERMINAL_STATUSES:
            status = "completed"
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE agent_run_queue
                SET
                    queue_status = ?,
                    lease_owner = '',
                    lease_token = '',
                    lease_expires_at = '',
                    heartbeat_at = '',
                    last_error = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE run_id = ?
                  AND lease_token = ?
                """,
                (status, error_text.strip(), now, now, run_id, lease_token),
            )
        return self.get_queue_job(run_id)

    def release_job_for_retry(
        self,
        *,
        run_id: str,
        lease_token: str,
        delay_seconds: float,
        error_text: str,
    ) -> dict[str, object] | None:
        job = self.get_queue_job(run_id)
        if job is None or str(job.get("lease_token", "")).strip() != lease_token:
            return None
        attempt_count = int(job.get("attempt_count", 0) or 0)
        max_attempts = int(job.get("max_attempts", 1) or 1)
        if attempt_count >= max_attempts:
            return self.complete_job(
                run_id=run_id,
                lease_token=lease_token,
                queue_status="failed",
                error_text=error_text,
            )
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        available_at = (now_dt + timedelta(seconds=max(0.0, float(delay_seconds)))).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE agent_run_queue
                SET
                    queue_status = 'queued',
                    lease_owner = '',
                    lease_token = '',
                    lease_expires_at = '',
                    heartbeat_at = '',
                    last_error = ?,
                    available_at = ?,
                    updated_at = ?,
                    completed_at = ''
                WHERE run_id = ?
                  AND lease_token = ?
                """,
                (error_text.strip(), available_at, now, run_id, lease_token),
            )
        return self.get_queue_job(run_id)

    def requeue_leased_jobs(self) -> list[dict[str, object]]:
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM agent_run_queue
                WHERE queue_status = 'leased'
                ORDER BY created_at ASC
                """
            ).fetchall()
            connection.execute(
                """
                UPDATE agent_run_queue
                SET
                    queue_status = 'queued',
                    lease_owner = '',
                    lease_token = '',
                    lease_expires_at = '',
                    heartbeat_at = '',
                    available_at = ?,
                    updated_at = ?
                WHERE queue_status = 'leased'
                """,
                (now, now),
            )
        return [self._row_to_queue_job(row) for row in rows]

    def request_cancel(self, run_id: str) -> dict[str, object] | None:
        return self.update_run(run_id, cancel_requested=1)

    def cancel_requested(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        return bool(run and run.get("cancel_requested"))

    def _row_to_run(self, row: sqlite3.Row, *, last_event_id: int) -> dict[str, object]:
        try:
            request = json.loads(str(row["request_json"]))
        except json.JSONDecodeError:
            request = {}
        if not isinstance(request, dict):
            request = {}
        return {
            "id": str(row["id"]),
            "session_id": str(row["session_id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "mode": str(row["mode"]),
            "status": str(row["status"]),
            "user_message": str(row["user_message"]),
            "fast_mode": bool(row["fast_mode"]),
            "model": str(row["model"]),
            "request": request,
            "final_message": str(row["final_message"]),
            "error_text": str(row["error_text"]),
            "cancel_requested": bool(row["cancel_requested"]),
            "blocked_on_approval_id": str(row["blocked_on_approval_id"]),
            "blocked_on_kind": str(row["blocked_on_kind"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "started_at": str(row["started_at"]),
            "completed_at": str(row["completed_at"]),
            "last_event_id": last_event_id,
            "terminal": str(row["status"]) in TERMINAL_RUN_STATUSES,
        }

    def _row_to_queue_job(self, row: sqlite3.Row) -> dict[str, object]:
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "run_id": str(row["run_id"]),
            "job_type": str(row["job_type"]),
            "payload": payload,
            "queue_status": str(row["queue_status"]),
            "attempt_count": int(row["attempt_count"]),
            "max_attempts": int(row["max_attempts"]),
            "available_at": str(row["available_at"]),
            "lease_owner": str(row["lease_owner"]),
            "lease_token": str(row["lease_token"]),
            "lease_expires_at": str(row["lease_expires_at"]),
            "heartbeat_at": str(row["heartbeat_at"]),
            "last_error": str(row["last_error"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "completed_at": str(row["completed_at"]),
            "terminal": str(row["queue_status"]) in QUEUE_TERMINAL_STATUSES,
        }
