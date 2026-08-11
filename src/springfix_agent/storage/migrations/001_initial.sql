-- 001_initial.sql
-- Initial schema for SpringFix Agent M4A SQLite persistence.
-- Applied by migration.py at application startup.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    repository_path TEXT NOT NULL,
    issue_description TEXT NOT NULL,
    error_log TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    current_node TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    created_timestamp TEXT NOT NULL,
    updated_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('tool_call', 'node_timing', 'llm_call', 'system_recovery')),
    node_name TEXT,
    sequence_number INTEGER NOT NULL,
    start_time TEXT,
    end_time TEXT,
    duration_ms INTEGER,
    status TEXT,
    payload_json TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id),
    UNIQUE(task_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_traces_task_id ON traces(task_id);

CREATE TABLE IF NOT EXISTS reports (
    task_id TEXT PRIMARY KEY,
    diagnosis_status TEXT,
    json_report TEXT NOT NULL,
    markdown_report TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);
