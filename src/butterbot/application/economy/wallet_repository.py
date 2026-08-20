"""Wallet persistence operations required by economy use cases."""

from __future__ import annotations

from typing import Protocol

from butterbot.domain.money_transfer import TransferResult
from butterbot.domain.wallet import Wallet


class WalletRepository(Protocol):
    """Persistence operations for durable wallets."""

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        """Return a user's wallet, creating a zero wallet when absent."""
        ...

    async def transfer(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        """Atomically transfer money between two wallets."""
        ...
