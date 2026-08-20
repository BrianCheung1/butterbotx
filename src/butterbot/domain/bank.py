"""Bank account models and capacity rules."""

from __future__ import annotations

from dataclasses import dataclass

from butterbot.domain.wallet import MAX_MONEY, Wallet

BANK_CAPACITY_BY_LEVEL = (150_000,)


def bank_capacity(level: int) -> int:
    """Return configured protected storage for a supported bank level."""
    if not 1 <= level <= len(BANK_CAPACITY_BY_LEVEL):
        raise ValueError("Bank level is not supported by the capacity catalog.")
    return BANK_CAPACITY_BY_LEVEL[level - 1]


@dataclass(frozen=True, slots=True)
class BankAccount:
    """A user's protected, capacity-limited bank account."""

    user_id: int
    balance: int
    level: int

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("User ID must be positive.")
        if self.balance < 0:
            raise ValueError("Bank balance cannot be negative.")
        if self.balance > MAX_MONEY:
            raise ValueError("Bank balance exceeds the supported limit.")
        bank_capacity(self.level)

    @property
    def capacity(self) -> int:
        """Return total protected storage configured for this level."""
        return bank_capacity(self.level)

    @property
    def remaining_capacity(self) -> int:
        """Return available storage, flooring over-capacity accounts at zero."""
        return max(0, self.capacity - self.balance)


@dataclass(frozen=True, slots=True)
class BankOverview:
    """A user's liquid wallet and protected bank state."""

    wallet: Wallet
    account: BankAccount

    def __post_init__(self) -> None:
        if self.wallet.user_id != self.account.user_id:
            raise ValueError("Wallet and bank account must belong to the same user.")
