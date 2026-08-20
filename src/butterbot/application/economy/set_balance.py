"""Set a user's wallet balance."""

from __future__ import annotations

from butterbot.application.economy.wallet_repository import WalletRepository
from butterbot.domain.wallet import MAX_MONEY, Wallet


class SetBalance:
    """Set one user's durable wallet balance."""

    def __init__(self, repository: WalletRepository) -> None:
        self._repository = repository

    async def execute(self, user_id: int, amount: int) -> Wallet:
        """Set a nonnegative integer-dollar wallet balance atomically."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        if amount < 0:
            raise ValueError("Balance cannot be negative.")
        if amount > MAX_MONEY:
            raise ValueError("Balance exceeds the supported limit.")
        return await self._repository.set_balance(user_id, amount)
