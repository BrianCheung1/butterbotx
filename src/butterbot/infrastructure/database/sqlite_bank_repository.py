"""SQLite persistence for bank-owned operations."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from butterbot.domain.bank import BankAccount, BankOverview
from butterbot.domain.wallet import Wallet


class SQLiteBankRepository:
    """Persist bank state on one serialized SQLite worker."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="butterbot-sqlite-bank"
        )

    async def get_or_create_overview(self, user_id: int) -> BankOverview:
        """Atomically create defaults and return wallet plus bank state."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _get_or_create_overview,
            self._database_path,
            user_id,
        )

    def close(self) -> None:
        """Finish queued work and release the repository worker."""
        self._executor.shutdown()


def _get_or_create_overview(database_path: Path, user_id: int) -> BankOverview:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        connection.execute(
            "INSERT OR IGNORE INTO bank_accounts (user_id) VALUES (?)", (user_id,)
        )
        row = connection.execute(
            """
            SELECT users.balance AS wallet_balance,
                   bank_accounts.balance AS bank_balance,
                   bank_accounts.level AS bank_level
            FROM users
            JOIN bank_accounts USING (user_id)
            WHERE users.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Bank overview was not available after creation.")
        overview = BankOverview(
            wallet=Wallet(user_id, row["wallet_balance"]),
            account=BankAccount(user_id, row["bank_balance"], row["bank_level"]),
        )
        connection.commit()
        return overview
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
