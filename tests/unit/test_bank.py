from __future__ import annotations

import pytest

from butterbot.domain.bank import BankAccount, BankOverview, bank_capacity
from butterbot.domain.wallet import MAX_MONEY, Wallet


def test_level_one_capacity_and_remaining_storage() -> None:
    account = BankAccount(user_id=1, balance=25_000, level=1)

    assert account.capacity == 150_000
    assert account.remaining_capacity == 125_000
    assert bank_capacity(1) == 150_000


def test_over_capacity_account_remains_valid_with_zero_remaining() -> None:
    account = BankAccount(user_id=1, balance=200_000, level=1)

    assert account.capacity == 150_000
    assert account.remaining_capacity == 0


@pytest.mark.parametrize(
    ("user_id", "balance", "level", "message"),
    [
        (0, 0, 1, "positive"),
        (1, -1, 1, "negative"),
        (1, MAX_MONEY + 1, 1, "supported limit"),
        (1, 0, 0, "not supported"),
        (1, 0, 2, "not supported"),
    ],
)
def test_bank_account_rejects_invalid_state(
    user_id: int, balance: int, level: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        BankAccount(user_id, balance, level)


def test_bank_overview_requires_matching_user() -> None:
    with pytest.raises(ValueError, match="same user"):
        BankOverview(
            wallet=Wallet(user_id=1, balance=0),
            account=BankAccount(user_id=2, balance=0, level=1),
        )
