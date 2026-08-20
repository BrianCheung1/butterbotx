"""Application use case for depositing wallet money into a bank account."""

from __future__ import annotations

from butterbot.application.economy.bank_repository import BankRepository
from butterbot.domain.bank import BankDepositResult, BankDepositSelection


class DepositToBank:
    """Move existing wallet money into protected bank storage."""

    def __init__(self, repository: BankRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        user_id: int,
        *,
        amount: int | None = None,
        percentage: int | None = None,
    ) -> BankDepositResult:
        """Validate the caller's selection and perform one atomic deposit."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        selection = BankDepositSelection(amount=amount, percentage=percentage)
        return await self._repository.deposit(user_id, selection)
