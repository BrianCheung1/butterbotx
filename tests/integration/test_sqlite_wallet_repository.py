from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from butterbot.domain.money_transfer import (
    InsufficientFunds,
    InvalidTransfer,
    WalletLimitExceeded,
)
from butterbot.domain.wallet import MAX_MONEY, Wallet
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
    assert result.balance == 0
    rows = database.run(
        lambda connection: connection.execute(
            "SELECT user_id, balance FROM users"
        ).fetchall()
    )
    assert [(row["user_id"], row["balance"]) for row in rows] == [(123, 0)]
    tables = database.run(
        lambda connection: connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    )
    assert [row["name"] for row in tables] == [
        "daily_claims",
        "mining_profiles",
        "schema_migrations",
        "users",
    ]


@pytest.mark.asyncio
async def test_existing_balance_is_returned_exactly(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    database.run(
        lambda connection: connection.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (456, 123_450),
        )
    )

    result = await repository.get_or_create_balance(456)

    assert result.balance == 123_450


@pytest.mark.asyncio
async def test_set_balance_creates_wallet_and_returns_exact_value(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    result = await repository.set_balance(901, 123_450)

    assert result.user_id == 901
    assert result.balance == 123_450
    assert balances(database, 901) == {901: 123_450}


@pytest.mark.asyncio
async def test_set_balance_replaces_existing_balance_and_accepts_zero(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 902, 500)

    result = await repository.set_balance(902, 0)

    assert result == Wallet(user_id=902, balance=0)
    assert balances(database, 902) == {902: 0}


@pytest.mark.asyncio
async def test_set_balance_accepts_maximum_wallet_value(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    result = await repository.set_balance(903, MAX_MONEY)

    assert result.balance == MAX_MONEY
    assert balances(database, 903) == {903: MAX_MONEY}


@pytest.mark.asyncio
async def test_set_balance_rolls_back_when_upsert_fails(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 904, 100)
    database.run(
        lambda connection: connection.execute(
            """
            CREATE TRIGGER reject_test_balance
            BEFORE UPDATE OF balance ON users
            WHEN NEW.balance = 777
            BEGIN
                SELECT RAISE(ABORT, 'test balance rejected');
            END
            """
        )
    )

    with pytest.raises(sqlite3.IntegrityError, match="test balance rejected"):
        await repository.set_balance(904, 777)

    assert balances(database, 904) == {904: 100}


@pytest.mark.asyncio
async def test_concurrent_set_balance_operations_remain_complete(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    results = await asyncio.gather(
        repository.set_balance(905, 111),
        repository.set_balance(905, 222),
    )

    assert {result.balance for result in results} == {111, 222}
    assert balances(database, 905)[905] in {111, 222}


@pytest.mark.asyncio
async def test_concurrent_first_lookups_create_one_wallet(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    results = await asyncio.gather(
        *(repository.get_or_create_balance(789) for _ in range(10))
    )

    assert [result.balance for result in results] == [0] * 10
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
                "INSERT INTO users (user_id, balance) VALUES (?, ?)",
                (999, -1),
            )
        )


def set_balance(database: SQLiteDatabase, user_id: int, balance: int) -> None:
    database.run(
        lambda connection: connection.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?) "
            "ON CONFLICT (user_id) DO UPDATE "
            "SET balance = excluded.balance",
            (user_id, balance),
        )
    )


def balances(database: SQLiteDatabase, *user_ids: int) -> dict[int, int]:
    placeholders = ", ".join("?" for _ in user_ids)
    rows = database.run(
        lambda connection: connection.execute(
            f"SELECT user_id, balance FROM users WHERE user_id IN ({placeholders})",
            user_ids,
        ).fetchall()
    )
    return {row["user_id"]: row["balance"] for row in rows}


@pytest.mark.asyncio
async def test_transfer_atomically_updates_both_wallets(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 10_000)

    result = await repository.transfer(1, 2, 2_500)

    assert result.sender.balance == 7_500
    assert result.recipient.balance == 2_500
    assert balances(database, 1, 2) == {1: 7_500, 2: 2_500}


@pytest.mark.asyncio
async def test_insufficient_funds_rolls_back_all_changes(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 500)
    set_balance(database, 2, 200)

    with pytest.raises(InsufficientFunds) as raised:
        await repository.transfer(1, 2, 600)

    assert raised.value.available_balance == 500
    assert balances(database, 1, 2) == {1: 500, 2: 200}


@pytest.mark.asyncio
async def test_unknown_sender_failure_rolls_back_created_wallets(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    with pytest.raises(InsufficientFunds) as raised:
        await repository.transfer(10, 20, 100)

    assert raised.value.available_balance == 0
    assert balances(database, 10, 20) == {}


@pytest.mark.asyncio
async def test_recipient_overflow_rolls_back_sender_debit(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 1_000)
    set_balance(database, 2, MAX_MONEY - 500)

    with pytest.raises(WalletLimitExceeded):
        await repository.transfer(1, 2, 600)

    assert balances(database, 1, 2) == {
        1: 1_000,
        2: MAX_MONEY - 500,
    }


@pytest.mark.asyncio
async def test_self_transfer_is_rejected_without_mutation(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 1_000)

    with pytest.raises(InvalidTransfer):
        await repository.transfer(1, 1, 100)

    assert balances(database, 1) == {1: 1_000}


@pytest.mark.asyncio
async def test_concurrent_transfers_cannot_overspend_sender(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 1_000)

    results = await asyncio.gather(
        repository.transfer(1, 2, 700),
        repository.transfer(1, 3, 700),
        return_exceptions=True,
    )

    assert sum(isinstance(result, InsufficientFunds) for result in results) == 1
    final = balances(database, 1, 2, 3)
    assert final[1] == 300
    assert final.get(2, 0) + final.get(3, 0) == 700


@pytest.mark.asyncio
async def test_concurrent_credits_preserve_every_transfer(
    database: SQLiteDatabase, repository: SQLiteWalletRepository
) -> None:
    set_balance(database, 1, 1_000)
    set_balance(database, 2, 1_000)

    await asyncio.gather(
        repository.transfer(1, 3, 400),
        repository.transfer(2, 3, 600),
    )

    assert balances(database, 1, 2, 3) == {1: 600, 2: 400, 3: 1_000}
