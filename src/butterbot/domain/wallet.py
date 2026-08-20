"""Wallet domain model."""

from __future__ import annotations

from dataclasses import dataclass

MAX_MONEY = 2**63 - 1


@dataclass(frozen=True, slots=True)
class Wallet:
    """A Discord user's nonnegative wallet, stored in integer dollars."""

    user_id: int
    balance: int

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("User ID must be positive.")
        if self.balance < 0:
            raise ValueError("Balance cannot be negative.")
        if self.balance > MAX_MONEY:
            raise ValueError("Balance exceeds the supported limit.")
