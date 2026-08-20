from __future__ import annotations

from dataclasses import dataclass

import pytest

from butterbot.application.economy.deposit_to_bank import DepositToBank
from butterbot.domain.bank import (
    BankAccount,
    BankDepositResult,
    BankDepositSelection,
    BankOverview,
)
from butterbot.domain.wallet import Wallet


@dataclass
class StubBankRepository:
    result: BankDepositResult
    call: tuple[int, BankDepositSelection] | None = None

    async def get_or_create_overview(self, user_id: int) -> BankOverview:
        raise AssertionError("Deposit must not use the balance lookup operation.")

    async def deposit(
        self, user_id: int, selection: BankDepositSelection
    ) -> BankDepositResult:
        self.call = (user_id, selection)
        return self.result


def deposit_result() -> BankDepositResult:
    return BankDepositResult(
        overview=BankOverview(
            wallet=Wallet(42, 750),
            account=BankAccount(42, 250, 1),
        ),
        amount=250,
        percentage=25,
        filled_remaining_capacity=False,
    )


@pytest.mark.asyncio
async def test_deposit_to_bank_builds_selection_and_uses_bank_repository() -> None:
    repository = StubBankRepository(deposit_result())

    result = await DepositToBank(repository).execute(42, percentage=25)

    assert result == repository.result
    assert repository.call == (42, BankDepositSelection(percentage=25))


@pytest.mark.asyncio
async def test_deposit_to_bank_rejects_invalid_user_before_repository() -> None:
    repository = StubBankRepository(deposit_result())

    with pytest.raises(ValueError, match="positive"):
        await DepositToBank(repository).execute(0, amount=10)

    assert repository.call is None
