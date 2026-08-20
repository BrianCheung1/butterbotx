from __future__ import annotations

import pytest

from butterbot.application.economy.get_balance import GetBalance
from butterbot.domain.wallet import Wallet


class FakeWalletRepository:
    def __init__(self, result: Wallet) -> None:
        self.result = result
        self.requested_user_ids: list[int] = []

    async def get_or_create_balance(self, user_id: int) -> Wallet:
        self.requested_user_ids.append(user_id)
        return self.result


@pytest.mark.asyncio
async def test_get_balance_returns_repository_result() -> None:
    expected = Wallet(user_id=42, balance_cents=12_345)
    repository = FakeWalletRepository(expected)

    result = await GetBalance(repository).execute(42)

    assert result is expected
    assert repository.requested_user_ids == [42]


@pytest.mark.asyncio
async def test_get_balance_rejects_invalid_user_id_before_repository_call() -> None:
    repository = FakeWalletRepository(Wallet(user_id=1, balance_cents=0))

    with pytest.raises(ValueError, match="positive"):
        await GetBalance(repository).execute(0)

    assert repository.requested_user_ids == []
