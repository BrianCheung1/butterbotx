from __future__ import annotations

import pytest

from butterbot.domain.bank import (
    BankAccount,
    BankCapacityExceeded,
    BankDepositSelection,
    BankDepositSelectionConflict,
    BankDepositSelectionRequired,
    BankDepositWouldBeZero,
    BankHasNoCapacity,
    BankOverview,
    InsufficientWalletBalance,
    InvalidBankDepositAmount,
    InvalidBankDepositPercentage,
    bank_capacity,
    resolve_bank_deposit,
)
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


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({}, BankDepositSelectionRequired),
        ({"amount": 1, "percentage": 25}, BankDepositSelectionConflict),
        ({"amount": 0}, InvalidBankDepositAmount),
        ({"amount": MAX_MONEY + 1}, InvalidBankDepositAmount),
        ({"percentage": 10}, InvalidBankDepositPercentage),
    ],
)
def test_deposit_selection_rejects_invalid_or_ambiguous_inputs(
    kwargs: dict[str, int], error: type[ValueError]
) -> None:
    with pytest.raises(error):
        BankDepositSelection(**kwargs)


@pytest.mark.parametrize("percentage", [25, 50, 75, 100])
def test_deposit_selection_accepts_supported_percentages(percentage: int) -> None:
    assert BankDepositSelection(percentage=percentage).percentage == percentage


def test_exact_deposit_checks_capacity_before_wallet_balance() -> None:
    account = BankAccount(user_id=1, balance=149_000, level=1)

    with pytest.raises(BankCapacityExceeded) as raised:
        resolve_bank_deposit(BankDepositSelection(amount=2_000), 0, account)

    assert raised.value.remaining_capacity == 1_000


def test_exact_deposit_rejects_insufficient_wallet() -> None:
    with pytest.raises(InsufficientWalletBalance) as raised:
        resolve_bank_deposit(
            BankDepositSelection(amount=101),
            100,
            BankAccount(user_id=1, balance=0, level=1),
        )

    assert raised.value.available_balance == 100


def test_percentage_deposit_floors_transaction_wallet_calculation() -> None:
    resolved = resolve_bank_deposit(
        BankDepositSelection(percentage=25),
        103,
        BankAccount(user_id=1, balance=0, level=1),
    )

    assert resolved.amount == 25
    assert resolved.filled_remaining_capacity is False


def test_percentage_deposit_caps_at_remaining_capacity() -> None:
    resolved = resolve_bank_deposit(
        BankDepositSelection(percentage=100),
        10_000,
        BankAccount(user_id=1, balance=149_000, level=1),
    )

    assert resolved.amount == 1_000
    assert resolved.filled_remaining_capacity is True


def test_percentage_deposit_rejects_zero_after_flooring() -> None:
    with pytest.raises(BankDepositWouldBeZero):
        resolve_bank_deposit(
            BankDepositSelection(percentage=25),
            3,
            BankAccount(user_id=1, balance=0, level=1),
        )


@pytest.mark.parametrize("balance", [150_000, 200_000])
def test_deposit_rejects_full_and_over_capacity_accounts(balance: int) -> None:
    with pytest.raises(BankHasNoCapacity):
        resolve_bank_deposit(
            BankDepositSelection(amount=1),
            1,
            BankAccount(user_id=1, balance=balance, level=1),
        )
