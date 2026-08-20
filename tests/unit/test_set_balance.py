from __future__ import annotations

import pytest

from butterbot.application.economy.set_balance import SetBalance
from butterbot.domain.money_transfer import TransferResult
from butterbot.domain.wallet import MAX_MONEY, Wallet


class FakeWalletRepository:
    def __init__(self, result: Wallet) -> None:
        self.result = result
        self.sets: list[tuple[int, int]] = []

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        raise AssertionError("SetBalance must not retrieve a wallet separately.")

    async def set_balance(self, user_id: int, amount: int) -> Wallet:
        self.sets.append((user_id, amount))
        return self.result

    async def transfer(
        self, sender_id: int, recipient_id: int, amount: int
    ) -> TransferResult:
        raise AssertionError("SetBalance must not transfer money.")


@pytest.mark.asyncio
async def test_set_balance_returns_repository_wallet() -> None:
    expected = Wallet(42, 1_999)
    repository = FakeWalletRepository(expected)

    result = await SetBalance(repository).execute(42, 1_999)

    assert result is expected
    assert repository.sets == [(42, 1_999)]


@pytest.mark.asyncio
async def test_set_balance_accepts_zero() -> None:
    repository = FakeWalletRepository(Wallet(42, 0))

    await SetBalance(repository).execute(42, 0)

    assert repository.sets == [(42, 0)]


@pytest.mark.parametrize(
    ("user_id", "amount"),
    [(0, 0), (-1, 0), (1, -1), (1, MAX_MONEY + 1)],
)
@pytest.mark.asyncio
async def test_set_balance_rejects_invalid_input_before_repository_call(
    user_id: int, amount: int
) -> None:
    repository = FakeWalletRepository(Wallet(1, 0))

    with pytest.raises(ValueError):
        await SetBalance(repository).execute(user_id, amount)

    assert repository.sets == []
