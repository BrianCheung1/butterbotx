"""SQLite persistence for atomic daily reward claims."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from butterbot.domain.daily_reward import (
    DailyClaimResult,
    DailyClaimState,
    DailyRewardExceedsWalletLimit,
    InvalidDailyClaimState,
    calculate_daily_reward,
)
from butterbot.domain.wallet import MAX_MONEY, Wallet


class SQLiteDailyClaimRepository:
    """Atomically persist wallet credit and daily claim state in SQLite."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="butterbot-sqlite-daily"
        )

    async def claim(self, user_id: int, claim_date: date) -> DailyClaimResult:
        """Credit one eligible daily reward under an immediate transaction."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _claim,
            self._database_path,
            user_id,
            claim_date,
        )

    def close(self) -> None:
        """Finish queued daily work and release its worker thread."""
        self._executor.shutdown()


def _claim(database_path: Path, user_id: int, claim_date: date) -> DailyClaimResult:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        wallet_row = connection.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if wallet_row is None:
            raise RuntimeError("Wallet was not available after creation.")

        daily_row = connection.execute(
            "SELECT streak, last_claim_date FROM daily_claims WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        state = _daily_state(daily_row)
        reward = calculate_daily_reward(state, claim_date)

        credited_row = connection.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ? AND balance <= ? - ?
            RETURNING balance
            """,
            (reward.total, user_id, MAX_MONEY, reward.total),
        ).fetchone()
        if credited_row is None:
            raise DailyRewardExceedsWalletLimit("Wallet cannot hold the daily reward.")

        connection.execute(
            """
            INSERT INTO daily_claims (user_id, streak, last_claim_date)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                streak = excluded.streak,
                last_claim_date = excluded.last_claim_date
            """,
            (user_id, reward.streak, claim_date.isoformat()),
        )
        result = DailyClaimResult(
            wallet=Wallet(user_id, credited_row["balance"]),
            reward=reward,
            claim_date=claim_date,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _daily_state(row: sqlite3.Row | None) -> DailyClaimState:
    if row is None:
        return DailyClaimState(streak=0, last_claim_date=None)
    stored_date = row["last_claim_date"]
    try:
        parsed_date = date.fromisoformat(stored_date)
    except (TypeError, ValueError) as error:
        raise InvalidDailyClaimState("Stored daily claim date is invalid.") from error
    if parsed_date.isoformat() != stored_date:
        raise InvalidDailyClaimState("Stored daily claim date is not canonical.")
    return DailyClaimState(streak=row["streak"], last_claim_date=parsed_date)
