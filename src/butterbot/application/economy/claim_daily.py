"""Claim a user's daily wallet reward."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

from butterbot.domain.daily_reward import DailyClaimResult


class DailyClaimRepository(Protocol):
    """Atomic persistence required by the daily claim use case."""

    async def claim(self, user_id: int, claim_date: date) -> DailyClaimResult:
        """Credit a wallet and persist daily state in one transaction."""
        ...


class ClaimDaily:
    """Claim one daily reward using a timezone-aware injected clock."""

    def __init__(
        self,
        repository: DailyClaimRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or _utc_now

    async def execute(self, user_id: int) -> DailyClaimResult:
        """Claim the reward for the clock's current UTC calendar date."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Daily claim clock must return an aware datetime.")
        claim_date = now.astimezone(UTC).date()
        return await self._repository.claim(user_id, claim_date)


def _utc_now() -> datetime:
    return datetime.now(UTC)
