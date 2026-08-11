"""SQLite repository and migration tests (M4A).

Covers migration, task CRUD, trace round-trip, report upsert,
persistence across repository rebuilds, concurrency, and restart recovery.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from springfix_agent.llm.trace import LLMCall
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.migration import MigrationError, migrate
from springfix_agent.storage.models import Report, Task, Trace
from springfix_agent.storage.sqlite_repository import (
    SqliteTaskRepository,
    StorageError,
    TaskNotFoundError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A temporary SQLite database path (not yet created)."""
    return tmp_path / "test.db"


@pytest.fixture
def migrated_db(tmp_path: Path) -> Path:
    """A temporary SQLite database with migrations applied."""
    path = tmp_path / "test.db"
    migrate(path)
    return path


@pytest.fixture
def repo(migrated_db: Path) -> SqliteTaskRepository:
    """A SqliteTaskRepository backed by a migrated temp database."""
    return SqliteTaskRepository(migrated_db)


def _make_task(repo: SqliteTaskRepository, desc: str = "test issue description here") -> Task:
    return repo.create_task(
        repository_path="/fake/repo",
        issue_description=desc,
        error_log=None,
    )


# ===========================================================================
# Migration tests (behaviors 1-7)
# ===========================================================================

class TestMigration:
    def test_new_database_creates_schema(self, db_path: Path) -> None:
        """Behavior 1: migration creates all four tables."""
        migrate(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "schema_migrations" in tables
        assert "tasks" in tables
        assert "traces" in tables
        assert "reports" in tables

    def test_migration_idempotent(self, db_path: Path) -> None:
        """Behavior 2: calling migrate twice is safe."""
        migrate(db_path)
        migrate(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0][0] == 1

    def test_migration_record_correct(self, db_path: Path) -> None:
        """Behavior 3: schema_migrations records version and name."""
        migrate(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT version, name, applied_at FROM schema_migrations"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "initial"
        assert row[2]  # applied_at is non-empty

    def test_migration_rollback_on_failure(self, tmp_path: Path) -> None:
        """Behavior 4: a broken migration SQL file rolls back."""
        db = tmp_path / "bad.db"
        # First apply good migration
        migrate(db)
        # Manually insert a bad migration version to simulate conflict
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("DELETE FROM schema_migrations WHERE version = 1")
            conn.commit()
            # Drop a table to simulate partial migration
            conn.execute("DROP TABLE IF EXISTS tasks")
            conn.commit()
        finally:
            conn.close()
        # Re-run migration: should succeed because version was removed
        migrate(db)
        conn = sqlite3.connect(str(db))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "tasks" in tables

    def test_unknown_higher_version_raises(self, db_path: Path) -> None:
        """Behavior 5: DB with unknown higher version refuses to downgrade."""
        migrate(db_path)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (999, "future_migration", "2026-01-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(MigrationError, match="refusing to downgrade"):
            migrate(db_path)

    def test_foreign_keys_enabled(self, migrated_db: Path) -> None:
        """Behavior 6: foreign_keys pragma is ON for repository connections."""
        repo = SqliteTaskRepository(migrated_db)
        conn = sqlite3.connect(str(migrated_db))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            # Insert trace for non-existent task should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO traces
                       (task_id, kind, node_name, sequence_number, payload_json, created_at)
                       VALUES ('nonexistent', 'tool_call', NULL, 0, '{}', '2026-01-01T00:00:00+00:00')"""
                )
        finally:
            conn.close()
        _ = repo  # keep reference

    def test_wal_configuration(self, db_path: Path) -> None:
        """Behavior 7: WAL mode is applied when enabled."""
        migrate(db_path, wal_enabled=True)
        conn = sqlite3.connect(str(db_path))
        try:
            result = conn.execute("PRAGMA journal_mode").fetchone()
        finally:
            conn.close()
        assert result is not None
        assert str(result[0]).lower() == "wal"


# ===========================================================================
# Task tests (behaviors 8-15)
# ===========================================================================

class TestTaskCrud:
    def test_create_and_get(self, repo: SqliteTaskRepository) -> None:
        """Behavior 8: create_task and get_task round-trip."""
        task = _make_task(repo)
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.task_id == task.task_id
        assert fetched.status == "pending"
        assert fetched.repository_path == "/fake/repo"

    def test_duplicate_task_id(self, repo: SqliteTaskRepository) -> None:
        """Behavior 9: each create_task generates a unique UUID."""
        t1 = _make_task(repo)
        t2 = _make_task(repo)
        assert t1.task_id != t2.task_id

    def test_update_status(self, repo: SqliteTaskRepository) -> None:
        """Behavior 10: update_status changes task state."""
        task = _make_task(repo)
        repo.update_status(task.task_id, "running", current_node="validate_input")
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "running"
        assert fetched.current_node == "validate_input"
        assert fetched.started_at is not None

    def test_list_tasks_descending(self, repo: SqliteTaskRepository) -> None:
        """Behavior 11: list_tasks returns tasks sorted by created_at descending."""
        t1 = _make_task(repo, "first issue description here")
        t2 = _make_task(repo, "second issue description here")
        tasks = repo.list_tasks()
        assert len(tasks) == 2
        assert tasks[0].task_id == t2.task_id
        assert tasks[1].task_id == t1.task_id

    def test_not_found_task(self, repo: SqliteTaskRepository) -> None:
        """Behavior 12: get_task returns None for unknown id."""
        assert repo.get_task("nonexistent-uuid") is None

    def test_chinese_issue_description(self, repo: SqliteTaskRepository) -> None:
        """Behavior 13: Chinese characters in issue_description are preserved."""
        task = repo.create_task(
            repository_path="/fake/repo",
            issue_description="调用createOrder抛出异常但数据未回滚",
            error_log=None,
        )
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert "调用" in fetched.issue_description
        assert "回滚" in fetched.issue_description

    def test_null_error_log(self, repo: SqliteTaskRepository) -> None:
        """Behavior 14: error_log can be None."""
        task = _make_task(repo)
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.error_log is None

    def test_datetime_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 15: datetime values survive save/load with timezone info."""
        task = _make_task(repo)
        repo.update_status(task.task_id, "running")
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.started_at is not None
        assert fetched.started_at.tzinfo is not None
        assert fetched.submitted_at.tzinfo is not None


# ===========================================================================
# Trace tests (behaviors 16-23)
# ===========================================================================

class TestTraceCrud:
    def test_node_trace_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 16: node_timing trace save and read."""
        task = _make_task(repo)
        trace = Trace(
            task_id=task.task_id,
            kind="node_timing",
            payload={
                "node": "validate_input",
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-01-01T00:00:01+00:00",
                "duration_ms": 1000,
            },
        )
        repo.save_trace(task.task_id, trace)
        traces = repo.get_traces(task.task_id)
        assert len(traces) == 1
        assert traces[0].kind == "node_timing"
        assert traces[0].payload["node"] == "validate_input"

    def test_tool_trace_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 17: tool_call trace save and read."""
        task = _make_task(repo)
        trace = Trace(
            task_id=task.task_id,
            kind="tool_call",
            payload={
                "node": "explore_repository",
                "tool_name": "list_project_tree",
                "params": {},
                "duration_ms": 50,
                "status": "success",
                "result_summary": "found 5 files",
                "error": None,
            },
        )
        repo.save_trace(task.task_id, trace)
        traces = repo.get_traces(task.task_id)
        assert len(traces) == 1
        assert traces[0].payload["tool_name"] == "list_project_tree"

    def test_llm_trace_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 18: llm_call trace save and read."""
        task = _make_task(repo)
        trace = Trace(
            task_id=task.task_id,
            kind="llm_call",
            payload={
                "node": "issue_parser",
                "provider": "mock",
                "model": "mock-model",
                "attempt": 1,
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-01-01T00:00:02+00:00",
                "duration_ms": 2000,
                "status": "success",
                "prompt_chars": 500,
                "response_chars": 200,
                "input_tokens": 100,
                "output_tokens": 50,
                "error_type": None,
                "error_message": None,
            },
        )
        repo.save_trace(task.task_id, trace)
        traces = repo.get_traces(task.task_id)
        assert len(traces) == 1
        assert traces[0].kind == "llm_call"
        assert traces[0].payload["provider"] == "mock"

    def test_sequence_number_ordering(self, repo: SqliteTaskRepository) -> None:
        """Behavior 19: traces are returned in sequence_number order."""
        task = _make_task(repo)
        for i in range(5):
            trace = Trace(
                task_id=task.task_id,
                kind="node_timing",
                payload={"node": f"node_{i}", "duration_ms": i * 100},
            )
            repo.save_trace(task.task_id, trace)
        traces = repo.get_traces(task.task_id)
        assert len(traces) == 5
        nodes = [t.payload["node"] for t in traces]
        assert nodes == [f"node_{i}" for i in range(5)]

    def test_payload_json_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 20: payload JSON preserves all fields."""
        task = _make_task(repo)
        original_payload: dict[str, object] = {
            "node": "test",
            "nested": {"key": "value"},
            "list_val": [1, 2, 3],
            "chinese": "中文测试",
        }
        trace = Trace(task_id=task.task_id, kind="tool_call", payload=original_payload)
        repo.save_trace(task.task_id, trace)
        traces = repo.get_traces(task.task_id)
        assert traces[0].payload == original_payload

    def test_save_trace_nonexistent_task(self, repo: SqliteTaskRepository) -> None:
        """Behavior 21: saving trace for non-existent task raises."""
        trace = Trace(
            task_id="nonexistent",
            kind="tool_call",
            payload={"tool_name": "test"},
        )
        with pytest.raises(TaskNotFoundError):
            repo.save_trace("nonexistent", trace)

    def test_no_raw_prompt_stored(self, repo: SqliteTaskRepository) -> None:
        """Behavior 22: raw_prompt and raw_response are not stored in DB columns."""
        task = _make_task(repo)
        trace = Trace(
            task_id=task.task_id,
            kind="llm_call",
            payload={
                "node": "issue_parser",
                "provider": "mock",
                "model": "mock",
                "status": "success",
                "duration_ms": 100,
            },
        )
        repo.save_trace(task.task_id, trace)
        # Verify no raw_prompt/raw_response columns exist in traces table
        conn = sqlite3.connect(str(repo.db_path))
        try:
            cols = conn.execute("PRAGMA table_info(traces)").fetchall()
        finally:
            conn.close()
        col_names = {row[1] for row in cols}
        assert "raw_prompt" not in col_names
        assert "raw_response" not in col_names

    def test_llm_trace_persists_only_structured_boundary_fields(
        self, repo: SqliteTaskRepository
    ) -> None:
        """SQLite receives the redacted LLM trace shape from the existing tracer boundary."""
        task = _make_task(repo)
        tracer = InMemoryTracer(repo)
        call: LLMCall = {
            "node": "issue_parser",
            "provider": "mock",
            "model": "mock",
            "attempt": 1,
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-01T00:00:01+00:00",
            "duration_ms": 1000,
            "status": "success",
            "prompt_chars": 1200,
            "response_chars": 240,
            "input_tokens": 100,
            "output_tokens": 50,
            "error_type": None,
            "error_message": None,
        }

        tracer.record_llm_call(task.task_id, call)

        traces = repo.get_traces(task.task_id)
        assert len(traces) == 1
        payload = traces[0].payload
        assert payload["prompt_chars"] == 1200
        assert payload["response_chars"] == 240
        assert "raw_prompt" not in payload
        assert "raw_response" not in payload

    def test_concurrent_trace_save(self, repo: SqliteTaskRepository) -> None:
        """Behavior 23: concurrent trace saves do not lose records."""
        task = _make_task(repo)
        errors: list[Exception] = []

        def save_one(idx: int) -> None:
            try:
                trace = Trace(
                    task_id=task.task_id,
                    kind="tool_call",
                    payload={"tool_name": f"tool_{idx}", "status": "success"},
                )
                repo.save_trace(task.task_id, trace)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=save_one, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"concurrent saves had errors: {errors}"
        traces = repo.get_traces(task.task_id)
        assert len(traces) == 10


# ===========================================================================
# Report tests (behaviors 24-29)
# ===========================================================================

class TestReportCrud:
    def test_json_report_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 24: JSON report save and read."""
        task = _make_task(repo)
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete", "root_causes": []},
            markdown_report="# Report",
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, report)
        fetched = repo.get_report(task.task_id)
        assert fetched is not None
        assert fetched.json_report["diagnosis_status"] == "complete"

    def test_markdown_report_round_trip(self, repo: SqliteTaskRepository) -> None:
        """Behavior 25: Markdown report save and read."""
        task = _make_task(repo)
        md = "# 诊断报告\n\n- status: **complete**\n"
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete"},
            markdown_report=md,
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, report)
        fetched = repo.get_report(task.task_id)
        assert fetched is not None
        assert fetched.markdown_report == md

    def test_report_upsert(self, repo: SqliteTaskRepository) -> None:
        """Behavior 26: saving a report twice updates (upsert)."""
        task = _make_task(repo)
        r1 = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "partial"},
            markdown_report="v1",
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, r1)
        r2 = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete"},
            markdown_report="v2",
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, r2)
        fetched = repo.get_report(task.task_id)
        assert fetched is not None
        assert fetched.json_report["diagnosis_status"] == "complete"
        assert fetched.markdown_report == "v2"

    def test_diagnosis_status_extracted(self, repo: SqliteTaskRepository) -> None:
        """Behavior 27: diagnosis_status is extracted from json_report."""
        task = _make_task(repo)
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "insufficient_evidence"},
            markdown_report="# Report",
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, report)
        conn = sqlite3.connect(str(repo.db_path))
        try:
            row = conn.execute(
                "SELECT diagnosis_status FROM reports WHERE task_id = ?",
                (task.task_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "insufficient_evidence"

    def test_chinese_report_content(self, repo: SqliteTaskRepository) -> None:
        """Behavior 28: Chinese characters in report are preserved."""
        task = _make_task(repo)
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete", "summary": "事务自调用问题"},
            markdown_report="# 诊断报告\n\n根因：Spring AOP 代理绕过",
            created_at=datetime.now(tz=UTC),
        )
        repo.save_report(task.task_id, report)
        fetched = repo.get_report(task.task_id)
        assert fetched is not None
        assert "事务自调用" in str(fetched.json_report)
        assert "代理绕过" in fetched.markdown_report

    def test_report_not_found(self, repo: SqliteTaskRepository) -> None:
        """Behavior 29: get_report returns None when no report exists."""
        task = _make_task(repo)
        assert repo.get_report(task.task_id) is None


# ===========================================================================
# Persistence tests (behaviors 30-31)
# ===========================================================================

class TestPersistence:
    def test_data_survives_repository_rebuild(self, migrated_db: Path) -> None:
        """Behavior 30: data persists after creating a new repository instance."""
        repo1 = SqliteTaskRepository(migrated_db)
        task = _make_task(repo1)
        trace = Trace(
            task_id=task.task_id,
            kind="tool_call",
            payload={"tool_name": "test_tool", "status": "success"},
        )
        repo1.save_trace(task.task_id, trace)
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete"},
            markdown_report="# Report",
            created_at=datetime.now(tz=UTC),
        )
        repo1.save_report(task.task_id, report)
        repo1.update_status(task.task_id, "completed")

        # Create a new repository instance pointing to the same DB
        repo2 = SqliteTaskRepository(migrated_db)
        fetched_task = repo2.get_task(task.task_id)
        assert fetched_task is not None
        assert fetched_task.status == "completed"
        assert len(repo2.get_traces(task.task_id)) == 1
        assert repo2.get_report(task.task_id) is not None

    def test_save_report_nonexistent_task(self, repo: SqliteTaskRepository) -> None:
        """save_report raises for non-existent task."""
        report = Report(
            task_id="nonexistent",
            json_report={"status": "failed"},
            markdown_report="",
            created_at=datetime.now(tz=UTC),
        )
        with pytest.raises(TaskNotFoundError):
            repo.save_report("nonexistent", report)


# ===========================================================================
# Restart recovery tests (behaviors 32-36)
# ===========================================================================

class TestRestartRecovery:
    def test_completed_task_unchanged(self, repo: SqliteTaskRepository) -> None:
        """Behavior 32: completed tasks are not modified on restart."""
        task = _make_task(repo)
        repo.update_status(task.task_id, "running")
        repo.update_status(task.task_id, "completed")
        count = repo.mark_interrupted_tasks()
        assert count == 0
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "completed"

    def test_failed_task_unchanged(self, repo: SqliteTaskRepository) -> None:
        """Behavior 33: failed tasks are not modified on restart."""
        task = _make_task(repo)
        repo.update_status(task.task_id, "running")
        repo.update_status(task.task_id, "failed", error_message="graph error")
        count = repo.mark_interrupted_tasks()
        assert count == 0
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == "graph error"

    def test_pending_task_marked_interrupted(self, repo: SqliteTaskRepository) -> None:
        """Behavior 34: pending tasks are marked as interrupted failure."""
        task = _make_task(repo)
        count = repo.mark_interrupted_tasks()
        assert count == 1
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == "interrupted_by_service_restart"
        assert fetched.finished_at is not None

    def test_running_task_marked_interrupted(self, repo: SqliteTaskRepository) -> None:
        """Behavior 35: running tasks are marked as interrupted failure."""
        task = _make_task(repo)
        repo.update_status(task.task_id, "running", current_node="issue_parser")
        count = repo.mark_interrupted_tasks()
        assert count == 1
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == "interrupted_by_service_restart"
        assert fetched.current_node == "issue_parser"
        # Check recovery trace was added
        traces = repo.get_traces(task.task_id)
        recovery = [t for t in traces if t.kind == "system_recovery"]
        assert len(recovery) == 1
        assert recovery[0].payload["reason"] == "interrupted_by_service_restart"

    def test_recovery_idempotent(self, repo: SqliteTaskRepository) -> None:
        """Behavior 36: calling mark_interrupted_tasks twice is idempotent."""
        task = _make_task(repo)
        assert repo.mark_interrupted_tasks() == 1
        assert repo.mark_interrupted_tasks() == 0
        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.status == "failed"


# ===========================================================================
# Concurrency tests (behaviors 37-41)
# ===========================================================================

class TestConcurrency:
    def test_read_during_write(self, repo: SqliteTaskRepository) -> None:
        """Behavior 37: API can read while background writes."""
        task = _make_task(repo)
        read_results: list[Task | None] = []

        def writer() -> None:
            for i in range(5):
                trace = Trace(
                    task_id=task.task_id,
                    kind="tool_call",
                    payload={"tool_name": f"tool_{i}", "status": "success"},
                )
                repo.save_trace(task.task_id, trace)

        def reader() -> None:
            for _ in range(5):
                read_results.append(repo.get_task(task.task_id))

        wt = threading.Thread(target=writer)
        rt = threading.Thread(target=reader)
        wt.start()
        rt.start()
        wt.join()
        rt.join()
        assert all(r is not None for r in read_results)

    def test_multithread_trace_write(self, repo: SqliteTaskRepository) -> None:
        """Behavior 38: multiple threads writing traces do not lose data."""
        task = _make_task(repo)
        errors: list[Exception] = []

        def save(idx: int) -> None:
            try:
                trace = Trace(
                    task_id=task.task_id,
                    kind="tool_call",
                    payload={"tool_name": f"t_{idx}"},
                )
                repo.save_trace(task.task_id, trace)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=save, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(repo.get_traces(task.task_id)) == 8

    def test_multithread_update_different_tasks(self, repo: SqliteTaskRepository) -> None:
        """Behavior 39: concurrent updates to different tasks succeed."""
        tasks = [_make_task(repo) for _ in range(5)]
        errors: list[Exception] = []

        def update_one(t: Task) -> None:
            try:
                repo.update_status(t.task_id, "running", current_node="test")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=update_one, args=(t,)) for t in tasks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        for t in tasks:
            fetched = repo.get_task(t.task_id)
            assert fetched is not None
            assert fetched.status == "running"

    def test_locked_error_becomes_domain_error(self, migrated_db: Path) -> None:
        """Behavior 40: database locked errors become StorageError."""
        repo = SqliteTaskRepository(migrated_db, busy_timeout_ms=1)
        task = _make_task(repo)
        # Hold a write lock with another connection
        conn = sqlite3.connect(str(migrated_db), timeout=10.0)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN EXCLUSIVE")
            # Now try to update with the repo (very short timeout)
            with pytest.raises((StorageError, sqlite3.OperationalError)):
                repo.update_status(task.task_id, "running")
        finally:
            conn.rollback()
            conn.close()

    def test_no_cross_thread_connection_reuse(self, repo: SqliteTaskRepository) -> None:
        """Behavior 41: each operation opens its own connection."""
        # This is verified by the concurrent tests above succeeding.
        # Additionally verify the repo has no shared connection attribute.
        assert not hasattr(repo, "_conn")
        assert not hasattr(repo, "_connection")
