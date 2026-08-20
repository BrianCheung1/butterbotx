from __future__ import annotations

import pytest

from butterbot.application.economy.transfer_money import TransferMoney
from butterbot.domain.money_transfer import (
    InvalidTransfer,
    TransferResult,
)
from butterbot.domain.wallet import MAX_MONEY, Wallet


class FakeWalletRepository:
    def __init__(self, result: TransferResult) -> None:
        self.result = result
        self.transfers: list[tuple[int, int, int]] = []

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        return Wallet(user_id, 0)

    async def transfer(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        self.transfers.append((sender_id, recipient_id, amount))
        return self.result

    async def set_balance(self, user_id: int, amount: int) -> Wallet:
        raise AssertionError("TransferMoney must not set a balance.")


@pytest.mark.asyncio
async def test_transfer_money_returns_repository_result() -> None:
    expected = TransferResult(Wallet(1, 4_000), Wallet(2, 6_000), 1_000)
    repository = FakeWalletRepository(expected)

    result = await TransferMoney(repository).execute(1, 2, 1_000)

    assert result is expected
    assert repository.transfers == [(1, 2, 1_000)]


@pytest.mark.parametrize(
    ("sender_id", "recipient_id", "amount"),
    [
        (0, 2, 100),
        (1, 0, 100),
        (1, 1, 100),
        (1, 2, 0),
        (1, 2, -1),
        (1, 2, MAX_MONEY + 1),
    ],
)
@pytest.mark.asyncio
async def test_transfer_money_rejects_invalid_request_before_repository_call(
    sender_id: int, recipient_id: int, amount: int
) -> None:
    repository = FakeWalletRepository(TransferResult(Wallet(1, 0), Wallet(2, 100), 100))

    with pytest.raises(InvalidTransfer):
        await TransferMoney(repository).execute(sender_id, recipient_id, amount)

    assert repository.transfers == []
