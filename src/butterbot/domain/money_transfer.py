"""Money-transfer domain concepts."""

from __future__ import annotations

from dataclasses import dataclass

from butterbot.domain.wallet import MAX_MONEY, Wallet


class InvalidTransfer(ValueError):
    """Raised when a transfer request violates a domain invariant."""


class InsufficientFunds(ValueError):
    """Raised when the sender cannot cover a transfer."""

    def __init__(self, available_balance: int) -> None:
        super().__init__("Sender has insufficient funds.")
        self.available_balance = available_balance


class WalletLimitExceeded(ValueError):
    """Raised when a transfer would exceed the recipient wallet limit."""


@dataclass(frozen=True, slots=True)
class TransferResult:
    """Wallet balances produced by a completed money transfer."""

    sender: Wallet
    recipient: Wallet
    amount: int

    def __post_init__(self) -> None:
        if self.sender.user_id == self.recipient.user_id:
            raise InvalidTransfer("Sender and recipient must be different users.")
        if self.amount <= 0:
            raise InvalidTransfer("Transfer amount must be positive.")
        if self.amount > MAX_MONEY:
            raise InvalidTransfer("Transfer amount exceeds the supported limit.")
