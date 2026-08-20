from __future__ import annotations

import pytest

from butterbot.discord_app.formatting.money import format_money


@pytest.mark.parametrize(
    ("amount_cents", "expected"),
    [(0, "$0"), (150, "$1.50"), (199_900, "$1,999")],
)
def test_format_money_is_exact(amount_cents: int, expected: str) -> None:
    assert format_money(amount_cents) == expected


def test_format_money_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        format_money(-1)
