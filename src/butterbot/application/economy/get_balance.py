"""Retrieve a user's wallet balance."""

from __future__ import annotations

from typing import Protocol

from butterbot.domain.wallet import Wallet


class WalletRepository(Protocol):
    """Persistence operations required by the balance use case."""

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        """Return a user's balance, creating a zero wallet when absent."""
        ...


class GetBalance:
    """Retrieve a durable wallet balance for one Discord user."""

    def __init__(self, repository: WalletRepository) -> None:
        self._repository = repository

    async def execute(self, user_id: int) -> Wallet:
        """Return the selected user's current wallet balance."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        return await self._repository.get_or_create_balance(user_id)
