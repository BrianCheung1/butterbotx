from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from butterbot.domain.mining import (
    InvalidMiningState,
    MiningCooldownActive,
    MiningResult,
    MiningRewardExceedsWalletLimit,
    MiningRoll,
)
from butterbot.domain.wallet import MAX_MONEY
from butterbot.infrastructure.database.migrations import MigrationRunner
from butterbot.infrastructure.database.sqlite import SQLiteDatabase
from butterbot.infrastructure.database.sqlite_mining_repository import (
    SQLiteMiningRepository,
)
from butterbot.infrastructure.database.sqlite_wallet_repository import (
    SQLiteWalletRepository,
)

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)
LOW_ROLL = MiningRoll(0, 0, 0, 0)


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
def repository(database: SQLiteDatabase) -> Iterator[SQLiteMiningRepository]:
    instance = SQLiteMiningRepository(database.path)
    yield instance
    instance.close()


def rows(database: SQLiteDatabase, user_id: int) -> tuple[sqlite3.Row, sqlite3.Row]:
    found = database.run(
        lambda connection: (
            connection.execute(
                "SELECT balance FROM users WHERE user_id = ?", (user_id,)
            ).fetchone(),
            connection.execute(
                "SELECT xp, total_actions, total_earned, next_mine_at "
                "FROM mining_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone(),
        )
    )
    assert found[0] is not None
    assert found[1] is not None
    return found[0], found[1]


def insert_profile(
    database: SQLiteDatabase,
    user_id: int,
    *,
    balance: int = 0,
    xp: int = 0,
    total_actions: int = 0,
    total_earned: int = 0,
    next_mine_at: str = "2026-08-20T11:59:00.000000+00:00",
) -> None:
    def insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, balance)
        )
        connection.execute(
            "INSERT INTO mining_profiles "
            "(user_id, xp, total_actions, total_earned, next_mine_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, xp, total_actions, total_earned, next_mine_at),
        )

    database.run(insert)


def test_schema_is_feature_owned_constrained_and_cascades(
    database: SQLiteDatabase,
) -> None:
    foreign_keys = database.run(
        lambda connection: connection.execute(
            "PRAGMA foreign_key_list(mining_profiles)"
        ).fetchall()
    )
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["table"] == "users"
    assert foreign_keys[0]["on_delete"] == "CASCADE"

    database.run(
        lambda connection: connection.execute("INSERT INTO users (user_id) VALUES (1)")
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        database.run(
            lambda connection: connection.execute(
                "INSERT INTO mining_profiles "
                "(user_id, xp, total_actions, total_earned, next_mine_at) "
                "VALUES (1, -1, 0, 0, 'x')"
            )
        )

    database.run(
        lambda connection: connection.execute(
            "INSERT INTO mining_profiles VALUES (1, 0, 0, 0, 'x')"
        )
    )
    database.run(
        lambda connection: connection.execute("DELETE FROM users WHERE user_id = 1")
    )
    assert (
        database.run(
            lambda connection: connection.execute(
                "SELECT 1 FROM mining_profiles WHERE user_id = 1"
            ).fetchone()
        )
        is None
    )


@pytest.mark.asyncio
async def test_first_mine_creates_wallet_and_profile_atomically(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    result = await repository.mine(10, NOW, LOW_ROLL)

    assert result.outcome.resource == "dirt"
    assert result.outcome.total_value == 50
    assert result.outcome.xp_gained == 5
    assert result.balance == 50
    assert result.level == 1
    assert result.xp_for_next_level == 12
    wallet, profile = rows(database, 10)
    assert wallet["balance"] == 50
    assert dict(profile) == {
        "xp": 5,
        "total_actions": 1,
        "total_earned": 50,
        "next_mine_at": "2026-08-20T12:00:30.000000+00:00",
    }


@pytest.mark.asyncio
async def test_mine_at_exact_cooldown_boundary_succeeds(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(
        database,
        11,
        balance=50,
        xp=10,
        total_actions=1,
        total_earned=50,
        next_mine_at="2026-08-20T12:00:00.000000+00:00",
    )

    result = await repository.mine(11, NOW, LOW_ROLL)

    assert result.previous_level == 1
    assert result.level == 2
    assert result.leveled_up is True
    assert result.xp == 15


@pytest.mark.asyncio
async def test_active_cooldown_changes_nothing(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(
        database,
        12,
        balance=50,
        xp=5,
        total_actions=1,
        total_earned=50,
        next_mine_at="2026-08-20T12:00:01.000000+00:00",
    )

    with pytest.raises(MiningCooldownActive) as captured:
        await repository.mine(12, NOW, LOW_ROLL)

    assert captured.value.next_mine_at == NOW + timedelta(seconds=1)
    wallet, profile = rows(database, 12)
    assert wallet["balance"] == 50
    assert profile["total_actions"] == 1


@pytest.mark.asyncio
async def test_wallet_overflow_rolls_back_profile(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(database, 13, balance=MAX_MONEY)

    with pytest.raises(MiningRewardExceedsWalletLimit):
        await repository.mine(13, NOW, LOW_ROLL)

    wallet, profile = rows(database, 13)
    assert wallet["balance"] == MAX_MONEY
    assert profile["total_actions"] == 0
    assert profile["xp"] == 0


@pytest.mark.asyncio
async def test_profile_update_failure_rolls_back_wallet_credit(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(database, 14, balance=100)
    database.run(
        lambda connection: connection.execute(
            """
            CREATE TRIGGER reject_mining_update
            BEFORE UPDATE ON mining_profiles
            BEGIN
                SELECT RAISE(ABORT, 'mining update rejected');
            END
            """
        )
    )

    with pytest.raises(sqlite3.IntegrityError, match="mining update rejected"):
        await repository.mine(14, NOW, LOW_ROLL)

    wallet, profile = rows(database, 14)
    assert wallet["balance"] == 100
    assert profile["total_actions"] == 0


@pytest.mark.asyncio
async def test_malformed_cooldown_rolls_back(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(database, 15, next_mine_at="not-a-timestamp")

    with pytest.raises(InvalidMiningState):
        await repository.mine(15, NOW, LOW_ROLL)

    wallet, profile = rows(database, 15)
    assert wallet["balance"] == 0
    assert profile["total_actions"] == 0


@pytest.mark.asyncio
async def test_separate_repositories_allow_only_one_simultaneous_mine(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    other_repository = SQLiteMiningRepository(database.path)
    try:
        results = await asyncio.gather(
            repository.mine(16, NOW, LOW_ROLL),
            other_repository.mine(16, NOW, LOW_ROLL),
            return_exceptions=True,
        )
    finally:
        other_repository.close()

    assert sum(isinstance(item, MiningResult) for item in results) == 1
    assert sum(isinstance(item, MiningCooldownActive) for item in results) == 1
    wallet, profile = rows(database, 16)
    assert wallet["balance"] == 50
    assert profile["total_actions"] == 1
    assert profile["xp"] == 5


@pytest.mark.asyncio
async def test_mining_and_transfer_serialize_shared_wallet_updates(
    database: SQLiteDatabase, repository: SQLiteMiningRepository
) -> None:
    insert_profile(database, 17, balance=100)
    wallet_repository = SQLiteWalletRepository(database.path)
    try:
        mining_result, transfer_result = await asyncio.gather(
            repository.mine(17, NOW, LOW_ROLL),
            wallet_repository.transfer(17, 18, 100),
        )
    finally:
        wallet_repository.close()

    assert mining_result.balance in {50, 150}
    assert transfer_result.sender.balance in {0, 50}
    final_sender = database.run(
        lambda connection: connection.execute(
            "SELECT balance FROM users WHERE user_id = 17"
        ).fetchone()
    )
    final_recipient = database.run(
        lambda connection: connection.execute(
            "SELECT balance FROM users WHERE user_id = 18"
        ).fetchone()
    )
    assert final_sender is not None
    assert final_recipient is not None
    assert final_sender["balance"] == 50
    assert final_recipient["balance"] == 100
