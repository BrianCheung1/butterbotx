"""Versioned SQL migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from butterbot.infrastructure.database.sqlite import SQLiteDatabase


@dataclass(frozen=True, slots=True)
class Migration:
    """A numbered SQL migration file."""

    version: int
    name: str
    sql: str
    checksum: str


class MigrationRunner:
    """Apply ordered SQL migrations once and record their checksums."""

    def __init__(self, migration_directory: Path) -> None:
        self._migration_directory = migration_directory

    def apply(self, database: SQLiteDatabase) -> None:
        """Create migration history and apply pending migrations atomically."""
        migrations = self._discover_migrations()
        database.run(lambda connection: _apply_migrations(connection, migrations))

    def _discover_migrations(self) -> list[Migration]:
        migrations: list[Migration] = []
        versions: set[int] = set()
        for path in sorted(self._migration_directory.glob("*.sql")):
            version, separator, _ = path.stem.partition("_")
            if not separator or not version.isdigit():
                raise RuntimeError(
                    f"Migration {path.name} must use NNN_description.sql naming."
                )
            migration_version = int(version)
            if migration_version in versions:
                raise RuntimeError(f"Duplicate migration version: {migration_version}")
            versions.add(migration_version)
            sql = path.read_text(encoding="utf-8")
            migrations.append(
                Migration(
                    version=migration_version,
                    name=path.name,
                    sql=sql,
                    checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                )
            )
        return migrations


def _apply_migrations(
    connection: sqlite3.Connection, migrations: list[Migration]
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for migration in migrations:
        existing = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (migration.version,),
        ).fetchone()
        if existing is not None:
            if existing["checksum"] != migration.checksum:
                raise RuntimeError(
                    f"Migration {migration.version} has changed after application."
                )
            continue

        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{migration.sql}\n"
                "INSERT INTO schema_migrations "
                "(version, name, checksum, applied_at) "
                f"VALUES ({migration.version}, {_sql_literal(migration.name)}, "
                f"{_sql_literal(migration.checksum)}, datetime('now'));\n"
                "COMMIT;"
            )
        except BaseException:
            connection.rollback()
            raise


def _sql_literal(value: str) -> str:
    """Quote a trusted migration metadata value for a SQL script."""
    return "'" + value.replace("'", "''") + "'"
