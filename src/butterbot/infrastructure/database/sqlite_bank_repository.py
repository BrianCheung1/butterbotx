"""SQLite persistence for bank-owned operations."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from butterbot.domain.bank import (
    BankAccount,
    BankCapacityExceeded,
    BankDepositResult,
    BankDepositSelection,
    BankHasNoCapacity,
    BankOverview,
    InsufficientWalletBalance,
    resolve_bank_deposit,
)
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

    async def deposit(
        self, user_id: int, selection: BankDepositSelection
    ) -> BankDepositResult:
        """Atomically debit the wallet and credit protected bank storage."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _deposit,
            self._database_path,
            user_id,
            selection,
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


def _deposit(
    database_path: Path,
    user_id: int,
    selection: BankDepositSelection,
) -> BankDepositResult:
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
            raise RuntimeError("Bank state was not available after creation.")

        account = BankAccount(user_id, row["bank_balance"], row["bank_level"])
        resolved = resolve_bank_deposit(
            selection,
            wallet_balance=row["wallet_balance"],
            account=account,
        )
        wallet_row = connection.execute(
            """
            UPDATE users
            SET balance = balance - ?
            WHERE user_id = ? AND balance >= ?
            RETURNING balance
            """,
            (resolved.amount, user_id, resolved.amount),
        ).fetchone()
        if wallet_row is None:
            available = connection.execute(
                "SELECT balance FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            raise InsufficientWalletBalance(0 if available is None else available[0])

        bank_row = connection.execute(
            """
            UPDATE bank_accounts
            SET balance = balance + ?
            WHERE user_id = ?
              AND level = ?
              AND balance <= ? - ?
            RETURNING balance, level
            """,
            (
                resolved.amount,
                user_id,
                account.level,
                account.capacity,
                resolved.amount,
            ),
        ).fetchone()
        if bank_row is None:
            current = connection.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
            remaining = 0 if current is None else max(0, account.capacity - current[0])
            if remaining == 0:
                raise BankHasNoCapacity("Bank has no remaining capacity.")
            raise BankCapacityExceeded(remaining)

        overview = BankOverview(
            wallet=Wallet(user_id, wallet_row["balance"]),
            account=BankAccount(user_id, bank_row["balance"], bank_row["level"]),
        )
        result = BankDepositResult(
            overview=overview,
            amount=resolved.amount,
            percentage=selection.percentage,
            filled_remaining_capacity=resolved.filled_remaining_capacity,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
