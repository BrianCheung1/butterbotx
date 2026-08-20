"""Wallet domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Wallet:
    """A Discord user's nonnegative wallet, stored in integer cents."""

    user_id: int
    balance_cents: int

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("User ID must be positive.")
        if self.balance_cents < 0:
            raise ValueError("Balance cannot be negative.")
