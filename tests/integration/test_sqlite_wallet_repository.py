from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase
from butterbot.infrastructure.database.sqlite_wallet_repository import (
    SQLiteWalletRepository,
)


def migration_directory() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "butterbot"
        / "infrastructure"
        / "database"
        / "migrations"
    )


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SQLiteDatabase]:
    instance = SQLiteDatabase(tmp_path / "butterbot.sqlite3")
    instance.open()
    MigrationRunner(migration_directory()).apply(instance)
    yield instance
    instance.close()


@pytest.fixture
def repository(database: SQLiteDatabase) -> Iterator[SQLiteWalletRepository]:
    instance = SQLiteWalletRepository(database.path)
    yield instance
    instance.close()


@pytest.mark.asyncio
async def test_first_lookup_creates_only_a_zero_balance_wallet(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    result = await repository.get_or_create_balance(123)

    assert result.user_id == 123
    assert result.balance_cents == 0
    rows = database.run(
        lambda connection: connection.execute(
            "SELECT user_id, balance_cents FROM users"
        ).fetchall()
    )
    assert [(row["user_id"], row["balance_cents"]) for row in rows] == [(123, 0)]
    tables = database.run(
        lambda connection: connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    )
    assert [row["name"] for row in tables] == ["schema_migrations", "users"]


@pytest.mark.asyncio
async def test_existing_balance_is_returned_exactly(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    database.run(
        lambda connection: connection.execute(
            "INSERT INTO users (user_id, balance_cents) VALUES (?, ?)",
            (456, 123_450),
        )
    )

    result = await repository.get_or_create_balance(456)

    assert result.balance_cents == 123_450


@pytest.mark.asyncio
async def test_concurrent_first_lookups_create_one_wallet(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    results = await asyncio.gather(
        *(repository.get_or_create_balance(789) for _ in range(10))
    )

    assert [result.balance_cents for result in results] == [0] * 10
    count = database.run(
        lambda connection: connection.execute(
            "SELECT COUNT(*) AS count FROM users WHERE user_id = ?", (789,)
        ).fetchone()["count"]
    )
    assert count == 1


def test_database_rejects_negative_balance(database: SQLiteDatabase) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        database.run(
            lambda connection: connection.execute(
                "INSERT INTO users (user_id, balance_cents) VALUES (?, ?)",
                (999, -1),
            )
        )
