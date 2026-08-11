"""SQLite-backed TaskRepository implementation (M4A).

Thread-safe connection strategy: each operation opens an independent
connection with ``foreign_keys``, ``busy_timeout`` and (optionally) WAL
enabled.  Writes are wrapped in explicit transactions; reads rely on WAL
for concurrent access.  No connection is shared across threads.

Restart recovery:
    ``mark_interrupted_tasks()`` marks any pending/running tasks as failed
    with ``error_message = "interrupted_by_service_restart"``.  This is
    called once at application startup.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from springfix_agent.storage.models import Report, Task, TaskStatus, Trace

_LOGGER = logging.getLogger(__name__)

_VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "running", "completed", "failed"}
)

_MAX_TRACE_SAVE_RETRIES: Final[int] = 5


class StorageError(RuntimeError):
    """Raised when a SQLite operation fails due to locking or I/O."""


class TaskNotFoundError(KeyError):
    """Raised when a task_id is unknown to the repository."""


def _iso(dt: datetime) -> str:
    """Serialize a datetime to ISO-8601 with timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _parse_iso(text: str) -> datetime:
    """Parse an ISO-8601 string back to a timezone-aware datetime."""
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _json_dumps(obj: object) -> str:
    """Deterministic JSON serialization with UTF-8 support."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _json_loads(text: str) -> dict[str, object]:
    """Parse JSON text, enforcing dict result."""
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError(f"expected JSON object, got {type(result).__name__}")
    return result


class SqliteTaskRepository:
    """SQLite-backed TaskRepository.

    Each public method opens a fresh connection, performs the operation,
    and closes the connection.  This ensures thread safety without
    requiring an explicit lock at the Python level.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        wal_enabled: bool = True,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self._db_path = Path(db_path).resolve()
        self._wal_enabled = wal_enabled
        self._busy_timeout_ms = busy_timeout_ms

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection with PRAGMAs applied."""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=self._busy_timeout_ms / 1000.0,
            isolation_level=None,
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        if self._wal_enabled:
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def create_task(
        self,
        repository_path: str,
        issue_description: str,
        error_log: str | None,
    ) -> Task:
        task_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        now_iso = _iso(now)
        task = Task(
            task_id=task_id,
            repository_path=repository_path,
            issue_description=issue_description,
            error_log=error_log,
            status="pending",
            submitted_at=now,
            started_at=None,
            finished_at=None,
            current_node=None,
            error_message=None,
        )
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """INSERT INTO tasks
                   (task_id, repository_path, issue_description, error_log,
                    status, current_node, created_at, started_at, finished_at,
                    error_message, created_timestamp, updated_timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    repository_path,
                    issue_description,
                    error_log,
                    "pending",
                    None,
                    now_iso,
                    None,
                    None,
                    None,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                raise StorageError(f"database locked during create_task: {e}") from e
            raise
        finally:
            conn.close()
        return task

    def get_task(self, task_id: str) -> Task | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT task_id, repository_path, issue_description, error_log,
                          status, current_node, created_at, started_at, finished_at,
                          error_message
                   FROM tasks WHERE task_id = ?""",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_tasks(self) -> list[Task]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT task_id, repository_path, issue_description, error_log,
                          status, current_node, created_at, started_at, finished_at,
                          error_message
                   FROM tasks ORDER BY created_at DESC"""
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_task(r) for r in rows]

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_node: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid status: {status!r}")
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT started_at, finished_at FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is None:
                raise TaskNotFoundError(task_id)

            now_iso = _iso(datetime.now(tz=UTC))
            sets: list[str] = ["status = ?", "updated_timestamp = ?"]
            params: list[object] = [status, now_iso]

            if status == "running" and existing[0] is None:
                sets.append("started_at = ?")
                params.append(now_iso)
            if status in {"completed", "failed"} and existing[1] is None:
                sets.append("finished_at = ?")
                params.append(now_iso)
            if current_node is not None:
                sets.append("current_node = ?")
                params.append(current_node)
            if error_message is not None:
                sets.append("error_message = ?")
                params.append(error_message)

            params.append(task_id)
            sql = f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?"
            try:
                conn.execute("BEGIN")
                conn.execute(sql, params)
                conn.commit()
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    raise StorageError(
                        f"database locked during update_status: {e}"
                    ) from e
                raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Trace operations
    # ------------------------------------------------------------------

    def save_trace(self, task_id: str, trace: Trace) -> None:
        payload = trace.payload
        node_name = str(payload.get("node", "")) or None
        start_time = payload.get("start")
        end_time = payload.get("end")
        raw_duration = payload.get("duration_ms")
        duration_val: int | None = None
        if raw_duration is not None:
            try:
                duration_val = int(raw_duration)  # type: ignore[call-overload]
            except (ValueError, TypeError):
                duration_val = None
        trace_status = payload.get("status")
        error_msg = payload.get("error") or payload.get("error_message")
        error_str: str | None = None
        if error_msg is not None:
            error_str = str(error_msg)[:500]

        payload_json = _json_dumps(payload)
        created_at = _iso(trace.recorded_at)

        conn = self._connect()
        try:
            # Verify task exists
            exists = conn.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if exists is None:
                raise TaskNotFoundError(task_id)

            for attempt in range(_MAX_TRACE_SAVE_RETRIES):
                row = conn.execute(
                    "SELECT COALESCE(MAX(sequence_number), -1) FROM traces WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                seq = int(row[0]) + 1
                try:
                    conn.execute("BEGIN")
                    conn.execute(
                        """INSERT INTO traces
                           (task_id, kind, node_name, sequence_number,
                            start_time, end_time, duration_ms, status,
                            payload_json, error_message, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            task_id,
                            trace.kind,
                            node_name,
                            seq,
                            str(start_time) if start_time else None,
                            str(end_time) if end_time else None,
                            duration_val,
                            str(trace_status) if trace_status else None,
                            payload_json,
                            error_str,
                            created_at,
                        ),
                    )
                    conn.commit()
                    break
                except sqlite3.IntegrityError:
                    conn.rollback()
                    if attempt == _MAX_TRACE_SAVE_RETRIES - 1:
                        raise
                    continue
                except sqlite3.OperationalError as e:
                    conn.rollback()
                    if "locked" in str(e).lower() or "busy" in str(e).lower():
                        raise StorageError(
                            f"database locked during save_trace: {e}"
                        ) from e
                    raise
        finally:
            conn.close()

    def get_traces(self, task_id: str) -> list[Trace]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT kind, payload_json, created_at
                   FROM traces WHERE task_id = ?
                   ORDER BY sequence_number ASC""",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()
        result: list[Trace] = []
        for row in rows:
            kind_str = str(row[0])
            payload = _json_loads(str(row[1]))
            recorded_at = _parse_iso(str(row[2]))
            result.append(
                Trace(
                    task_id=task_id,
                    kind=kind_str,  # type: ignore[arg-type]
                    recorded_at=recorded_at,
                    payload=payload,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Report operations
    # ------------------------------------------------------------------

    def save_report(self, task_id: str, report: Report) -> None:
        conn = self._connect()
        try:
            exists = conn.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if exists is None:
                raise TaskNotFoundError(task_id)

            json_report_text = _json_dumps(report.json_report)
            markdown_text = report.markdown_report
            created_iso = _iso(report.created_at)
            now_iso = _iso(datetime.now(tz=UTC))

            diagnosis_status = str(
                report.json_report.get("diagnosis_status", "")
            ) or None

            try:
                conn.execute("BEGIN")
                existing = conn.execute(
                    "SELECT created_at FROM reports WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """INSERT INTO reports
                           (task_id, diagnosis_status, json_report,
                            markdown_report, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            task_id,
                            diagnosis_status,
                            json_report_text,
                            markdown_text,
                            created_iso,
                            now_iso,
                        ),
                    )
                else:
                    conn.execute(
                        """UPDATE reports
                           SET diagnosis_status = ?,
                               json_report = ?,
                               markdown_report = ?,
                               updated_at = ?
                           WHERE task_id = ?""",
                        (
                            diagnosis_status,
                            json_report_text,
                            markdown_text,
                            now_iso,
                            task_id,
                        ),
                    )
                conn.commit()
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    raise StorageError(
                        f"database locked during save_report: {e}"
                    ) from e
                raise
        finally:
            conn.close()

    def get_report(self, task_id: str) -> Report | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT task_id, json_report, markdown_report, created_at
                   FROM reports WHERE task_id = ?""",
                (task_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        json_report = _json_loads(str(row[1]))
        return Report(
            task_id=str(row[0]),
            json_report=json_report,
            markdown_report=str(row[2]),
            created_at=_parse_iso(str(row[3])),
        )

    # ------------------------------------------------------------------
    # Restart recovery
    # ------------------------------------------------------------------

    def mark_interrupted_tasks(self) -> int:
        """Mark pending/running tasks as failed after a service restart.

        Returns the number of tasks marked as interrupted.
        Idempotent: calling twice has no additional effect because it only
        targets tasks with status IN ('pending', 'running').
        """
        now_iso = _iso(datetime.now(tz=UTC))
        conn = self._connect()
        try:
            interrupted_rows = conn.execute(
                """SELECT task_id, current_node
                   FROM tasks
                   WHERE status IN ('pending', 'running')""",
            ).fetchall()
            if not interrupted_rows:
                return 0

            count = 0
            conn.execute("BEGIN")
            try:
                for row in interrupted_rows:
                    tid = str(row[0])
                    original_node = str(row[1]) if row[1] else None
                    node = original_node or "interrupted"
                    conn.execute(
                        """UPDATE tasks
                           SET status = 'failed',
                               current_node = ?,
                               finished_at = ?,
                               error_message = 'interrupted_by_service_restart',
                               updated_timestamp = ?
                           WHERE task_id = ?""",
                        (node, now_iso, now_iso, tid),
                    )
                    # Add a recovery trace
                    recovery_payload = _json_dumps(
                        {"reason": "interrupted_by_service_restart", "original_node": original_node}
                    )
                    seq_row = conn.execute(
                        "SELECT COALESCE(MAX(sequence_number), -1) FROM traces WHERE task_id = ?",
                        (tid,),
                    ).fetchone()
                    seq = int(seq_row[0]) + 1
                    conn.execute(
                        """INSERT INTO traces
                           (task_id, kind, node_name, sequence_number,
                            payload_json, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            tid,
                            "system_recovery",
                            "interrupted",
                            seq,
                            recovery_payload,
                            now_iso,
                        ),
                    )
                    count += 1
                    _LOGGER.info(
                        "marked task %s as interrupted (was pending/running)", tid
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_task(row: tuple[object, ...]) -> Task:
        """Convert a database row to a Task domain model."""
        status_str = str(row[4])
        if status_str not in _VALID_STATUSES:
            raise ValueError(f"invalid task status in database: {status_str!r}")
        status: TaskStatus = status_str  # type: ignore[assignment]

        started_at: datetime | None = None
        if row[7] is not None:
            started_at = _parse_iso(str(row[7]))
        finished_at: datetime | None = None
        if row[8] is not None:
            finished_at = _parse_iso(str(row[8]))

        error_log: str | None = None
        if row[3] is not None:
            error_log = str(row[3])
        current_node: str | None = None
        if row[5] is not None:
            current_node = str(row[5])
        error_message: str | None = None
        if row[9] is not None:
            error_message = str(row[9])

        return Task(
            task_id=str(row[0]),
            repository_path=str(row[1]),
            issue_description=str(row[2]),
            error_log=error_log,
            status=status,
            submitted_at=_parse_iso(str(row[6])),
            started_at=started_at,
            finished_at=finished_at,
            current_node=current_node,
            error_message=error_message,
        )
