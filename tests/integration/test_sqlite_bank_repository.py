from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from butterbot.domain.bank import (
    BankCapacityExceeded,
    BankDepositSelection,
    BankHasNoCapacity,
    InsufficientWalletBalance,
)
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


def seed_bank(
    database: SQLiteDatabase,
    *,
    user_id: int = 100,
    wallet_balance: int,
    bank_balance: int = 0,
) -> None:
    database.run(
        lambda connection: (
            connection.execute(
                "INSERT INTO users (user_id, balance) VALUES (?, ?)",
                (user_id, wallet_balance),
            ),
            connection.execute(
                "INSERT INTO bank_accounts (user_id, balance) VALUES (?, ?)",
                (user_id, bank_balance),
            ),
        )
    )


def balances(database: SQLiteDatabase, user_id: int = 100) -> tuple[int, int]:
    row = database.run(
        lambda connection: connection.execute(
            """
            SELECT users.balance, bank_accounts.balance
            FROM users JOIN bank_accounts USING (user_id)
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    )
    return row[0], row[1]


@pytest.mark.asyncio
async def test_exact_deposit_conserves_currency_atomically(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=10_000, bank_balance=2_000)

    result = await repository.deposit(100, BankDepositSelection(amount=3_000))

    assert result.amount == 3_000
    assert result.overview.wallet.balance == 7_000
    assert result.overview.account.balance == 5_000
    assert balances(database) == (7_000, 5_000)
    assert sum(balances(database)) == 12_000


@pytest.mark.asyncio
async def test_percentage_uses_transaction_current_wallet_and_floor_division(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=103)

    first = await repository.deposit(100, BankDepositSelection(percentage=50))
    second = await repository.deposit(100, BankDepositSelection(percentage=50))

    assert first.amount == 51
    assert second.amount == 26
    assert balances(database) == (26, 77)


@pytest.mark.asyncio
async def test_percentage_deposit_fills_remaining_capacity_and_reports_cap(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=20_000, bank_balance=149_000)

    result = await repository.deposit(100, BankDepositSelection(percentage=100))

    assert result.amount == 1_000
    assert result.filled_remaining_capacity is True
    assert balances(database) == (19_000, 150_000)


@pytest.mark.asyncio
async def test_exact_capacity_failure_precedes_wallet_failure_without_mutation(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=10, bank_balance=149_000)

    with pytest.raises(BankCapacityExceeded) as raised:
        await repository.deposit(100, BankDepositSelection(amount=2_000))

    assert raised.value.remaining_capacity == 1_000
    assert balances(database) == (10, 149_000)


@pytest.mark.asyncio
async def test_insufficient_wallet_rejects_without_mutation(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=10, bank_balance=100)

    with pytest.raises(InsufficientWalletBalance):
        await repository.deposit(100, BankDepositSelection(amount=11))

    assert balances(database) == (10, 100)


@pytest.mark.asyncio
@pytest.mark.parametrize("bank_balance", [150_000, 200_000])
async def test_full_or_over_capacity_bank_rejects_without_mutation(
    database: SQLiteDatabase,
    repository: SQLiteBankRepository,
    bank_balance: int,
) -> None:
    seed_bank(database, wallet_balance=10_000, bank_balance=bank_balance)

    with pytest.raises(BankHasNoCapacity):
        await repository.deposit(100, BankDepositSelection(percentage=100))

    assert balances(database) == (10_000, bank_balance)


@pytest.mark.asyncio
async def test_bank_credit_failure_rolls_back_wallet_debit(
    database: SQLiteDatabase, repository: SQLiteBankRepository
) -> None:
    seed_bank(database, wallet_balance=1_000)
    database.run(
        lambda connection: connection.execute(
            """
            CREATE TRIGGER reject_bank_credit
            BEFORE UPDATE ON bank_accounts
            BEGIN
                SELECT RAISE(ABORT, 'bank credit rejected');
            END
            """
        )
    )

    with pytest.raises(sqlite3.IntegrityError, match="bank credit rejected"):
        await repository.deposit(100, BankDepositSelection(amount=500))

    assert balances(database) == (1_000, 0)


@pytest.mark.asyncio
async def test_separate_repositories_cannot_overspend_wallet(
    database: SQLiteDatabase,
) -> None:
    seed_bank(database, wallet_balance=100)
    first = SQLiteBankRepository(database.path)
    second = SQLiteBankRepository(database.path)
    try:
        results = await asyncio.gather(
            first.deposit(100, BankDepositSelection(amount=80)),
            second.deposit(100, BankDepositSelection(amount=80)),
            return_exceptions=True,
        )
    finally:
        first.close()
        second.close()

    assert sum(isinstance(result, InsufficientWalletBalance) for result in results) == 1
    assert balances(database) == (20, 80)


@pytest.mark.asyncio
async def test_separate_repositories_cannot_overfill_bank(
    database: SQLiteDatabase,
) -> None:
    seed_bank(database, wallet_balance=20_000, bank_balance=140_000)
    first = SQLiteBankRepository(database.path)
    second = SQLiteBankRepository(database.path)
    try:
        results = await asyncio.gather(
            first.deposit(100, BankDepositSelection(amount=10_000)),
            second.deposit(100, BankDepositSelection(amount=10_000)),
            return_exceptions=True,
        )
    finally:
        first.close()
        second.close()

    assert sum(isinstance(result, BankHasNoCapacity) for result in results) == 1
    assert balances(database) == (10_000, 150_000)
