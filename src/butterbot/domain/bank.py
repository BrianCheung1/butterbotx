"""Bank account models and capacity rules."""

from __future__ import annotations

from dataclasses import dataclass

from butterbot.domain.wallet import MAX_MONEY, Wallet

BANK_CAPACITY_BY_LEVEL = (150_000,)
SUPPORTED_BANK_DEPOSIT_PERCENTAGES = frozenset({25, 50, 75, 100})


class BankDepositError(ValueError):
    """Base error for an invalid or unavailable bank deposit."""


class BankDepositSelectionRequired(BankDepositError):
    """Raised when neither deposit input was selected."""


class BankDepositSelectionConflict(BankDepositError):
    """Raised when both deposit inputs were selected."""


class InvalidBankDepositAmount(BankDepositError):
    """Raised when an exact deposit amount is outside supported bounds."""


class InvalidBankDepositPercentage(BankDepositError):
    """Raised when a percentage is not one of the supported choices."""


class BankDepositWouldBeZero(BankDepositError):
    """Raised when percentage rounding produces a zero-dollar deposit."""


class BankHasNoCapacity(BankDepositError):
    """Raised when an account is full or already over capacity."""


class BankCapacityExceeded(BankDepositError):
    """Raised when an exact deposit exceeds remaining capacity."""

    def __init__(self, remaining_capacity: int) -> None:
        self.remaining_capacity = remaining_capacity
        super().__init__("Deposit exceeds remaining bank capacity.")


class InsufficientWalletBalance(BankDepositError):
    """Raised when the wallet cannot fund an exact deposit."""

    def __init__(self, available_balance: int) -> None:
        self.available_balance = available_balance
        super().__init__("Wallet balance is insufficient for this deposit.")


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


@dataclass(frozen=True, slots=True)
class BankDepositSelection:
    """Exactly one caller-selected way to calculate a deposit."""

    amount: int | None = None
    percentage: int | None = None

    def __post_init__(self) -> None:
        if self.amount is None and self.percentage is None:
            raise BankDepositSelectionRequired("Choose an amount or percentage.")
        if self.amount is not None and self.percentage is not None:
            raise BankDepositSelectionConflict(
                "Choose an amount or percentage, not both."
            )
        if self.amount is not None and not 1 <= self.amount <= MAX_MONEY:
            raise InvalidBankDepositAmount("Deposit amount must be positive.")
        if (
            self.percentage is not None
            and self.percentage not in SUPPORTED_BANK_DEPOSIT_PERCENTAGES
        ):
            raise InvalidBankDepositPercentage("Deposit percentage is unsupported.")


@dataclass(frozen=True, slots=True)
class ResolvedBankDeposit:
    """Transaction-current amount produced from a deposit selection."""

    amount: int
    filled_remaining_capacity: bool


@dataclass(frozen=True, slots=True)
class BankDepositResult:
    """Committed bank deposit and resulting account overview."""

    overview: BankOverview
    amount: int
    percentage: int | None
    filled_remaining_capacity: bool

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("Deposited amount must be positive.")


def resolve_bank_deposit(
    selection: BankDepositSelection,
    wallet_balance: int,
    account: BankAccount,
) -> ResolvedBankDeposit:
    """Resolve a selection against transaction-current wallet and bank state."""
    if wallet_balance < 0:
        raise ValueError("Wallet balance cannot be negative.")
    remaining_capacity = account.remaining_capacity
    if remaining_capacity == 0:
        raise BankHasNoCapacity("Bank has no remaining capacity.")

    if selection.amount is not None:
        if selection.amount > remaining_capacity:
            raise BankCapacityExceeded(remaining_capacity)
        if selection.amount > wallet_balance:
            raise InsufficientWalletBalance(wallet_balance)
        return ResolvedBankDeposit(selection.amount, False)

    percentage = selection.percentage
    if percentage is None:  # Defends against invalid construction bypasses.
        raise BankDepositSelectionRequired("Choose an amount or percentage.")
    calculated_amount = wallet_balance * percentage // 100
    if calculated_amount == 0:
        raise BankDepositWouldBeZero("Percentage deposit rounds to zero dollars.")
    actual_amount = min(calculated_amount, remaining_capacity)
    return ResolvedBankDeposit(
        amount=actual_amount,
        filled_remaining_capacity=calculated_amount > remaining_capacity,
    )
