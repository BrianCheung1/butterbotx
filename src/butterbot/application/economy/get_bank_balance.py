"""Application use case for retrieving bank and wallet balances."""

from __future__ import annotations

from butterbot.application.economy.bank_repository import BankRepository
from butterbot.domain.bank import BankOverview


class GetBankBalance:
    """Retrieve one user's complete bank overview."""

    def __init__(self, repository: BankRepository) -> None:
        self._repository = repository

    async def execute(self, user_id: int) -> BankOverview:
        """Validate the user and retrieve their lazily created account."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        return await self._repository.get_or_create_overview(user_id)
