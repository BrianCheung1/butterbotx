"""Transfer money between user wallets."""

from __future__ import annotations

from butterbot.application.economy.wallet_repository import WalletRepository
from butterbot.domain.money_transfer import (
    InvalidTransfer,
    TransferResult,
)
from butterbot.domain.wallet import MAX_MONEY


class TransferMoney:
    """Validate and atomically transfer money between two users."""

    def __init__(self, repository: WalletRepository) -> None:
        self._repository = repository

    async def execute(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        """Transfer a positive integer-dollar amount between distinct users."""
        _validate_transfer(sender_id, recipient_id, amount)
        return await self._repository.transfer(
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
        )


def _validate_transfer(sender_id: int, recipient_id: int, amount: int) -> None:
    if sender_id <= 0 or recipient_id <= 0:
        raise InvalidTransfer("User IDs must be positive.")
    if sender_id == recipient_id:
        raise InvalidTransfer("Sender and recipient must be different users.")
    if amount <= 0:
        raise InvalidTransfer("Transfer amount must be positive.")
    if amount > MAX_MONEY:
        raise InvalidTransfer("Transfer amount exceeds the supported limit.")
