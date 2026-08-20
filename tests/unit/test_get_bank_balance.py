from __future__ import annotations

import pytest

from butterbot.application.economy.get_bank_balance import GetBankBalance
from butterbot.domain.bank import BankAccount, BankOverview
from butterbot.domain.wallet import Wallet


class FakeBankRepository:
    def __init__(self, result: BankOverview) -> None:
        self.result = result
        self.requested_user_ids: list[int] = []

    async def get_or_create_overview(self, user_id: int) -> BankOverview:
        self.requested_user_ids.append(user_id)
        return self.result


@pytest.mark.asyncio
async def test_get_bank_balance_returns_repository_overview() -> None:
    expected = BankOverview(Wallet(42, 5_000), BankAccount(42, 10_000, 1))
    repository = FakeBankRepository(expected)

    result = await GetBankBalance(repository).execute(42)

    assert result is expected
    assert repository.requested_user_ids == [42]


@pytest.mark.asyncio
async def test_get_bank_balance_rejects_invalid_user_before_repository() -> None:
    repository = FakeBankRepository(BankOverview(Wallet(1, 0), BankAccount(1, 0, 1)))

    with pytest.raises(ValueError, match="positive"):
        await GetBankBalance(repository).execute(0)

    assert repository.requested_user_ids == []
