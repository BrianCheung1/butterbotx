from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from butterbot.application.economy.claim_daily import ClaimDaily
from butterbot.domain.daily_reward import DailyClaimResult, DailyReward
from butterbot.domain.wallet import Wallet


class FakeDailyClaimRepository:
    def __init__(self, result: DailyClaimResult) -> None:
        self.result = result
        self.calls: list[tuple[int, date]] = []

    async def claim(self, user_id: int, claim_date: date) -> DailyClaimResult:
        self.calls.append((user_id, claim_date))
        return self.result


def claim_result() -> DailyClaimResult:
    return DailyClaimResult(
        Wallet(1, 1_000), DailyReward(1_000, 0, 1_000, 1), date(2026, 8, 19)
    )


@pytest.mark.asyncio
async def test_claim_daily_reads_clock_once_and_uses_utc_date() -> None:
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return datetime(2026, 8, 19, 23, 30, tzinfo=UTC)

    repository = FakeDailyClaimRepository(claim_result())

    result = await ClaimDaily(repository, clock).execute(1)

    assert result is repository.result
    assert calls == 1
    assert repository.calls == [(1, date(2026, 8, 19))]


@pytest.mark.asyncio
async def test_claim_daily_normalizes_aware_clock_to_utc() -> None:
    eastern = timezone(timedelta(hours=-4))
    repository = FakeDailyClaimRepository(claim_result())
    service = ClaimDaily(
        repository,
        lambda: datetime(2026, 8, 19, 23, 30, tzinfo=eastern),
    )

    await service.execute(1)

    assert repository.calls == [(1, date(2026, 8, 20))]


@pytest.mark.asyncio
async def test_claim_daily_rejects_naive_clock_before_repository() -> None:
    repository = FakeDailyClaimRepository(claim_result())
    service = ClaimDaily(repository, lambda: datetime(2026, 8, 19, 12))

    with pytest.raises(ValueError, match="aware"):
        await service.execute(1)

    assert repository.calls == []


@pytest.mark.asyncio
async def test_claim_daily_rejects_invalid_user_before_reading_clock() -> None:
    clock_read = False

    def clock() -> datetime:
        nonlocal clock_read
        clock_read = True
        return datetime.now(UTC)

    repository = FakeDailyClaimRepository(claim_result())

    with pytest.raises(ValueError, match="positive"):
        await ClaimDaily(repository, clock).execute(0)

    assert clock_read is False
    assert repository.calls == []
