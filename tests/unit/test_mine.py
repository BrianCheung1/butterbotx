from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from butterbot.application.mining.mine import Mine
from butterbot.domain.mining import MiningOutcome, MiningResult, MiningRoll


def result() -> MiningResult:
    return MiningResult(
        outcome=MiningOutcome("dirt", "Common", 50, 0, 50, 5),
        previous_level=1,
        level=1,
        xp=5,
        xp_for_next_level=12,
        total_actions=1,
        total_earned=50,
        balance=50,
        next_mine_at=datetime(2026, 8, 20, 12, 0, 30, tzinfo=UTC),
    )


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[int, datetime, MiningRoll]] = []

    async def mine(self, user_id: int, now: datetime, roll: MiningRoll) -> MiningResult:
        self.calls.append((user_id, now, roll))
        return result()


class FixedRollSource:
    def __init__(self) -> None:
        self.roll = MiningRoll(1, 2, 3, 4)
        self.calls = 0

    def create_roll(self) -> MiningRoll:
        self.calls += 1
        return self.roll


@pytest.mark.asyncio
async def test_mine_reads_clock_and_roll_once_and_normalizes_utc() -> None:
    repository = FakeRepository()
    rolls = FixedRollSource()
    clock_calls = 0
    eastern = timezone(timedelta(hours=-4))

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return datetime(2026, 8, 20, 8, tzinfo=eastern)

    actual = await Mine(repository, rolls, clock).execute(42)

    assert actual == result()
    assert clock_calls == 1
    assert rolls.calls == 1
    assert repository.calls == [(42, datetime(2026, 8, 20, 12, tzinfo=UTC), rolls.roll)]


@pytest.mark.asyncio
async def test_mine_rejects_invalid_user_before_clock_or_roll() -> None:
    repository = FakeRepository()
    rolls = FixedRollSource()
    clock_called = False

    def clock() -> datetime:
        nonlocal clock_called
        clock_called = True
        return datetime.now(UTC)

    with pytest.raises(ValueError, match="positive"):
        await Mine(repository, rolls, clock).execute(0)

    assert clock_called is False
    assert rolls.calls == 0
    assert repository.calls == []


@pytest.mark.asyncio
async def test_mine_rejects_naive_clock_before_creating_roll() -> None:
    repository = FakeRepository()
    rolls = FixedRollSource()

    with pytest.raises(ValueError, match="aware"):
        await Mine(repository, rolls, lambda: datetime(2026, 8, 20)).execute(1)

    assert rolls.calls == 0
    assert repository.calls == []
