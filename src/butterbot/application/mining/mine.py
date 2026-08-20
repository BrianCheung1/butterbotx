"""Execute one mining action."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from butterbot.domain.mining import MiningResult, MiningRoll


class MiningRepository(Protocol):
    """Atomic persistence required by the mining use case."""

    async def mine(self, user_id: int, now: datetime, roll: MiningRoll) -> MiningResult:
        """Commit one eligible mining action and its wallet reward."""
        ...


class MiningRollSource(Protocol):
    """Source of all random input for a mining action."""

    def create_roll(self) -> MiningRoll:
        """Create one complete mining roll."""
        ...


class Mine:
    """Coordinate one mining action with injected time and randomness."""

    def __init__(
        self,
        repository: MiningRepository,
        roll_source: MiningRollSource,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._roll_source = roll_source
        self._clock = clock or _utc_now

    async def execute(self, user_id: int) -> MiningResult:
        """Mine once for a valid Discord user."""
        if user_id <= 0:
            raise ValueError("User ID must be positive.")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Mining clock must return an aware datetime.")
        utc_now = now.astimezone(UTC)
        roll = self._roll_source.create_roll()
        return await self._repository.mine(user_id, utc_now, roll)


def _utc_now() -> datetime:
    return datetime.now(UTC)
