"""SQLite wallet persistence."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from butterbot.domain.money_transfer import (
    InsufficientFunds,
    InvalidTransfer,
    TransferResult,
    WalletLimitExceeded,
)
from butterbot.domain.wallet import MAX_MONEY, Wallet


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

    async def transfer(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        """Atomically debit one wallet and credit another."""
        _validate_transfer(sender_id, recipient_id, amount)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _transfer,
            self._database_path,
            sender_id,
            recipient_id,
            amount,
        )

    async def set_balance(self, user_id: int, amount: int) -> Wallet:
        """Atomically create or replace a wallet balance."""
        _validate_balance(user_id, amount)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            _set_balance,
            self._database_path,
            user_id,
            amount,
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
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Wallet was not available after creation.")
        wallet = Wallet(user_id=user_id, balance=row["balance"])
        connection.commit()
        return wallet
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _transfer(
    database_path: Path,
    sender_id: int,
    recipient_id: int,
    amount: int,
) -> TransferResult:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (sender_id,)
        )
        connection.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (recipient_id,)
        )

        sender_row = connection.execute(
            """
            UPDATE users
            SET balance = balance - ?
            WHERE user_id = ? AND balance >= ?
            RETURNING balance
            """,
            (amount, sender_id, amount),
        ).fetchone()
        if sender_row is None:
            available_row = connection.execute(
                "SELECT balance FROM users WHERE user_id = ?", (sender_id,)
            ).fetchone()
            available_balance = 0 if available_row is None else available_row[0]
            raise InsufficientFunds(available_balance)

        recipient_row = connection.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ? AND balance <= ? - ?
            RETURNING balance
            """,
            (amount, recipient_id, MAX_MONEY, amount),
        ).fetchone()
        if recipient_row is None:
            raise WalletLimitExceeded(
                "Recipient wallet cannot hold the transfer amount."
            )

        result = TransferResult(
            sender=Wallet(sender_id, sender_row[0]),
            recipient=Wallet(recipient_id, recipient_row[0]),
            amount=amount,
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _set_balance(database_path: Path, user_id: int, amount: int) -> Wallet:
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            INSERT INTO users (user_id, balance)
            VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE
            SET balance = excluded.balance
            RETURNING balance
            """,
            (user_id, amount),
        ).fetchone()
        if row is None:
            raise RuntimeError("Wallet balance was not returned after update.")
        wallet = Wallet(user_id=user_id, balance=row["balance"])
        connection.commit()
        return wallet
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _validate_transfer(sender_id: int, recipient_id: int, amount: int) -> None:
    if sender_id <= 0 or recipient_id <= 0:
        raise InvalidTransfer("User IDs must be positive.")
    if sender_id == recipient_id:
        raise InvalidTransfer("Sender and recipient must be different users.")
    if amount <= 0 or amount > MAX_MONEY:
        raise InvalidTransfer("Transfer amount is outside the supported range.")


def _validate_balance(user_id: int, amount: int) -> None:
    if user_id <= 0:
        raise ValueError("User ID must be positive.")
    if amount < 0:
        raise ValueError("Balance cannot be negative.")
    if amount > MAX_MONEY:
        raise ValueError("Balance exceeds the supported limit.")
