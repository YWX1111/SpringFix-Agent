"""Minimal deterministic SQLite migration system.

Reads SQL files from the ``migrations/`` package directory, applies them
in version order inside transactions, and records each applied version in
``schema_migrations``.  Idempotent: calling ``migrate()`` twice is a no-op.

Design constraints:
    - No SQLAlchemy / Alembic dependency.
    - No schema duplicated in Python strings.
    - Unknown higher-version DB raises, never silently downgrades.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_MIGRATION_FILE_RE = re.compile(r"^(\d+)_(\w+)\.sql$")


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied or a version conflict is detected."""


def _discover_migrations() -> list[tuple[int, str, str]]:
    """Return ``(version, name, sql_text)`` tuples sorted by version.

    Migration files live in the ``migrations/`` sub-package and follow the
    naming convention ``<NNN>_<name>.sql``.
    """
    migrations: list[tuple[int, str, str]] = []
    pkg = resources.files("springfix_agent.storage.migrations")
    entries = sorted(pkg.iterdir(), key=lambda e: e.name)
    for item in entries:
        fname = item.name
        match = _MIGRATION_FILE_RE.match(fname)
        if match is None:
            continue
        version = int(match.group(1))
        name = match.group(2)
        sql_text = item.read_text(encoding="utf-8")
        migrations.append((version, name, sql_text))
    migrations.sort(key=lambda m: m[0])
    return migrations


def _get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of already-applied migration versions."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    if cursor.fetchone() is None:
        return set()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row[0]) for row in rows}


def migrate(db_path: str | Path, *, wal_enabled: bool = True, busy_timeout_ms: int = 5000) -> None:
    """Apply all pending migrations to the SQLite database at *db_path*.

    - Creates the database file and parent directories if needed.
    - Enables ``foreign_keys`` and ``busy_timeout`` for the migration connection.
    - Each migration runs inside its own transaction; failure rolls back that
      single migration without affecting previously applied ones.
    - Idempotent: already-applied versions are skipped.
    - Raises ``MigrationError`` if the database contains a version higher than
      any available migration file (refuses silent downgrade).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    available = _discover_migrations()
    if not available:
        _LOGGER.warning("no migration files discovered")
        return

    conn = sqlite3.connect(str(db_path), timeout=busy_timeout_ms / 1000.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        if wal_enabled:
            conn.execute("PRAGMA journal_mode = WAL")

        applied = _get_applied_versions(conn)

        available_versions = {v for v, _, _ in available}
        unknown = applied - available_versions
        if unknown:
            max_available = max(available_versions) if available_versions else 0
            max_unknown = max(unknown)
            if max_unknown > max_available:
                raise MigrationError(
                    f"database contains version {max_unknown} which is higher than "
                    f"available migration {max_available}; refusing to downgrade"
                )

        for version, name, sql_text in available:
            if version in applied:
                continue
            _LOGGER.info("applying migration %03d_%s", version, name)
            try:
                conn.execute("BEGIN")
                conn.executescript(sql_text)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, datetime.now(tz=UTC).isoformat()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise MigrationError(
                    f"migration {version:03d}_{name} failed"
                ) from None
            _LOGGER.info("migration %03d_%s applied", version, name)
    finally:
        conn.close()
