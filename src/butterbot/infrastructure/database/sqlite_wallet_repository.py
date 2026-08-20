"""SQLite wallet persistence."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from butterbot.domain.wallet import Wallet


class SQLiteWalletRepository:
    """Persist wallets on one serialized SQLite worker."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="butterbot-sqlite-wallet"
        )

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        """Create a zero wallet when needed and return its current balance."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _get_or_create,
            self._database_path,
            user_id,
        )

    def close(self) -> None:
        """Finish queued repository work and release its worker thread."""
        self._executor.shutdown()


def _get_or_create(database_path: Path, user_id: int) -> Wallet:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        row = connection.execute(
            "SELECT balance_cents FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Wallet was not available after creation.")
        wallet = Wallet(user_id=user_id, balance_cents=row["balance_cents"])
        connection.commit()
        return wallet
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
