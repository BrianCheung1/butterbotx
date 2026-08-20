"""Daily reward and streak business rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from butterbot.domain.wallet import Wallet

DAILY_BASE_REWARD = 1_000
DAILY_BONUS_CAP = 1_000_000
DAILY_STREAK_RESET_DAYS = 14
_FIRST_CAPPED_PREVIOUS_STREAK = 11


class DailyAlreadyClaimed(ValueError):
    """Raised when a user has already claimed on the requested UTC date."""

    def __init__(self, next_claim_at: datetime) -> None:
        super().__init__("Daily reward has already been claimed for this UTC date.")
        self.next_claim_at = next_claim_at


class InvalidDailyClaimState(ValueError):
    """Raised when persisted daily state violates its business invariants."""


class DailyRewardExceedsWalletLimit(ValueError):
    """Raised when a wallet cannot hold its daily reward."""


@dataclass(frozen=True, slots=True)
class DailyClaimState:
    """A user's daily streak before a claim attempt."""

    streak: int
    last_claim_date: date | None

    def __post_init__(self) -> None:
        if self.streak < 0:
            raise InvalidDailyClaimState("Daily streak cannot be negative.")
        if self.last_claim_date is None and self.streak != 0:
            raise InvalidDailyClaimState(
                "A nonzero daily streak requires a previous claim date."
            )


@dataclass(frozen=True, slots=True)
class DailyReward:
    """Reward and streak produced by an eligible daily claim."""

    base: int
    bonus: int
    total: int
    streak: int


@dataclass(frozen=True, slots=True)
class DailyClaimResult:
    """Durable wallet and daily state produced by a successful claim."""

    wallet: Wallet
    reward: DailyReward
    claim_date: date


def calculate_daily_reward(state: DailyClaimState, claim_date: date) -> DailyReward:
    """Calculate one claim using UTC calendar-date streak semantics."""
    previous_streak = state.streak
    if state.last_claim_date is not None:
        gap_days = (claim_date - state.last_claim_date).days
        if gap_days < 0:
            raise InvalidDailyClaimState("Last daily claim date is in the future.")
        if gap_days == 0:
            raise DailyAlreadyClaimed(_next_utc_midnight(claim_date))
        if gap_days >= DAILY_STREAK_RESET_DAYS:
            previous_streak = 0

    bonus = _daily_bonus(previous_streak)
    return DailyReward(
        base=DAILY_BASE_REWARD,
        bonus=bonus,
        total=DAILY_BASE_REWARD + bonus,
        streak=previous_streak + 1,
    )


def _daily_bonus(previous_streak: int) -> int:
    if previous_streak == 0:
        return 0
    if previous_streak >= _FIRST_CAPPED_PREVIOUS_STREAK:
        return DAILY_BONUS_CAP
    return DAILY_BASE_REWARD * 2 ** (previous_streak - 1)


def _next_utc_midnight(claim_date: date) -> datetime:
    return datetime.combine(claim_date + timedelta(days=1), time.min, tzinfo=UTC)
