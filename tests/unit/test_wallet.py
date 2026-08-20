from __future__ import annotations

import pytest

from butterbot.domain.wallet import Wallet


def test_wallet_accepts_nonnegative_integer_dollars() -> None:
    assert Wallet(user_id=123, balance=150).balance == 150


@pytest.mark.parametrize(
    ("user_id", "balance"),
    [(0, 0), (-1, 0), (1, -1)],
)
def test_wallet_rejects_invalid_values(user_id: int, balance: int) -> None:
    with pytest.raises(ValueError):
        Wallet(user_id=user_id, balance=balance)
