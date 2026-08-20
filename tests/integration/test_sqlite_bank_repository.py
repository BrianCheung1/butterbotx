from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase
from butterbot.infrastructure.database.sqlite_bank_repository import (
    SQLiteBankRepository,
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
def repository(database: SQLiteDatabase) -> Iterator[SQLiteBankRepository]:
    instance = SQLiteBankRepository(database.path)
    yield instance
    instance.close()


@pytest.mark.asyncio
async def test_first_lookup_creates_wallet_and_level_one_bank_atomically(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    result = await repository.get_or_create_overview(123)

    assert result.wallet.balance == 0
    assert result.account.balance == 0
    assert result.account.level == 1
    assert result.account.capacity == 150_000
    rows = database.run(
        lambda connection: connection.execute(
            "SELECT user_id, balance, level FROM bank_accounts"
        ).fetchall()
    )
    assert [tuple(row) for row in rows] == [(123, 0, 1)]


@pytest.mark.asyncio
async def test_existing_wallet_and_bank_state_are_returned_exactly(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    database.run(
        lambda connection: connection.executescript(
            """
            INSERT INTO users (user_id, balance) VALUES (456, 8500);
            INSERT INTO bank_accounts (user_id, balance, level)
            VALUES (456, 25000, 1);
            """
        )
    )

    result = await repository.get_or_create_overview(456)

    assert result.wallet.balance == 8_500
    assert result.account.balance == 25_000
    assert result.account.remaining_capacity == 125_000


@pytest.mark.asyncio
async def test_over_capacity_persisted_balance_remains_readable(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    database.run(
        lambda connection: connection.executescript(
            """
            INSERT INTO users (user_id) VALUES (789);
            INSERT INTO bank_accounts (user_id, balance) VALUES (789, 200000);
            """
        )
    )

    result = await repository.get_or_create_overview(789)

    assert result.account.balance == 200_000
    assert result.account.remaining_capacity == 0


@pytest.mark.asyncio
async def test_bank_creation_failure_rolls_back_new_wallet(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    database.run(
        lambda connection: connection.execute(
            """
            CREATE TRIGGER reject_bank_creation
            BEFORE INSERT ON bank_accounts
            BEGIN
                SELECT RAISE(ABORT, 'bank creation rejected');
            END
            """
        )
    )

    with pytest.raises(sqlite3.IntegrityError, match="bank creation rejected"):
        await repository.get_or_create_overview(999)

    assert (
        database.run(
            lambda connection: connection.execute(
                "SELECT user_id FROM users WHERE user_id = 999"
            ).fetchone()
        )
        is None
    )


@pytest.mark.asyncio
async def test_separate_repositories_create_one_account_concurrently(
    database: SQLiteDatabase,
) -> None:
    first = SQLiteBankRepository(database.path)
    second = SQLiteBankRepository(database.path)
    try:
        results = await asyncio.gather(
            first.get_or_create_overview(321),
            second.get_or_create_overview(321),
        )
    finally:
        first.close()
        second.close()

    assert [result.account.balance for result in results] == [0, 0]
    count = database.run(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM bank_accounts WHERE user_id = 321"
        ).fetchone()[0]
    )
    assert count == 1


def test_bank_constraints_and_foreign_key_deletion(database: SQLiteDatabase) -> None:
    database.run(
        lambda connection: connection.execute(
            "INSERT INTO users (user_id) VALUES (555)"
        )
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.run(
            lambda connection: connection.execute(
                "INSERT INTO bank_accounts (user_id, balance) VALUES (555, -1)"
            )
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.run(
            lambda connection: connection.execute(
                "INSERT INTO bank_accounts (user_id, level) VALUES (555, 0)"
            )
        )

    database.run(
        lambda connection: connection.execute(
            "INSERT INTO bank_accounts (user_id) VALUES (555)"
        )
    )
    database.run(
        lambda connection: connection.execute("DELETE FROM users WHERE user_id = 555")
    )
    assert (
        database.run(
            lambda connection: connection.execute(
                "SELECT user_id FROM bank_accounts WHERE user_id = 555"
            ).fetchone()
        )
        is None
    )
