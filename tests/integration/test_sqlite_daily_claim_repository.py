from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from butterbot.domain.daily_reward import (
    DailyAlreadyClaimed,
    DailyClaimResult,
    DailyRewardExceedsWalletLimit,
    InvalidDailyClaimState,
)
from butterbot.domain.wallet import MAX_MONEY
from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase
from butterbot.infrastructure.database.sqlite_daily_claim_repository import (
    SQLiteDailyClaimRepository,
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
def repository(database: SQLiteDatabase) -> Iterator[SQLiteDailyClaimRepository]:
    instance = SQLiteDailyClaimRepository(database.path)
    yield instance
    instance.close()


def user_row(database: SQLiteDatabase, user_id: int) -> sqlite3.Row:
    row = database.run(
        lambda connection: connection.execute(
            "SELECT user_id, balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    )
    assert row is not None
    return row


def daily_row_or_none(database: SQLiteDatabase, user_id: int) -> sqlite3.Row | None:
    return database.run(
        lambda connection: connection.execute(
            "SELECT streak, last_claim_date FROM daily_claims WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    )


def daily_row(database: SQLiteDatabase, user_id: int) -> sqlite3.Row:
    row = daily_row_or_none(database, user_id)
    assert row is not None
    return row


def insert_state(
    database: SQLiteDatabase,
    user_id: int,
    *,
    balance: int,
    streak: int,
    last_claim_date: str,
) -> None:
    def insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, balance),
        )
        connection.execute(
            "INSERT INTO daily_claims (user_id, streak, last_claim_date) "
            "VALUES (?, ?, ?)",
            (user_id, streak, last_claim_date),
        )

    database.run(insert)


def test_daily_claim_schema_has_constraints_and_cascade(
    database: SQLiteDatabase,
) -> None:
    foreign_keys = database.run(
        lambda connection: connection.execute(
            "PRAGMA foreign_key_list(daily_claims)"
        ).fetchall()
    )
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["table"] == "users"
    assert foreign_keys[0]["from"] == "user_id"
    assert foreign_keys[0]["to"] == "user_id"
    assert foreign_keys[0]["on_delete"] == "CASCADE"

    database.run(
        lambda connection: connection.execute("INSERT INTO users (user_id) VALUES (1)")
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        database.run(
            lambda connection: connection.execute(
                "INSERT INTO daily_claims "
                "(user_id, streak, last_claim_date) VALUES (1, -1, '2026-08-19')"
            )
        )
    database.run(
        lambda connection: connection.execute(
            "INSERT INTO daily_claims "
            "(user_id, streak, last_claim_date) VALUES (1, 1, '2026-08-19')"
        )
    )

    database.run(
        lambda connection: connection.execute("DELETE FROM users WHERE user_id = 1")
    )
    assert daily_row_or_none(database, 1) is None


@pytest.mark.asyncio
async def test_first_claim_creates_wallet_and_canonical_daily_state(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    result = await repository.claim(10, date(2026, 8, 19))

    assert result.wallet.balance == 1_000
    assert result.reward.streak == 1
    assert result.reward.total == 1_000
    assert dict(user_row(database, 10)) == {"user_id": 10, "balance": 1_000}
    assert dict(daily_row(database, 10)) == {
        "streak": 1,
        "last_claim_date": "2026-08-19",
    }


@pytest.mark.asyncio
async def test_consecutive_claim_credits_exact_reward(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    insert_state(database, 11, balance=5_000, streak=2, last_claim_date="2026-08-18")

    result = await repository.claim(11, date(2026, 8, 19))

    assert (result.reward.bonus, result.reward.total, result.reward.streak) == (
        2_000,
        3_000,
        3,
    )
    assert user_row(database, 11)["balance"] == 8_000
    assert dict(daily_row(database, 11)) == {
        "streak": 3,
        "last_claim_date": "2026-08-19",
    }


@pytest.mark.asyncio
async def test_same_day_claim_rolls_back_every_change(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    insert_state(database, 12, balance=5_000, streak=3, last_claim_date="2026-08-19")

    with pytest.raises(DailyAlreadyClaimed):
        await repository.claim(12, date(2026, 8, 19))

    assert user_row(database, 12)["balance"] == 5_000
    assert dict(daily_row(database, 12)) == {
        "streak": 3,
        "last_claim_date": "2026-08-19",
    }


@pytest.mark.parametrize(
    ("claim_date", "expected_streak", "expected_total"),
    [(date(2026, 9, 1), 6, 17_000), (date(2026, 9, 2), 1, 1_000)],
)
@pytest.mark.asyncio
async def test_streak_gap_boundary(
    database: SQLiteDatabase,
    repository: SQLiteDailyClaimRepository,
    claim_date: date,
    expected_streak: int,
    expected_total: int,
) -> None:
    insert_state(database, 13, balance=0, streak=5, last_claim_date="2026-08-19")

    result = await repository.claim(13, claim_date)

    assert result.reward.streak == expected_streak
    assert result.reward.total == expected_total


@pytest.mark.asyncio
async def test_wallet_overflow_rolls_back_daily_state(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    insert_state(
        database,
        14,
        balance=MAX_MONEY,
        streak=1,
        last_claim_date="2026-08-18",
    )

    with pytest.raises(DailyRewardExceedsWalletLimit):
        await repository.claim(14, date(2026, 8, 19))

    assert user_row(database, 14)["balance"] == MAX_MONEY
    assert daily_row(database, 14)["last_claim_date"] == "2026-08-18"


@pytest.mark.asyncio
async def test_daily_state_failure_rolls_back_wallet_credit(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    insert_state(database, 15, balance=500, streak=1, last_claim_date="2026-08-18")
    database.run(
        lambda connection: connection.execute(
            """
            CREATE TRIGGER reject_daily_update
            BEFORE UPDATE ON daily_claims
            BEGIN
                SELECT RAISE(ABORT, 'daily update rejected');
            END
            """
        )
    )

    with pytest.raises(sqlite3.IntegrityError, match="daily update rejected"):
        await repository.claim(15, date(2026, 8, 19))

    assert user_row(database, 15)["balance"] == 500
    assert daily_row(database, 15)["last_claim_date"] == "2026-08-18"


@pytest.mark.asyncio
async def test_malformed_stored_date_rolls_back(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    insert_state(database, 16, balance=500, streak=1, last_claim_date="2026-99-99")

    with pytest.raises(InvalidDailyClaimState):
        await repository.claim(16, date(2026, 8, 19))

    assert user_row(database, 16)["balance"] == 500


@pytest.mark.asyncio
async def test_separate_repositories_allow_only_one_simultaneous_claim(
    database: SQLiteDatabase, repository: SQLiteDailyClaimRepository
) -> None:
    other_repository = SQLiteDailyClaimRepository(database.path)
    try:
        results = await asyncio.gather(
            repository.claim(17, date(2026, 8, 19)),
            other_repository.claim(17, date(2026, 8, 19)),
            return_exceptions=True,
        )
    finally:
        other_repository.close()

    assert sum(isinstance(result, DailyClaimResult) for result in results) == 1
    assert sum(isinstance(result, DailyAlreadyClaimed) for result in results) == 1
    assert user_row(database, 17)["balance"] == 1_000
    assert dict(daily_row(database, 17)) == {
        "streak": 1,
        "last_claim_date": "2026-08-19",
    }
