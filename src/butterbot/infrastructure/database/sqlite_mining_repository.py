"""SQLite persistence for atomic mining actions."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from butterbot.domain.mining import (
    MINING_CATALOG,
    MINING_COOLDOWN_SECONDS,
    InvalidMiningState,
    MiningCooldownActive,
    MiningResult,
    MiningRewardExceedsWalletLimit,
    MiningRoll,
    cumulative_xp_for_level,
    level_for_xp,
    resolve_mining,
)
from butterbot.domain.wallet import MAX_MONEY


class SQLiteMiningRepository:
    """Atomically persist mining progression and wallet rewards in SQLite."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="butterbot-sqlite-mining"
        )

    async def mine(self, user_id: int, now: datetime, roll: MiningRoll) -> MiningResult:
        """Commit one eligible mining action under an immediate transaction."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Mining time must be timezone-aware.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _mine,
            self._database_path,
            user_id,
            now.astimezone(UTC),
            roll,
        )

    def close(self) -> None:
        """Finish queued mining work and release its worker thread."""
        self._executor.shutdown()


def _mine(
    database_path: Path, user_id: int, now: datetime, roll: MiningRoll
) -> MiningResult:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        row = connection.execute(
            """
            SELECT u.balance, m.xp, m.total_actions, m.total_earned,
                   m.next_mine_at
            FROM users AS u
            LEFT JOIN mining_profiles AS m ON m.user_id = u.user_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Wallet was not available after creation.")

        xp = 0 if row["xp"] is None else _nonnegative_int(row["xp"], "XP")
        total_actions = (
            0
            if row["total_actions"] is None
            else _nonnegative_int(row["total_actions"], "action count")
        )
        total_earned = (
            0
            if row["total_earned"] is None
            else _nonnegative_int(row["total_earned"], "earned total")
        )
        if row["next_mine_at"] is not None:
            next_mine_at = _parse_utc_timestamp(row["next_mine_at"])
            if now < next_mine_at:
                raise MiningCooldownActive(next_mine_at)

        previous_level = level_for_xp(xp)
        outcome = resolve_mining(MINING_CATALOG, previous_level, roll)
        credited = connection.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ? AND balance <= ? - ?
            RETURNING balance
            """,
            (outcome.total_value, user_id, MAX_MONEY, outcome.total_value),
        ).fetchone()
        if credited is None:
            raise MiningRewardExceedsWalletLimit(
                "Wallet cannot hold the mining reward."
            )

        new_xp = xp + outcome.xp_gained
        new_level = level_for_xp(new_xp)
        next_mine_at = now + timedelta(seconds=MINING_COOLDOWN_SECONDS)
        new_total_actions = total_actions + 1
        new_total_earned = total_earned + outcome.total_value
        connection.execute(
            """
            INSERT INTO mining_profiles
                (user_id, xp, total_actions, total_earned, next_mine_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                xp = excluded.xp,
                total_actions = excluded.total_actions,
                total_earned = excluded.total_earned,
                next_mine_at = excluded.next_mine_at
            """,
            (
                user_id,
                new_xp,
                new_total_actions,
                new_total_earned,
                _format_utc_timestamp(next_mine_at),
            ),
        )
        result = MiningResult(
            outcome=outcome,
            previous_level=previous_level,
            level=new_level,
            xp=new_xp,
            xp_for_next_level=(
                None if new_level == 25 else cumulative_xp_for_level(new_level + 1)
            ),
            total_actions=new_total_actions,
            total_earned=new_total_earned,
            balance=credited["balance"],
            next_mine_at=next_mine_at,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise InvalidMiningState(f"Stored mining {name} is invalid.")
    return value


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidMiningState("Stored mining cooldown is invalid.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise InvalidMiningState("Stored mining cooldown is invalid.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidMiningState("Stored mining cooldown must be timezone-aware.")
    utc_value = parsed.astimezone(UTC)
    if _format_utc_timestamp(utc_value) != value:
        raise InvalidMiningState("Stored mining cooldown is not canonical UTC.")
    return utc_value


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")
