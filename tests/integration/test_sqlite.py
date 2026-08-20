from __future__ import annotations

from pathlib import Path

import pytest

from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase


def test_database_lifecycle_and_migration_history(tmp_path: Path) -> None:
    migration_directory = tmp_path / "migrations"
    migration_directory.mkdir()
    (migration_directory / "001_create_example.sql").write_text(
        "CREATE TABLE example (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    database = SQLiteDatabase(tmp_path / "database" / "butterbot.sqlite3")

    database.open()
    MigrationRunner(migration_directory).apply(database)

    rows = database.run(
        lambda connection: connection.execute(
            "SELECT version, name FROM schema_migrations"
        ).fetchall()
    )
    assert [(row["version"], row["name"]) for row in rows] == [
        (1, "001_create_example.sql")
    ]

    database.close()
    with pytest.raises(RuntimeError, match="has not been opened"):
        database.run(lambda connection: connection.execute("SELECT 1"))
