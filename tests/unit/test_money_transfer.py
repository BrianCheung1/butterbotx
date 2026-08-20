from __future__ import annotations

import pytest

from butterbot.domain.money_transfer import InvalidTransfer, TransferResult
from butterbot.domain.wallet import Wallet


def test_transfer_result_records_wallets_and_amount() -> None:
    result = TransferResult(
        sender=Wallet(user_id=1, balance=5_000),
        recipient=Wallet(user_id=2, balance=3_000),
        amount=2_000,
    )

    assert result.sender.balance == 5_000
    assert result.recipient.balance == 3_000
    assert result.amount == 2_000


@pytest.mark.parametrize(
    ("sender", "recipient", "amount"),
    [
        (Wallet(1, 0), Wallet(1, 0), 100),
        (Wallet(1, 0), Wallet(2, 0), 0),
        (Wallet(1, 0), Wallet(2, 0), -1),
    ],
)
def test_transfer_result_rejects_invalid_values(
    sender: Wallet, recipient: Wallet, amount: int
) -> None:
    with pytest.raises(InvalidTransfer):
        TransferResult(sender, recipient, amount)
