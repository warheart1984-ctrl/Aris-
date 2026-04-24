from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3


SNAPSHOT_BUCKETS = (
    "command_approvals",
    "command_resume_states",
    "patch_resume_states",
)


class ApprovalStateDatabase:
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
                CREATE TABLE IF NOT EXISTS approval_snapshot (
                    bucket TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS approval_audit_session_idx
                ON approval_audit_log(session_id, id DESC)
                """
            )

    def has_snapshot_data(self) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM approval_snapshot LIMIT 1"
            ).fetchone()
        return row is not None

    def load_snapshot(self) -> dict[str, list[dict[str, object]]]:
        snapshot = {bucket: [] for bucket in SNAPSHOT_BUCKETS}
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT bucket, payload_json FROM approval_snapshot"
            ).fetchall()
        for row in rows:
            bucket = str(row["bucket"])
            if bucket not in snapshot:
                continue
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, list):
                snapshot[bucket] = [item for item in payload if isinstance(item, dict)]
        return snapshot

    def save_snapshot(
        self,
        *,
        snapshot: dict[str, list[dict[str, object]]],
        updated_at: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM approval_snapshot")
            for bucket in SNAPSHOT_BUCKETS:
                payload = snapshot.get(bucket, [])
                if not payload:
                    continue
                connection.execute(
                    """
                    INSERT INTO approval_snapshot(bucket, payload_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        bucket,
                        json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
                        updated_at,
                    ),
                )

    def append_audit(
        self,
        *,
        session_id: str,
        approval_id: str,
        kind: str,
        action: str,
        created_at: str,
        details: dict[str, object],
    ) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO approval_audit_log(
                    session_id,
                    approval_id,
                    kind,
                    action,
                    created_at,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    approval_id,
                    kind,
                    action,
                    created_at,
                    json.dumps(details, separators=(",", ":"), ensure_ascii=True),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_audit(self, *, session_id: str, limit: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, approval_id, kind, action, created_at, details_json
                FROM approval_audit_log
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        entries: list[dict[str, object]] = []
        for row in rows:
            try:
                details = json.loads(str(row["details_json"]))
            except json.JSONDecodeError:
                details = {}
            if not isinstance(details, dict):
                details = {}
            entries.append(
                {
                    "id": int(row["id"]),
                    "session_id": str(row["session_id"]),
                    "approval_id": str(row["approval_id"]),
                    "kind": str(row["kind"]),
                    "action": str(row["action"]),
                    "created_at": str(row["created_at"]),
                    "details": details,
                }
            )
        return entries

    def migrate_legacy_snapshot(self, legacy_path: Path) -> bool:
        if self.has_snapshot_data() or not legacy_path.exists():
            return False
        try:
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        snapshot = {
            bucket: [
                item
                for item in payload.get(bucket, [])
                if isinstance(item, dict)
            ]
            for bucket in SNAPSHOT_BUCKETS
        }
        self.save_snapshot(
            snapshot=snapshot,
            updated_at=str(payload.get("migrated_at", "")).strip()
            or datetime.now(UTC).isoformat(),
        )
        try:
            legacy_path.unlink()
        except OSError:
            pass
        return True
